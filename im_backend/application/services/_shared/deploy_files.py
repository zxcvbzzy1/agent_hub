"""部署产物文件打包的共享工具。

deploy 产物对应一个部署工作目录（manager 的 workdir），下载/打包时需要把该目录下的
文件打成 zip。下载单个部署（GET /deployments/{id}/download）与“打包下载一次 run 的全部
内联产物”（POST /artifacts/bundle）都复用这里的解析与压缩逻辑，避免 deploy 走错路径。
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from im_backend.infra.agent_flow_bridge.pathing import ensure_agent_flow_path

ensure_agent_flow_path()
from infra.deploy.manager import DEPLOY_ROOT, deployment_manager  # noqa: E402


def resolve_deploy_workdir(
    deployment_id: str | None = None,
    download_dir: str | None = None,
) -> Path | None:
    """解析部署工作目录用于下载/打包，无法解析时返回 None。

    - 部署仍在内存中：以其 workdir 为权威；
    - 否则用持久化的 download_dir 回退，但必须位于 DEPLOY_ROOT 内（越界返回 None）。
    """
    if deployment_id:
        dep = deployment_manager.get(deployment_id)
        if dep is not None:
            workdir = Path(dep.workdir)
            return workdir if workdir.is_dir() else None
    if download_dir:
        candidate = Path(download_dir).resolve()
        try:
            candidate.relative_to(DEPLOY_ROOT)
        except ValueError:
            return None
        return candidate if candidate.is_dir() else None
    return None


def zip_dir_bytes(workdir: Path) -> bytes:
    """把目录下所有文件打包成 zip 字节（arcname 相对 workdir）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in workdir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(workdir)))
    return buf.getvalue()
