"""Capture a finished session into memory: update the inferred role, run the
configured summarizer, and persist each extracted node. Shared by the SessionEnd
hook and the memory_ingest_session tool (DRY).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import memory
from . import roles as role_engine
from . import summarizer

if TYPE_CHECKING:
    from ..config import Settings
    from .models import SaveResult
    from .search_backends import SearchBackend
    from .store import Store


def capture_session(
    store: "Store",
    settings: "Settings",
    *,
    transcript_text: str,
    repo: str | None = None,
    session_id: str | None = None,
    search_backend: "SearchBackend | None" = None,
) -> list["SaveResult"]:
    if not transcript_text or not transcript_text.strip():
        return []
    # Update the inferred role from this session, then extract memory with it.
    role_engine.update_from_session(store, transcript_text)
    role = role_engine.current_role(store, settings.role)
    results: list = []
    # Always-on horizon: auto-capture any standing preferences the user stated.
    if getattr(settings, "detect_preferences", True):
        try:
            from . import preferences
            results += preferences.capture_from_session(
                store, role, transcript_text, search_backend=search_backend)
        except Exception:
            pass
    items = summarizer.summarize_session(
        store, settings, transcript_text, role=role, repo=repo)
    for it in items:
        res = memory.save(
            store, role, type_=it["type"], title=it["title"], body=it["body"],
            repo=repo, tags=it.get("tags"), links=it.get("links"),
            session_id=session_id, search_backend=search_backend,
        )
        results.append(res)
    return results


def capture_delta(
    store: "Store",
    settings: "Settings",
    *,
    transcript_path: str,
    repo: str | None = None,
    session_id: str | None = None,
    search_backend: "SearchBackend | None" = None,
    force: bool = False,
    min_turns: int = 1,
) -> list["SaveResult"]:
    """Capture only the *new* transcript events since this session's high-water
    mark, then advance the mark. Idempotent across the Stop / PreCompact /
    SessionEnd triggers that all call into here.

    - ``force=True``  → flush whatever delta exists (PreCompact, SessionEnd).
    - ``force=False`` → only fire once at least ``min_turns`` new user turns have
      accumulated (the throttled end-of-turn Stop trigger); otherwise leave the
      mark unadvanced so the next trigger picks the delta up.
    """
    from . import checkpoint, ingest

    events = ingest.read_transcript(transcript_path)
    marker = checkpoint.load(store, session_id)
    start = int(marker.get("processed_events", 0))
    if start > len(events):  # transcript rotated/truncated → reprocess from 0
        start = 0
    delta = events[start:]
    if not delta:
        return []
    new_user_turns = sum(1 for e in delta if e["role"] == "user")
    if not force and new_user_turns < max(1, min_turns):
        return []  # accumulate; a later trigger will flush this delta

    text = "\n\n".join(f"{e['role']}: {e['text']}" for e in delta)
    results = capture_session(
        store, settings, transcript_text=text, repo=repo,
        session_id=session_id, search_backend=search_backend,
    )
    marker["processed_events"] = len(events)
    marker["captures"] = int(marker.get("captures", 0)) + 1
    checkpoint.save(store, session_id, marker)
    return results
