#!/bin/bash
# Removes PiStartup. Anything you switched off stays switched off -
# switch things back on in the app first if you want them back.
rm -rf "$HOME/.local/share/pistartup"
rm -f "$HOME/.local/share/applications/pistartup.desktop" "$HOME/Desktop/pistartup.desktop"
echo "PiStartup removed."
