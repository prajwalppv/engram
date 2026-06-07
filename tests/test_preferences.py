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


def test_detect_ignores_tool_output_and_file_dumps():
    # Tool results / file dumps arrive flattened as "user:" text. They must NOT be
    # mined as standing preferences just because they contain "by default" / "always"
    # — that was the root cause of bogus "Pref: 111 112 …" entries.
    text = (
        "user: please always run the full test suite before pushing\n\n"
        "user: 95 - An always-on layer learns your standing preferences\n"
        "111 112 It learns them automatically when you state a rule\n"
        "218 219 ## Semantic recall (default)\n"
        "Semantic recall on by default (local embeddings); avoid network calls\n\n"
        "user: see the docs at https://example.com/always-do-this by default"
    )
    found = preferences.detect(text)
    assert found == ["please always run the full test suite before pushing"], found


def test_read_transcript_excludes_tool_results():
    import json, tempfile, os
    from engram.core import ingest
    lines = [
        {"type": "user", "message": {"role": "user", "content": "always use uv"}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "content": "1 always import os\n2 def main(): ..."}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "done"},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
    ]
    p = tempfile.mktemp(suffix=".jsonl")
    Path(p).write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    try:
        ev = ingest.read_transcript(p)
    finally:
        os.remove(p)
    texts = [e["text"] for e in ev]
    assert "always use uv" in texts
    assert "done" in texts
    assert not any("import os" in t for t in texts)  # tool_result dropped
    assert not any("ls" == t for t in texts)         # tool_use dropped


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
