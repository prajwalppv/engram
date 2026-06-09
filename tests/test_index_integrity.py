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


def test_reader_reloads_after_out_of_band_index_write(store, generic, monkeypatch):
    # The freshness fix: a long-running reader (the MCP server) must notice when
    # another process — a capture HOOK — indexed new memories to disk, and reload
    # instead of serving its stale startup snapshot (else recall misses them and
    # engram_info falsely reports drift).
    monkeypatch.setattr(SemanticSearchBackend, "_embed", _fake_embed)
    memory.save(store, generic, type_="Note", title="A", body="aaa")
    idx = store.root / ".index"
    reader = _backend(store)
    reader.reindex_all(store)                     # reader caches {A}
    assert reader.verify(store)["indexed"] == 1

    # another process saves AND indexes B out-of-band → disk index is now {A,B}
    memory.save(store, generic, type_="Note", title="B", body="bbb")
    SemanticSearchBackend(store, index_dir=idx).index_note(memory.read(store, "B"))

    # reader sees the disk changed and reloads — recall + verify reflect {A,B}
    assert {h.title for h in reader.query("bbb", limit=5)} >= {"B"}
    v = reader.verify(store)
    assert v["in_sync"] and v["indexed"] == 2, v


def test_torn_two_file_read_does_not_crash_search(store, generic, monkeypatch):
    # vectors.npy and meta.json are two separate atomic replaces; a lock-free
    # reader can catch a torn pair (more vectors than meta). _search must not
    # IndexError past _meta — the load clamps to the consistent prefix.
    import json as _json
    import numpy as np
    monkeypatch.setattr(SemanticSearchBackend, "_embed", _fake_embed)
    for t, b in [("A", "aaa"), ("B", "bbb")]:
        memory.save(store, generic, type_="Note", title=t, body=b)
    sb = _backend(store)
    sb.reindex_all(store)                       # disk: 2 vectors, 2 meta
    idx = store.root / ".index"
    # Simulate a torn write: vectors grew to 3 rows, meta still has 2 entries.
    vecs = np.load(idx / "vectors.npy")
    np.save(idx / "vectors.npy", np.vstack([vecs, vecs[:1]]))   # now 3 rows
    assert len(_json.loads((idx / "meta.json").read_text())) == 2

    fresh = _backend(store)
    hits = fresh.query("aaa", limit=5)          # must not raise
    assert len(fresh._meta) == len(fresh._vecs)  # clamped to consistent prefix
    assert all(h.rel_path for h in hits)


def test_lexical_in_memory_matches_disk_scan(store, generic, monkeypatch):
    # the O(N)-disk-scan fix: lexical() over in-memory index text must rank the same
    # as the disk-reading TextSearchBackend (same scoring), just far faster.
    from engram.core.search_backends import TextSearchBackend
    monkeypatch.setattr(SemanticSearchBackend, "_embed", _fake_embed)
    for t, b in [("Redis cache", "we use redis for the session cache layer"),
                 ("Postgres billing", "store money as integer cents in postgres"),
                 ("Blue-green deploy", "ship with blue-green to avoid cache downtime")]:
        memory.save(store, generic, type_="Decision", title=t, body=b)
    sb = _backend(store)
    sb.reindex_all(store)
    assert all("text" in m for m in sb._meta)              # searchable text stored
    q = "redis cache session"
    mem = [h.title for h in sb.lexical(q, limit=5)]
    disk = [h.title for h in TextSearchBackend(store).query(q, limit=5)]
    assert set(mem) == set(disk) and mem[0] == disk[0]     # same hits, same top


def test_old_index_auto_upgrades_to_lexical_text(store, generic, monkeypatch):
    monkeypatch.setattr(SemanticSearchBackend, "_embed", _fake_embed)
    memory.save(store, generic, type_="Note", title="Alpha", body="alpha beta gamma")
    sb = _backend(store)
    sb.reindex_all(store)
    # simulate a pre-upgrade index: strip the new `text` field and persist
    for m in sb._meta:
        m.pop("text", None)
    sb._persist()
    fresh = _backend(store)
    fresh._ensure_loaded()                                  # auto-upgrade on load
    assert all("text" in m for m in fresh._meta)
    assert [h.title for h in fresh.lexical("alpha", limit=3)] == ["Alpha"]


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
