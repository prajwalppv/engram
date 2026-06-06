"""Recall ranking — turn "most similar vector" into "the right memory".

Three ideas layered over the raw semantic backend:
  1. HYBRID retrieval — fuse the dense (embedding) ranking with a lexical
     (term-overlap) ranking via Reciprocal Rank Fusion. Lexical catches the exact
     tokens embeddings are weak at (error codes, function names, flags, IDs);
     fusion needs no score-scale calibration.
  2. LIGHT boosts — nudge by recency, scope precedence (more-specific wins), and
     type durability. Relevance still dominates; these break ties sensibly.
  3. GRAPH expansion — pull the linked neighbors of the strongest hits (discounted),
     so related memory surfaces too (the multi-hop value of the wikilink graph).

All cheap and local. `hybrid=False`/`expand_graph=False` fall back to plain fusion.
"""
from __future__ import annotations

import datetime
import math
from typing import TYPE_CHECKING

from . import scoping
from .models import MemoryHit

if TYPE_CHECKING:
    from .search_backends import SearchBackend
    from .store import Store

RRF_K = 60               # standard Reciprocal Rank Fusion constant
# Dense (embedding) recall is the primary signal; lexical AUGMENTS it (recovers
# exact-term hits the embedding misses) but is weighted lower so it can't overturn
# a clear dense winner. Measured: symmetric fusion hurt paraphrase queries.
DENSE_W = 1.0
LEX_W = 0.5
# Boosts only break near-ties — kept tiny so relevance dominates (measured: large
# boosts reordered correct hits and dropped MRR).
W_RECENCY = 0.04         # max fractional uplift from recency
W_SCOPE = 0.04           # max uplift from scope specificity
W_TYPE = 0.02            # max uplift from type durability
GRAPH_DECAY = 0.5        # neighbors inherit this fraction of a parent's score
HALF_LIFE_DAYS = 45.0

_DURABILITY = {
    "Preference": 1.0, "Decision": 0.8, "Constraint": 0.8, "Gotcha": 0.8,
    "Convention": 0.7, "Procedure": 0.7, "Requirement": 0.7, "Tradeoff": 0.6,
    "Note": 0.4, "SessionDigest": 0.3, "SessionSummary": 0.1,
}


def _recency(created, today: datetime.date) -> float:
    try:
        d = datetime.date.fromisoformat(str(created)[:10])
        return math.exp(-max((today - d).days, 0) / HALF_LIFE_DAYS)
    except Exception:
        return 0.0


def _rrf(weighted_lists: list[tuple[list[str], float]]) -> dict[str, float]:
    """Weighted Reciprocal Rank Fusion: score(item) = Σ w / (RRF_K + rank)."""
    out: dict[str, float] = {}
    for lst, w in weighted_lists:
        for r, rel in enumerate(lst):
            out[rel] = out.get(rel, 0.0) + w / (RRF_K + r + 1)
    return out


def hybrid_recall(store: "Store", search_backend: "SearchBackend", query: str, *,
                  repo: str | None = None, role: str | None = None,
                  area: str | None = None, session: str | None = None,
                  type_: str | None = None, limit: int = 8,
                  hybrid: bool = True, expand_graph: bool = True) -> list[MemoryHit]:
    from . import frontmatter as fm
    from . import memory
    from .search_backends import TextSearchBackend

    pool = max(limit * 5, 25)
    dense = search_backend.query(query, limit=pool)
    weighted = [([h.rel_path for h in dense], DENSE_W)]
    if hybrid:
        lexical = TextSearchBackend(store).query(query, limit=pool)
        weighted.append(([h.rel_path for h in lexical], LEX_W))
    fused = _rrf(weighted)
    if not fused:
        return []

    # Read each candidate once; drop superseded + non-applicable + wrong type.
    cand = {}
    for rel in fused:
        try:
            cand[rel] = memory.read(store, rel)
        except Exception:
            continue
    retired = scoping.superseded_titles(list(cand.values()))
    today = datetime.date.today()

    scored: dict[str, tuple[float, object]] = {}
    for rel, ent in cand.items():
        if fm.sanitize_title(ent.title) in retired:
            continue
        if not scoping.applies(ent, repo=repo, role=role, area=area, session=session):
            continue
        if type_ and ent.type.lower() != type_.lower():
            continue
        base = fused[rel]
        boost = (W_RECENCY * _recency(ent.frontmatter.get("created"), today)
                 + W_SCOPE * (scoping.rank(ent.scope) / 4.0)
                 + W_TYPE * _DURABILITY.get(ent.type, 0.4))
        scored[rel] = (base * (1.0 + boost), ent)

    # Graph expansion: linked neighbors of the strongest hits (discounted).
    if expand_graph and scored:
        top = sorted(scored.items(), key=lambda kv: kv[1][0], reverse=True)[:3]
        for _, (sc, ent) in top:
            for nbr in (ent.links or []):
                try:
                    n = memory.read(store, nbr)
                except Exception:
                    continue
                if n.rel_path in scored:
                    continue
                if not scoping.applies(n, repo=repo, role=role, area=area, session=session):
                    continue
                if type_ and n.type.lower() != type_.lower():
                    continue
                scored[n.rel_path] = (sc * GRAPH_DECAY, n)

    ranked = sorted(scored.values(), key=lambda se: se[0], reverse=True)[:limit]
    return [MemoryHit(id=e.id, rel_path=e.rel_path, title=e.title, type=e.type,
                      repo=e.repo, score=round(float(s), 6)) for s, e in ranked]
