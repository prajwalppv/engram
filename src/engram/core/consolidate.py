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


def related(store: "Store", backend: "SearchBackend | None", *, title: str, body: str,
            exclude_titles: tuple[str, ...] = (), max_links: int = 3,
            lex_min: float = 0.25, lex_max: float = 0.7,
            sem_min: float = 0.55, sem_max: float = 0.88, limit: int = 8) -> list[str]:
    """Titles of existing memories a new (title, body) is RELATED to — the band
    *below* near-duplicate (those merge) but above unrelated. Cross-type on purpose:
    a Decision and the Gotcha about the same thing should link. Auto-linking these at
    capture turns a graph of orphans into a load-bearing one (graph-expansion recall).
    """
    text = f"{title}\n\n{body}"
    try:
        cands = backend.find_similar(text, limit=limit) if backend else []
    except Exception:
        cands = []
    is_semantic = backend.__class__.__name__ == "SemanticSearchBackend"
    new_tok = _tokens(_clean_body(body))
    excl = {fm.sanitize_title(t) for t in exclude_titles}
    excl.add(fm.sanitize_title((title or "").strip()))
    out: list[str] = []
    for h in cands:
        try:
            ent = memory.read(store, h.rel_path)
        except Exception:
            continue
        st = fm.sanitize_title((ent.title or "").strip())
        if st in excl:
            continue
        lex = jaccard(new_tok, _tokens(_clean_body(ent.body)))
        sem = (h.score or 0.0) if is_semantic else 0.0
        if (lex_min <= lex < lex_max) or (is_semantic and sem_min <= sem < sem_max):
            out.append(ent.title)
            excl.add(st)
            if len(out) >= max_links:
                break
    return out


# --------------------------------------------------------------- live-data backfill
_VERSION_RE = re.compile(r"^v?\d+(\.\d+)+$")


def _add_links(store: "Store", rel_path: str, new_titles: list[str]) -> int:
    """Add wikilinks to an existing node's frontmatter WITHOUT touching its body
    (mirrors memory.save's append link-merge). Returns how many new links were added."""
    meta, body = fm.parse(store.read(rel_path))
    cur = meta.get("links")
    have: set[str] = set()
    seq = fm.CommentedSeq() if cur is None else cur
    if cur is not None:
        for it in (cur if isinstance(cur, list) else [cur]):
            t = fm.link_target(str(it))
            if t:
                have.add(fm.sanitize_title(t))
    else:
        meta["links"] = seq
    added = 0
    for t in new_titles:
        if t and fm.sanitize_title(t) not in have:
            seq.append(fm.wikilink(t))
            have.add(fm.sanitize_title(t))
            added += 1
    if added:
        store.write(rel_path, fm.dump(meta, body), snapshot_message=f"backfill links {rel_path}")
    return added


def backfill_links(store: "Store", backend: "SearchBackend | None", *,
                   max_links: int = 3, dry_run: bool = True) -> dict:
    """Retroactively link existing memories to their related neighbors — heals a
    store full of orphans (graph-expansion recall needs edges). Additive and
    idempotent: never removes a link, never re-adds one. ``dry_run`` reports only."""
    ents = [memory._read_entry(store, p) for p in store.iter_entries()]
    report = {"scanned": len(ents), "nodes_linked": 0, "links_added": 0,
              "dry_run": dry_run, "examples": []}
    for e in ents:
        existing = list(e.links or [])
        need = max_links - len(existing)
        if need <= 0:
            continue  # already at the cap → CONVERGENT (repeat runs add nothing)
        rel = related(store, backend, title=e.title, body=e.body,
                      exclude_titles=tuple(existing), max_links=need)
        if not rel:
            continue
        added = len(rel) if dry_run else _add_links(store, e.rel_path, rel)
        if added:
            report["nodes_linked"] += 1
            report["links_added"] += added
            if len(report["examples"]) < 8:
                report["examples"].append({"title": e.title[:48], "links": rel})
    return report


def rescope_repo(store: "Store", *, match, to: str | None, dry_run: bool = True) -> dict:
    """Relabel ``repo`` for entries where ``match(repo)`` is true → ``to``. For
    correcting cwd-derived mislabels (engram work captured under the wrong cwd) and
    clearing version-string garbage. ``match`` is a callable repo:str -> bool."""
    report = {"changed": 0, "dry_run": dry_run, "to": to, "examples": []}
    for p in store.iter_entries():
        e = memory._read_entry(store, p)
        if e.repo and match(str(e.repo)):
            report["changed"] += 1
            if len(report["examples"]) < 8:
                report["examples"].append({"title": e.title[:48], "from": str(e.repo), "to": to})
            if not dry_run:
                meta, body = fm.parse(store.read(e.rel_path))
                meta["repo"] = to
                store.write(e.rel_path, fm.dump(meta, body),
                            snapshot_message=f"rescope repo {e.rel_path}")
    return report


def is_version_repo(repo: str) -> bool:
    return bool(_VERSION_RE.match(repo or ""))


def cap_links(store: "Store", *, max_links: int = 4, dry_run: bool = True) -> dict:
    """Trim any node with more than ``max_links`` links down to the first that many
    (preserves originals + earliest related). Repairs over-dense graphs."""
    report = {"trimmed": 0, "nodes": 0, "dry_run": dry_run}
    for p in store.iter_entries():
        e = memory._read_entry(store, p)
        if not e.links or len(e.links) <= max_links:
            continue
        keep = e.links[:max_links]
        report["nodes"] += 1
        report["trimmed"] += len(e.links) - len(keep)
        if not dry_run:
            meta, body = fm.parse(store.read(e.rel_path))
            seq = fm.CommentedSeq()
            for l in keep:
                seq.append(fm.wikilink(l))
            meta["links"] = seq
            store.write(e.rel_path, fm.dump(meta, body),
                        snapshot_message=f"cap links {e.rel_path}")
    return report


def prune_dangling_links(store: "Store", *, dry_run: bool = True) -> dict:
    """Remove wikilinks pointing to notes that no longer exist (broken graph edges
    from renames/forgets). Harmless at recall (graph-expansion skips them) but untidy."""
    ents = [memory._read_entry(store, p) for p in store.iter_entries()]
    titles = {fm.sanitize_title(e.title) for e in ents}
    report = {"removed": 0, "dry_run": dry_run, "examples": []}
    for e in ents:
        if not e.links:
            continue
        keep = [l for l in e.links if fm.sanitize_title(l) in titles]
        if len(keep) == len(e.links):
            continue
        removed = [l for l in e.links if fm.sanitize_title(l) not in titles]
        report["removed"] += len(removed)
        if len(report["examples"]) < 8:
            report["examples"].append({"title": e.title[:40], "removed": removed})
        if not dry_run:
            meta, body = fm.parse(store.read(e.rel_path))
            if keep:
                seq = fm.CommentedSeq()
                for l in keep:
                    seq.append(fm.wikilink(l))
                meta["links"] = seq
            else:
                meta["links"] = None
            store.write(e.rel_path, fm.dump(meta, body),
                        snapshot_message=f"prune dangling links {e.rel_path}")
    return report
