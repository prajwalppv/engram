"""Project (repo) attribution — derive the repo from the FILES a session edited,
not the cwd. This is the general, on-the-fly fix for cross-project mislabeling."""
from __future__ import annotations

import json
import subprocess

from engram.config import Settings
from engram.core import capture, ingest, memory, projects, summarizer


# ---------------------------------------------------------------- repo_name
def test_repo_name_none_and_version():
    assert projects.repo_name(None) is None
    assert projects.repo_name("") is None
    assert projects.repo_name("/nonexistent/x/0.1.6") is None     # version garbage
    assert projects.repo_name("/nonexistent/x/v2.1.0") is None


def test_repo_name_plain_dir_and_file(tmp_path):
    d = tmp_path / "acme"
    d.mkdir()
    assert projects.repo_name(str(d)) == "acme"
    f = d / "src.py"
    f.write_text("x")
    assert projects.repo_name(str(f)) == "acme"   # a file resolves to its dir's repo


# ---------------------------------------------------------------- dominant_repo
def test_dominant_repo(tmp_path):
    a = tmp_path / "alpha"; a.mkdir(); subprocess.run(["git", "init", "-q", str(a)])
    b = tmp_path / "beta"; b.mkdir(); subprocess.run(["git", "init", "-q", str(b)])
    paths = []
    for d, files in [(a, ["1.py", "2.py"]), (b, ["3.py"])]:
        for f in files:
            (d / f).write_text("x")          # edited files exist on disk
            paths.append(str(d / f))
    assert projects.dominant_repo(paths) == "alpha"   # most-edited repo wins
    assert projects.dominant_repo([]) is None


# ---------------------------------------------------------------- edited_paths
def test_edited_paths_extracts_edit_tools(tmp_path):
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "editing"},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/repo/a.py"}},
            {"type": "tool_use", "name": "Write", "input": {"file_path": "/repo/b.py"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "user", "message": {"role": "user", "content": "hi"}},
    ]
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert ingest.edited_paths(str(p)) == ["/repo/a.py", "/repo/b.py"]  # Bash excluded


# ---------------------------------------------------------------- the real fix
def test_capture_attributes_to_edited_repo_not_cwd(tmp_path, store, generic,
                                                   text_backend, monkeypatch):
    # session EDITS files in repo "beta" but the hook's cwd is "alpha" — the memory
    # must be scoped to beta (where the work happened), not alpha (the cwd).
    beta = tmp_path / "beta"; beta.mkdir()
    subprocess.run(["git", "init", "-q", str(beta)])
    edited = beta / "billing.py"
    edited.write_text("# billing\n")   # edited files exist on disk
    lines = [
        {"type": "user", "message": {"role": "user", "content": "use postgres for billing"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": str(edited)}}]}},
    ]
    tp = tmp_path / "t.jsonl"
    tp.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    monkeypatch.setattr(summarizer, "summarize_session",
                        lambda s_, set_, txt, *, role, repo, candidates=None: [
                            {"type": "Decision", "title": "Pg billing", "body": "postgres for billing"}])

    capture.capture_delta(store, Settings(summarizer="heuristic", manage_claude_md=False),
                          transcript_path=str(tp), repo="alpha", session_id="x",
                          search_backend=text_backend, force=True)
    assert memory.read(store, "Pg billing").repo == "beta"   # inferred from edits, not cwd


def test_explicit_override_beats_inference(tmp_path, store, generic, text_backend, monkeypatch):
    beta = tmp_path / "beta"; beta.mkdir()
    subprocess.run(["git", "init", "-q", str(beta)])
    lines = [
        {"type": "user", "message": {"role": "user", "content": "decision about x"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": str(beta / "f.py")}}]}},
    ]
    tp = tmp_path / "t.jsonl"
    tp.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    monkeypatch.setattr(summarizer, "summarize_session",
                        lambda s_, set_, txt, *, role, repo, candidates=None: [
                            {"type": "Decision", "title": "Pinned", "body": "body"}])
    capture.capture_delta(store, Settings(repo="pinned-repo", summarizer="heuristic",
                                          manage_claude_md=False),
                          transcript_path=str(tp), repo="alpha", session_id="y",
                          search_backend=text_backend, force=True)
    assert memory.read(store, "Pinned").repo == "pinned-repo"  # explicit override wins
