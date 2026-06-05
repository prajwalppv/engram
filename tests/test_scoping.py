"""Phase 2 — scope ladder + precedence (applicability, supersede, legacy reads)."""
from __future__ import annotations

from engram.core import export, memory, preferences, scoping
from engram.core.models import MemoryEntry


# ---------------------------------------------------------------- helpers
def test_scoping_helpers():
    assert scoping.rank("repo") > scoping.rank("global")
    assert scoping.rank("session") == max(scoping.rank(s) for s in scoping.LADDER)
    assert scoping.default_scope(horizon="preference") == "global"
    assert scoping.default_scope(horizon="working") == "session"
    assert scoping.default_scope(repo="x") == "repo"
    assert scoping.default_scope() == "global"
    assert scoping.normalize("BOGUS", repo="x") == "repo"
    assert scoping.normalize("Repo") == "repo"


def test_applies_matrix():
    g = MemoryEntry(id="g", rel_path="g.md", type="X", title="g", scope="global")
    assert scoping.applies(g, repo="a", role="swe")
    r = MemoryEntry(id="r", rel_path="r.md", type="X", title="r", scope="repo", repo="a")
    assert scoping.applies(r, repo="a") and not scoping.applies(r, repo="b")
    assert scoping.applies(r, repo=None)  # unknown ctx never excludes
    ro = MemoryEntry(id="x", rel_path="x.md", type="X", title="x", scope="role", role="pm")
    assert scoping.applies(ro, role="pm") and not scoping.applies(ro, role="swe")
    ar = MemoryEntry(id="y", rel_path="y.md", type="X", title="y", scope="area", area="python")
    assert scoping.applies(ar, area="python") and not scoping.applies(ar, area="go")


# ---------------------------------------------------------------- save defaults
def test_save_computes_default_scope(store, swe):
    r1 = memory.read(store, memory.save(store, swe, type_="Decision",
                                        title="Repo thing", body="x", repo="a").rel_path)
    assert r1.scope == "repo" and r1.visibility == "private"
    r2 = memory.read(store, memory.save(store, swe, type_="Note",
                                        title="No repo", body="y").rel_path)
    assert r2.scope == "global"


# ---------------------------------------------------------------- applicability in recall
def test_recall_excludes_other_repo_scope(store, swe, text_backend):
    memory.save(store, swe, type_="Decision", title="Use Postgres",
                body="banana checkout database choice", repo="alpha", search_backend=text_backend)
    memory.save(store, swe, type_="Convention", title="Tabs not spaces",
                body="banana global style rule", scope="global", search_backend=text_backend)
    in_beta = {h.title for h in memory.recall(store, text_backend, "banana", repo="beta", limit=10)}
    assert "Tabs not spaces" in in_beta and "Use Postgres" not in in_beta
    in_alpha = {h.title for h in memory.recall(store, text_backend, "banana", repo="alpha", limit=10)}
    assert {"Tabs not spaces", "Use Postgres"} <= in_alpha


def test_list_recent_applicability_and_exclusions(store, swe):
    memory.save(store, swe, type_="Decision", title="A repo", body="x", repo="alpha")
    memory.save(store, swe, type_="Decision", title="B global", body="y", scope="global")
    beta = {e.title for e in memory.list_recent(store, repo="beta")}
    assert "B global" in beta and "A repo" not in beta
    alpha = {e.title for e in memory.list_recent(store, repo="alpha")}
    assert {"A repo", "B global"} <= alpha
    # preference horizon is excludable (shown separately by the recall hook)
    preferences.add(store, swe, "Always use uv.")
    no_pref = {e.title for e in memory.list_recent(store, exclude_horizons={"preference"})}
    assert not any("Pref:" in t for t in no_pref)


# ---------------------------------------------------------------- supersede
def test_supersede_retires_old_memory(store, swe):
    memory.save(store, swe, type_="Convention", title="Old rule", body="old", scope="global")
    memory.save(store, swe, type_="Convention", title="New rule", body="new",
                scope="global", supersedes=["Old rule"])
    titles = {e.title for e in memory.list_recent(store)}
    assert "New rule" in titles and "Old rule" not in titles


# ---------------------------------------------------------------- preference precedence
def test_preferences_precedence_ordering_and_ctx(store, swe):
    preferences.add(store, swe, "Always use uv.")  # global
    memory.save(store, swe, type_="Preference", title="Pref: poetry here",
                body="In this repo use poetry.", horizon="preference",
                scope="repo", repo="legacy")
    allp = preferences.list_preferences(store)            # None ctx → both
    assert len(allp) == 2 and allp[0].scope == "global"   # global ordered first
    other = preferences.list_preferences(store, repo="newrepo")
    assert all(p.scope == "global" for p in other)        # repo-scoped one excluded
    here = preferences.list_preferences(store, repo="legacy")
    assert any(p.scope == "repo" for p in here)           # surfaces in its own repo
    assert here[-1].scope == "repo"                        # most-specific last (wins)


# ---------------------------------------------------------------- legacy reads
def test_legacy_scope_mapping_is_backward_compatible(store):
    # pre-horizon legacy note: `scope` held a visibility value, no `visibility` key
    store.write("Decision/Legacy.md",
                "---\ntype: Decision\ntitle: Legacy\nscope: private\nrepo: alpha\n---\n# Legacy\n\nbody\n")
    e = memory.read(store, "Legacy")
    assert e.scope == "repo"           # applicability derived from repo
    assert e.visibility == "private"   # legacy 'scope' value preserved as visibility
    # Phase-1 preference note: ladder value in `scope`, no `visibility` key
    store.write("Preference/P.md",
                "---\ntype: Preference\ntitle: P\nscope: global\nhorizon: preference\n---\n# P\n\nalways x\n")
    p = memory.read(store, "P")
    assert p.scope == "global" and p.horizon == "preference" and p.visibility == "private"


# ---------------------------------------------------------------- visibility (export) axis
def test_visibility_is_separate_from_scope(store, swe):
    memory.save(store, swe, type_="Decision", title="Shareable", body="x",
                scope="global", visibility="team")
    memory.save(store, swe, type_="Decision", title="Private one", body="y", scope="global")
    out = export.export(store, scope="team")
    titles = {e["title"] for e in out["eligible"]}
    assert "Shareable" in titles and "Private one" not in titles
