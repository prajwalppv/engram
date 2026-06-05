"""Memory entries = graph nodes persisted as markdown. Save / recall / read.

Memory ACCUMULATES: saving to an existing title appends a dated block rather than
overwriting (a journey-preservation value). Every
entry carries a ``scope`` (default ``private``) — the dormant seam for a future
opt-in team export.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import frontmatter as fm
from .errors import MemoryNotFoundError
from .models import MemoryEntry, MemoryHit, SaveResult
from .store import Store

if TYPE_CHECKING:
    from ..roles.base import Role
    from .search_backends import SearchBackend


def _today() -> str:
    return datetime.date.today().isoformat()


def _id_for(folder: str, title: str) -> str:
    t = fm.sanitize_title(title)
    return f"{folder}/{t}" if folder else t


def _read_entry(store: Store, path: Path) -> MemoryEntry:
    text = store.read(path)
    meta, body = fm.parse(text)
    rel = store.relpath(path)
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    title = str(meta.get("title") or Path(rel).stem)
    links = []
    raw_links = meta.get("links")
    if raw_links:
        for item in (raw_links if isinstance(raw_links, list) else [raw_links]):
            tgt = fm.link_target(str(item))
            if tgt:
                links.append(tgt)
    tags = meta.get("tags") or []
    type_str = str(meta.get("type") or folder or "Memory")
    default_horizon = {"SessionSummary": "episodic", "SessionDigest": "episodic",
                       "Preference": "preference"}.get(type_str, "semantic")
    return MemoryEntry(
        id=str(meta.get("id") or _id_for(folder, title)),
        rel_path=rel,
        type=type_str,
        title=title,
        body=body,
        horizon=str(meta.get("horizon") or default_horizon),
        scope=str(meta.get("scope") or "private"),
        repo=(str(meta["repo"]) if meta.get("repo") else None),
        role=(str(meta["role"]) if meta.get("role") else None),
        tags=[str(t) for t in (tags if isinstance(tags, list) else [tags])],
        links=links,
        frontmatter={k: (str(v) if not isinstance(v, (list, dict, int, float, bool, type(None))) else v)
                     for k, v in dict(meta).items()},
    )


def find_path(store: Store, identifier: str) -> Path | None:
    ident = identifier.strip()
    if ident.endswith(".md") or "/" in ident:
        # relpath or id (id == relpath without .md)
        cand = store.resolve(ident if ident.endswith(".md") else ident + ".md")
        if store.backend.exists(cand):
            return cand
    want = fm.sanitize_title(ident)
    for p in store.iter_entries():
        if fm.sanitize_title(p.stem) == want:
            return p
    return None


def read(store: Store, identifier: str) -> MemoryEntry:
    p = find_path(store, identifier)
    if p is None:
        raise MemoryNotFoundError(f"No memory matched '{identifier}'.")
    return _read_entry(store, p)


def save(
    store: Store,
    role: "Role",
    *,
    type_: str,
    title: str,
    body: str,
    repo: str | None = None,
    tags: list[str] | None = None,
    links: list[str] | None = None,
    scope: str = "private",
    horizon: str = "semantic",
    session_id: str | None = None,
    search_backend: "SearchBackend | None" = None,
) -> SaveResult:
    """Create a memory node, or append a dated block if its title already exists."""
    title = title.strip()
    folder = role.folder_for(type_)
    existing = find_path(store, title)

    if existing is not None:
        meta, old_body = fm.parse(store.read(existing))
        stamp = _today() + (f" · session {session_id}" if session_id else "")
        new_body = old_body.rstrip() + f"\n\n**{stamp}**\n\n{body.rstrip()}\n"
        # merge any new links into frontmatter
        if links:
            cur = meta.get("links")
            have = set()
            seq = fm.CommentedSeq() if cur is None else cur
            if cur is not None:
                for it in (cur if isinstance(cur, list) else [cur]):
                    t = fm.link_target(str(it))
                    if t:
                        have.add(fm.sanitize_title(t))
            else:
                meta["links"] = seq
            for l in links:
                if fm.sanitize_title(l) not in have:
                    seq.append(fm.wikilink(l))
        content = fm.dump(meta, new_body)
        rel = store.relpath(existing)
        backup = store.write(rel, content, snapshot_message=f"append {rel}")
        ent = _read_entry(store, existing)
        if search_backend is not None:
            try:
                search_backend.index_note(ent)
            except Exception:
                pass
        return SaveResult(id=ent.id, rel_path=rel, action="appended", backup_rel_path=backup)

    rel = f"{folder}/{fm.sanitize_title(title)}.md" if folder else f"{fm.sanitize_title(title)}.md"
    meta_in: dict[str, Any] = {
        "id": _id_for(folder, title),
        "type": type_,
        "title": title,
        "horizon": horizon,
        "scope": scope,
        "repo": repo,
        "role": role.name,
        "created": _today(),
        "source_session": session_id,
    }
    meta = fm.build(meta_in, links=links, tags=tags)
    stamp = _today() + (f" · session {session_id}" if session_id else "")
    body_out = f"# {title}\n\n**{stamp}**\n\n{body.rstrip()}\n"
    backup = store.write(rel, fm.dump(meta, body_out), snapshot_message=f"create {rel}")
    ent = _read_entry(store, store.resolve(rel))
    if search_backend is not None:
        try:
            search_backend.index_note(ent)
        except Exception:
            pass
    return SaveResult(id=ent.id, rel_path=rel, action="created", backup_rel_path=backup)


def list_recent(store: Store, *, repo: str | None = None, limit: int = 8,
                types: list[str] | None = None) -> list[MemoryEntry]:
    """Most-recent memories (optionally for a repo) — used by SessionStart recall,
    where there's no query yet. Recency by the `created` frontmatter date."""
    ents: list[MemoryEntry] = []
    for p in store.iter_entries():
        ent = _read_entry(store, p)
        if repo and ent.repo != repo:
            continue
        if types and ent.type not in types:
            continue
        ents.append(ent)
    ents.sort(key=lambda e: (str(e.frontmatter.get("created") or ""), e.rel_path), reverse=True)
    return ents[:limit]


def recall(
    store: Store,
    search_backend: "SearchBackend",
    query: str,
    *,
    repo: str | None = None,
    scope: str | None = None,
    type_: str | None = None,
    limit: int = 8,
) -> list[MemoryHit]:
    """Recall memories relevant to ``query`` (semantic when available), with
    optional repo/scope/type filters applied post-hoc."""
    hits = search_backend.query(query, limit=limit * 3)
    out: list[MemoryHit] = []
    for h in hits:
        if repo or scope or type_:
            try:
                ent = read(store, h.rel_path)
            except MemoryNotFoundError:
                continue
            if repo and ent.repo != repo:
                continue
            if scope and ent.scope != scope:
                continue
            if type_ and ent.type.lower() != type_.lower():
                continue
            h.repo = ent.repo
            h.id = ent.id
        out.append(h)
        if len(out) >= limit:
            break
    return out
