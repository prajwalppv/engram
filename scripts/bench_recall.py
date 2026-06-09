"""Recall-latency benchmark — characterize hybrid_recall cost vs store size, and
break it into components so we optimize the real bottleneck (not a guess).

    uv run python scripts/bench_recall.py 200 1000 3000
"""
from __future__ import annotations

import random
import sys
import tempfile
import time
from pathlib import Path

from engram.core import frontmatter as fm
from engram.core import memory, ranking, vigor
from engram.core.search_backends import SemanticSearchBackend, TextSearchBackend
from engram.core.store import FileSystemBackend, Store

VOCAB = ("redis postgres cache deploy index lock hook recall prune vigor session "
         "token graph embed lexical dense fusion blue green webhook idempotent cents "
         "migration backoff retry latency throttle scope role horizon supersede "
         "dedup autolink orphan dangling maintenance ebbinghaus decay access").split()
TYPES = ["Decision", "Gotcha", "Convention", "Note"]


def build(n: int, store: Store) -> None:
    random.seed(0)
    for i in range(n):
        terms = random.sample(VOCAB, 8)
        title = f"{terms[0]}-{terms[1]}-{i}"
        body = " ".join(terms) + f" detail number {i} about the {terms[2]} system"
        meta = {"id": f"Notes/{title}", "type": random.choice(TYPES), "title": title,
                "horizon": "semantic", "scope": "repo", "repo": "bench",
                "created": "2026-06-01"}
        store.write(f"Notes/{fm.sanitize_title(title)}.md", fm.dump(meta, body))


def _t(fn, *a, **k):
    t = time.perf_counter()
    r = fn(*a, **k)
    return (time.perf_counter() - t) * 1000, r


def bench(n: int) -> None:
    d = Path(tempfile.mkdtemp())
    store = Store(FileSystemBackend(d / "store"))
    build(n, store)
    be = SemanticSearchBackend(store, index_dir=d / "store" / ".index")
    be.reindex_all(store)  # batch embed once
    q = "redis cache deploy latency"
    pool = max(8 * 5, 25)

    memory.recall(store, be, q, limit=8)  # warm caches/model
    runs = 5
    full = min(_t(memory.recall, store, be, q, limit=8)[0] for _ in range(runs))
    dense = min(_t(be.query, q, limit=pool)[0] for _ in range(runs))
    lex_disk = min(_t(TextSearchBackend(store).query, q, limit=pool)[0] for _ in range(runs))
    lex_mem = min(_t(be.lexical, q, limit=pool)[0] for _ in range(runs))
    fbc = min(_t(vigor.feedback_counts, store)[0] for _ in range(runs))
    # candidate read loop (read each fused candidate once) — bounded by pool, not N
    dh = be.query(q, limit=pool)
    cand_t = min(_t(lambda: [memory.read(store, h.rel_path) for h in dh])[0] for _ in range(runs))

    print(f"N={n:5d} | full_recall={full:7.1f}ms | dense={dense:5.1f} | "
          f"lex_disk(old)={lex_disk:7.1f} | lex_mem(new)={lex_mem:6.1f} | "
          f"feedback={fbc:4.1f} | cand_reads={cand_t:5.1f}")


if __name__ == "__main__":
    sizes = [int(x) for x in sys.argv[1:]] or [200, 1000, 3000]
    print("recall latency by store size (ms, min of 5 warm runs):")
    for n in sizes:
        bench(n)
