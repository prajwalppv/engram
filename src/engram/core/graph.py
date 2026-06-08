"""Wikilink graph over memory entries: outgoing links, backlinks, neighborhood.

Neighborhood is what makes recall graph-aware — pull a node AND its linked
context, not just an isolated hit.
"""
from __future__ import annotations

from . import frontmatter as fm
from . import memory
from .errors import MemoryNotFoundError
from .models import LinkRef
from .store import Store


def outgoing_links(store: Store, identifier: str) -> list[LinkRef]:
    ent = memory.read(store, identifier)
    seen, out = set(), []
    def add(t, alias=None):
        k = (t or "").strip()
        if k and k not in seen:
            seen.add(k)
            out.append(LinkRef(target=k, alias=alias, source_rel_path=ent.rel_path))
    for t in ent.links:
        add(t)
    for t, alias in fm.iter_wikilinks(ent.body):
        add(t, alias)
    return out


def backlinks(store: Store, identifier: str) -> list[LinkRef]:
    path = memory.find_path(store, identifier)
    if path is None:
        raise MemoryNotFoundError(f"No memory matched '{identifier}'.")
    target = fm.sanitize_title(path.stem)
    refs = []
    for p in store.iter_entries():
        if p == path:
            continue
        text = store.read(p)
        for t, alias in fm.iter_wikilinks(text):
            if fm.sanitize_title(t) == target:
                refs.append(LinkRef(target=target, alias=alias, source_rel_path=store.relpath(p)))
                break
    return refs


def provenance(store: Store, identifier: str) -> dict:
    """Why is this memory here? Composes its ORIGIN (when, which session, which
    role/scope), its TEMPORAL lineage (what it retired, and whether/when it was
    itself retired), and its GRAPH context (links + backlinks). Powers /engram:why."""
    ent = memory.read(store, identifier)
    fmd = ent.frontmatter
    superseded_by = fmd.get("superseded_by")
    def _name(rel: str | None) -> str:
        rel = rel or ""
        return fm.sanitize_title(rel.rsplit("/", 1)[-1][:-3]) if rel.endswith(".md") else rel
    return {
        "id": ent.id,
        "title": ent.title,
        "type": ent.type,
        "horizon": ent.horizon,
        "scope": ent.scope,
        "repo": ent.repo,
        "role": ent.role,
        "created": str(fmd.get("created") or "") or None,
        "source_session": str(fmd.get("source_session") or "") or None,
        "supersedes": list(ent.supersedes),                      # facts THIS one retired
        "superseded_by": str(superseded_by) if superseded_by else None,
        "superseded_on": str(fmd.get("superseded_on") or "") or None,
        "retired": bool(superseded_by),                          # is this the stale one now?
        "links": [l.target for l in outgoing_links(store, identifier)],
        "backlinks": [_name(b.source_rel_path) for b in backlinks(store, identifier)],
    }


def neighborhood(store: Store, identifier: str, *, depth: int = 1) -> list[str]:
    """Titles of memories within ``depth`` hops (out + back) of the given one."""
    frontier = {fm.sanitize_title(identifier)}
    seen = set(frontier)
    result = set()
    for _ in range(max(depth, 0)):
        nxt = set()
        for ident in frontier:
            try:
                for l in outgoing_links(store, ident):
                    nxt.add(fm.sanitize_title(l.target))
                for b in backlinks(store, ident):
                    src = b.source_rel_path or ""
                    nxt.add(fm.sanitize_title(src.rsplit("/", 1)[-1][:-3]))
            except MemoryNotFoundError:
                continue
        nxt -= seen
        result |= nxt
        seen |= nxt
        frontier = nxt
    return sorted(t for t in result if t)
