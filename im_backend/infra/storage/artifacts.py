from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import BinaryIO


class ArtifactStorage:
    def __init__(self, store, root_dir: str | Path) -> None:
        self._store = store
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, *, file: BinaryIO, filename: str, content_type: str = "") -> dict:
        artifact_id = str(uuid.uuid4())
        safe_name = Path(filename or "artifact.bin").name
        target = self.root_dir / f"{artifact_id}-{safe_name}"
        with target.open("wb") as output:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)

        record = {
            "artifact_id": artifact_id,
            "filename": safe_name,
            "content_type": content_type,
            "size": os.path.getsize(target),
            "path": str(target),
        }
        return self._store.insert_one("im_artifacts", record)

    def save_bytes(self, *, content: bytes, filename: str, content_type: str = "") -> dict:
        artifact_id = str(uuid.uuid4())
        safe_name = Path(filename or "artifact.bin").name
        target = self.root_dir / f"{artifact_id}-{safe_name}"
        with target.open("wb") as output:
            output.write(content)

        record = {
            "artifact_id": artifact_id,
            "filename": safe_name,
            "content_type": content_type,
            "size": os.path.getsize(target),
            "path": str(target),
        }
        return self._store.insert_one("im_artifacts", record)

    def get(self, artifact_id: str) -> dict | None:
        return self._store.find_one("im_artifacts", {"artifact_id": artifact_id})
