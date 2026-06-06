"""Index integrity: cross-process-safe writes (no lost updates) + self-heal on
drift + accurate verify(). Uses a deterministic fake embedder so no model is
downloaded."""
from __future__ import annotations

import hashlib

import numpy as np

from engram.core import memory
from engram.core.search_backends import SemanticSearchBackend


def _fake_embed(self, texts):
    out = []
    for t in texts:
        seed = int(hashlib.sha256(t.encode()).hexdigest(), 16) % (2**32)
        v = np.random.default_rng(seed).standard_normal(16).astype("float32")
        out.append(v / (np.linalg.norm(v) + 1e-12))
    return np.asarray(out, dtype="float32")


def _backend(store):
    return SemanticSearchBackend(store, index_dir=store.root / ".index")


def test_index_self_heals_on_drift(store, generic, monkeypatch):
    monkeypatch.setattr(SemanticSearchBackend, "_embed", _fake_embed)
    # Save notes WITHOUT a backend → nothing indexed (simulates drift / out-of-band writes).
    for i in range(4):
        memory.save(store, generic, type_="Note", title=f"N{i}", body=f"alpha body {i}")
    sb = _backend(store)
    sb._ensure_loaded()  # first use → detects drift → rebuilds
    v = sb.verify(store)
    assert v["in_sync"] and v["indexed"] == 4 and v["missing_count"] == 0


def test_stale_instance_does_not_clobber(store, generic, monkeypatch):
    # The core race fix: a stale in-memory backend must reload from disk before
    # writing, so it can't drop rows another process added.
    monkeypatch.setattr(SemanticSearchBackend, "_embed", _fake_embed)
    for t, b in [("A", "aaa"), ("B", "bbb"), ("C", "ccc")]:
        memory.save(store, generic, type_="Note", title=t, body=b)
    a, b_, c = (memory.read(store, t) for t in ("A", "B", "C"))
    idx = store.root / ".index"

    inst = SemanticSearchBackend(store, index_dir=idx)
    inst.index_note(a)                                   # disk = {A}; inst cache = {A}
    SemanticSearchBackend(store, index_dir=idx).index_note(b_)  # another writer → disk = {A,B}
    inst.index_note(c)  # inst is STALE ({A}); must reload {A,B} then add C — not clobber B

    fresh = SemanticSearchBackend(store, index_dir=idx)
    fresh._load_from_disk()
    assert {m["rel_path"] for m in fresh._meta} == {a.rel_path, b_.rel_path, c.rel_path}


def test_verify_detects_missing(store, generic, monkeypatch):
    monkeypatch.setattr(SemanticSearchBackend, "_embed", _fake_embed)
    memory.save(store, generic, type_="Note", title="A", body="aaa")
    _backend(store).reindex_all(store)
    memory.save(store, generic, type_="Note", title="B", body="bbb")  # out-of-band, unindexed

    sb = _backend(store)
    sb._load_from_disk()  # loads {A}; sets _loaded so verify() won't auto-heal first
    v = sb.verify(store)
    assert v["in_sync"] is False and v["missing_count"] == 1


def test_reindex_drops_deleted_notes(store, generic, monkeypatch):
    monkeypatch.setattr(SemanticSearchBackend, "_embed", _fake_embed)
    ra = memory.save(store, generic, type_="Note", title="A", body="aaa")
    memory.save(store, generic, type_="Note", title="B", body="bbb")
    sb = _backend(store)
    sb.reindex_all(store)
    assert sb.verify(store)["indexed"] == 2
    # delete A's file on disk, then reindex → index should drop it
    (store.root / ra.rel_path).unlink()
    rep = sb.reindex_all(store)
    assert rep["total"] == 1 and sb.verify(store)["in_sync"]
