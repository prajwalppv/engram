"""Generic role — the cold-start default before a role is inferred."""
from __future__ import annotations

from .base import Role


class GenericRole(Role):
    name = "generic"
    description = "Role-agnostic memory (cold start)."
    node_types = ["Note", "Decision", "Gotcha", "SessionSummary"]
    signal_terms = set()
