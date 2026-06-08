---
description: Explain why a recalled memory exists and whether it's still current (provenance)
disable-model-invocation: true
---
The user wants the provenance of a memory — call `memory_why` with the memory's id,
title, or path (the argument the user gave). Then summarize plainly:

- **What it is**: title, type, horizon, scope/repo, the role that captured it.
- **Where it came from**: the `created` date and `source_session` (its origin).
- **Is it still current?** If `retired` is true, say it was **superseded on
  `superseded_on` by `superseded_by`** — so it's history, not the live fact, and
  point the user at the superseding memory. If it `supersedes` other titles, note
  that it replaced them.
- **Graph context**: its `links` and `backlinks` (what it connects to / what
  references it).

Keep it short and trustworthy — the point is to help the user decide whether to
rely on the fact. If the identifier doesn't resolve, say so and suggest
`memory_recall` to find the right title first.
