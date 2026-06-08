"""Bonsai pruning — keep memory razor-sharp by compressing stale growth, never
hard-deleting, bounded per cycle, and measured every time.

Policy (v1; the deep-research findings tune these defaults, not the structure):
  * Vigor scoring (apical dominance) ranks every node — see vigor.py.
  * RAMIFICATION (consolidate, don't delete): stale, low-vigor, unreferenced,
    unused *session* leaves are folded — per repo — into one denser SessionDigest
    node. Knowledge is compressed, not lost.
  * JIN/SHARI (meaningful deadwood): durable types (Decision/Gotcha/Convention…)
    are never auto-pruned; pruned items are ARCHIVED (recoverable), never deleted.
  * ⅓-RULE: at most ``prune_max_fraction`` of nodes touched per cycle; dry-run default.
  * MEASUREMENT: before/after metrics + a history log + a "resurrection" signal
    (restored items = a pruning mistake) feed the self-improvement loop.
"""
from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from . import memory, vigor, working
from . import roles as role_engine
from .store import Store

if TYPE_CHECKING:
    from ..config import Settings
    from .search_backends import SearchBackend

ARCHIVE_DIR = ".archive"
HISTORY_REL = ".state/prune-history.jsonl"


# ---------------------------------------------------------------- metrics
def metrics(store: Store, scored: dict | None = None) -> dict:
    scored = scored if scored is not None else vigor.score_all(store)
    total = len(scored)
    by_type: dict[str, int] = {}
    by_horizon: dict[str, int] = {}
    ephemeral = orphans = 0
    vig_sum = 0.0
    for d in scored.values():
        e = d["entry"]
        by_type[e.type] = by_type.get(e.type, 0) + 1
        by_horizon[e.horizon] = by_horizon.get(e.horizon, 0) + 1
        if d["ephemeral"]:
            ephemeral += 1
        if d["indegree"] == 0 and not e.links:
            orphans += 1
        vig_sum += d["vigor"]
    return {
        "total": total, "by_type": by_type, "by_horizon": by_horizon,
        "ephemeral": ephemeral, "orphans": orphans,
        "avg_vigor": round(vig_sum / total, 3) if total else 0.0,
    }


# ---------------------------------------------------------------- analyze
def _effective_fraction(store: Store, settings: "Settings") -> float:
    """Honor the self-tuned prune fraction (written by optimize.tune_prune_params)."""
    p = store.root / ".state" / "tuned.json"
    if p.exists():
        try:
            return float(json.loads(p.read_text(encoding="utf-8")).get(
                "prune_max_fraction", settings.prune_max_fraction))
        except Exception:
            pass
    return settings.prune_max_fraction


def analyze(store: Store, settings: "Settings") -> dict:
    scored = vigor.score_all(store)
    total = len(scored)
    # staleness = ephemeral + old + unused + unreferenced; lowest vigor first.
    stale = [d for d in scored.values()
             if d["ephemeral"] and d["age_days"] >= settings.prune_min_age_days
             and d["access"] < vigor.PRUNE_ACCESS_FLOOR and d["indegree"] == 0
             and d["entry"].horizon != "preference"]  # preferences are lifelines
    stale.sort(key=lambda d: d["vigor"])
    cap = max(1, int(total * _effective_fraction(store, settings)))
    stale = stale[:cap]

    groups: dict[str, list] = {}
    for d in stale:
        groups.setdefault(d["entry"].repo or "general", []).append(d)

    plan = []
    for repo, ds in groups.items():
        if len(ds) >= settings.prune_min_cluster:
            plan.append({
                "action": "consolidate", "repo": repo,
                "rel_paths": [d["entry"].rel_path for d in ds],
                "titles": [d["entry"].title for d in ds],
            })
    return {
        "metrics_before": metrics(store, scored),
        "plan": plan,
        "candidate_count": sum(len(p["rel_paths"]) for p in plan),
        "cap": cap,
    }


# ---------------------------------------------------------------- apply helpers
def _archive(store: Store, rel: str, stamp: str) -> None:
    src = store.resolve(rel)
    dest = store.root / ARCHIVE_DIR / stamp / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def _first_line(body: str) -> str:
    for ln in body.splitlines():
        s = ln.strip()
        if s and not s.startswith("#") and not s.startswith("_") and not s.startswith("**"):
            return s
    return ""


def _log_history(store: Store, record: dict) -> None:
    p = store.root / HISTORY_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), **record}
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- prune
def prune(store: Store, settings: "Settings",
          search_backend: "SearchBackend | None" = None, *,
          dry_run: bool = True) -> dict:
    a = analyze(store, settings)
    working_ttl = getattr(settings, "working_ttl_hours", 18)
    if dry_run:
        return {**a, "dry_run": True, "applied": False,
                "working_expirable": working.expired_count(store, working_ttl)}
    # Apply: per-horizon working-memory TTL cleanup runs on every apply, even when
    # there's no note-consolidation plan.
    working_pruned = working.prune_expired(store, working_ttl)
    if not a["plan"]:
        return {**a, "dry_run": False, "applied": True, "archived": 0,
                "consolidated": [], "working_pruned": working_pruned}

    role = role_engine.current_role(store, settings.role)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    archived, consolidated = 0, []

    for grp in a["plan"]:
        repo = grp["repo"]
        # build the consolidated digest body from the originals
        bullets = []
        for rel in grp["rel_paths"]:
            try:
                ent = memory.read(store, rel)
            except Exception:
                continue
            created = str(ent.frontmatter.get("created") or "")
            bullets.append(f"- **{created}** {ent.title}: {_first_line(ent.body)[:160]}")
        if not bullets:
            continue
        digest_body = (f"Folded {len(bullets)} stale session note(s) for `{repo}` "
                       f"on {stamp[:8]}.\n\n" + "\n".join(bullets))
        memory.save(store, role, type_="SessionDigest",
                    title=f"Consolidated Sessions — {repo}", body=digest_body,
                    repo=repo, search_backend=search_backend)
        # archive (recoverable) + drop from index
        for rel in grp["rel_paths"]:
            try:
                _archive(store, rel, stamp)
                if search_backend is not None:
                    search_backend.remove(rel)
                archived += 1
            except Exception:
                continue
        consolidated.append({"repo": repo, "folded": len(grp["rel_paths"])})

    after = metrics(store)
    report = {
        "dry_run": False, "applied": True,
        "metrics_before": a["metrics_before"], "metrics_after": after,
        "archived": archived, "consolidated": consolidated,
        "working_pruned": working_pruned,
        "archive_stamp": stamp,
    }
    _log_history(store, {k: report[k] for k in
                         ("metrics_before", "metrics_after", "archived", "consolidated")})
    return report


# ---------------------------------------------------------------- restore + measure
def restore(store: Store, identifier: str) -> dict:
    """Un-archive a pruned memory (also logs a 'resurrection' = pruning mistake)."""
    root = store.root / ARCHIVE_DIR
    want = identifier.strip()
    if want.endswith(".md"):
        want = want[:-3]
    match = None
    if root.exists():
        for p in root.rglob("*.md"):
            if p.stem == want.rsplit("/", 1)[-1]:
                match = p
                break
    if match is None:
        return {"restored": None, "reason": "not found in archive"}
    rel = match.relative_to(root).as_posix().split("/", 1)[-1]  # strip <stamp>/
    dest = store.resolve(rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(match), str(dest))
    _log_history(store, {"resurrection": rel})
    return {"restored": rel}


def effectiveness(store: Store) -> dict:
    """Read prune history → trend signals for the self-improvement loop."""
    p = store.root / HISTORY_REL
    cycles, resurrections = [], 0
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("resurrection"):
                resurrections += 1
            elif "metrics_after" in r:
                cycles.append(r)
    deltas = []
    for r in cycles:
        b, af = r.get("metrics_before", {}), r.get("metrics_after", {})
        deltas.append({
            "ts": r.get("ts"),
            "nodes": f'{b.get("total", "?")}→{af.get("total", "?")}',
            "ephemeral": f'{b.get("ephemeral", "?")}→{af.get("ephemeral", "?")}',
            "avg_vigor": f'{b.get("avg_vigor", "?")}→{af.get("avg_vigor", "?")}',
            "archived": r.get("archived", 0),
        })
    return {
        "cycles": len(cycles),
        "resurrections": resurrections,
        "resurrection_rate": round(resurrections / sum(c.get("archived", 0) for c in cycles), 3)
        if cycles and sum(c.get("archived", 0) for c in cycles) else 0.0,
        "history": deltas[-10:],
        "note": ("resurrection_rate is the key quality signal — archived memories "
                 "later restored were pruned by mistake; drive it toward 0."),
    }
