---
description: Save or recall a runbook / procedure (how we do X) in engram
disable-model-invocation: true
---
The user wants to capture or look up a **procedure / runbook** ("how we deploy",
"the release steps", "how to set up the dev env").

- To **save** one: call `memory_save` with `type: "Procedure"`, `horizon: "procedural"`,
  a clear `title` (e.g. "Runbook: deploy checkout-service"), the ordered steps in
  `body`, and `repo` if it's project-specific. If you're updating an existing runbook,
  reuse the same title (engram appends the new version and keeps the prior one).
- To **recall** one: call `memory_recall` with the task (e.g. "how do we deploy").

engram also captures runbooks automatically when you spell out a process with steps,
so often you won't need this. Procedures are durable and never auto-pruned.

$ARGUMENTS
