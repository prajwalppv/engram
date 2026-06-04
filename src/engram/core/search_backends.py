"""SearchBackend seam: Text (default) + Semantic (local fastembed, lazy).

Design: heavy deps are lazy-imported inside the semantic
backend; falls back to text if unavailable; index persisted OUTSIDE the visible
store tree (under the store's .index dir, which iter_entries ignores).
"""
from __future__ import annotations

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

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        import numpy as np
        if self._vec_path.exists() and self._meta_path.exists():
            with open(self._vec_path, "rb") as f:
                self._vecs = np.load(f)
            self._meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            self._loaded = True
        else:
            self._loaded = True
            self.reindex_all(self.store)

    def index_note(self, entry: MemoryEntry) -> None:
        import numpy as np
        self._ensure_loaded()
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
        self._ensure_loaded()
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
        return {"backend": "semantic", "indexed": indexed, "skipped": skipped}

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
