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
from . import scoping
from .errors import MemoryNotFoundError
from .models import MemoryEntry, MemoryHit, SaveResult
from .store import Store

if TYPE_CHECKING:
    from ..roles.base import Role
    from .search_backends import SearchBackend


def _today() -> str:
    return datetime.date.today().isoformat()


# Compact-index budget: a recall hit carries a bounded preview so the agent can
# judge relevance WITHOUT a follow-up memory_read of every hit (progressive
# disclosure — index first, full body on demand). Kept short on purpose.
SNIPPET_CHARS = 160


def snippet(body: str, n: int = SNIPPET_CHARS) -> str:
    """First meaningful prose line of a memory body, whitespace-collapsed and
    truncated. Skips the heading (#), dated stamp (**…**), and meta (_…_) lines."""
    for ln in (body or "").splitlines():
        s = ln.strip()
        if s and not s.startswith(("#", "_", "**")):
            s = " ".join(s.split())
            return s if len(s) <= n else s[: n - 1].rstrip() + "…"
    return ""


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
    repo_v = str(meta["repo"]) if meta.get("repo") else None
    # scope/visibility disambiguation. New notes write a `visibility` key, so the
    # `scope` key is the applicability ladder. Phase-1 preference notes wrote a
    # ladder value ('global') without `visibility`. Pre-horizon legacy notes wrote
    # a visibility value ('private'/'team') in `scope` and no ladder/visibility.
    raw_scope = str(meta.get("scope") or "")
    if "visibility" in meta:
        scope_v = raw_scope if scoping.is_ladder(raw_scope) else scoping.default_scope(repo=repo_v)
        visibility_v = str(meta.get("visibility") or "private")
    elif scoping.is_ladder(raw_scope):
        scope_v, visibility_v = raw_scope, "private"
    else:
        visibility_v = raw_scope or "private"
        scope_v = scoping.default_scope(repo=repo_v)
    raw_sup = meta.get("supersedes") or []
    supersedes = [str(x) for x in (raw_sup if isinstance(raw_sup, list) else [raw_sup])]
    return MemoryEntry(
        id=str(meta.get("id") or _id_for(folder, title)),
        rel_path=rel,
        type=type_str,
        title=title,
        body=body,
        horizon=str(meta.get("horizon") or default_horizon),
        scope=scope_v,
        visibility=visibility_v,
        repo=repo_v,
        area=(str(meta["area"]) if meta.get("area") else None),
        role=(str(meta["role"]) if meta.get("role") else None),
        supersedes=supersedes,
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


def _retire(store: Store, titles: list[str], *, by: str) -> None:
    """Stamp each superseded note with a DATED retirement back-reference
    (``superseded_by`` / ``superseded_on``). Content is kept — the journey is
    preserved — and recall already drops superseded titles, so the *current* fact
    surfaces while history stays traceable. This is the bitemporal record."""
    by_key = fm.sanitize_title(by)
    for t in titles:
        if fm.sanitize_title(str(t)) == by_key:
            continue  # never retire self
        p = find_path(store, str(t))
        if p is None:
            continue
        try:
            meta, body = fm.parse(store.read(p))
            if str(meta.get("superseded_by") or "") == by:
                continue  # idempotent
            meta["superseded_by"] = by
            meta["superseded_on"] = _today()
            rel = store.relpath(p)
            store.write(rel, fm.dump(meta, body), snapshot_message=f"retire {rel}")
        except Exception:
            continue


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
    scope: str | None = None,
    horizon: str = "semantic",
    visibility: str = "private",
    area: str | None = None,
    supersedes: list[str] | None = None,
    session_id: str | None = None,
    search_backend: "SearchBackend | None" = None,
) -> SaveResult:
    """Create a memory node, or append a dated block if its title already exists."""
    scope = scoping.normalize(scope, repo=repo) if scope else \
        scoping.default_scope(horizon=horizon, repo=repo)
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
        if supersedes:
            _retire(store, supersedes, by=title)
        return SaveResult(id=ent.id, rel_path=rel, action="appended", backup_rel_path=backup)

    rel = f"{folder}/{fm.sanitize_title(title)}.md" if folder else f"{fm.sanitize_title(title)}.md"
    meta_in: dict[str, Any] = {
        "id": _id_for(folder, title),
        "type": type_,
        "title": title,
        "horizon": horizon,
        "scope": scope,
        "visibility": visibility,
        "repo": repo,
        "area": area,
        "role": role.name,
        "supersedes": list(supersedes) if supersedes else None,
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
    if supersedes:
        _retire(store, supersedes, by=title)
    return SaveResult(id=ent.id, rel_path=rel, action="created", backup_rel_path=backup)


def list_recent(store: Store, *, repo: str | None = None, role: str | None = None,
                area: str | None = None, limit: int = 8,
                types: list[str] | None = None,
                exclude_horizons: set[str] | None = None) -> list[MemoryEntry]:
    """Most-recent memories that APPLY in the given context — used by SessionStart
    recall, where there's no query yet. Applicability-filtered (so other repos'
    memory never leaks in), superseded entries dropped. Recency by `created`."""
    all_ents = [_read_entry(store, p) for p in store.iter_entries()]
    superseded = scoping.superseded_titles(all_ents)
    out: list[MemoryEntry] = []
    for ent in all_ents:
        if types and ent.type not in types:
            continue
        if exclude_horizons and ent.horizon in exclude_horizons:
            continue
        if fm.sanitize_title(ent.title) in superseded:
            continue
        if not scoping.applies(ent, repo=repo, role=role, area=area):
            continue
        out.append(ent)
    out.sort(key=lambda e: (str(e.frontmatter.get("created") or ""), e.rel_path), reverse=True)
    return out[:limit]


def recall(
    store: Store,
    search_backend: "SearchBackend",
    query: str,
    *,
    repo: str | None = None,
    scope: str | None = None,
    type_: str | None = None,
    role: str | None = None,
    area: str | None = None,
    session: str | None = None,
    limit: int = 8,
    hybrid: bool = True,
    expand_graph: bool = True,
) -> list[MemoryHit]:
    """Recall memories relevant to ``query`` — hybrid (lexical + dense) ranking with
    light recency/scope/type boosts and graph-neighbor expansion (see core/ranking).
    Results are applicability-filtered to the (repo, role, area, session) context, so
    memories scoped to a different repo/role/area never surface. ``scope``/``type_``
    are optional exact filters."""
    from . import ranking
    hits = ranking.hybrid_recall(
        store, search_backend, query, repo=repo, role=role, area=area,
        session=session, type_=type_, limit=(limit * 2 if scope else limit),
        hybrid=hybrid, expand_graph=expand_graph)
    if scope:
        out: list[MemoryHit] = []
        for h in hits:
            try:
                if read(store, h.rel_path).scope == scope:
                    out.append(h)
            except MemoryNotFoundError:
                continue
        return out[:limit]
    return hits
