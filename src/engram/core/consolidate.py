"""Near-duplicate detection for capture — the noisy-heart fix.

Auto-capture restates the same fact across sessions with slightly different
wording, so the graph slowly fills with near-duplicate nodes (exact-title repeats
are already merged by ``memory.save``; near-dups with a *different* title are not).
This finds the existing node a new (title, body) restates so capture can MERGE into
it (append a dated block) instead of spawning a near-dup.

The decision is a normalized token **Jaccard** — deterministic, backend-free, so
it behaves identically on the text fallback and is testable without a model. When
the semantic backend is active its cosine score widens the net to catch lexically
different paraphrases too. A merge only ever APPENDS, so even a wrong match never
loses content (both texts live on in the node, recoverable).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from . import frontmatter as fm
from . import memory

if TYPE_CHECKING:
    from .models import MemoryEntry
    from .search_backends import SearchBackend
    from .store import Store

_WORD = re.compile(r"[a-z0-9]+")


def _clean_body(body: str) -> str:
    """Drop the heading, dated stamps, and underscore-meta a stored node carries
    (``# Title`` / ``**2026-06-07**`` / ``_…_``) so the similarity sees only the
    substantive content — those tokens (the title words, dates) otherwise dilute it."""
    out = []
    for ln in (body or "").splitlines():
        s = ln.strip()
        if not s or s.startswith(("#", "_")) or (s.startswith("**") and s.endswith("**")):
            continue
        out.append(s)
    return " ".join(out)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if len(w) > 2}


def jaccard(a: set[str], b: set[str]) -> float:
    """Token-set overlap in [0, 1]: |A∩B| / |A∪B|."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def near_duplicate(store: "Store", backend: "SearchBackend | None", *,
                   title: str, body: str, type_: str | None = None,
                   lex_threshold: float = 0.7, sem_threshold: float = 0.88,
                   limit: int = 5) -> "MemoryEntry | None":
    """Return an existing entry that ``(title, body)`` restates, else None.

    Same-type only (we never merge a Gotcha into a Decision). Exact-title matches
    are skipped — those are ``memory.save``'s append path, not a near-dup.
    """
    text = f"{title}\n\n{body}"
    try:
        cands = backend.find_similar(text, limit=limit) if backend else []
    except Exception:
        cands = []
    is_semantic = backend.__class__.__name__ == "SemanticSearchBackend"
    # Compare on BODY tokens, not title+body: titles vary far more than content for
    # a restatement ("Rate limit API" vs "Throttle the API"), and would dilute the
    # overlap. The body carries the fact.
    new_tok = _tokens(_clean_body(body))
    want_title = fm.sanitize_title((title or "").strip())
    for h in cands:
        try:
            ent = memory.read(store, h.rel_path)
        except Exception:
            continue
        if type_ and ent.type != type_:
            continue
        if fm.sanitize_title((ent.title or "").strip()) == want_title:
            continue  # exact-title restatement is handled by memory.save
        lex = jaccard(new_tok, _tokens(_clean_body(ent.body)))
        sem_ok = is_semantic and (h.score or 0.0) >= sem_threshold
        if lex >= lex_threshold or sem_ok:
            return ent
    return None
