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


def _first_body_line(body: str) -> str:
    # Skip the heading (#), the dated stamp (**…**), and underscore-meta (_…_).
    return next((ln.strip() for ln in (body or "").splitlines() if ln.strip()
                 and not ln.startswith(("#", "_", "**"))), "")


def cmd_recall() -> int:
    """Print SessionStart additionalContext: the always-on layer (your standing
    preferences, so they apply THIS session) + memory recalled for this repo. Also
    refreshes the persistent managed block in CLAUDE.md (the hybrid other half).

    The ENTIRE body is guarded: this hook's stdout is a strict contract (only the
    additionalContext JSON may be emitted), so any failure must produce no stdout
    and exit 0 rather than risk a partial print + traceback corrupting it.
    """
    try:
        data = _read_hook_input()
        cwd = data.get("cwd")
        repo = _repo_of(cwd)
        from .core import memory, preferences
        from .core import roles as role_engine
        store, settings = _store_and_settings()
        role = role_engine.current_role_name(store, settings.role)
        area = settings.area

        prefs = preferences.list_preferences(store, repo=repo, role=role, area=area)
        # Persistent half of the hybrid layer: refresh the managed CLAUDE.md block.
        if getattr(settings, "manage_claude_md", True):
            target = settings.claude_md_path or (Path(cwd) / "CLAUDE.md" if cwd else None)
            if target:
                try:
                    preferences.sync_claude_md(store, str(target), repo=repo, role=role, area=area)
                except Exception:
                    pass

        # Recalled memory excludes horizons surfaced elsewhere (prefs here; working
        # memory injected only on resume) and is applicability-filtered to context.
        ents = memory.list_recent(store, repo=repo, role=role, area=area, limit=6,
                                  exclude_horizons={"preference", "working"})

        sections: list[str] = []
        # Working memory: only when RESUMING a session (a fresh snapshot exists for
        # this exact session_id). A brand-new session has none, so nothing shows.
        if getattr(settings, "working_memory", True):
            from .core import working
            try:  # self-prune stale working snapshots (per-horizon TTL, cheap)
                working.prune_expired(store, settings.working_ttl_hours)
            except Exception:
                pass
            wstate = working.load(store, data.get("session_id"))
            if working.is_fresh(wstate, settings.working_ttl_hours) and wstate.get("summary"):
                sections.append("### engram — resuming where you left off")
                sections.append(f"- {wstate['summary']}")
                sections.append("")
        if prefs:  # always-on: applies immediately this session
            sections.append("### engram — your preferences")
            for e in prefs[:8]:
                sections.append(f"- {_first_body_line(e.body) or e.title}")
            sections.append("")
        if ents:
            sections.append(f"### engram — recalled memory{f' for `{repo}`' if repo else ''}")
            for e in ents:
                sections.append(f"- **{e.title}** ({e.type}) — {_first_body_line(e.body)[:160]}")
            sections.append("")
        if not sections:
            return 0
        sections.append("_(Local private memory. `memory_recall` for more, "
                        "`memory_save` to remember, `/engram:status` to manage preferences.)_")
        payload = json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": "\n".join(sections)}})
    except Exception:
        return 0  # never block a session; emit nothing on failure
    print(payload)
    return 0


def _capture(*, force: bool, label: str) -> int:
    """Shared capture path for the Stop / PreCompact / SessionEnd triggers.

    Folds only the unprocessed delta of the live transcript into memory and
    advances the session high-water mark. ``force`` flushes any delta; otherwise
    it waits for ``capture_every_turns`` new user turns (the throttled Stop path).
    """
    data = _read_hook_input()
    cwd = data.get("cwd")
    repo = _repo_of(cwd)
    tpath = data.get("transcript_path")
    if not tpath or not os.path.exists(tpath):
        return 0
    try:
        from .core import capture, preferences
        from .core.search_backends import build_backend
        store, settings = _store_and_settings()
        backend = build_backend(settings, store)  # keep new memories indexed for recall
        results = capture.capture_delta(
            store, settings, transcript_path=tpath, repo=repo,
            session_id=data.get("session_id"), search_backend=backend,
            force=force, min_turns=settings.capture_every_turns,
        )
        # Refresh the persistent CLAUDE.md block if a new preference was captured.
        if getattr(settings, "manage_claude_md", True):
            target = settings.claude_md_path or (Path(cwd) / "CLAUDE.md" if cwd else None)
            if target:
                try:
                    from .core import roles as role_engine
                    role = role_engine.current_role_name(store, settings.role)
                    preferences.sync_claude_md(store, str(target), repo=repo,
                                               role=role, area=settings.area)
                except Exception:
                    pass
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
    # Recursion guard (belt-and-suspenders to the launcher check): never let a
    # nested `claude -p` summarizer run trigger another capture.
    if os.environ.get("ENGRAM_DISABLE_HOOKS"):
        raise SystemExit(0)
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
