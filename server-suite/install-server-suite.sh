#!/bin/bash
# Pi Server Suite installer (Raspberry Pi 5 / Pi 500, Raspberry Pi OS Bookworm or newer)
#
#   bash install-server-suite.sh            pick the apps you want (asks before each one)
#   bash install-server-suite.sh --all      install the apps without asking (still asks about the Task Manager
#                                           and WiFi Share, which change the whole Pi)
#   bash install-server-suite.sh --hub-only just the Server Room hub (used by Set Up My Apps.sh)
#
# Adds a Desktop icon and a menu entry for Server Room and each app you pick. Apps that run all the
# time (PiMesh, PodDeck, RAID Watch, the Task Manager web page) use their own installers.
# Nothing here changes your SSH, firewall or update settings - the Server Room check-up shows you
# the commands for that, and you decide.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
APPS="$ROOT/apps"
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
MENU="$HOME/.local/share/applications"
MODE="${1:-}"
mkdir -p "$DESK" "$MENU"

say()  { printf '%s\n' "$*"; }
ask() {   # ask "question [y/N] " default
  [ "$MODE" = "--all" ] && return 0
  local a
  if [ ! -t 0 ]; then return 1; fi
  read -r -p "$1" a || a=""
  a="${a:-$2}"
  case "$a" in [Yy]*) return 0 ;; *) return 1 ;; esac
}
# ask_big: for things that change the whole Pi - always asks, even with --all (no keyboard = no)
ask_big() {
  local a
  if [ ! -t 0 ]; then return 1; fi
  read -r -p "$1" a || a=""
  case "${a:-n}" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

# launcher <file-id> <Name> <Comment> <Exec> <Path> <Icon> <Terminal true|false> <Categories>
launcher() {
  local body="[Desktop Entry]
Type=Application
Name=$2
Comment=$3
Exec=$4
Path=$5
Icon=$6
Terminal=$7
Categories=$8"
  printf '%s\n' "$body" > "$MENU/$1.desktop"
  printf '%s\n' "$body" > "$DESK/$2.desktop"
  chmod +x "$MENU/$1.desktop" "$DESK/$2.desktop"
  gio set "$DESK/$2.desktop" metadata::trusted true 2>/dev/null || true
}

BROWSER=""
for b in chromium-browser chromium firefox x-www-browser; do
  if command -v "$b" >/dev/null 2>&1; then BROWSER="$b"; break; fi
done
[ -z "$BROWSER" ] && BROWSER="xdg-open"

MODEL="$(tr -d '\0' 2>/dev/null </proc/device-tree/model || echo "this computer")"
ARCH="$(uname -m)"
say
say "  PI SERVER SUITE  -  for $MODEL"
say "  ------------------------------------------------------------"
case "$MODEL" in
  *"Pi 5"*|*"Pi 500"*) ;;
  *) say "  Note: the suite is made for the Raspberry Pi 5 and Pi 500. Most of it works on a Pi 4 too." ;;
esac

# ---------------------------------------------------------------- Server Room (always)
SR="$HERE"
chmod +x "$SR/server-room.py" 2>/dev/null || true
launcher "server-room" "Server Room" "Pi Server Suite hub: server check-up and every suite app" \
  "python3 \"$SR/server-room.py\" --open" "$SR" "$SR/server-room.png" false "System;Monitor;"
STARTED=""
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/server-room.service" <<EOS
[Unit]
Description=Server Room (Pi Server Suite hub, http://127.0.0.1:8410)

[Service]
ExecStart=/usr/bin/env python3 "$SR/server-room.py"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOS
  systemctl --user daemon-reload || true
  systemctl --user enable server-room.service >/dev/null 2>&1 || true
  systemctl --user restart server-room.service && STARTED=1
fi
if [ -z "$STARTED" ]; then
  mkdir -p "$HOME/.config/autostart"
  printf '%s\n' "[Desktop Entry]
Type=Application
Name=Server Room helper
Exec=python3 \"$SR/server-room.py\"
NoDisplay=true
X-GNOME-Autostart-enabled=true" > "$HOME/.config/autostart/server-room.desktop"
  nohup python3 "$SR/server-room.py" >/dev/null 2>&1 &
fi
say "  Server Room: installed (starts with the Pi, only this Pi can open it)."

[ "$MODE" = "--hub-only" ] && exit 0

# ---------------------------------------------------------------- the apps
say
say "  Now pick the apps. Press Enter to skip one."
say

# RAID Forge + RAID Watch
RF="$APPS/raidforge"
if [ -f "$RF/raidforge.py" ] && ask "  RAID Forge - set up RAID on your drives (+ RAID Watch alarm)? [Y/n] " y; then
  chmod +x "$RF/raidforge.py" "$RF/install.sh" 2>/dev/null || true
  launcher "raidforge" "RAID Forge" "Build and manage RAID 0/1/5/6/10 arrays" "python3 \"$RF/raidforge.py\"" "$RF" "$RF/raidforge.svg" false "System;Utility;"
  printf '%s\n' "[Desktop Entry]
Type=Application
Name=RAID Forge (Demo)
Comment=Try RAID Forge with pretend drives - changes nothing
Exec=python3 \"$RF/raidforge.py\" --demo
Path=$RF
Icon=$RF/raidforge.svg
Terminal=false
Categories=System;Utility;" > "$MENU/raidforge-demo.desktop"
  if ! python3 -c "import tkinter" 2>/dev/null || ! command -v mdadm >/dev/null 2>&1 || ! command -v smartctl >/dev/null 2>&1; then
    say "    It needs python3-tk, mdadm and smartmontools. You'll be asked for your password."
    sudo apt-get install -y --no-install-recommends python3-tk mdadm smartmontools \
      || say "    Note: that didn't finish. Try:  sudo apt-get install python3-tk mdadm smartmontools"
  fi
  say "    Done. Try 'RAID Forge (Demo)' in the menu first - it uses pretend drives."
fi

# PiDirStat
PD="$APPS/pidirstat"
if [ -f "$PD/pidirstat.py" ] && ask "  PiDirStat - see what's filling your drives? [Y/n] " y; then
  chmod +x "$PD/pidirstat.py" 2>/dev/null || true
  launcher "pidirstat" "PiDirStat" "See what's filling up your drives" "python3 \"$PD/pidirstat.py\" / --open" "$PD" "$PD/pidirstat-icon.png" true "System;Utility;"
fi

# PodDeck
PK="$APPS/poddeck"
if [ -f "$PK/poddeck.py" ]; then
  if [ "$ARCH" != "aarch64" ]; then
    say "  PodDeck: skipped - it needs 64-bit Raspberry Pi OS (this one is $ARCH)."
  elif ask "  PodDeck - run containers (Uptime Kuma, File Browser...) with a control panel? [Y/n] " y; then
    chmod +x "$PK"/*.sh "$PK/poddeck.py" 2>/dev/null || true
    launcher "poddeck" "PodDeck" "Control panel for Podman containers" "bash \"$PK/start-poddeck.sh\"" "$PK" "$PK/poddeck-icon.png" true "System;Utility;"
    if ask "    Install Podman and start PodDeck with the Pi now? [Y/n] " y; then
      bash "$PK/install.sh" || say "    Note: PodDeck didn't finish. Try:  bash \"$PK/install.sh\""
    fi
  fi
fi

# NetSentry
NS="$APPS/netsentry"
if [ -f "$NS/netsentry.py" ] && ask "  NetSentry - watch the network for intruders? [Y/n] " y; then
  chmod +x "$NS/netsentry.py" "$NS/start-netsentry.sh" 2>/dev/null || true
  launcher "netsentry" "NetSentry" "Real-time network watchdog - spots intruders and suspicious devices" "python3 \"$NS/netsentry.py\"" "$NS" "$NS/netsentry-icon.png" true "Network;"
fi

# NetPulse
NP="$APPS/netpulse"
if [ -f "$NP/netpulse.py" ] && ask "  NetPulse - up/down board and ping graphs for your devices? [Y/n] " y; then
  chmod +x "$NP/netpulse.py" "$NP/start-netpulse.sh" 2>/dev/null || true
  command -v ping >/dev/null 2>&1 || sudo apt-get install -y iputils-ping || true
  launcher "netpulse" "NetPulse" "Network monitor - up/down board and ping graphs" "python3 \"$NP/netpulse.py\"" "$NP" "$NP/netpulse-icon.png" true "Network;"
fi

# WiFi Share
WS="$APPS/wifi-share"
if [ -f "$WS/wifi_share.py" ] && ask_big "  WiFi Share - share Wi-Fi out of the Ethernet port? [y/N] "; then
  chmod +x "$WS/wifi_share.py" 2>/dev/null || true
  command -v nmcli >/dev/null 2>&1 || say "    Note: WiFi Share needs NetworkManager (raspi-config > Advanced Options > Network Config)."
  python3 -c "import tkinter" 2>/dev/null || sudo apt-get install -y python3-tk || true
  launcher "wifi-share" "WiFi Share" "Share Wi-Fi to the Ethernet port and see who's connected" "python3 \"$WS/wifi_share.py\"" "$WS" "$WS/wifi-share-icon.png" false "Network;"
fi

# PiMesh
PM="$APPS/pimesh"
if [ -f "$PM/pimesh.py" ] && ask "  PiMesh - link all your Pis into one dashboard? [Y/n] " y; then
  chmod +x "$PM"/*.sh "$PM/pimesh.py" 2>/dev/null || true
  say "    Use the SAME mesh name and key on every Pi. You'll be asked for your password."
  sudo bash "$PM/install.sh" || say "    Note: PiMesh didn't finish. Try:  sudo bash \"$PM/install.sh\""
fi

# Task Manager
TM="$APPS/task-manager"
if [ -f "$TM/install.sh" ]; then
  say "  RPi500+ Task Manager: Windows-style Task Manager, phone web page and 'Update everything'."
  say "    It changes the whole Pi: turns on VNC, boots to the desktop and adds a backup hotspot"
  say "    (only when there's no network). Skip it on a headless server."
  if ask_big "    Install it? [y/N] "; then
    chmod +x "$TM"/*.sh "$TM/rpi500_taskmgr.py" 2>/dev/null || true
    sudo bash "$TM/install.sh" || say "    Note: it didn't finish. Try:  sudo bash \"$TM/install.sh\""
  fi
fi

# Blueprint Wiki
BW="$APPS/blueprint-wiki"
if [ -f "$BW/server.py" ] && ask "  Blueprint Wiki - write down how your server is set up? [Y/n] " y; then
  chmod +x "$BW/server.py" "$BW/start.sh" "$BW/install-pi.sh" 2>/dev/null || true
  launcher "blueprint-wiki" "Blueprint Wiki" "Your wiki for projects, networks and prototypes" "bash \"$BW/start.sh\"" "$BW" "$BW/blueprint-wiki-icon.png" false "Office;Development;"
fi

# Latch
LT="$APPS/latch"
if [ -f "$LT/index.html" ] && ask "  Latch - offline password safe for all your server passwords? [Y/n] " y; then
  launcher "latch" "Latch" "Offline password safe" "$BROWSER \"$LT/index.html\"" "$LT" "$ROOT/thumbs/latch.jpg" false "Utility;Security;"
fi

# Pi OS: don't ask "Execute?" every time a launcher is double-clicked
f="$HOME/.config/libfm/libfm.conf"
if [ -f "$f" ] && ! grep -q '^quick_exec=1' "$f" && grep -q '^\[config\]' "$f"; then
  sed -i '/^\[config\]/a quick_exec=1' "$f"
fi

say
say "  All set! Double-click 'Server Room' on the Desktop."
say "  Start with the Server check-up tab - it shows what to fix first."
say "  The Shelf (home-network hub) installs on its own: github.com/hardwaremack-prog/the-shelf"
say
python3 "$SR/server-room.py" --open >/dev/null 2>&1 &
sleep 2
