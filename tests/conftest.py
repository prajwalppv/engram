from __future__ import annotations

import os
from pathlib import Path

import pytest

from engram.core.search_backends import TextSearchBackend
from engram.core.store import FileSystemBackend, Store
from engram.roles import get_role


@pytest.fixture(autouse=True)
def _isolate_engram_env(monkeypatch):
    """Tests must not be affected by ambient ENGRAM_* config (e.g. an ENGRAM_REPO
    set in the developer's shell/settings) — Settings() reads the environment."""
    for k in list(os.environ):
        if k.startswith("ENGRAM_"):
            monkeypatch.delenv(k, raising=False)


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
