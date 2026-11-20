"""Temporary storage for uploaded and generated files.

Each file lives in its own folder named by a random, unguessable id, next to a small
``meta.json``. Files expire 4 hours after upload (spec section 6). There is no database and
no record of who uploaded what.
"""

import asyncio
import json
import logging
import re
import shutil
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

RETENTION_SECONDS = 4 * 60 * 60
CLEANUP_INTERVAL_SECONDS = 15 * 60
EXPIRED_MESSAGE = "This file has expired. Please upload it again."

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
_META = "meta.json"

log = logging.getLogger(__name__)


class FileExpired(LookupError):
    """The id is unknown, malformed or older than the retention period."""

    def __init__(self) -> None:
        super().__init__(EXPIRED_MESSAGE)


@dataclass(frozen=True)
class StoredFile:
    id: str
    filename: str
    ext: str
    created_at: float
    path: Path

    @property
    def expires_at(self) -> float:
        return self.created_at + RETENTION_SECONDS

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()


class FileStore:
    def __init__(self, root: Path | str, retention: float = RETENTION_SECONDS) -> None:
        self.root = Path(root)
        self.retention = retention

    def _dir(self, file_id: str) -> Path:
        if not _ID_RE.fullmatch(file_id or ""):
            raise FileExpired()
        return self.root / file_id

    def save(
        self, filename: str, content: bytes, now: float | None = None
    ) -> StoredFile:
        file_id = secrets.token_urlsafe(32)
        folder = self.root / file_id
        folder.mkdir(parents=True, exist_ok=False)
        # Store under a fixed name so a user-supplied filename never touches the path.
        ext = Path(filename).suffix.lower()
        path = folder / f"file{ext}"
        path.write_bytes(content)
        created = time.time() if now is None else now
        meta = {"filename": filename, "ext": ext, "created_at": created}
        (folder / _META).write_text(json.dumps(meta), encoding="utf-8")
        return StoredFile(file_id, filename, ext, created, path)

    def get(self, file_id: str, now: float | None = None) -> StoredFile:
        folder = self._dir(file_id)
        try:
            meta = json.loads((folder / _META).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise FileExpired() from None
        now = time.time() if now is None else now
        if now - meta["created_at"] >= self.retention:
            self._remove(folder)
            raise FileExpired()
        path = folder / f"file{meta['ext']}"
        if not path.is_file():
            raise FileExpired()
        return StoredFile(
            file_id, meta["filename"], meta["ext"], meta["created_at"], path
        )

    def delete(self, file_id: str) -> None:
        """Delete a file now. Unknown ids are ignored, so Clear can always succeed."""
        try:
            folder = self._dir(file_id)
        except FileExpired:
            return
        self._remove(folder)

    def cleanup(self, now: float | None = None) -> int:
        """Delete every file older than the retention period. Returns the number deleted."""
        if not self.root.is_dir():
            return 0
        now = time.time() if now is None else now
        removed = 0
        for folder in self.root.iterdir():
            if not folder.is_dir():
                continue
            try:
                created = json.loads((folder / _META).read_text(encoding="utf-8"))[
                    "created_at"
                ]
            except (OSError, ValueError, KeyError):
                # Half-written or foreign folder: fall back to its modification time.
                created = folder.stat().st_mtime
            if now - created >= self.retention:
                self._remove(folder)
                removed += 1
        return removed

    @staticmethod
    def _remove(folder: Path) -> None:
        shutil.rmtree(folder, ignore_errors=True)


def get_store() -> FileStore:
    return FileStore(Path(get_settings().data_dir) / "uploads")


async def run_cleanup_loop(interval: float = CLEANUP_INTERVAL_SECONDS) -> None:
    """Delete expired files now and then every `interval` seconds, until cancelled."""
    while True:
        try:
            removed = await asyncio.to_thread(get_store().cleanup)
            if removed:
                log.info("Deleted %d expired document assistant file(s)", removed)
        except OSError:
            log.exception("File cleanup failed")
        await asyncio.sleep(interval)
