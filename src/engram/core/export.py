"""DORMANT seam: opt-in team export. Intentionally not implemented.

Every memory already carries a ``scope`` (default ``private``) and a stable id, so
a future, explicit, sanitized export of selected memories is a feature flip — not
a refactor. Until then this does nothing but report what *would* be eligible.
Sharing will always be: opt-in, redacted, explicit. Never automatic, never a server.
"""
from __future__ import annotations

from . import memory
from .store import Store


def export(store: Store, *, scope: str = "team", redact: bool = True) -> dict:
    """Not enabled. Reports eligible (non-private) memories without exporting."""
    eligible = []
    for p in store.iter_entries():
        ent = memory._read_entry(store, p)
        if ent.scope == scope:
            eligible.append({"id": ent.id, "title": ent.title, "type": ent.type})
    return {
        "status": "not_implemented",
        "message": ("Team export is a deliberate future feature. Memory stays "
                    "local and private. When enabled it will be opt-in + redacted."),
        "requested_scope": scope,
        "redact": redact,
        "eligible_count": len(eligible),
        "eligible": eligible[:50],
    }
