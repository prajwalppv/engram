"""Engineering-manager role. NOTE: people-memory here is sensitive by design."""
from __future__ import annotations

from .base import Role


class EMRole(Role):
    name = "em"
    description = "Engineering manager: people, team, process, commitments."
    node_types = ["Person", "OneOnOne", "Commitment", "Process",
                  "TeamDecision", "CrossTeamDep", "SessionSummary"]
    # People/performance memory must never be auto-shared and gets stricter handling.
    sensitive_types = {"Person", "OneOnOne"}
    signal_terms = {
        "1:1", "one-on-one", "one on one", "direct report", "report", "performance",
        "headcount", "hiring", "interview", "promotion", "career", "growth", "feedback",
        "team", "escalation", "conflict", "stakeholder", "cross-team", "roadmap",
        "prioritization", "commitment", "deadline", "review cycle", "mentor",
    }

    def folder_for(self, type_: str) -> str:
        return {
            "Person": "People", "OneOnOne": "OneOnOnes", "Commitment": "Commitments",
            "Process": "Processes", "TeamDecision": "Decisions",
            "CrossTeamDep": "Dependencies", "SessionSummary": "Sessions",
        }.get(type_, type_)

    def extraction_hint(self) -> str:
        return ("Capture: team decisions and commitments, process notes, cross-team "
                "dependencies. Person/1:1 context is SENSITIVE — keep it factual and "
                "minimal, never store anything you wouldn't want on the person's record. "
                "It is private to this machine and never shared.")

    def recall_hint(self) -> str:
        return ("Surface prior commitments, team decisions, and cross-team context for "
                "the current topic. Bring up sensitive people-context sparingly.")
