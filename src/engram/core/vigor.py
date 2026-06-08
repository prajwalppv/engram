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

# Access-feedback model (Ebbinghaus, after mem0): the signal that ACTUALLY fires is
# recall ACCESS — a memory surfaced for a query is a relevance vote — with recency
# decay so a once-popular-but-stale memory fades. Explicit used/read are rarer,
# higher-confidence acts that weigh more. This replaces the old "recalled-but-not-
# explicitly-used = noise" model, which depended on signals that never fired in
# practice (used/read were provably 0).
ACCESS_CAP = 50              # diminishing returns on raw access count
ACCESS_HALFLIFE_DAYS = 14.0  # half-life of access RECENCY (distinct from creation-recency)
PRUNE_ACCESS_FLOOR = 1.0     # ephemeral notes with decayed-access below this may be pruned


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


def access_stats(store: Store) -> dict[str, dict]:
    """Per-id access signal from the feedback log: {id: {count, used, read, last}}.
    `count` = recall hits (the signal that actually fires); used/read are rarer,
    higher-confidence acts; `last` = most recent access timestamp (ISO string)."""
    p = store.root / ".state" / "feedback.jsonl"
    out: dict[str, dict] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        kind, ts = ev.get("kind"), ev.get("ts")
        if kind not in ("recall", "used", "read"):
            continue
        for mid in ev.get("ids", []):
            d = out.setdefault(mid, {"count": 0, "used": 0, "read": 0, "last": None})
            if kind == "recall":
                d["count"] += 1
            else:
                d[kind] = d.get(kind, 0) + 1
            if ts and (d["last"] is None or ts > d["last"]):
                d["last"] = ts
    return out


def decayed_access(stat: dict | None, now: datetime.datetime | None = None) -> float:
    """Ebbinghaus memory strength (mem0's model): access frequency with recency
    decay. Recall counts as access; explicit used/read weigh more.
    ``min(eff, CAP) * 0.5^(days_since_last_access / HALFLIFE)``."""
    if not stat:
        return 0.0
    eff = stat.get("count", 0) + 2 * stat.get("used", 0) + stat.get("read", 0)
    if eff <= 0:
        return 0.0
    now = now or datetime.datetime.now()
    days = 0.0
    last = stat.get("last")
    if last:
        try:
            days = max((now - datetime.datetime.fromisoformat(last)).total_seconds() / 86400.0, 0.0)
        except Exception:
            days = 0.0
    return min(eff, ACCESS_CAP) * (0.5 ** (days / ACCESS_HALFLIFE_DAYS))


def recall_boost(stat: dict | None, now: datetime.datetime | None = None) -> float:
    """Bounded [0, 1) recall-feedback boost for ranking — saturating so a popular
    memory can't run away (rich-get-richer guard). ~0.25 at 1 access, ~0.5 at 3."""
    da = decayed_access(stat, now)
    return da / (da + 3.0)


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


def score(entry: MemoryEntry, *, access: float, indeg: int,
          today: datetime.date) -> float:
    """Vigor (apical dominance): how alive/load-bearing a memory is. Reward
    recall-ACCESS strength (recency-decayed frequency, mem0's signal), structural
    in-degree, creation-recency, and type durability. A memory that stops being
    recalled lets its access term decay toward 0 → eligible for bonsai pruning."""
    age = _age_days(entry.frontmatter.get("created"), today)
    half_life = HORIZON_HALFLIFE.get(entry.horizon, HALF_LIFE_DAYS)
    recency = math.exp(-age / half_life)
    durability = TYPE_DURABILITY.get(entry.type, 1.0)
    return (1.5 * math.log1p(max(access, 0.0))   # recall-access strength (decayed)
            + 1.5 * math.log1p(max(indeg, 0))
            + 1.0 * recency
            + durability)


def score_all(store: Store, today: datetime.date | None = None,
              now: datetime.datetime | None = None) -> dict[str, dict]:
    """Vigor + signals for every entry, keyed by rel_path."""
    today = today or datetime.date.today()
    now = now or datetime.datetime.now()
    stats = access_stats(store)
    deg = indegree(store)
    out: dict[str, dict] = {}
    for p in store.iter_entries():
        ent = memory._read_entry(store, p)
        st = stats.get(ent.id, {})
        access = decayed_access(st, now)
        ind = deg.get(fm.sanitize_title(ent.title), 0)
        out[ent.rel_path] = {
            "entry": ent,
            "vigor": round(score(ent, access=access, indeg=ind, today=today), 3),
            "access": round(access, 3),
            "used": st.get("used", 0), "recall": st.get("count", 0),
            "read": st.get("read", 0), "indegree": ind,
            "age_days": _age_days(ent.frontmatter.get("created"), today),
            "horizon": ent.horizon,
            "ephemeral": ent.type in EPHEMERAL_TYPES,
        }
    return out
