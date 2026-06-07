"""SearchBackend seam: Text (default) + Semantic (local fastembed, lazy).

Design: heavy deps are lazy-imported inside the semantic
backend; falls back to text if unavailable; index persisted OUTSIDE the visible
store tree (under the store's .index dir, which iter_entries ignores).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import MemoryEntry, MemoryHit
from .store import Store


@runtime_checkable
class SearchBackend(Protocol):
    def index_note(self, entry: MemoryEntry) -> None: ...
    def remove(self, rel_path: str) -> None: ...
    def reindex_all(self, store: Store) -> dict: ...
    def query(self, text: str, *, limit: int = 25) -> list[MemoryHit]: ...
    def find_similar(self, text: str, *, limit: int = 5, min_score: float = 0.0) -> list[MemoryHit]: ...
    def stats(self) -> dict: ...


def content_hash(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\n{body}".encode()).hexdigest()


def build_backend(settings, store) -> "SearchBackend":
    """Pick the search backend from settings. Semantic when requested AND its deps
    are importable; otherwise text. A missing dep degrades gracefully (never crashes).
    Shared by the MCP server and the SessionEnd hook so indexing stays consistent."""
    import importlib.util
    import sys
    if str(getattr(settings, "search_backend", "text")).lower() == "semantic":
        missing = [m for m in ("fastembed", "numpy") if importlib.util.find_spec(m) is None]
        if missing:
            print(f"[engram] semantic recall needs {', '.join(missing)}; "
                  f"using text recall", file=sys.stderr)
        else:
            return SemanticSearchBackend(
                store, index_dir=settings.resolved_index_dir(),
                model_name=settings.embedding_model)
    return TextSearchBackend(store)


def _snippet(body: str, term: str, width: int = 140) -> str | None:
    i = body.lower().find(term.lower())
    if i < 0:
        return None
    s = max(0, i - width // 2)
    e = min(len(body), i + width // 2)
    return ("…" if s else "") + body[s:e].replace("\n", " ").strip() + ("…" if e < len(body) else "")


class TextSearchBackend:
    """Index-free substring search; the safe default and fallback."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def index_note(self, entry: MemoryEntry) -> None:
        return None

    def remove(self, rel_path: str) -> None:
        return None

    def reindex_all(self, store: Store) -> dict:
        return {"backend": "text", "indexed": 0}

    def _scan(self, text: str, limit: int) -> list[MemoryHit]:
        import re
        from . import memory  # lazy to avoid cycle
        terms = [w for w in re.findall(r"\w+", (text or "").lower()) if len(w) > 2]
        hits = []
        for p in self.store.iter_entries():
            ent = memory._read_entry(self.store, p)
            title_l = ent.title.lower()
            hay = (ent.title + "\n" + ent.body).lower()
            if terms:
                score = sum(hay.count(t) + (2.0 if t in title_l else 0.0) for t in terms)
                if score <= 0:
                    continue
            else:
                score = 0.0
            hits.append(MemoryHit(id=ent.id, rel_path=ent.rel_path, title=ent.title,
                                  type=ent.type, score=score, repo=ent.repo,
                                  snippet=_snippet(ent.body, terms[0]) if terms else None))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def query(self, text: str, *, limit: int = 25) -> list[MemoryHit]:
        return self._scan(text, limit)

    def find_similar(self, text: str, *, limit: int = 5, min_score: float = 0.0) -> list[MemoryHit]:
        return self._scan(text, limit)

    def stats(self) -> dict:
        return {"backend": "text", "notes": sum(1 for _ in self.store.iter_entries())}


class SemanticSearchBackend:
    """Local embedding recall. Persists vectors.npy + meta.json under index_dir."""

    def __init__(self, store: Store, *, index_dir: Path,
                 model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.store = store
        self.index_dir = Path(index_dir)
        self.model_name = model_name
        self.cache_dir = os.environ.get("FASTEMBED_CACHE_PATH") or str(self.index_dir / "model_cache")
        self._model = None
        self._vecs = None
        self._meta: list[dict] | None = None
        self._loaded = False
        self._lock_held = False
        self._fp: tuple | None = None  # on-disk index fingerprint at last load

    def _disk_fingerprint(self) -> tuple | None:
        """Cheap freshness signal for the on-disk index (mtime+size of both files).
        Lets a long-running reader (the MCP server) notice when a separate process
        — e.g. a capture HOOK — has written new memories+index rows out-of-band,
        and reload instead of serving a stale startup snapshot."""
        try:
            sv, sm = self._vec_path.stat(), self._meta_path.stat()
            return (sv.st_mtime_ns, sv.st_size, sm.st_mtime_ns, sm.st_size)
        except OSError:
            return None

    @property
    def _vec_path(self) -> Path:
        return self.index_dir / "vectors.npy"

    @property
    def _meta_path(self) -> Path:
        return self.index_dir / "meta.json"

    def _embedder(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def _embed(self, texts: list[str]):
        import numpy as np
        arr = np.asarray(list(self._embedder().embed(texts)), dtype="float32")
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        return arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12)

    def _persist(self) -> None:
        import numpy as np
        self.index_dir.mkdir(parents=True, exist_ok=True)
        tv = self._vec_path.with_suffix(".npy.tmp")
        with open(tv, "wb") as f:
            np.save(f, self._vecs if self._vecs is not None else np.zeros((0, 0), "float32"))
        os.replace(tv, self._vec_path)
        tm = self._meta_path.with_suffix(".json.tmp")
        with open(tm, "w", encoding="utf-8") as f:
            json.dump(self._meta or [], f, ensure_ascii=False)
        os.replace(tm, self._meta_path)
        self._fp = self._disk_fingerprint()  # our own write is now the fresh baseline

    # ---- concurrency + integrity (the store is shared across editors/hosts) ---
    @contextlib.contextmanager
    def _lock(self):
        """Cross-process exclusive lock around index read-modify-write, so two
        Claude Code hosts sharing ~/.engram/store can't clobber each other's rows.
        Reentrant within a process (avoids flock self-deadlock); best-effort where
        fcntl is unavailable."""
        if self._lock_held:
            yield
            return
        self.index_dir.mkdir(parents=True, exist_ok=True)
        f = None
        try:
            import fcntl
            f = open(self.index_dir / ".lock", "w")
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except Exception:
            f = None
        self._lock_held = True
        try:
            yield
        finally:
            self._lock_held = False
            if f is not None:
                try:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                f.close()

    def _load_from_disk(self) -> None:
        """Authoritative state from disk. Corrupt/partial files → treat as empty
        (the drift check then rebuilds). Always call this under _lock before a
        mutation, so we never persist on top of a stale in-memory snapshot."""
        import numpy as np
        self._vecs, self._meta = None, []
        if self._vec_path.exists() and self._meta_path.exists():
            try:
                with open(self._vec_path, "rb") as fh:
                    self._vecs = np.load(fh)
                self._meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            except Exception:
                self._vecs, self._meta = None, []
        self._loaded = True
        self._fp = self._disk_fingerprint()

    def _store_rels(self, store: Store) -> set:
        return {store.relpath(p) for p in store.iter_entries()}

    def _drift(self, store: Store) -> bool:
        idx = {m.get("rel_path") for m in (self._meta or [])}
        return idx != self._store_rels(store)

    def verify(self, store: Store) -> dict:
        """Report index ↔ store integrity without rebuilding."""
        self._ensure_loaded()
        idx = {m.get("rel_path") for m in (self._meta or [])}
        cur = self._store_rels(store)
        missing = sorted(cur - idx)   # in the store but not indexed (un-recallable!)
        stale = sorted(idx - cur)     # indexed but the note is gone
        return {"indexed": len(idx), "store_notes": len(cur),
                "missing": missing[:50], "stale": stale[:50],
                "missing_count": len(missing), "stale_count": len(stale),
                "in_sync": not missing and not stale}

    def _ensure_loaded(self) -> None:
        # Reload when never loaded OR when the on-disk index changed under us (a
        # capture hook in another process added memories). Without the freshness
        # check a long-running server would serve its stale startup snapshot and
        # both miss newly-captured memories in recall AND mis-report drift.
        if self._loaded and self._fp == self._disk_fingerprint():
            return
        self._load_from_disk()
        # Self-heal: rebuild if the index is empty/corrupt or has DRIFTED from the
        # store (a concurrent write that lost rows, or notes added out-of-band).
        try:
            if self._drift(self.store):
                self.reindex_all(self.store)
        except Exception:
            pass

    def index_note(self, entry: MemoryEntry) -> None:
        import numpy as np
        with self._lock():
            self._load_from_disk()  # fresh authoritative state before mutating
            h = content_hash(entry.title, entry.body)
            meta = self._meta or []
            for i, m in enumerate(meta):
                if m["rel_path"] == entry.rel_path:
                    if m.get("hash") == h:
                        return
                    self._vecs[i] = self._embed([f"{entry.title}\n\n{entry.body}"])[0]
                    meta[i] = {"rel_path": entry.rel_path, "id": entry.id, "title": entry.title,
                               "type": entry.type, "repo": entry.repo, "hash": h}
                    self._meta = meta
                    self._persist()
                    return
            vec = self._embed([f"{entry.title}\n\n{entry.body}"])
            self._vecs = vec if (self._vecs is None or len(self._vecs) == 0) else np.vstack([self._vecs, vec])
            meta.append({"rel_path": entry.rel_path, "id": entry.id, "title": entry.title,
                         "type": entry.type, "repo": entry.repo, "hash": h})
            self._meta = meta
            self._persist()

    def remove(self, rel_path: str) -> None:
        with self._lock():
            self._load_from_disk()
            meta = self._meta or []
            keep = [i for i, m in enumerate(meta) if m["rel_path"] != rel_path]
            if len(keep) == len(meta):
                return
            self._meta = [meta[i] for i in keep]
            if self._vecs is not None and len(self._vecs):
                self._vecs = self._vecs[keep]
            self._persist()

    def reindex_all(self, store: Store) -> dict:
        import numpy as np
        from . import memory
        with self._lock():
            self._load_from_disk()  # reuse current rows for hash-skip, under lock
            prev = {m["rel_path"]: (i, m) for i, m in enumerate(self._meta or [])}
            prev_vecs = self._vecs
            new_meta, new_rows, to_embed = [], [], []
            indexed = skipped = 0
            for p in store.iter_entries():
                ent = memory._read_entry(store, p)
                h = content_hash(ent.title, ent.body)
                idx = len(new_meta)
                new_meta.append({"rel_path": ent.rel_path, "id": ent.id, "title": ent.title,
                                 "type": ent.type, "repo": ent.repo, "hash": h})
                if ent.rel_path in prev and prev[ent.rel_path][1].get("hash") == h and prev_vecs is not None:
                    new_rows.append(prev_vecs[prev[ent.rel_path][0]]); skipped += 1
                else:
                    new_rows.append(None); to_embed.append((idx, f"{ent.title}\n\n{ent.body}")); indexed += 1
            if to_embed:
                embs = self._embed([t for _, t in to_embed])
                for (idx, _), v in zip(to_embed, embs):
                    new_rows[idx] = v
            self._vecs = np.vstack([r.reshape(1, -1) for r in new_rows]) if new_rows else np.zeros((0, 0), "float32")
            self._meta = new_meta
            self._loaded = True
            self._persist()
            removed = max(0, len(prev) - skipped)
            return {"backend": "semantic", "indexed": indexed, "skipped": skipped,
                    "removed": removed, "total": len(new_meta)}

    def _search(self, text: str, limit: int) -> list[MemoryHit]:
        import numpy as np
        self._ensure_loaded()
        if self._vecs is None or len(self._vecs) == 0:
            return []
        q = self._embed([text])[0]
        scores = self._vecs @ q
        order = np.argsort(-scores)[:limit]
        hits = []
        for i in order:
            m = self._meta[int(i)]
            hits.append(MemoryHit(id=m.get("id"), rel_path=m["rel_path"], title=m["title"],
                                  type=m.get("type"), repo=m.get("repo"), score=float(scores[int(i)])))
        return hits

    def query(self, text: str, *, limit: int = 25) -> list[MemoryHit]:
        return self._search(text, limit)

    def find_similar(self, text: str, *, limit: int = 5, min_score: float = 0.0) -> list[MemoryHit]:
        return [h for h in self._search(text, limit) if h.score >= min_score]

    def stats(self) -> dict:
        self._ensure_loaded()
        return {"backend": "semantic", "model": self.model_name,
                "notes": len(self._meta or []), "index_dir": str(self.index_dir)}
