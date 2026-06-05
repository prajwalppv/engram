---
description: Show engram memory + inferred-role status, and manage learned preferences
disable-model-invocation: true
---
Call `engram_info`, `role_status`, and `memory_list_preferences`, then give a short summary:
- store location, total memories, and the search backend;
- the active role with the soft weights over roles, and how many sessions have been observed;
- the **standing preferences** engram has learned (the always-on layer) — list each one.

If the user asks to remove/forget a preference (or one looks wrong or stale), call
`memory_forget` with its id or title to remove it (recoverable). Mention that preferences
are injected every session and also written to a managed block in CLAUDE.md.
