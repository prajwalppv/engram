"""Vigor scoring — a node's "energy" (apical dominance).

Vigor blends the signals that mean "this memory is alive and load-bearing":
recall-usage (feedback), recency, backlink in-degree (structural importance), and
type durability (a Decision is trunk; a SessionSummary is a leaf). Low-vigor,
old, unreferenced leaves are what pruning compresses; high-vigor trunk is kept.
"""
from __future__ import annotations

import datetime
import json
import math
from pathlib import Path

from . import frontmatter as fm
from . import memory
from .models import MemoryEntry
from .store import Store

# Type durability: how trunk-like a node is (higher = keep longer).
TYPE_DURABILITY = {
    "Preference": 3.0,  # lifeline — also guarded out of pruning entirely
    "Procedure": 2.5,   # runbooks: durable, supersede-with-history (never auto-pruned)
    "Decision": 2.0, "Gotcha": 2.0, "Convention": 2.0, "Requirement": 2.0,
    "Person": 2.0, "Tradeoff": 1.5, "Service": 1.5, "Commitment": 1.5,
    "Process": 1.5, "SessionDigest": 1.2, "Note": 1.0, "SessionSummary": 0.4,
}
EPHEMERAL_TYPES = {"SessionSummary"}
HALF_LIFE_DAYS = 30.0

# Per-horizon recency half-life (days): how fast a memory's recency signal decays.
# Working scratch fades in a day; preferences effectively never. This is what makes
# pruning horizon-aware — durable horizons keep their vigor far longer.
HORIZON_HALFLIFE = {
    "working": 1.0, "episodic": 21.0, "semantic": 45.0,
    "procedural": 120.0, "preference": 3650.0,
}


def feedback_counts(store: Store) -> dict[str, dict[str, int]]:
    """Per-memory-id usage counts from the feedback log: {id: {recall, used, read}}.

    recall = surfaced in a recall; used = explicitly marked useful; read = body
    fetched after the compact index (an implicit usefulness vote)."""
    p = store.root / ".state" / "feedback.jsonl"
    out: dict[str, dict[str, int]] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        kind = ev.get("kind")
        if kind not in ("recall", "used", "read"):
            continue
        for mid in ev.get("ids", []):
            out.setdefault(mid, {"recall": 0, "used": 0, "read": 0})
            out[mid][kind] = out[mid].get(kind, 0) + 1
    return out


def usefulness(used: int, read: int, recall: int) -> float:
    """Demonstrated-usefulness ratio in [0, 1]: of the times a memory was surfaced,
    how often was it actually acted on (explicitly used, or its body fetched)?
    Smoothed so a single recall doesn't swing it. read counts at half an explicit
    use. A memory recalled often but never acted on → ~0 (noise)."""
    acted = used + 0.5 * max(read, 0)
    return min(acted / (max(recall, 0) + 1.0), 1.0)


def indegree(store: Store) -> dict[str, int]:
    """Backlink in-degree per node title (structural importance)."""
    deg: dict[str, int] = {}
    for p in store.iter_entries():
        text = store.read(p)
        seen = set()
        for t, _ in fm.iter_wikilinks(text):
            st = fm.sanitize_title(t)
            if st and st not in seen:
                seen.add(st)
                deg[st] = deg.get(st, 0) + 1
    return deg


def _age_days(created: str | None, today: datetime.date) -> int:
    if not created:
        return 9999
    try:
        d = datetime.date.fromisoformat(str(created)[:10])
        return max((today - d).days, 0)
    except Exception:
        return 9999


def score(entry: MemoryEntry, *, used: int, recall: int, indeg: int,
          today: datetime.date, read: int = 0) -> float:
    age = _age_days(entry.frontmatter.get("created"), today)
    half_life = HORIZON_HALFLIFE.get(entry.horizon, HALF_LIFE_DAYS)
    recency = math.exp(-age / half_life)
    durability = TYPE_DURABILITY.get(entry.type, 1.0)
    # Reward DEMONSTRATED usefulness (explicit use + body fetch), and DECAY noise
    # (surfaced repeatedly but never acted on). Previously raw recall was rewarded,
    # which protected recalled-but-never-used noise from pruning — backwards.
    acted = used + 0.5 * max(read, 0)
    noise = max(recall - used - read, 0)
    return (2.0 * acted
            + 1.5 * math.log1p(max(indeg, 0))
            + 1.0 * recency
            + durability
            - 0.5 * math.log1p(noise))


def score_all(store: Store, today: datetime.date | None = None) -> dict[str, dict]:
    """Vigor + signals for every entry, keyed by rel_path."""
    today = today or datetime.date.today()
    fb = feedback_counts(store)
    deg = indegree(store)
    out: dict[str, dict] = {}
    for p in store.iter_entries():
        ent = memory._read_entry(store, p)
        c = fb.get(ent.id, {})
        used, recall, read = c.get("used", 0), c.get("recall", 0), c.get("read", 0)
        ind = deg.get(fm.sanitize_title(ent.title), 0)
        out[ent.rel_path] = {
            "entry": ent,
            "vigor": round(score(ent, used=used, recall=recall, read=read,
                                 indeg=ind, today=today), 3),
            "used": used, "recall": recall, "read": read, "indegree": ind,
            "usefulness": round(usefulness(used, read, recall), 3),
            "age_days": _age_days(ent.frontmatter.get("created"), today),
            "horizon": ent.horizon,
            "ephemeral": ent.type in EPHEMERAL_TYPES,
        }
    return out
