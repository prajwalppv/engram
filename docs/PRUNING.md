# Bonsai pruning for memory (engram)

Memory that only ever grows goes stale and noisy. Bonsai masters keep a living
tree sharp, balanced, and true to form **by removing** — and the same principles
map almost one-to-one onto pruning a knowledge/memory graph. This is the design,
grounded in a verified deep-research pass on bonsai technique (sources below).

## The mapping (bonsai principle → engram mechanism)

| Bonsai principle (verified) | engram mechanism (v1) |
|---|---|
| **Apical dominance** — strong tips hoard energy; cut them to redirect growth | **Vigor scoring** (`vigor.py`): each node scored by recall-usage + recency + backlink in-degree + type durability. Low-vigor leaves are pruning targets; recall surfaces high-vigor trunk. |
| **Ramification** — repeatedly cut back to a node to build dense, fine twigging | **Consolidate, don't delete** (`prune.py`): stale session leaves are *folded* per-repo into one denser `SessionDigest`. Compression, not loss. |
| **Jin / shari** — deliberately preserve meaningful deadwood (age, lineage) | **Durable types never auto-pruned** (Decision/Gotcha/Convention…); pruned items are **archived** (`.archive/`, recoverable), never hard-deleted. |
| **Preserve lifelines** — never sever the living vascular path or all above it dies | **Only in-degree-0 nodes are pruned.** Anything other memories link *to* is kept, so no edge is ever orphaned. |
| **The ⅓ rule** — never remove more than ~⅓ of foliage at once; only prune healthy trees | **Bounded per cycle** (`prune_max_fraction`, default 0.25); dry-run by default. |
| **Cut strong zones to feed weak** — balance energy across the tree | Per-repo consolidation targets *over-grown* repos (many stale sessions) while sparse repos are left alone. |
| **Timing / dormancy** — heavy cuts when dormant, so wounds heal before load | Pruning is the "repotting cadence" — run periodically/off-peak, separate from live recall. |
| **Hide scars / no trace** | Pruning in-degree-0 nodes leaves no dangling references; the graph reads as if always that shape. |

## What makes it novel (the patent-worthy core)
Existing memory systems mostly **delete by recency/TTL or cap by size**. engram's
pruner combines, as one loop:
1. **multi-signal vigor** (usage × recency × structural in-degree × type durability),
2. **compression instead of deletion** (ramification — fold a cluster into a denser node),
3. **lifeline + deadwood preservation** (never cut linked-to or durable nodes; archive, never delete),
4. **bounded, reversible cycles**, and
5. **self-tuning aggressiveness via a "resurrection rate"** — an archived memory that
   later has to be restored is a labeled *false-positive*; driving that rate toward 0
   lets the system learn its own safe pruning fraction instead of borrowing bonsai's ⅓ by analogy.

(#5 directly answers the research's own open question: *"is there a principled way to
derive the analogous safe-removal fraction for a memory graph rather than borrowing ⅓?"*)

> Patentability is not guaranteed — that needs a prior-art search + counsel. But the
> combination above, especially resurrection-rate-governed self-tuning compression, is
> genuinely new for memory systems and worth documenting for a filing.

## Measurement (built in, for self-improvement)
Every cycle logs before/after metrics to `.state/prune-history.jsonl`:
- node count, ephemeral count, **average vigor** (sharpness), orphans, archived count.
- `memory_prune_effectiveness` reports the trend + the **resurrection rate** (the key
  quality signal). Demo result: one cycle took 5→4 nodes, ephemeral 4→2, **avg vigor 1.13→1.63**.

This feeds the feedback→prompt-optimizer (next task): the optimizer can tune
`prune_max_fraction`, staleness age, and vigor weights to minimize resurrection rate
while maximizing recall usefulness.

## Tools / commands
- `memory_prune(dry_run=True)` — plan + before/after metrics (apply with `dry_run=false`).
- `memory_restore(identifier)` — un-archive (and log the resurrection signal).
- `memory_prune_effectiveness()` — trend + resurrection rate.
- `/engram:prune` — dry-run preview, then asks before applying.

## Honest caveats (from the research)
- The ⅓ figures are bonsai *heuristics*, not laws — which is exactly why engram makes
  the fraction **measured and self-tuned**, not fixed.
- v1 consolidates *session* leaves only (the fastest-bloating, lowest-value class).
  Semantic near-duplicate merging across all types, and "defoliation" (forced refresh of
  stale node bodies), are natural v2 extensions.

## Sources (verified, 3-0 unless noted)
- Bonsai Empire — pruning, defoliation, calendar: https://www.bonsaiempire.com/basics/styling/pruning
- Wikipedia — Bonsai aesthetics; Deadwood techniques (jin/shari, lifelines): https://en.wikipedia.org/wiki/Deadwood_bonsai_techniques
- EvergreenGardenWorks — branch-selection rules (one-per-position, ⅓ caliper): https://www.evergreengardenworks.com/rules.htm
- bonsai-science.com — ramification & apical dominance physiology
- Big Think — "reveal the trunk / no trace of the artist": https://bigthink.com/thinking/bonsai-tree-care-secret-philosophy/
