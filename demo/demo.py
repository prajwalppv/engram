#!/usr/bin/env python3
"""A tiny, self-contained demo of engram's value: Claude Code remembers across
sessions — privately, on your machine.

It writes to a throwaway store ($ENGRAM_STORE_DIR or /tmp/engram-demo) so it's
clean and repeatable, and uses the real engram core (same code the plugin runs).
Drive it from the repo root:  uv run python demo/demo.py
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

STORE = Path(os.environ.setdefault(
    "ENGRAM_STORE_DIR", "/tmp/engram-demo")).expanduser()
os.environ.setdefault("ENGRAM_SEARCH_BACKEND", "semantic")
# Keep the recording clean: no HF progress bars / warnings / tokenizer noise.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def slow(line: str = "", pause: float = 0.5) -> None:
    print(line)
    sys.stdout.flush()
    time.sleep(pause)


def main() -> int:
    # Fresh store each run so the demo is deterministic.
    if STORE.exists():
        shutil.rmtree(STORE, ignore_errors=True)
    STORE.mkdir(parents=True, exist_ok=True)

    from engram.config import load_settings
    from engram.core import memory
    from engram.core.roles import current_role
    from engram.core.search_backends import build_backend
    from engram.core.store import FileSystemBackend, Store

    settings = load_settings()
    store = Store(FileSystemBackend(settings.resolved_store()))
    backend = build_backend(settings, store)
    role = current_role(store, settings.role)

    slow("🧠 engram — Claude Code that remembers across sessions\n", 0.8)

    # --- Monday: you make durable decisions while working ---------------------
    slow("── Monday · repo: checkout-service ──────────────────────────────", 0.6)
    seed = [
        ("Decision", "Use Postgres over Mongo for checkout",
         "Chose Postgres: we need multi-row transactions for the cart→order "
         "flow and strong consistency on inventory. Mongo's eventual "
         "consistency bit us in the prototype."),
        ("Gotcha", "Stripe webhooks must be idempotent",
         "Stripe retries webhooks; dedupe on event.id or you double-charge. "
         "We key on the PaymentIntent id in the `processed_events` table."),
        ("Convention", "Money is always integer cents",
         "Never floats for currency. Store/compute in integer cents; format "
         "only at the UI boundary."),
    ]
    for type_, title, body in seed:
        memory.save(store, role, type_=type_, title=title, body=body,
                    repo="checkout-service", search_backend=backend)
        slow(f"   ✍️  remembered  [{type_}]  {title}", 0.45)

    slow("\n   (session ends — Claude would normally forget all of this)\n", 0.9)

    # --- A week later: brand-new session, you ask a fuzzy question ------------
    slow("── The next week · brand-new session ───────────────────────────", 0.6)
    query = "which database did we go with for the cart and why?"
    slow(f"   you ▸ {query}\n", 0.8)
    slow("   engram recalls (semantic match, fully on-device):", 0.5)

    hits = memory.recall(store, backend, query, repo="checkout-service", limit=3)
    for h in hits:
        slow(f"      • [{h.type}] {h.title}   ·  score {h.score:.2f}", 0.5)

    slow("")
    slow("   → Claude answers with YOUR prior decision — no re-explaining.", 0.7)
    slow("\n🔒 Everything stayed on this machine. No server, no account, no telemetry.",
         0.4)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
