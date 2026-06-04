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
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")  # keep the demo output (and any GIF) clean

STORE = Path(os.environ.setdefault(
    "ENGRAM_STORE_DIR", "/tmp/engram-demo")).expanduser()
os.environ.setdefault("ENGRAM_SEARCH_BACKEND", "semantic")
# Keep the embedding-model cache OUTSIDE the throwaway store, so wiping the store
# each run doesn't force a re-download (and a recording warmup actually sticks).
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH", str(Path.home() / ".cache" / "engram-demo-model"))
# Keep the recording clean: no HF progress bars / warnings / tokenizer noise.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def slow(line: str = "", pause: float = 0.35) -> None:
    print(line)
    sys.stdout.flush()
    time.sleep(pause)


def _excerpt(memory, store, rel_path: str, n: int = 86) -> str:
    """First real line of a remembered note's body (skip heading + datestamp)."""
    try:
        body = memory.read(store, rel_path).body or ""
    except Exception:
        return ""
    for ln in body.splitlines():
        s = ln.strip()
        if s and not s.startswith("#") and not s.startswith("_") and not s.startswith("**"):
            return s if len(s) <= n else s[: n - 1].rstrip() + "…"
    return ""


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

    slow("🧠 engram — Claude Code remembers the things that bite you\n", 0.7)

    # --- Session 1: a hard week on the checkout service -----------------------
    slow("── Session 1 · last sprint · repo: checkout-service ─────────────", 0.5)
    seed = [
        ("Gotcha", "Payment webhook double-charged 1,400 customers (PROD-142)",
         "Synchronous retries on the Stripe webhook double-charged 1,400 customers "
         "on 2026-05-12. NEVER retry the webhook inline — dedupe on event.id and "
         "process async."),
        ("Decision", "Idempotency-Key required on every write endpoint",
         "All POST/PUT take an Idempotency-Key header, stored in processed_requests "
         "to short-circuit retries. Added after a load test produced duplicate orders."),
        ("Gotcha", "orders↔inventory deadlock under concurrent checkout",
         "Concurrent checkouts deadlock on the orders/inventory FK. Always acquire "
         "row locks in ascending id order."),
        ("Decision", "Postgres over Mongo for checkout",
         "Need multi-row transactions for cart→order and strong inventory "
         "consistency. Mongo's eventual consistency caused oversells in the prototype."),
        ("Convention", "Money in integer cents; timestamps in UTC ISO-8601",
         "Never floats for currency — store/compute in integer cents, format at the "
         "UI edge. All timestamps stored UTC, ISO-8601."),
        ("Constraint", "PCI — full card numbers never touch logs",
         "Mask PAN to last-4 everywhere; full card data never enters logs, traces, "
         "or memory. Audited quarterly."),
    ]
    for type_, title, body in seed:
        memory.save(store, role, type_=type_, title=title, body=body,
                    repo="checkout-service", search_backend=backend)
        slow(f"   ✍️  [{type_}]  {title}", 0.3)

    slow("\n   (session ends — normally Claude forgets every line of this)\n", 0.8)

    # --- Session 2: a new feature, weeks later, blank-slate Claude ------------
    slow("── Session 2 · today · new feature: subscription renewals ───────", 0.5)
    slow("   …a brand-new session. engram recalls by MEANING, fully on-device:\n", 0.6)

    asks = [
        ("I'll add automatic retries to the renewal payment call — anything I should know?",
         "🛑 stops you re-causing the May-12 incident"),
        ("how do we keep a write endpoint safe if the client calls it twice?", ""),
        ("what's our rule for storing money amounts and timestamps?", ""),
        ("are we allowed to log a customer's full credit-card number?", ""),
    ]
    shown: set[str] = set()
    for q, why in asks:
        slow(f"   you ▸ {q}", 0.6)
        # Surface the most relevant memory we haven't shown yet — so each
        # question recalls a DIFFERENT crucial fact from the prior session.
        hits = memory.recall(store, backend, q, repo="checkout-service", limit=4)
        h = next((x for x in hits if x.rel_path not in shown), hits[0] if hits else None)
        if h:
            shown.add(h.rel_path)
            slow(f"      ↳ [{h.type}] {h.title}  ·  {h.score:.2f}", 0.35)
            ex = _excerpt(memory, store, h.rel_path)
            if ex:
                slow(f"        “{ex}”", 0.3)
            if why:
                slow(f"        {why}", 0.45)
        slow("", 0.15)

    slow("→ Different words, surfaced by meaning. The incident, the conventions,", 0.4)
    slow("  the constraints — carried across sessions so they're never relearned.", 0.6)
    slow("\n🔒 Everything stayed on this machine. No server, no account, no telemetry.",
         0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
