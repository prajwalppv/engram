"""The Role contract — the Profile seam applied to PEOPLE.

A role defines what memory matters for someone in that role: the node ontology,
how to route it, what to extract from a session, what to prioritize recalling,
and which types are sensitive. Roles are inferred (soft weights) but each is a
plain, declarative object — no MCP imports.
"""
from __future__ import annotations


class Role:
    name: str = "base"
    description: str = "Generic memory."

    #: The memory ontology for this role (graph node types).
    node_types: list[str] = ["Note", "Decision", "SessionSummary"]

    #: Terms that, when seen in a session, suggest this role (drives inference).
    signal_terms: set[str] = set()

    #: Types considered sensitive (stricter handling; never auto-shared).
    sensitive_types: set[str] = set()

    def folder_for(self, type_: str) -> str:
        """Where a node of ``type_`` is filed (relative to the store root)."""
        return type_ if type_ else "Notes"

    def is_sensitive(self, type_: str) -> bool:
        return type_ in self.sensitive_types

    def extraction_hint(self) -> str:
        """Guidance for distilling a session into memory (used by the save flow)."""
        return ("Capture durable facts worth remembering next time: decisions and "
                "their rationale, gotchas, and useful context.")

    def recall_hint(self) -> str:
        """What to prioritize when recalling at the start of a session."""
        return "Surface prior decisions and gotchas relevant to the current work."
