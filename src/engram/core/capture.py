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
    # Strip user-marked <private> spans BEFORE anything reads the transcript —
    # role inference, summarizer, preference/procedure detection, and the index all
    # see only the redacted text, so marked secrets never reach the store.
    if getattr(settings, "redact_private", True):
        from . import redact
        transcript_text = redact.strip_private(transcript_text)
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
    # Procedural horizon: capture any runbooks the user spelled out (lead-in + steps).
    if getattr(settings, "detect_procedures", True):
        try:
            from . import procedural
            results += procedural.capture_from_session(
                store, role, transcript_text, repo=repo, search_backend=search_backend)
        except Exception:
            pass
    items = summarizer.summarize_session(
        store, settings, transcript_text, role=role, repo=repo)
    dedup = getattr(settings, "dedup_on_capture", True)
    autolink = getattr(settings, "autolink_on_capture", True)
    for it in items:
        title = it["title"]
        links = list(it.get("links") or [])
        merged = False
        if dedup or autolink:
            try:
                from . import consolidate
            except Exception:
                consolidate = None
            # Near-duplicate consolidation: if this restates an existing node, save
            # under THAT title so memory.save appends (merges) — no near-dup spawned.
            if dedup and consolidate is not None:
                try:
                    dup = consolidate.near_duplicate(
                        store, search_backend, title=title, body=it["body"], type_=it["type"],
                        lex_threshold=getattr(settings, "dedup_lex_threshold", 0.7),
                        sem_threshold=getattr(settings, "dedup_sem_threshold", 0.88))
                    if dup is not None:
                        title, merged = dup.title, True
                except Exception:
                    pass
            # Auto-link a genuinely NEW node to its related neighbors so the graph
            # becomes load-bearing (graph-expansion recall) instead of all orphans.
            if autolink and not merged and consolidate is not None:
                try:
                    links += consolidate.related(store, search_backend,
                                                 title=title, body=it["body"], exclude_titles=tuple(links))
                    links = list(dict.fromkeys(links))
                except Exception:
                    pass
        res = memory.save(
            store, role, type_=it["type"], title=title, body=it["body"],
            repo=repo, tags=it.get("tags"), links=links or None,
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
    # Working memory: refresh the session's "where was I" snapshot every tick
    # (cheap, no LLM) — independent of the throttled expensive capture below.
    if getattr(settings, "working_memory", True):
        try:
            from . import working
            wevents = events
            if getattr(settings, "redact_private", True):
                from . import redact
                wevents = [{**e, "text": redact.strip_private(e["text"])} for e in events]
            working.update(store, session_id, wevents, repo)
        except Exception:
            pass
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
