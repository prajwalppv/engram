---
description: Self-improve engram (tune pruning + optimize the extraction prompt)
---
Run the self-improvement pass:
1. Call `memory_eval_status` and summarize recall quality + eval-case counts.
2. Call `memory_tune_prune` and report whether prune aggressiveness changed and why.
3. Call `memory_optimize_prompt` with dry_run=true and report the base vs candidate score; if the candidate wins, ask me before applying (dry_run=false).
