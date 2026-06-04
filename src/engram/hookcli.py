"""engram-hook — the tiny CLI the Claude Code plugin hooks call. Talks to the
local core directly (no MCP round-trip), so it's fast and needs no running server.

  SessionStart →  engram-hook recall      (stdin: {cwd,...})  → injects context
  Stop         →  engram-hook capture      (stdin: {transcript_path,...}) [throttled]
  PreCompact   →  engram-hook precompact   (stdin: {transcript_path,...}) [forced flush]
  SessionEnd   →  engram-hook ingest       (stdin: {transcript_path,...}) [forced flush]

Capture is incremental + idempotent via a per-session high-water mark, so the
three capture triggers never double-store. Memory survives even if the terminal
is closed without a clean exit (Stop/PreCompact already flushed the work).

All on-device. Best-effort: never block or fail a session.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _read_hook_input() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _repo_of(cwd: str | None) -> str | None:
    if not cwd:
        return None
    return Path(cwd).name or None


def _store_and_settings():
    from .config import load_settings
    from .core.store import FileSystemBackend, Store
    s = load_settings()
    return Store(FileSystemBackend(s.resolved_store())), s


def cmd_recall() -> int:
    """Print SessionStart additionalContext with what we remember about this repo."""
    data = _read_hook_input()
    repo = _repo_of(data.get("cwd"))
    try:
        from .core import memory
        store, _ = _store_and_settings()
        ents = memory.list_recent(store, repo=repo, limit=6)
        if not ents and repo:
            ents = memory.list_recent(store, limit=4)  # fall back to global recent
    except Exception:
        return 0  # never block a session
    if not ents:
        return 0
    lines = [f"### engram — recalled memory{f' for `{repo}`' if repo else ''}", ""]
    for e in ents:
        first = next((ln for ln in e.body.splitlines() if ln.strip()
                      and not ln.startswith("#") and not ln.startswith("_")), "")
        lines.append(f"- **{e.title}** ({e.type}) — {first[:160]}")
    lines.append("")
    lines.append("_(Local private memory. Call `memory_recall` for more, `memory_save` to remember.)_")
    ctx = "\n".join(lines)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": ctx}}))
    return 0


def _capture(*, force: bool, label: str) -> int:
    """Shared capture path for the Stop / PreCompact / SessionEnd triggers.

    Folds only the unprocessed delta of the live transcript into memory and
    advances the session high-water mark. ``force`` flushes any delta; otherwise
    it waits for ``capture_every_turns`` new user turns (the throttled Stop path).
    """
    data = _read_hook_input()
    repo = _repo_of(data.get("cwd"))
    tpath = data.get("transcript_path")
    if not tpath or not os.path.exists(tpath):
        return 0
    try:
        from .core import capture
        from .core.search_backends import build_backend
        store, settings = _store_and_settings()
        backend = build_backend(settings, store)  # keep new memories indexed for recall
        results = capture.capture_delta(
            store, settings, transcript_path=tpath, repo=repo,
            session_id=data.get("session_id"), search_backend=backend,
            force=force, min_turns=settings.capture_every_turns,
        )
        if results:
            print(f"[engram] {label}: captured {len(results)} memory item(s) for "
                  f"{repo or 'general'}", file=sys.stderr)
    except Exception as e:  # best-effort
        print(f"[engram] {label} skipped: {e}", file=sys.stderr)
    return 0


def cmd_capture() -> int:
    """Stop hook — throttled, incremental end-of-turn capture."""
    try:
        _, settings = _store_and_settings()
        if not settings.capture_on_stop:
            return 0
    except Exception:
        return 0
    return _capture(force=False, label="stop")


def cmd_precompact() -> int:
    """PreCompact hook — flush the delta before context is summarized away."""
    return _capture(force=True, label="precompact")


def cmd_ingest() -> int:
    """SessionEnd hook — final flush of any remaining delta."""
    return _capture(force=True, label="ingest")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    dispatch = {
        "recall": cmd_recall,
        "capture": cmd_capture,
        "precompact": cmd_precompact,
        "ingest": cmd_ingest,
    }
    fn = dispatch.get(cmd)
    if fn is None:
        print("usage: engram-hook {recall|capture|precompact|ingest}", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(fn())


if __name__ == "__main__":
    main()
