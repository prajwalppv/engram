"""Recall ranking: hybrid fusion beats pure dense on exact terms, graph expansion
surfaces neighbors, superseded memories are dropped, and scope precedence breaks
ties. A stub dense backend lets us assert behavior without an embedding model."""
from __future__ import annotations

from engram.core import memory, ranking
from engram.core.models import MemoryHit


class StubDense:
    """Returns a fixed dense ranking (by rel_path) — lets a test pin the embedding
    order so we can prove what the lexical/boost/graph layers add."""
    def __init__(self, order: list[str]):
        self.order = order

    def query(self, text: str, *, limit: int = 25) -> list[MemoryHit]:
        return [MemoryHit(rel_path=r, title=r) for r in self.order][:limit]


def _save(store, role, title, body, **kw):
    return memory.save(store, role, type_=kw.pop("type_", "Note"), title=title,
                       body=body, **kw).rel_path


def test_hybrid_recovers_exact_term_dense_misses(store, generic):
    a = _save(store, generic, "Error E1234 handling", "when you hit code E1234 do the dance")
    b = _save(store, generic, "General logging", "logs are generally good to have")
    # Dense ranks the WRONG note first (embeddings are weak at the literal token).
    dense = StubDense([b, a])
    top_dense = ranking.hybrid_recall(store, dense, "E1234", hybrid=False, expand_graph=False)
    assert top_dense[0].rel_path == b  # pure dense gets it wrong
    top_hybrid = ranking.hybrid_recall(store, dense, "E1234", hybrid=True, expand_graph=False)
    assert top_hybrid[0].rel_path == a  # lexical fusion fixes it


def test_graph_expansion_surfaces_neighbor(store, generic):
    parent = _save(store, generic, "Parent", "alpha parent unique topic", links=["Child"])
    _save(store, generic, "Child", "completely unrelated zzz content")
    dense = StubDense([parent])
    no_graph = ranking.hybrid_recall(store, dense, "alpha parent unique", expand_graph=False)
    assert {h.title for h in no_graph} == {"Parent"}
    with_graph = ranking.hybrid_recall(store, dense, "alpha parent unique", expand_graph=True)
    assert "Child" in {h.title for h in with_graph}  # neighbor pulled in


def test_superseded_memory_is_dropped(store, generic):
    old = _save(store, generic, "Old way", "we use poetry for deps", type_="Decision")
    new = _save(store, generic, "New way", "we use uv for deps now",
                type_="Decision", supersedes=["Old way"])
    dense = StubDense([old, new])
    titles = {h.title for h in ranking.hybrid_recall(store, dense, "deps", expand_graph=False)}
    assert "New way" in titles and "Old way" not in titles


def test_scope_precedence_breaks_ties(store, generic):
    g = _save(store, generic, "Global note", "shared topic phrase", scope="global")
    r = _save(store, generic, "Repo note", "shared topic phrase", repo="proj")  # scope→repo
    # Equal dense rank list (g first); the more-specific repo-scoped note should win
    # on the scope boost.
    dense = StubDense([g, r])
    out = ranking.hybrid_recall(store, dense, "shared topic phrase",
                                hybrid=False, expand_graph=False)
    assert out[0].title == "Repo note"
