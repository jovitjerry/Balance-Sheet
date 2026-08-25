"""File storage for original uploads.

Uploaded binaries never go into a MongoDB document; the document holds a
:class:`~app.core.schemas.StorageRef` and the bytes live here.

``FileStorage`` is the seam. Swapping in S3 or Azure Blob later means writing
one class against this protocol and changing ``STORAGE_BACKEND`` - no caller
changes.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Protocol, runtime_checkable

from app.core.errors import StorageError
from app.core.schemas import StorageRef


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def key_for(sha256: str, extension: str = "") -> str:
    """Build a storage key from a content hash.

    The key is derived from the file's SHA-256 and **never** from the
    client-supplied filename, which is attacker-controlled and the classic
    path-traversal vector. Content addressing also gives deduplication and
    idempotent re-upload for free, and removes filename-collision handling
    entirely.

    Sharded two levels (``ab/cd/abcd...ef.pdf``) so no directory accumulates
    tens of thousands of entries.
    """
    if len(sha256) != 64 or not all(c in "0123456789abcdef" for c in sha256):
        raise ValueError(f"not a lowercase hex sha256 digest: {sha256!r}")
    suffix = extension.lower()
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    if any(ch in suffix for ch in ("/", "\\", "..", "\0")):
        raise ValueError(f"unsafe extension: {extension!r}")
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}{suffix}"


@runtime_checkable
class FileStorage(Protocol):
    """Where original uploaded files are kept."""

    backend: str

    async def save(self, data: bytes, *, key: str, content_type: str) -> StorageRef: ...

    async def open(self, ref: StorageRef) -> bytes: ...

    async def delete(self, ref: StorageRef) -> None: ...


class LocalFileStorage:
    """Filesystem-backed storage rooted at a single directory."""

    backend = "local"

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # -- internals ---------------------------------------------------------

    def _resolve(self, key: str) -> Path:
        """Map a key to an absolute path, refusing anything outside the root.

        Belt and braces: keys are generated from content hashes, but this class
        must not become a file-read primitive if a key ever reaches it from
        somewhere less trustworthy.
        """
        if not key or key.startswith("/") or "\0" in key:
            raise StorageError(f"invalid storage key: {key!r}")
        parts = PurePosixPath(key).parts
        if any(part in ("..", ".") for part in parts) or PurePosixPath(key).is_absolute():
            raise StorageError(f"invalid storage key: {key!r}")
        candidate = (self.root / Path(*parts)).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise StorageError(f"storage key escapes the root directory: {key!r}")
        return candidate

    def _save_sync(self, data: bytes, key: str) -> int:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory, then rename. A crash
        # mid-write therefore cannot leave a truncated file that would still
        # hash-match its key.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".partial")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        return len(data)

    def _open_sync(self, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"no stored object for key {key!r}") from exc

    def _delete_sync(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    # -- FileStorage -------------------------------------------------------

    async def save(self, data: bytes, *, key: str, content_type: str) -> StorageRef:
        size = await asyncio.to_thread(self._save_sync, data, key)
        return StorageRef(
            backend=self.backend, key=key, size_bytes=size, content_type=content_type
        )

    async def open(self, ref: StorageRef) -> bytes:
        return await asyncio.to_thread(self._open_sync, ref.key)

    async def delete(self, ref: StorageRef) -> None:
        await asyncio.to_thread(self._delete_sync, ref.key)


def build_storage(backend: str, storage_dir: Path) -> FileStorage:
    """Construct the configured storage backend."""
    if backend == "local":
        return LocalFileStorage(storage_dir)
    raise StorageError(
        f"unknown STORAGE_BACKEND {backend!r}; only 'local' is implemented"
    )


__all__ = [
    "FileStorage",
    "LocalFileStorage",
    "build_storage",
    "key_for",
    "sha256_of",
]
