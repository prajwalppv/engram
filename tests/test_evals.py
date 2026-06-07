"""Eval GATES — quality metrics with thresholds (not just correctness). A real
quality regression (worse recall, a noisier guardrail, false-positive preference
detection, mis-inferred role, unsafe pruning) fails CI here. All deterministic:
text backend / stateless scorers, no embedding-model download.

Thresholds are set below current measured values, with headroom for noise; tighten
as quality improves.
"""
from __future__ import annotations

from engram.config import Settings
from engram.core import eval as ev
from engram.core import memory


def _save(store, generic, title, body, **kw):
    memory.save(store, generic, type_=kw.pop("type_", "Note"), title=title, body=body, **kw)


# --------------------------------------------------------------- recall gate
def test_recall_quality_gate(store, generic, text_backend):
    facts = [
        ("Use Postgres", "we chose multi-row transactions for the cart checkout flow"),
        ("Stripe webhook idempotency", "dedupe on the event id to avoid a double charge"),
        ("Money in cents", "store currency amounts as integer cents, never floats"),
        ("Deploy via blue-green", "ship with blue-green to avoid downtime on release"),
        ("Rate limit the API", "throttle the public api to protect the database"),
    ]
    for t, b in facts:
        _save(store, generic, t, b, type_="Decision")
    cases = [
        {"query": "multi-row transactions database", "expected_id": memory.read(store, "Use Postgres").id},
        {"query": "avoid charging a customer twice", "expected_id": memory.read(store, "Stripe webhook idempotency").id},
        {"query": "how to store currency amounts", "expected_id": memory.read(store, "Money in cents").id},
        {"query": "release without downtime", "expected_id": memory.read(store, "Deploy via blue-green").id},
    ]
    r = ev.score_recall(store, text_backend, cases, k=5)
    assert r["recall_at_k"] >= 0.75, r
    assert r["mrr"] >= 0.6, r


# --------------------------------------------------------------- guardrail gate
def test_guardrail_precision_and_silence_gate(store, generic):
    _save(store, generic, "Never force-push shared branches",
          "Never run git push --force on shared branches; rewrites history. Use --force-with-lease.",
          type_="Gotcha")
    _save(store, generic, "Payment webhook never retry inline",
          "Never retry the payment webhook inline; dedupe on event id (PROD-142).", type_="Gotcha")
    _save(store, generic, "Migrations are irreversible in prod",
          "Production database migrations cannot be rolled back; take a snapshot first.",
          type_="Constraint")
    cases = [
        {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"},
         "expected": "Never force-push shared branches"},
        {"tool_name": "Edit", "tool_input": {"file_path": "payment_webhook.py", "old_string": "def retry():"},
         "expected": "Payment webhook never retry inline"},
        {"tool_name": "Bash", "tool_input": {"command": "alembic upgrade head  # run migration on prod database"},
         "expected": "Migrations are irreversible in prod"},
        # benign — must stay silent
        {"tool_name": "Bash", "tool_input": {"command": "echo hello world"}, "expected": None},
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "expected": None},
        {"tool_name": "Edit", "tool_input": {"file_path": "README.md", "old_string": "typo here"}, "expected": None},
    ]
    g = ev.score_guardrail(store, cases)
    assert g["precision"] >= 0.8, g       # of fires, ≥80% correct
    assert g["recall"] >= 0.66, g         # catch most should-fires
    assert g["silence_rate"] >= 0.9, g    # almost never fire on benign actions


# --------------------------------------------------- preference-detection gate
def test_preference_detection_gate():
    cases = [
        {"text": "always use uv, never pip", "is_preference": True},
        {"text": "from now on, commit only when I ask", "is_preference": True},
        {"text": "I prefer terse answers", "is_preference": True},
        {"text": "please always run the tests before pushing", "is_preference": True},
        # NOT standing preferences — must not pollute the always-on layer
        {"text": "the build failed because of a null pointer", "is_preference": False},
        {"text": "can you fix this bug in the parser", "is_preference": False},
        {"text": "what does this function do", "is_preference": False},
        # real-world noise: tool output / file dumps flattened into "user:" turns.
        # These leaked bogus prefs before the tool_result exclusion + non-prose guard.
        {"text": "218 219 ## Semantic recall (default) on by default", "is_preference": False},
        {"text": "95 - an always-on layer learns your standing preferences", "is_preference": False},
        {"text": "see the docs at https://example.com/always by default", "is_preference": False},
    ]
    p = ev.score_preference_detection(cases)
    assert p["precision"] >= 0.8, p   # false positives are costly (every session)
    assert p["recall"] >= 0.7, p


# --------------------------------------------------------- role-inference gate
def test_role_inference_gate():
    cases = [
        {"text": "fixed the null pointer exception, added a unit test, opened a pull request to merge",
         "expected_role": "swe"},
        {"text": "debugging a race condition in the cache; the api endpoint had high latency",
         "expected_role": "swe"},
        {"text": "updated the roadmap and the prd; prioritized the backlog for the next milestone launch",
         "expected_role": "pm"},
        {"text": "defined the okr and kpi for adoption; gathered customer feedback on the feature",
         "expected_role": "pm"},
        {"text": "had a 1:1 with my direct report about their promotion and career growth; handled a team escalation",
         "expected_role": "em"},
    ]
    r = ev.score_role_inference(cases)
    assert r["accuracy"] >= 0.8, r


# --------------------------------------------------------------- pruning safety
def test_pruning_never_plans_lifelines(store, generic):
    # durable + preference memory must never be planned for pruning
    _save(store, generic, "Always use uv", "standing rule", type_="Preference", horizon="preference")
    _save(store, generic, "Use Postgres", "the db decision", type_="Decision")
    # ≥2 stale ephemeral session notes for one repo → eligible for consolidation
    for i in range(3):
        _save(store, generic, f"Session note {i}", f"chatter {i}", type_="SessionSummary", repo="svc")
    settings = Settings(prune_min_age_days=0, prune_min_cluster=2, prune_max_fraction=1.0)
    s = ev.prune_safety(store, settings)
    assert s["safe"] is True, s
    assert s["planned"] >= 1  # the ephemeral notes ARE eligible (so the test is meaningful)


# --------------------------------------------------------------- extraction gate
def test_extraction_coverage_gate(generic):
    # Deterministic floor using the heuristic summarizer as the extract_fn (no LLM
    # in CI). The real claude -p extraction eval is exercised live, not gated here.
    from engram.core import summarizer

    def extract_fn(prompt, transcript, repo):
        return summarizer.HeuristicSummarizer().summarize(transcript, role=generic, repo=repo)

    cases = [
        {"transcript": "we decided to use postgres because we need multi-row transactions for the cart",
         "expected_terms": ["postgres", "transactions"]},
        {"transcript": "the gotcha is that stripe webhooks must be idempotent or you double charge",
         "expected_terms": ["stripe", "idempotent"]},
    ]
    coverage = ev.score_extraction("(prompt unused by heuristic)", cases, extract_fn)
    assert coverage >= 0.5, coverage
