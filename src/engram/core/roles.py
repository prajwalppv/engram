"""Role inference — soft weights over roles, learned from session text.

Never a hard label: we keep a distribution (a tech lead can be 0.6 swe / 0.4 em),
update it with an EMA each session, and let the user override. State lives in a
dot-dir the memory scanner ignores, and never leaves the machine.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..roles import all_roles, available_roles, get_role
from ..roles.base import Role
from .store import Store

_STATE_REL = ".state/role.json"


def _state_path(store: Store) -> Path:
    return store.root / _STATE_REL


def load_model(store: Store) -> dict:
    p = _state_path(store)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"weights": {}, "sessions": 0}


def save_model(store: Store, model: dict) -> None:
    p = _state_path(store)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(model, indent=2), encoding="utf-8")


def infer_signals(text: str) -> dict[str, float]:
    """Count each role's signal terms in ``text`` → a normalized distribution."""
    low = (text or "").lower()
    raw: dict[str, float] = {}
    for role in all_roles():
        if not role.signal_terms:
            continue
        hits = sum(low.count(term) for term in role.signal_terms)
        if hits:
            raw[role.name] = float(hits)
    total = sum(raw.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in raw.items()}


def update_from_session(store: Store, text: str, *, alpha: float = 0.3) -> dict:
    """Blend this session's signal distribution into the stored weights (EMA)."""
    model = load_model(store)
    weights: dict[str, float] = dict(model.get("weights", {}))
    dist = infer_signals(text)
    if dist:
        for name in set(weights) | set(dist):
            old = weights.get(name, 0.0)
            new = dist.get(name, 0.0)
            weights[name] = (1 - alpha) * old + alpha * new
        # renormalize
        s = sum(weights.values()) or 1.0
        weights = {k: v / s for k, v in weights.items()}
    model["weights"] = weights
    model["sessions"] = int(model.get("sessions", 0)) + 1
    save_model(store, model)
    return model


def reinforce(store: Store, role_name: str, *, amount: float = 0.1) -> dict:
    """Feedback nudge: bump a role's weight (e.g. when its memories get used)."""
    model = load_model(store)
    weights = dict(model.get("weights", {}))
    weights[role_name] = weights.get(role_name, 0.0) + amount
    s = sum(weights.values()) or 1.0
    model["weights"] = {k: v / s for k, v in weights.items()}
    save_model(store, model)
    return model


def set_pinned(store: Store, name: str | None) -> dict:
    """Persistently pin (or clear with None/'auto') the active role."""
    model = load_model(store)
    if not name or name == "auto":
        model.pop("pinned", None)
    else:
        model["pinned"] = name
    save_model(store, model)
    return model


def current_role_name(store: Store, pinned: str = "auto") -> str:
    if pinned and pinned != "auto":
        return pinned
    model = load_model(store)
    if model.get("pinned"):
        return str(model["pinned"])
    weights = model.get("weights", {})
    if not weights:
        return "generic"
    return max(weights, key=weights.get)


def current_role(store: Store, pinned: str = "auto") -> Role:
    return get_role(current_role_name(store, pinned))


def status(store: Store, pinned: str = "auto") -> dict:
    model = load_model(store)
    is_pinned = (pinned and pinned != "auto") or bool(model.get("pinned"))
    return {
        "active_role": current_role_name(store, pinned),
        "source": "pinned" if is_pinned else "inferred",
        "weights": {k: round(v, 3) for k, v in sorted(
            model.get("weights", {}).items(), key=lambda kv: kv[1], reverse=True)},
        "sessions_observed": model.get("sessions", 0),
        "available_roles": available_roles(),
    }
