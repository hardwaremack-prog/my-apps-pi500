#!/bin/sh
# Dead Mall Arena - join a game someone else is hosting on your network
#   ./join-game.sh 192.168.1.20
HOST="$1"
if [ -z "$HOST" ]; then
  printf "Address shown in the host's server window (like 192.168.1.20:8090): "
  read HOST
fi
[ -z "$HOST" ] && exit 1
case "$HOST" in *:*) URL="http://$HOST/" ;; *) URL="http://$HOST:8090/" ;; esac
BROWSER="$(command -v chromium-browser || command -v chromium || command -v google-chrome || command -v firefox)"
case "$BROWSER" in
  *chromium*|*chrome*) "$BROWSER" --ignore-gpu-blocklist --enable-gpu-rasterization --start-fullscreen --no-first-run --app="$URL" >/dev/null 2>&1 ;;
  *) "$BROWSER" "$URL" ;;
esac
