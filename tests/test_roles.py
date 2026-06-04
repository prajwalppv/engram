from __future__ import annotations

from engram.core import roles as R


def test_infer_signals_distinguishes_roles():
    swe_text = "Fixed a null pointer exception in the API endpoint, added a unit test, opened a PR."
    pm_text = "Reprioritized the roadmap with stakeholders; the customer churn metric drove the spec."
    swe_dist = R.infer_signals(swe_text)
    pm_dist = R.infer_signals(pm_text)
    assert max(swe_dist, key=swe_dist.get) == "swe"
    assert max(pm_dist, key=pm_dist.get) == "pm"


def test_update_from_session_shifts_weights(store):
    R.update_from_session(store, "stack trace, refactor, deploy the endpoint, unit test")
    assert R.current_role_name(store) == "swe"
    # several PM-heavy sessions move the inferred role
    for _ in range(6):
        R.update_from_session(store, "roadmap stakeholder requirement prioritize customer churn spec")
    assert R.current_role_name(store) == "pm"


def test_pin_overrides_inference(store):
    R.update_from_session(store, "stack trace refactor endpoint test")  # infers swe
    R.set_pinned(store, "em")
    st = R.status(store)
    assert st["active_role"] == "em" and st["source"] == "pinned"
    R.set_pinned(store, None)
    assert R.status(store)["source"] == "inferred"


def test_cold_start_is_generic(store):
    assert R.current_role_name(store) == "generic"
