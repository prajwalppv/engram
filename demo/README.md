# engram demo

A tiny, self-contained demo of engram's core value: **Claude Code remembers
across sessions — privately, on your machine.**

## Run it (prints to your terminal)
```bash
uv run python demo/demo.py
```
It writes to a throwaway store (`/tmp/engram-demo`), seeds a few decisions as if
from a past session, then — in a "new session" — recalls them from a fuzzy,
differently-worded question via local semantic search. The same engram core the
plugin runs; nothing leaves your machine.

## Record the GIF (for the README / marketplace)
Uses [VHS](https://github.com/charmbracelet/vhs):
```bash
brew install vhs          # once
vhs demo/engram.tape      # → writes docs/demo.gif
```
The tape warms the embedding-model cache off-camera, then records the clean run.
Tweak size/theme/speed at the top of `demo/engram.tape`.
