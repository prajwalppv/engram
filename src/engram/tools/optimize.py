"""Self-improvement tools: tune prune params, optimize the extraction prompt
(gated + versioned), inspect eval status, manage prompt versions."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..core import eval as ev
from ..core import evalset, optimize
from ..core.proposer import ClaudeHeadlessProposer
from . import Deps


def register(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool()
    def memory_tune_prune(target_resurrection: float = 0.05) -> dict:
        """Self-tune pruning aggressiveness from the resurrection rate. If pruned
        memories are being restored too often, prune less; if never, prune a bit
        more. Learns the safe removal fraction from feedback."""
        return optimize.tune_prune_params(
            deps.store, deps.settings, target_resurrection=target_resurrection)

    @mcp.tool()
    def memory_optimize_prompt(dry_run: bool = True) -> dict:
        """Propose + gate a better extraction prompt using your eval cases. A
        candidate is accepted ONLY if it beats the current prompt on a held-out
        split; accepted versions are saved (rollback available). Dry-run by default.
        """
        return optimize.optimize_extraction_prompt(
            deps.store, deps.settings, proposer=ClaudeHeadlessProposer(
                timeout=deps.settings.summarizer_timeout), dry_run=dry_run)

    @mcp.tool()
    def memory_prompt_history() -> list[dict]:
        """List accepted extraction-prompt versions (with their eval scores)."""
        return optimize.prompt_history(deps.store)

    @mcp.tool()
    def memory_prompt_rollback() -> dict:
        """Revert the extraction prompt to the previous version (or the shipped default)."""
        return optimize.rollback_prompt(deps.store)

    @mcp.tool()
    def memory_eval(k: int = 5) -> dict:
        """Run the recall scorecard and report the metrics — labeled recall@k/MRR
        (from your feedback + golden cases) PLUS an automatic, label-free
        self-retrieval health score. This is the number to drive engram's quality
        and to catch regressions/index drift."""
        return ev.run(deps.store, deps.search_backend, k=k)

    @mcp.tool()
    def memory_add_recall_case(query: str, expected: str, repo: str | None = None) -> dict:
        """Add a GOLDEN recall case: a query and the memory (title or id) that
        should be recalled for it. Builds a labeled set so recall@k/MRR is
        measurable without waiting on usage feedback."""
        n = evalset.add_recall_case(deps.store, query, expected, repo)
        return {"golden_recall_cases": n}

    @mcp.tool()
    def memory_eval_status() -> dict:
        """Show eval health: recall ranking quality (feedback + goldens), label-free
        self-retrieval health, and how many eval cases exist."""
        recall_cases = evalset.load_all_recall_cases(deps.store)
        return {
            "recall": ev.score_recall(deps.store, deps.search_backend, recall_cases),
            "self_retrieval": ev.self_retrieval(deps.store, deps.search_backend),
            "recall_cases": len(recall_cases),
            "golden_recall_cases": len(evalset.load_golden_recall_cases(deps.store)),
            "extraction_cases": len(evalset.load_extraction_cases(deps.store)),
            "tuned": optimize.load_tuned(deps.store),
        }

    @mcp.tool()
    def memory_add_eval_case(transcript: str, expected_terms: list[str],
                             repo: str | None = None) -> dict:
        """Add an extraction eval case (a sample transcript + key phrases a good
        memory must capture). These drive prompt optimization."""
        n = evalset.add_extraction_case(deps.store, transcript, expected_terms, repo)
        return {"extraction_cases": n}
