from __future__ import annotations

import re
import time
from uuid import UUID
from pathlib import Path
from typing import BinaryIO

MAX_FILE_SIZE = 20 * 1024 * 1024


class FileTooLarge(ValueError):
    pass


class LocalFileStorage:
    """Only server-generated UUID directories under the upload root are accessible."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, file_id: str, filename: str, stream: BinaryIO) -> tuple[str, int]:
        name = re.sub(r'[\x00-\x1f\x7f/\\\\]', '_', filename or 'file.bin').strip(' .')
        # Bound UTF-8 bytes, not characters, to respect filesystem filename limits.
        name = name.encode('utf-8')[:200].decode('utf-8', errors='ignore') or 'file.bin'
        directory = self.root / file_id
        directory.mkdir()
        target = directory / name
        size = 0
        try:
            with target.open('xb') as output:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        raise FileTooLarge('单文件不能超过 20 MiB')
                    output.write(chunk)
            return str(target), size
        except BaseException:
            target.unlink(missing_ok=True)
            directory.rmdir()
            raise

    def path(self, record: dict) -> Path:
        target = Path(record['storage_path'])
        expected_parent = self.root / record['file_id']
        if not target.is_absolute() or target.parent != expected_parent:
            raise ValueError('文件路径不属于上传目录')
        if target.is_symlink() or expected_parent.is_symlink() or target.resolve().parent != expected_parent:
            raise ValueError('上传目录中不允许符号链接')
        return target

    def delete(self, record: dict) -> None:
        target = self.path(record)
        target.unlink(missing_ok=True)
        if target.parent.exists():
            target.parent.rmdir()

    def sweep_orphans(self, has_record) -> None:
        """Remove only expired server UUID directories left by interrupted uploads."""
        for directory in self.root.iterdir():
            try:
                if directory.is_symlink() or not directory.is_dir() or str(UUID(directory.name)) != directory.name:
                    continue
                if directory.stat().st_mtime > time.time() - 86400 or has_record(directory.name):
                    continue
                children = list(directory.iterdir())
                if any(child.is_symlink() or not child.is_file() for child in children):
                    continue
                for child in children:
                    child.unlink(missing_ok=True)
                directory.rmdir()
            except (ValueError, FileNotFoundError):
                continue
