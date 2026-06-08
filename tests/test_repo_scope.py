"""Repo-derivation hardening — the scope ladder must not be corrupted by junk repo
labels (version strings from plugin-cache cwds, etc.)."""
from __future__ import annotations

from engram.hookcli import _repo_of


def test_repo_of_none():
    assert _repo_of(None) is None
    assert _repo_of("") is None


def test_repo_of_rejects_version_strings():
    # plugin-cache cwds like .../engram/engram/0.1.6 yielded "0.1.6" as a "repo"
    assert _repo_of("/nonexistent/path/0.1.6") is None
    assert _repo_of("/nonexistent/path/v1.2.3") is None
    assert _repo_of("/nonexistent/path/2.0") is None


def test_repo_of_plain_dir_uses_basename(tmp_path):
    d = tmp_path / "myproject"
    d.mkdir()
    # not a git repo → falls back to the directory basename (a real project name)
    assert _repo_of(str(d)) == "myproject"


def test_engram_repo_override(monkeypatch):
    # the cross-project fix: an explicit ENGRAM_REPO pins the repo regardless of cwd
    from engram.config import Settings
    assert Settings(repo="engram").repo == "engram"
    monkeypatch.setenv("ENGRAM_REPO", "engram")
    assert Settings().repo == "engram"
