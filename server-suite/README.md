# Pi Server Suite

Everything you need to run a Raspberry Pi 5 or Pi 500 as a home server, in one place.
**Server Room** is the hub: a **Running servers** bar at the top shows every web server on the Pi
(and whether other devices can reach it) with a **Stop** button for each, plus a light for every
suite app and a plain-English **Server check-up** that tells you what to fix first.

![Server Room](../thumbs/server-room.jpg)

## The apps

| | App | What it does |
|---|---|---|
| 🩺 | **Server Room** | The hub. Server check-up (about 20 checks) plus Open/Start for every app below. Port 8410, this Pi only. |
| 💽 | **RAID Forge** + RAID Watch | Point-and-click RAID 0/1/5/6/10 on USB drives or a SATA/NVMe HAT, move the system onto the RAID, and get an alarm (and a phone push) if a drive fails. |
| 📊 | **PiDirStat** | See what's filling your drives, WinDirStat-style. |
| 📦 | **PodDeck** | Control panel for Podman containers, with one-click Uptime Kuma, File Browser and more. Port 8070. |
| 🛡️ | **NetSentry** | Live list of every device on your network, with warnings about anything suspicious. |
| 📈 | **NetPulse** | Up/down board for your devices (import IPs from Excel) and ping-over-time graphs. |
| 🔌 | **WiFi Share** | Share the Pi's Wi-Fi out of its Ethernet port. |
| 🕸️ | **PiMesh** | Links all your Pis into one live dashboard. Port 8470. |
| 🧮 | **RPi500+ Task Manager** | Windows-style Task Manager, phone web page and an "Update everything" button. |
| 📘 | **Blueprint Wiki** | Document your server: pages, checklists, PDFs, network maps. |
| 🔐 | **Latch** | Offline password safe for your server, router and container passwords. |
| 🚀 | **PiStartup** | Everything that starts with the Pi, with boot times; switch off what a server doesn't need. |
| ⚡ | **VNC Turbo** | Makes remote desktop fast again: finds the cause and fixes it with one click, all undoable. |
| 🌀 | **Pironman Pilot** | Only on a Pi 5 in a SunFounder Pironman 5 MAX case: OLED, quiet fan curves, side-fan speed control, lights, safe overclocking. |
| 🗂️ | **Tidy Suite** | Hosts the whole Tidy Suite for everyone on your Wi-Fi (port 8780); each person's work is saved on the Pi. |
| 🎙️ | **Pip** | Offline voice assistant for a headset - no internet needed. |
| ✂️ | **PiSnip** | Snipping Tool: screenshots, markup and screen recording. |
| 🗄️ | **The Shelf** | Home-network hub (installs separately: [the-shelf](https://github.com/hardwaremack-prog/the-shelf)). |

## What the check-up looks at

- **Hardware**: temperature, power supply dips and throttling, USB power for drives, fan
- **Storage**: running from the SD card (it wears out), disk space on every drive, RAID health and rebuilds, log size
- **Security**: SSH password logins and root login, fail2ban, firewall, what's open to the network, sudo without a password
- **Updates**: waiting updates (and how many are security fixes), automatic security updates, restart needed, bootloader (EEPROM)
- **Reliability**: clock sync, failed services (switch off what you don't need in PiStartup), freeze protection (hardware watchdog), backups, a fixed address for the Pi

Each problem says what it means and gives a command you can copy. Server Room never changes anything by itself.

## Install

On the Pi, open a Terminal in this folder and run:

```bash
bash server-suite/install-server-suite.sh
```

It adds a **Server Room** icon to the Desktop and menu, starts the hub with the Pi, then asks about each app.
Already using My Apps? `Set Up My Apps.sh` installs Server Room for you, and the suite has its own **Server Suite** tab.

Just want to look? `python3 server-suite/server-room.py --demo --open` runs it with pretend data on any computer.

## Needs

- Raspberry Pi 5 or Pi 500 (most of it works on a Pi 4)
- Raspberry Pi OS Bookworm or newer; PodDeck needs the 64-bit version
- Python 3 (already on Raspberry Pi OS). Server Room uses only the standard library.
