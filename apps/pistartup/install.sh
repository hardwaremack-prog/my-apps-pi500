#!/bin/bash
# PiStartup installer - adds PiStartup to the menu (Preferences) and the Desktop.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/.local/share/pistartup"

echo "Installing PiStartup..."
if ! python3 -c "import tkinter" 2>/dev/null; then
  echo "Installing python3-tk (needs sudo)..."
  sudo apt-get update && sudo apt-get install -y python3-tk
fi

mkdir -p "$APP_DIR" "$HOME/.local/share/applications"
cp "$HERE/pistartup.py" "$HERE/pistartup.svg" "$APP_DIR/"
chmod +x "$APP_DIR/pistartup.py"

cat > "$HOME/.local/share/applications/pistartup.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PiStartup
Comment=See and switch off the apps and services that start with your Pi
Exec=python3 $APP_DIR/pistartup.py
Icon=$APP_DIR/pistartup.svg
Categories=Settings;System;
Terminal=false
EOF

if [ -d "$HOME/Desktop" ]; then
  cp "$HOME/.local/share/applications/pistartup.desktop" "$HOME/Desktop/"
  chmod +x "$HOME/Desktop/pistartup.desktop"
fi

echo "Done! Open it from Menu > Preferences > PiStartup (or the Desktop icon)."
echo "Or run:  python3 $APP_DIR/pistartup.py"
