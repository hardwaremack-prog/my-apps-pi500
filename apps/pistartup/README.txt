PiStartup - see everything that starts with your Raspberry Pi and switch it off/on

Install:   bash install.sh      (adds it to Menu > Preferences and the Desktop)
Run once:  python3 pistartup.py
Remove:    bash uninstall.sh

What it shows:
  - Desktop autostart apps, and your labwc / LXDE / Wayfire autostart lines
  - @reboot jobs in your crontab
  - System and user background services, with how long each took at last boot
  - /etc/rc.local commands (read-only)

Double-click a row (or use the button) to turn it off or on. Core desktop and
system pieces are locked, and risky ones (SSH, Wi-Fi, VNC, sound...) ask first.
Desktop changes apply at next login, services at next boot. Everything can be
switched back on from the "Switched off" filter.
