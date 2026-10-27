"""Import directory copies separately from message attachments."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from im_backend.application.services._shared.run_options import validate_workdir


class WorkspaceService:
    def __init__(self, rooms, root):
        self.rooms = rooms
        self.root = Path(os.getenv("IM_WORKSPACE_ROOT", str(root))).expanduser().resolve()
        self.file_limit = int(os.getenv("IM_WORKSPACE_FILE_BYTES", str(20 * 1024 * 1024)))
        self.total_limit = int(os.getenv("IM_WORKSPACE_TOTAL_BYTES", str(200 * 1024 * 1024)))
        self.count_limit = int(os.getenv("IM_WORKSPACE_MAX_FILES", "5000"))

    def access(self, room_id, user_id):
        room = self.rooms.ensure_group_room(room_id)
        if room.get("created_by") != user_id:
            raise KeyError("群聊不存在")
        return room

    def detail(self, room_id, user_id):
        room = self.access(room_id, user_id)
        configured = (room.get("metadata") or {}).get("workdir") or ""
        return {"workdir": configured, "effective_workdir": configured or self.rooms.default_workdir,
                "limits": {"file_bytes": self.file_limit, "total_bytes": self.total_limit, "files": self.count_limit}}

    @staticmethod
    def relative_path(value):
        if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
            raise ValueError("目录路径无效")
        path = PurePosixPath(value)
        if path.is_absolute() or any(p in {"", ".", ".."} for p in value.split("/")) or ":" in value:
            raise ValueError("导入路径必须是目录内的相对路径")
        return path

    def prepare_import(self, room_id, user_id, paths, directories, uploads):
        self.access(room_id, user_id)
        if len(paths) != len(uploads) or len(paths) > self.count_limit or len(directories) > self.count_limit:
            raise ValueError("文件清单不匹配或文件数量超限")
        file_paths = [self.relative_path(p) for p in paths]
        dir_paths = [self.relative_path(p) for p in directories]
        if len(set(file_paths)) != len(file_paths) or len(set(dir_paths)) != len(dir_paths):
            raise ValueError("导入目标路径重复")
        if set(file_paths) & set(dir_paths):
            raise ValueError("同一路径不能同时为文件和目录")
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".import-", dir=self.root))
        try:
            for relative in dir_paths:
                (staging / relative).mkdir(parents=True, exist_ok=True)
            total = 0
            for relative, upload in zip(file_paths, uploads):
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with target.open("xb") as output:
                    while chunk := upload.file.read(1024 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size > self.file_limit or total > self.total_limit:
                            raise ValueError("目录导入超过文件大小或总大小限制")
                        output.write(chunk)
            target = self.root / uuid4().hex
            staging.rename(target)
            return str(target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    async def activate(self, room_id, user_id, workdir):
        self.access(room_id, user_id)
        return await self.rooms.update_room(room_id, metadata={"workdir": validate_workdir(workdir)} if workdir else {"workdir": ""},
                                            user_id=user_id)
