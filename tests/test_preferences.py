"""Phase 1 horizons — preferences / always-on layer."""
from __future__ import annotations

from pathlib import Path

from engram.core import claudemd, memory, preferences, prune, vigor
from engram.config import Settings


# ---------------------------------------------------------------- detection
def test_detect_fires_on_standing_instructions():
    text = (
        "user: from now on, always use uv and never pip.\n\n"
        "assistant: got it.\n\n"
        "user: I prefer terse answers.\n\n"
        "user: by default, lint with ruff."
    )
    found = preferences.detect(text)
    joined = " | ".join(found).lower()
    assert any("uv" in f.lower() for f in found)
    assert any("terse" in f.lower() for f in found)
    assert any("ruff" in f.lower() for f in found)


def test_detect_ignores_non_preferences():
    text = (
        "user: this test always crashes on CI.\n\n"
        "assistant: always remember to hydrate.\n\n"   # assistant turn — ignored
        "user: can you fix the parser?"
    )
    # "this test always crashes" is not sentence-initial always/never and has no
    # standing cue; the assistant turn is excluded entirely.
    assert preferences.detect(text) == []


# ---------------------------------------------------------------- add / list / forget
def test_add_list_dedupe_and_forget(store, swe, text_backend):
    r1 = preferences.add(store, swe, "Always use uv, never pip.", search_backend=text_backend)
    assert r1 is not None and r1.action == "created"
    # near-duplicate is skipped
    assert preferences.add(store, swe, "always use uv, never pip", search_backend=text_backend) is None

    prefs = preferences.list_preferences(store)
    assert len(prefs) == 1
    e = prefs[0]
    assert e.horizon == "preference" and e.type == "Preference" and e.scope == "global"

    out = preferences.forget(store, e.id, search_backend=text_backend)
    assert out["forgot"]
    assert preferences.list_preferences(store) == []


def test_capture_from_session_stores_global_prefs(store, swe, text_backend):
    text = "user: please always run the tests before committing.\n\nassistant: ok"
    saved = preferences.capture_from_session(store, swe, text, search_backend=text_backend)
    assert len(saved) == 1
    assert preferences.list_preferences(store)[0].scope == "global"


# ---------------------------------------------------------------- CLAUDE.md block
def test_claude_md_block_is_idempotent_and_scoped(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# My project\n\nExisting notes.\n", encoding="utf-8")

    assert claudemd.update_managed_block(p, "## Prefs\n- always use uv") is True
    after = p.read_text(encoding="utf-8")
    assert "Existing notes." in after  # user content preserved
    assert claudemd.START in after and claudemd.END in after

    # same content → no change
    assert claudemd.update_managed_block(p, "## Prefs\n- always use uv") is False
    # update replaces in place, no duplicate block
    assert claudemd.update_managed_block(p, "## Prefs\n- never force-push") is True
    final = p.read_text(encoding="utf-8")
    assert final.count(claudemd.START) == 1
    assert "never force-push" in final and "always use uv" not in final

    # empty content removes the block but keeps user content
    assert claudemd.update_managed_block(p, "") is True
    cleaned = p.read_text(encoding="utf-8")
    assert claudemd.START not in cleaned and "Existing notes." in cleaned


def test_sync_claude_md_renders_preferences(store, swe, tmp_path, text_backend):
    preferences.add(store, swe, "Always use uv.", search_backend=text_backend)
    p = tmp_path / "CLAUDE.md"
    assert preferences.sync_claude_md(store, p) is True
    assert "Always use uv." in p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- lifeline
def test_preferences_are_never_pruned(store, swe, text_backend):
    # an old, unused, unreferenced preference must survive pruning
    preferences.add(store, swe, "Always use uv.", search_backend=text_backend)
    # backdate it so it would otherwise be prune-eligible if it were ephemeral
    p = preferences.list_preferences(store)[0]
    a = prune.analyze(store, Settings())
    targeted = {rp for grp in a["plan"] for rp in grp["rel_paths"]}
    assert p.rel_path not in targeted
    assert vigor.TYPE_DURABILITY["Preference"] >= 2.0


# ---------------------------------------------------------------- backward compat
def test_horizon_defaults_backward_compatible(store, swe):
    r = memory.save(store, swe, type_="Decision", title="Pick Postgres", body="txns")
    e = memory.read(store, r.rel_path)
    assert e.horizon == "semantic"  # default for existing/typed facts
