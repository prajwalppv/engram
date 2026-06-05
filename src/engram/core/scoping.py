"""Scope ladder + precedence — Phase 2 of memory horizons.

A memory's ``scope`` says WHERE it applies, from broad to narrow:

    global → role → area → repo → session

Two jobs:
  * **Applicability** — recall only surfaces memories that apply in the current
    context, so repo-A's conventions never leak into repo-B. Unknown context
    dimensions never exclude (we only filter OUT clearly wrong-context memories).
  * **Precedence** — "more specific wins": a repo-scoped rule outranks a global
    one. ``rank`` gives the ordering; an explicit ``supersedes`` list lets a memory
    retire ones it replaces.

This is the *applicability* axis. It is deliberately separate from the dormant
export/visibility axis (private | team), which lives on ``MemoryEntry.visibility``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MemoryEntry

# broad → narrow; list index == precedence rank (higher = more specific = wins)
LADDER = ["global", "role", "area", "repo", "session"]
_RANK = {s: i for i, s in enumerate(LADDER)}


def is_ladder(scope: str | None) -> bool:
    return (scope or "").strip().lower() in _RANK


def normalize(scope: str | None, *, repo: str | None = None) -> str:
    s = (scope or "").strip().lower()
    return s if s in _RANK else ("repo" if repo else "global")


def rank(scope: str | None) -> int:
    return _RANK.get((scope or "").strip().lower(), 0)


def default_scope(*, horizon: str = "semantic", repo: str | None = None) -> str:
    if horizon == "preference":
        return "global"
    if horizon == "working":
        return "session"
    return "repo" if repo else "global"


def applies(entry: "MemoryEntry", *, repo: str | None = None, role: str | None = None,
            area: str | None = None, session: str | None = None) -> bool:
    """Does ``entry`` apply in this context? A None context dimension is treated as
    'unknown' and never excludes — only a *mismatch* on a known dimension does."""
    s = (entry.scope or "global").lower()
    if s == "global":
        return True
    if s == "role":
        return role is None or (entry.role or "").lower() == role.lower()
    if s == "area":
        return area is None or (entry.area or "") == area
    if s == "repo":
        return repo is None or (entry.repo or "") == repo
    if s == "session":
        sess = str(entry.frontmatter.get("source_session") or "")
        return session is None or sess == session
    return True


def superseded_titles(entries: list["MemoryEntry"]) -> set[str]:
    """Titles retired by some other entry's ``supersedes`` list (sanitized)."""
    from . import frontmatter as fm
    out: set[str] = set()
    for e in entries:
        for t in (e.supersedes or []):
            st = fm.sanitize_title(str(t))
            if st:
                out.add(st)
    return out
