"""Software-engineer role."""
from __future__ import annotations

from .base import Role


class SWERole(Role):
    name = "swe"
    description = "Software engineer: code, systems, debugging."
    node_types = ["Decision", "Gotcha", "Convention", "Service", "Bug", "SessionSummary"]
    signal_terms = {
        "bug", "stack trace", "traceback", "refactor", "pull request", "pr", "merge",
        "compile", "build", "test", "deploy", "endpoint", "api", "database", "schema",
        "function", "class", "module", "dependency", "exception", "null", "race condition",
        "latency", "cache", "regression", "commit", "branch", "lint", "type error",
    }

    def folder_for(self, type_: str) -> str:
        return {
            "Decision": "Decisions", "Gotcha": "Gotchas", "Convention": "Conventions",
            "Service": "Services", "Bug": "Bugs", "SessionSummary": "Sessions",
        }.get(type_, type_)

    def extraction_hint(self) -> str:
        return ("Capture: architecture/design decisions and WHY, gotchas & non-obvious "
                "bugs and their fixes, code conventions, and quirks of services/deps. "
                "Prefer 'why we did X' over 'what the code is'.")

    def recall_hint(self) -> str:
        return ("Surface prior decisions, gotchas, and conventions for this repo/area "
                "before writing or debugging code.")
