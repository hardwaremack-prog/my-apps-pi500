#!/bin/sh
# Dead Mall Arena - Raspberry Pi 500 / Pi 5
# Starts the LAN server in a terminal window and opens the game in Chromium.
# The server keeps running until you close that terminal window (or press Ctrl+C in it),
# even if Chromium was already open.
cd "$(dirname "$0")" || exit 1

# double-clicked with "Execute" (no terminal)? reopen ourselves in a terminal window
if [ ! -t 1 ] && [ -z "$DMA_IN_TERMINAL" ]; then
  export DMA_IN_TERMINAL=1
  for term in lxterminal x-terminal-emulator xfce4-terminal gnome-terminal xterm; do
    if command -v "$term" >/dev/null 2>&1; then
      case "$term" in
        gnome-terminal) exec gnome-terminal -- sh "$PWD/start-pi.sh" ;;
        *) exec "$term" -e sh "$PWD/start-pi.sh" ;;
      esac
    fi
  done
  # no terminal program found: carry on without one
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is needed:  sudo apt install python3"
  printf "Press Enter to close..."; read _; exit 1
fi

rm -f server-port.txt
python3 server.py --port "${PORT:-8090}" &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; exit 0' INT TERM HUP

# wait (up to 10 s) for the server to report which port it got
i=0
while [ ! -s server-port.txt ] && [ $i -lt 40 ]; do
  if ! kill -0 $SERVER 2>/dev/null; then
    echo; echo "The server could not start (see the message above)."
    printf "Press Enter to close..."; read _; exit 1
  fi
  sleep 0.25; i=$((i+1))
done
GOTPORT="$(cat server-port.txt 2>/dev/null)"
[ -z "$GOTPORT" ] && GOTPORT="${PORT:-8090}"
URL="http://localhost:$GOTPORT/"

BROWSER="$(command -v chromium-browser || command -v chromium || command -v firefox)"
if [ -z "$BROWSER" ]; then
  echo "No browser found. Open $URL in your browser."
else
  # launched in the background: if Chromium is already open it just adds a window and returns,
  # and that must not stop the server
  case "$BROWSER" in
    *chromium*) "$BROWSER" --ignore-gpu-blocklist --enable-gpu-rasterization \
                  --no-first-run --start-maximized --app="$URL" >/dev/null 2>&1 & ;;
    *) "$BROWSER" "$URL" >/dev/null 2>&1 & ;;
  esac
  echo "  Opening the game at $URL"
fi
echo "  Close this window when you're done playing."
wait $SERVER
