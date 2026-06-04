# engram — architecture

engram is a Claude Code **plugin** with two halves: a set of **lifecycle hooks**
that capture and recall memory automatically, and a local **MCP server** that
exposes memory as tools. Both talk to the same vendor-neutral **core**, which
reads and writes a **local knowledge graph** of markdown notes. Nothing leaves
the machine.

---

## 1. Capture & recall lifecycle

Memory is captured at **multiple points** in a session — not just at the end —
so nothing is lost if context is compacted or the terminal is closed abruptly.
Every capture is **incremental and idempotent**: a per-session high-water mark
means each trigger only folds the *new* delta into memory.

```mermaid
flowchart TD
    subgraph CC["Claude Code session"]
        direction TB
        S0(["SessionStart<br/>startup · resume · clear · compact"])
        UP(["UserPromptSubmit"])
        TURN["assistant turn"]
        STOP(["Stop<br/>end of every turn"])
        PC(["PreCompact<br/>before context is summarized away"])
        SE(["SessionEnd<br/>clean exit only — unreliable on kill"])
    end

    S0 -->|recall| R[["engram-hook recall<br/>list_recent for this repo"]]
    R -->|additionalContext| TURN
    UP --> TURN
    TURN --> STOP
    STOP -->|"capture (throttled: ≥ N new turns)"| CAP
    PC -->|"capture (forced flush)"| CAP
    SE -->|"capture (forced flush)"| CAP

    CAP["capture_delta()<br/>only new events since high-water mark"]
    CAP --> HWM[(".state/sessions/&lt;id&gt;.json<br/>high-water mark")]
    CAP --> SUM["summarizer<br/>(claude -p → heuristic fallback)"]
    SUM --> SAVE["memory.save()<br/>typed, linked nodes"]
    SAVE --> STORE[("local store<br/>markdown graph + index")]
    STORE -.->|next session| R

    classDef hook fill:#1f2937,stroke:#60a5fa,color:#e5e7eb;
    classDef work fill:#0f172a,stroke:#34d399,color:#e5e7eb;
    classDef data fill:#111827,stroke:#fbbf24,color:#e5e7eb;
    class S0,UP,STOP,PC,SE hook;
    class R,CAP,SUM,SAVE work;
    class HWM,STORE data;
```

**Why multiple triggers?** `SessionEnd` alone is fragile — it does not reliably
fire when the terminal window is closed, the process is killed, or the OS shuts
down. So engram also captures:

| Trigger | When | Mode | Purpose |
|---|---|---|---|
| `Stop` | end of every assistant turn | throttled (≥ `capture_every_turns` new turns), async | steady incremental capture; durable even if you never exit cleanly |
| `PreCompact` | right before auto/manual compaction | forced flush | **lossless across compaction** — the main silent-loss event in long sessions |
| `SessionEnd` | clean exit (`/exit`, Ctrl-D, `/clear`, logout) | forced flush | final flush of the remaining delta |
| `SessionStart` | start / resume / clear / **compact** | — | recall memory back into context (incl. *after* a compaction) |

---

## 2. The high-water mark (incremental, idempotent)

All three capture triggers funnel through `capture_delta()`, which reads the live
transcript, skips everything already captured, and processes only the new tail.
This is what makes it safe to fire often and from overlapping events.

```mermaid
sequenceDiagram
    participant T as transcript.jsonl
    participant C as capture_delta()
    participant M as high-water mark
    participant G as memory graph

    Note over T,G: turn 3 ends → Stop (throttled, gate=3)
    C->>M: load mark (processed=0)
    C->>T: read events (6)
    C->>C: delta = events[0:6], new user turns = 3 ≥ gate
    C->>G: summarize + save delta
    C->>M: mark = 6

    Note over T,G: turn 4 ends → Stop (only 1 new turn < gate)
    C->>M: load mark (processed=6)
    C->>T: read events (8)
    C->>C: delta = events[6:8], 1 turn < gate → hold
    C-->>M: mark unchanged (6)

    Note over T,G: context fills → PreCompact (forced)
    C->>M: load mark (processed=6)
    C->>T: read events (8)
    C->>G: flush delta events[6:8]
    C->>M: mark = 8
```

Downstream, `memory.save()` also applies **content-hash** and **semantic** dedup,
so even if the same delta is processed twice (e.g. a `--resume` re-reads an old
transcript), it is merged, never duplicated.

---

## 3. Components & data flow

Two adapters (hooks + MCP) over one core over one local store. The core has **no**
MCP or vendor imports — every external concern is a swappable seam.

```mermaid
flowchart LR
    subgraph Claude["Claude Code"]
        H["lifecycle hooks"]
        MCPc["MCP client"]
    end

    subgraph Plugin["engram plugin (on-device)"]
        direction TB
        HK["hookcli<br/>recall · capture · precompact · ingest"]
        SRV["MCP server<br/>20 tools (stdio)"]
        subgraph Core["core/ (vendor-neutral)"]
            MEM["memory · graph"]
            CAP["capture · checkpoint"]
            SUMM["summarizer (seam)"]
            SB["search_backends (seam)"]
            PR["prune (bonsai) · vigor"]
            OPT["optimize · feedback · evalset"]
            ROL["roles (Profile seam)"]
        end
        ST[("local store<br/>markdown + wikilinks<br/>.index/ · .state/")]
    end

    H --> HK
    MCPc --> SRV
    HK --> Core
    SRV --> Core
    Core --> ST
    SUMM -.->|"claude -p (the model you already run)"| Claude

    classDef ext fill:#1f2937,stroke:#60a5fa,color:#e5e7eb;
    classDef core fill:#0f172a,stroke:#34d399,color:#e5e7eb;
    classDef data fill:#111827,stroke:#fbbf24,color:#e5e7eb;
    class H,MCPc ext;
    class HK,SRV,MEM,CAP,SUMM,SB,PR,OPT,ROL core;
    class ST,Plugin core;
    class ST data;
```

**Privacy boundary:** the only thing that ever leaves the plugin is a local
`claude -p` call for summarization — the same model binary the developer already
runs. Memory itself (markdown, index, state) is plain files on the local disk.
There is no network/server/auth code in engram at all.

### Swappable seams
| Seam | Default | Swap to |
|---|---|---|
| `search_backends` | semantic (fastembed/ONNX, local) | text (zero-dep) |
| `summarizer` | `claude -p` (LLM) | heuristic (no-LLM) |
| roles (`Profile`) | swe / pm / em / generic | any via the `engram.roles` entry-point |
| storage | local filesystem | the `StorageBackend` protocol |

---

## 4. Self-improvement loop
Captured memory is not static. A feedback signal (was a recalled memory used,
edited, or rejected?) tunes the inferred role weights and the extraction prompt,
while **bonsai pruning** consolidates stale notes and self-tunes its own
aggressiveness from a measured *resurrection rate*. See [PRUNING.md](PRUNING.md).
