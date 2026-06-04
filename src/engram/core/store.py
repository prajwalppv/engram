"""The local memory store — filesystem-backed, safety-wrapped. On-device only.

A thin StorageBackend protocol keeps the door open for a different backend later
a small seam, but there is one impl: the local filesystem.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from . import safety
from .errors import StoreSafetyError

BACKUP_DIR = ".backups"
INDEX_DIR = ".index"


@runtime_checkable
class StorageBackend(Protocol):
    root: Path

    def exists(self, abs_path: Path) -> bool: ...
    def read_text(self, abs_path: Path) -> str: ...
    def write_text(self, abs_path: Path, content: str) -> None: ...
    def iter_markdown(self) -> Iterable[Path]: ...


class FileSystemBackend:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def exists(self, abs_path: Path) -> bool:
        return abs_path.exists()

    def read_text(self, abs_path: Path) -> str:
        return abs_path.read_text(encoding="utf-8")

    def write_text(self, abs_path: Path, content: str) -> None:
        # Atomic: write to a sibling temp file then rename, so a hook killed
        # mid-write can never leave a truncated/corrupt memory node behind.
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = abs_path.with_name(f".{abs_path.name}.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, abs_path)

    def iter_markdown(self) -> Iterable[Path]:
        return self.root.rglob("*.md")


class Store:
    def __init__(self, backend: StorageBackend, *, git_snapshot: bool = False) -> None:
        self.backend = backend
        self.root = backend.root
        self.git_snapshot_enabled = git_snapshot

    def resolve(self, rel_or_abs: str | Path) -> Path:
        return safety.resolve_in_store(self.root, rel_or_abs)

    def relpath(self, abs_path: Path) -> str:
        return abs_path.resolve().relative_to(self.root).as_posix()

    def _is_internal(self, abs_path: Path) -> bool:
        try:
            rel = abs_path.resolve().relative_to(self.root)
        except ValueError:
            return True
        parts = rel.parts
        return (not parts) or parts[0].startswith(".") or parts[-1].startswith("_")

    def exists(self, rel_or_abs: str | Path) -> bool:
        return self.backend.exists(self.resolve(rel_or_abs))

    def read(self, rel_or_abs: str | Path) -> str:
        return self.backend.read_text(self.resolve(rel_or_abs))

    def iter_entries(self) -> Iterable[Path]:
        for p in self.backend.iter_markdown():
            if not self._is_internal(p):
                yield p

    def write(self, rel_or_abs: str | Path, content: str,
              *, snapshot_message: str | None = None) -> str | None:
        target = self.resolve(rel_or_abs)
        if target.is_dir():
            raise StoreSafetyError(f"'{rel_or_abs}' is a directory.")
        backup_rel = None
        if self.backend.exists(target):
            b = safety.backup_file(self.root, target, BACKUP_DIR)
            backup_rel = b.resolve().relative_to(self.root).as_posix()
        self.backend.write_text(target, content)
        if self.git_snapshot_enabled and snapshot_message:
            safety.git_snapshot(self.root, snapshot_message)
        return backup_rel
