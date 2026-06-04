---
description: Bonsai-prune memory (dry-run preview by default)
disable-model-invocation: true
---
Call `memory_prune` with dry_run=true and show me the plan: which stale session notes would be folded into per-repo digests, the before/after metrics, and how many nodes would be touched. Then ask me whether to apply it for real (dry_run=false). Also call `memory_prune_effectiveness` and summarize the trend (especially the resurrection rate).
