# engram demo — records the cross-session recall loop as a GIF.
#
# Prereq: VHS  (https://github.com/charmbracelet/vhs)  →  brew install vhs
# Record:  vhs demo/engram.tape      (run from the repo root)
# Output:  docs/demo.gif
#
# The embedding model is cached outside the throwaway store (demo.py sets
# FASTEMBED_CACHE_PATH), so the run is fast and the recording is clean.

Output docs/demo.gif

Set Shell bash
Set FontSize 18
Set Width 1320
Set Height 900
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 40ms

# --- off-camera: clean prompt + trigger any uv sync so the visible run is clean.
Hide
Type "export PS1='$ '" Enter
Type "uv run python -c 'pass' >/dev/null 2>&1" Enter
Sleep 20s
Type "clear" Enter
Show

# --- the actual recording (demo runs ~14s; wait for the closing line) ---------
Type "uv run python demo/demo.py" Sleep 400ms Enter
Wait+Screen@90s /telemetry/
Sleep 2s
