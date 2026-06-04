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
    items = summarizer.summarize_session(
        store, settings, transcript_text, role=role, repo=repo)
    results = []
    for it in items:
        res = memory.save(
            store, role, type_=it["type"], title=it["title"], body=it["body"],
            repo=repo, tags=it.get("tags"), links=it.get("links"),
            session_id=session_id, search_backend=search_backend,
        )
        results.append(res)
    return results
