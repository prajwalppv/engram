"""The store must be ONE stable per-user location — never fragmented per
install/host via $CLAUDE_PLUGIN_DATA (the v0.3.1 unified-store fix)."""
from __future__ import annotations

from pathlib import Path

from engram.config import Settings


def test_default_store_ignores_claude_plugin_data(monkeypatch):
    # Even when the host sets CLAUDE_PLUGIN_DATA (which differs per install/host),
    # the default store stays the stable per-user path — so memory never splits.
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/tmp/some-install-specific-dir")
    monkeypatch.delenv("ENGRAM_STORE_DIR", raising=False)
    assert Settings().resolved_store() == (Path.home() / ".engram" / "store").resolve()


def test_engram_store_dir_override_still_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGRAM_STORE_DIR", str(tmp_path / "custom"))
    assert Settings().resolved_store() == (tmp_path / "custom").resolve()
