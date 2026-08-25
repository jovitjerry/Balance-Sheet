"""Tests for the local file store."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import StorageError
from app.core.schemas import StorageRef
from app.core.storage import LocalFileStorage, build_storage, key_for, sha256_of

PAYLOAD = b"%PDF-1.7 pretend balance sheet"
DIGEST = sha256_of(PAYLOAD)


class TestKeyDerivation:
    def test_key_is_derived_from_the_hash_and_sharded(self) -> None:
        key = key_for(DIGEST, ".pdf")
        assert key == f"{DIGEST[:2]}/{DIGEST[2:4]}/{DIGEST}.pdf"

    def test_extension_is_normalised(self) -> None:
        assert key_for(DIGEST, "PDF").endswith(".pdf")

    def test_identical_bytes_produce_identical_keys(self) -> None:
        assert key_for(sha256_of(PAYLOAD)) == key_for(sha256_of(PAYLOAD))

    @pytest.mark.parametrize("bad", ["", "nothex", "z" * 64, DIGEST.upper()])
    def test_non_hex_digest_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="sha256"):
            key_for(bad)

    @pytest.mark.parametrize("bad", ["../evil", "a/b", "..", "x\0y"])
    def test_unsafe_extension_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="unsafe extension"):
            key_for(DIGEST, bad)


class TestRoundTrip:
    async def test_save_then_open_returns_the_same_bytes(
        self, storage: LocalFileStorage
    ) -> None:
        ref = await storage.save(PAYLOAD, key=key_for(DIGEST, ".pdf"), content_type="application/pdf")
        assert ref.backend == "local"
        assert ref.size_bytes == len(PAYLOAD)
        assert await storage.open(ref) == PAYLOAD

    async def test_file_lands_on_disk_under_the_sharded_path(
        self, storage: LocalFileStorage
    ) -> None:
        key = key_for(DIGEST, ".pdf")
        await storage.save(PAYLOAD, key=key, content_type="application/pdf")
        assert (storage.root / DIGEST[:2] / DIGEST[2:4] / f"{DIGEST}.pdf").is_file()

    async def test_no_partial_files_are_left_behind(
        self, storage: LocalFileStorage
    ) -> None:
        """Writes go to a temp file and are renamed into place."""
        await storage.save(PAYLOAD, key=key_for(DIGEST, ".pdf"), content_type="application/pdf")
        assert list(storage.root.rglob("*.partial")) == []

    async def test_resaving_the_same_key_is_idempotent(
        self, storage: LocalFileStorage
    ) -> None:
        key = key_for(DIGEST, ".pdf")
        await storage.save(PAYLOAD, key=key, content_type="application/pdf")
        await storage.save(PAYLOAD, key=key, content_type="application/pdf")
        assert len(list(storage.root.rglob("*.pdf"))) == 1

    async def test_delete_removes_the_object(self, storage: LocalFileStorage) -> None:
        ref = await storage.save(PAYLOAD, key=key_for(DIGEST, ".pdf"), content_type="application/pdf")
        await storage.delete(ref)
        with pytest.raises(StorageError, match="no stored object"):
            await storage.open(ref)

    async def test_delete_is_idempotent(self, storage: LocalFileStorage) -> None:
        ref = StorageRef(backend="local", key=key_for(DIGEST), size_bytes=0, content_type="x")
        await storage.delete(ref)  # must not raise

    async def test_opening_a_missing_object_raises(self, storage: LocalFileStorage) -> None:
        ref = StorageRef(backend="local", key=key_for(DIGEST), size_bytes=0, content_type="x")
        with pytest.raises(StorageError, match="no stored object"):
            await storage.open(ref)


class TestPathTraversal:
    """Keys are hash-derived, but this class must not be a file-read primitive."""

    @pytest.mark.parametrize(
        "key",
        [
            "../../../etc/passwd",
            "..",
            "a/../../b",
            "/absolute/path",
            "",
            "with\0null",
        ],
    )
    async def test_escaping_keys_are_refused(
        self, storage: LocalFileStorage, key: str
    ) -> None:
        ref = StorageRef(backend="local", key=key, size_bytes=0, content_type="x")
        with pytest.raises(StorageError):
            await storage.open(ref)

    async def test_nothing_is_written_outside_the_root(
        self, storage: LocalFileStorage, tmp_path: Path
    ) -> None:
        with pytest.raises(StorageError):
            await storage.save(b"x", key="../escaped.txt", content_type="text/plain")
        assert not (tmp_path / "escaped.txt").exists()


class TestBuildStorage:
    def test_local_backend_is_built(self, tmp_path: Path) -> None:
        assert isinstance(build_storage("local", tmp_path), LocalFileStorage)

    def test_unknown_backend_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(StorageError, match="unknown STORAGE_BACKEND"):
            build_storage("s3", tmp_path)
