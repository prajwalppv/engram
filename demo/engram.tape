# engram demo — records the cross-session recall loop as a GIF.
#
# Prereq: VHS  (https://github.com/charmbracelet/vhs)  →  brew install vhs
# Record:  vhs demo/engram.tape      (run from the repo root)
# Output:  docs/demo.gif
#
# The first run downloads the embedding model (~once). The Hide/Show block below
# warms it off-camera so the recording itself is clean.

Output docs/demo.gif

Set Shell bash
Set FontSize 18
Set Width 1180
Set Height 760
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 40ms

# --- warm the model cache off-camera so the GIF has no download noise ---------
Hide
Type "uv run python demo/demo.py > /dev/null 2>&1" Enter
Wait@180s
Type "clear" Enter
Show

# --- the actual recording ----------------------------------------------------
Type "uv run python demo/demo.py" Sleep 400ms Enter
Wait@120s
Sleep 3s
