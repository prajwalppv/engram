"""engram-hook — tiny CLI the Claude Code plugin hooks call. Talks to the local
core directly (no MCP round-trip), so it's fast and needs no running server.

  SessionStart →  engram-hook recall   (stdin: {cwd,...})  → injects context
  SessionEnd   →  engram-hook ingest   (stdin: {transcript_path, cwd,...})

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


def cmd_ingest() -> int:
    """Distill the ended session into a memory + update the inferred role."""
    data = _read_hook_input()
    repo = _repo_of(data.get("cwd"))
    tpath = data.get("transcript_path")
    if not tpath or not os.path.exists(tpath):
        return 0
    try:
        from .core import ingest, memory
        from .core import roles as role_engine
        store, settings = _store_and_settings()
        distilled = ingest.distill_path(tpath, repo=repo)
        if not distilled:
            return 0
        role_engine.update_from_session(store, distilled["full_text"])
        role = role_engine.current_role(store, settings.role)
        memory.save(store, role, type_="SessionSummary", title=distilled["title"],
                    body=distilled["body"], repo=repo,
                    session_id=data.get("session_id"), search_backend=None)
        print(f"[engram] captured session memory for {repo or 'general'}", file=sys.stderr)
    except Exception as e:  # best-effort
        print(f"[engram] ingest skipped: {e}", file=sys.stderr)
    return 0


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "recall":
        raise SystemExit(cmd_recall())
    if cmd == "ingest":
        raise SystemExit(cmd_ingest())
    print("usage: engram-hook {recall|ingest}", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
