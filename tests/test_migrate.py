"""The unified-store migration shim must rescue a legacy store exactly once,
non-destructively, and never break startup (v0.3.2)."""
from __future__ import annotations

from pathlib import Path

from engram.core import migrate


def _seed_store(root: Path, n: int = 3) -> Path:
    store = root / "store"
    (store / "Decisions").mkdir(parents=True)
    for i in range(n):
        (store / "Decisions" / f"d{i}.md").write_text(f"# d{i}\n\nbody {i}\n", encoding="utf-8")
    return store


def test_migrates_from_legacy_when_target_empty(tmp_path, monkeypatch):
    # Isolate home so only our seeded legacy store is a candidate (not real ones).
    monkeypatch.setattr(migrate.Path, "home", staticmethod(lambda: tmp_path / "home"))
    legacy = _seed_store(tmp_path / "legacy", 3)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "legacy"))
    target = tmp_path / "unified" / "store"

    report = migrate.maybe_migrate(target)

    assert report is not None and report["notes"] == 3
    assert (target / "Decisions" / "d0.md").exists()
    # non-destructive: the legacy store is untouched
    assert (legacy / "Decisions" / "d0.md").exists()


def test_noop_when_target_already_populated(tmp_path, monkeypatch):
    monkeypatch.setattr(migrate.Path, "home", staticmethod(lambda: tmp_path / "home"))
    _seed_store(tmp_path / "legacy", 5)
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "legacy"))
    target = _seed_store(tmp_path / "unified", 1)  # already has content

    assert migrate.maybe_migrate(target) is None
    # untouched: still just the 1 original note, no copy-in
    assert migrate._note_count(target) == 1


def test_noop_when_no_legacy(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setattr(migrate.Path, "home", staticmethod(lambda: tmp_path / "nohome"))
    assert migrate.maybe_migrate(tmp_path / "unified" / "store") is None


def test_never_raises_on_bad_input(monkeypatch):
    # A failure inside must be swallowed (best-effort), never propagate.
    monkeypatch.setattr(migrate, "_legacy_candidates",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert migrate.maybe_migrate(Path("/nonexistent/unified/store")) is None
