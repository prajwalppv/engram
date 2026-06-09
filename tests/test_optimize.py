from __future__ import annotations

import json

from engram.config import Settings
from engram.core import evalset, optimize


def _write_prune_history(store, lines):
    p = store.root / ".state" / "prune-history.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")


# --- deterministic prune self-tuner --------------------------------------
def test_tune_prune_reduces_on_high_resurrection(store):
    settings = Settings(prune_max_fraction=0.25)
    _write_prune_history(store, [
        {"metrics_before": {"total": 10}, "metrics_after": {"total": 8}, "archived": 2},
        {"resurrection": "Sessions/x.md"},  # 1 restored of 2 archived → rate 0.5
    ])
    out = optimize.tune_prune_params(store, settings)
    assert out["changed"] and out["new"] < 0.25
    assert optimize.load_tuned(store)["prune_max_fraction"] == out["new"]


def test_tune_prune_increases_when_clean(store):
    settings = Settings(prune_max_fraction=0.25)
    _write_prune_history(store, [
        {"metrics_before": {}, "metrics_after": {}, "archived": 1} for _ in range(3)
    ])
    out = optimize.tune_prune_params(store, settings)
    assert out["changed"] and out["new"] > 0.25


def test_tune_prune_noop_without_cycles(store):
    out = optimize.tune_prune_params(store, Settings())
    assert out["changed"] is False


# --- gated, versioned prompt optimizer (injected fakes; no LLM) -----------
def _seed_cases(store, n=4):
    for i in range(n):
        evalset.add_extraction_case(store, f"transcript {i}", ["alpha", "beta"], repo="r")


class _FakeProposer:
    def __init__(self, candidate):
        self.candidate = candidate

    def propose(self, current, failures):
        return self.candidate


def _fake_extract(prompt, transcript, repo):
    # a "good" prompt (contains BETTER) extracts the expected terms; else nothing
    if "BETTER" in prompt:
        return [{"title": "alpha", "body": "beta", "type": "Decision"}]
    return []


def test_optimize_accepts_better_prompt(store):
    _seed_cases(store)
    settings = Settings()
    cand = "BETTER extraction. {role_name} {role_description} {extraction_hint} {node_types} {repo} {existing_memory} {transcript}"
    res = optimize.optimize_extraction_prompt(
        store, settings, proposer=_FakeProposer(cand), extract_fn=_fake_extract)
    assert res["accepted"] and res["candidate_score"] > res["base_score"]
    assert res.get("version_saved")
    assert "BETTER" in optimize.active_prompt(store)  # override now active


def test_optimize_rejects_non_improving(store):
    _seed_cases(store)
    settings = Settings()
    cand = "still bad but different {existing_memory} {transcript}"  # no BETTER → score 0, not > base 0
    res = optimize.optimize_extraction_prompt(
        store, settings, proposer=_FakeProposer(cand), extract_fn=_fake_extract)
    assert res["accepted"] is False


def test_optimize_rejects_candidate_dropping_placeholder(store):
    _seed_cases(store)
    res = optimize.optimize_extraction_prompt(
        store, Settings(), proposer=_FakeProposer("BETTER but no placeholder"),
        extract_fn=_fake_extract)
    assert res["changed"] is False and "placeholder" in res["reason"]


def test_optimize_needs_minimum_cases(store):
    res = optimize.optimize_extraction_prompt(
        store, Settings(), proposer=_FakeProposer("x"), extract_fn=_fake_extract)
    assert res["changed"] is False and "eval cases" in res["reason"]


def test_prompt_rollback(store):
    _seed_cases(store)
    cand = "BETTER {role_name} {role_description} {extraction_hint} {node_types} {repo} {existing_memory} {transcript}"
    optimize.optimize_extraction_prompt(
        store, Settings(), proposer=_FakeProposer(cand), extract_fn=_fake_extract)
    assert "BETTER" in optimize.active_prompt(store)
    optimize.rollback_prompt(store)
    assert "BETTER" not in optimize.active_prompt(store)  # back to shipped default


# --- recall eval harvested from feedback ---------------------------------
def test_harvest_and_score_recall(store, swe, text_backend):
    from engram.core import feedback, memory
    res = memory.save(store, swe, type_="Decision", title="Use Postgres",
                      body="relational integrity", repo="r")
    feedback.record_recall(store, "postgres database", [res.id])
    feedback.record_signal(store, "used", [res.id], roles_used=["swe"])
    cases = evalset.harvest_recall_cases(store)
    assert cases and cases[0]["expected_id"] == res.id
    score = __import__("engram.core.eval", fromlist=["score_recall"]).score_recall(
        store, text_backend, cases)
    assert score["recall_at_k"] == 1.0  # the used memory ranks for its query
