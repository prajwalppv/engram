"""Proactive guardrails: fire the right memory before a risky tool, stay quiet on
unrelated actions, dedup per session, respect scope, and only use guardrail types.
All lexical → no embedding model needed."""
from __future__ import annotations

from engram.core import memory, proactive


def _g(store, generic, title, body, **kw):
    memory.save(store, generic, type_=kw.pop("type_", "Gotcha"), title=title, body=body, **kw)


def test_fires_on_matching_risky_command(store, generic):
    _g(store, generic, "Never force-push shared branches",
       "Never run git push --force on shared branches; it rewrites history. Use --force-with-lease.")
    adv = proactive.guardrail(store, tool_name="Bash",
                              tool_input={"command": "git push --force origin main"})
    assert adv and adv["title"] == "Never force-push shared branches" and adv["type"] == "Gotcha"


def test_silent_on_unrelated_action(store, generic):
    _g(store, generic, "Never force-push shared branches",
       "Never run git push --force on shared branches.")
    assert proactive.guardrail(store, tool_name="Bash",
                               tool_input={"command": "echo hello world today"}) is None


def test_dedup_per_session(store, generic):
    _g(store, generic, "Payment webhook gotcha",
       "Never retry the payment webhook inline; dedupe on event id.")
    ti = {"file_path": "payment_webhook.py", "old_string": "def retry(): ..."}
    first = proactive.guardrail(store, tool_name="Edit", tool_input=ti, session="s1")
    assert first and "Payment" in first["title"]
    proactive.mark_shown(store, "s1", first["rel_path"])
    assert proactive.guardrail(store, tool_name="Edit", tool_input=ti, session="s1") is None
    # a different session still gets it
    assert proactive.guardrail(store, tool_name="Edit", tool_input=ti, session="s2") is not None


def test_respects_scope(store, generic):
    _g(store, generic, "Repo-only deploy rule",
       "deploy with the special blessed runbook only", repo="alpha")  # scope→repo
    ti = {"command": "deploy with the special blessed runbook"}
    assert proactive.guardrail(store, tool_name="Bash", tool_input=ti, repo="alpha") is not None
    assert proactive.guardrail(store, tool_name="Bash", tool_input=ti, repo="beta") is None


def test_ignores_non_guardrail_types(store, generic):
    # An episodic session summary with overlapping tokens must NOT fire.
    _g(store, generic, "Session about deploying", "we were deploying the blessed runbook today",
       type_="SessionSummary")
    ti = {"command": "deploying the blessed runbook"}
    assert proactive.guardrail(store, tool_name="Bash", tool_input=ti) is None


def test_threshold_suppresses_weak_matches(store, generic):
    _g(store, generic, "Some convention", "configuration files live under config",
       type_="Convention")
    # one weak/common-ish overlap shouldn't clear a high threshold
    adv = proactive.guardrail(store, tool_name="Bash",
                              tool_input={"command": "cat configuration"}, min_score=5.0)
    assert adv is None
