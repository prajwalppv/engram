from __future__ import annotations

from pathlib import Path

import pytest

from engram.core.search_backends import TextSearchBackend
from engram.core.store import FileSystemBackend, Store
from engram.roles import get_role


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(FileSystemBackend(tmp_path / "store"))


@pytest.fixture
def text_backend(store: Store) -> TextSearchBackend:
    return TextSearchBackend(store)


@pytest.fixture
def swe():
    return get_role("swe")


@pytest.fixture
def generic():
    return get_role("generic")
