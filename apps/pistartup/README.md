# PiStartup

See everything that starts with your Raspberry Pi and switch it off or back on.

![PiStartup](screenshot.png)

- **Desktop autostart apps**, plus your labwc / LXDE / Wayfire autostart lines
- **@reboot jobs** in your crontab
- **System and user services**, with how long each took at the last boot (filter: *Slowest at boot*)
- **/etc/rc.local** commands (shown, read-only)

Double-click a row (or use the button) to turn it off or on. Core desktop and system pieces are locked, and risky ones (SSH, Wi-Fi, VNC, sound...) ask first. Before it first edits one of your autostart files it saves a `.pistartup.bak` copy. Desktop changes apply at your next login, services at the next boot, and everything can be switched back on from the *Switched off* filter.

## Install
```bash
bash install.sh      # adds it to Menu > Preferences and the Desktop
```
Run once without installing: `python3 pistartup.py`. Remove: `bash uninstall.sh`.

Part of the [Pi Server Suite](https://github.com/hardwaremack-prog/pi-server-suite).
