# engram demo — records the cross-session recall loop as a GIF.
#
# Prereq: VHS  (https://github.com/charmbracelet/vhs)  →  brew install vhs
# Record:  vhs demo/engram.tape      (run from the repo root)
# Output:  docs/demo.gif
#
# The embedding model is cached outside the throwaway store (demo.py sets
# FASTEMBED_CACHE_PATH), so the Hide/Show warmup below sticks and the recorded
# run is fast and clean.

Output docs/demo.gif

Set Shell bash
Set FontSize 18
Set Width 1180
Set Height 760
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 40ms

# --- off-camera: clean prompt + warm uv sync and the model cache --------------
Hide
Type "export PS1='$ '" Enter
Type "uv sync >/dev/null 2>&1; uv run python demo/demo.py >/dev/null 2>&1" Enter
Sleep 75s
Type "clear" Enter
Show

# --- the actual recording ----------------------------------------------------
Type "uv run python demo/demo.py" Sleep 400ms Enter
Wait+Screen@120s /telemetry/
Sleep 2s
