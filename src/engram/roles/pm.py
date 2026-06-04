"""Product-manager role."""
from __future__ import annotations

from .base import Role


class PMRole(Role):
    name = "pm"
    description = "Product manager: requirements, stakeholders, tradeoffs."
    node_types = ["Decision", "Requirement", "Stakeholder", "CustomerSignal",
                  "Tradeoff", "SessionSummary"]
    signal_terms = {
        "roadmap", "requirement", "spec", "prd", "stakeholder", "customer", "user",
        "priorit", "tradeoff", "scope", "milestone", "okr", "kpi", "metric", "launch",
        "feature", "backlog", "epic", "user story", "persona", "go-to-market", "gtm",
        "adoption", "churn", "feedback", "deadline", "release",
    }

    def folder_for(self, type_: str) -> str:
        return {
            "Decision": "Decisions", "Requirement": "Requirements",
            "Stakeholder": "Stakeholders", "CustomerSignal": "CustomerSignals",
            "Tradeoff": "Tradeoffs", "SessionSummary": "Sessions",
        }.get(type_, type_)

    def extraction_hint(self) -> str:
        return ("Capture: product decisions and their rationale, requirements and the "
                "WHY behind them, stakeholder positions, customer signals, and tradeoffs "
                "considered. Preserve reasoning, not just conclusions.")

    def recall_hint(self) -> str:
        return ("Surface prior product decisions, the rationale behind requirements, and "
                "stakeholder/customer context relevant to the current topic.")
