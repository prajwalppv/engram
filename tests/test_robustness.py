"""Regression tests for the hook-safety / failure-mode hardening:
recursion guard, child-env sentinel, and atomic memory writes.
"""
from __future__ import annotations

import engram.hookcli as hookcli
from engram.core import summarizer
from engram.core.store import FileSystemBackend


def test_hooks_noop_when_recursion_sentinel_set(monkeypatch):
    """Inside a nested `claude -p` (ENGRAM_DISABLE_HOOKS=1) the hook entrypoint
    must exit 0 immediately and never dispatch — this is what breaks the
    summarizer→hook→summarizer recursion."""
    monkeypatch.setenv("ENGRAM_DISABLE_HOOKS", "1")
    monkeypatch.setattr("sys.argv", ["engram-hook", "capture"])
    calls = {"n": 0}
    monkeypatch.setattr(hookcli, "cmd_capture",
                        lambda: calls.__setitem__("n", calls["n"] + 1) or 0)
    try:
        hookcli.main()
    except SystemExit as e:
        assert e.code == 0
    assert calls["n"] == 0  # never dispatched


def test_run_claude_sets_recursion_sentinel_and_new_session(monkeypatch):
    """The summarizer must spawn `claude -p` with ENGRAM_DISABLE_HOOKS=1 in the
    child env (so its hooks no-op) and in its own process group (so we can reap
    it on timeout)."""
    captured = {}

    class FakeProc:
        returncode = 0
        def communicate(self, timeout=None):
            return ("[]", "")

    def fake_popen(cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        captured["new_session"] = kwargs.get("start_new_session")
        return FakeProc()

    monkeypatch.setattr(summarizer.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(summarizer.subprocess, "Popen", fake_popen)

    assert summarizer.run_claude("hi", timeout=5) == "[]"
    assert captured["env"].get("ENGRAM_DISABLE_HOOKS") == "1"
    assert captured["new_session"] is True


def test_run_claude_reaps_child_on_timeout(monkeypatch):
    """On timeout, run_claude must kill the child's process group and raise —
    never leave a `claude` lingering past the hook budget."""
    killed = {"pg": False}

    class SlowProc:
        returncode = None
        pid = 4242
        def communicate(self, timeout=None):
            if timeout:
                raise summarizer.subprocess.TimeoutExpired("claude", timeout)
            return ("", "")

    monkeypatch.setattr(summarizer.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(summarizer.subprocess, "Popen", lambda *a, **k: SlowProc())
    monkeypatch.setattr(summarizer.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(summarizer.os, "killpg",
                        lambda pg, sig: killed.__setitem__("pg", True))

    try:
        summarizer.run_claude("hi", timeout=1)
        assert False, "expected RuntimeError on timeout"
    except RuntimeError as e:
        assert "timed out" in str(e)
    assert killed["pg"] is True


def test_store_write_is_atomic(tmp_path):
    """Writes go through a temp file + rename and leave no partial/temp files."""
    b = FileSystemBackend(tmp_path)
    p = tmp_path / "Decision" / "note.md"
    b.write_text(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello"
    assert not list(tmp_path.rglob(".*.tmp"))  # no leftover temp files
