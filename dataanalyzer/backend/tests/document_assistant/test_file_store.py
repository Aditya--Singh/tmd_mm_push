import asyncio
import time

import pytest

from app.tabs.document_assistant import file_store as fs
from app.tabs.document_assistant.file_store import (
    RETENTION_SECONDS,
    FileExpired,
    FileStore,
)

T0 = 1_800_000_000.0


@pytest.fixture
def store(tmp_path):
    return FileStore(tmp_path / "uploads")


def test_save_and_get(store):
    saved = store.save("Letter.DOCX", b"abc", now=T0)
    got = store.get(saved.id, now=T0 + 60)
    assert got.filename == "Letter.DOCX"
    assert got.ext == ".docx"
    assert got.read_bytes() == b"abc"
    assert got.expires_at == T0 + RETENTION_SECONDS


def test_ids_are_long_random_and_unique(store):
    ids = {store.save("a.txt", b"x").id for _ in range(20)}
    assert len(ids) == 20
    assert all(len(i) >= 40 for i in ids)


def test_user_filename_never_used_as_path(store):
    saved = store.save("../../evil.txt", b"x")
    assert saved.path.parent.parent == store.root
    assert saved.path.name == "file.txt"


def test_expired_file_is_rejected_and_removed(store):
    saved = store.save("a.txt", b"x", now=T0)
    with pytest.raises(FileExpired) as err:
        store.get(saved.id, now=T0 + RETENTION_SECONDS)
    assert "expired" in str(err.value)
    assert not (store.root / saved.id).exists()


def test_unknown_and_malformed_ids_are_expired(store):
    with pytest.raises(FileExpired):
        store.get("A" * 43)
    with pytest.raises(FileExpired):
        store.get("../etc")
    with pytest.raises(FileExpired):
        store.get("")


def test_cleanup_deletes_old_and_keeps_new(store):
    old = store.save("old.txt", b"x", now=T0)
    new = store.save("new.txt", b"y", now=T0 + RETENTION_SECONDS - 10)
    assert store.cleanup(now=T0 + RETENTION_SECONDS + 1) == 1
    assert not (store.root / old.id).exists()
    assert store.get(new.id, now=T0 + RETENTION_SECONDS + 1).read_bytes() == b"y"


def test_cleanup_on_missing_root(tmp_path):
    assert FileStore(tmp_path / "nope").cleanup() == 0


def test_delete_now(store):
    saved = store.save("a.txt", b"x")
    store.delete(saved.id)
    with pytest.raises(FileExpired):
        store.get(saved.id)
    store.delete(saved.id)  # deleting again is fine
    store.delete("../../etc")  # malformed ids are ignored, never touch the disk


def test_cleanup_loop_runs_on_start(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store = fs.get_store()
    old = store.save("old.txt", b"x", now=time.time() - RETENTION_SECONDS - 60)
    new = store.save("new.txt", b"y")

    async def run_once():
        task = asyncio.create_task(fs.run_cleanup_loop(interval=3600))
        await asyncio.sleep(0.2)
        task.cancel()

    asyncio.run(run_once())
    assert not (store.root / old.id).exists()
    assert (store.root / new.id).exists()
