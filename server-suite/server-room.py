#!/usr/bin/env python3
"""
Server Room - the hub of the Pi Server Suite (Raspberry Pi 5 / Pi 500).

  * Server Check-up: ~20 plain-English checks every Pi server should pass
    (power, heat, boot drive, disk space, RAID, SSH, firewall, updates,
    time sync, failed services, watchdog, backups...). Each problem comes
    with what it means and a command you can copy to fix it.
    Nothing is ever changed for you.
  * Suite apps: a green/red light for every app in the suite, Open when
    it's running, Start when it isn't.

Run:   python3 server-room.py            (then open http://127.0.0.1:8410)
       python3 server-room.py --open     (and open the browser)
       python3 server-room.py --demo     (pretend data, for trying it on a PC)
It only listens on 127.0.0.1, so only this Pi can reach it.
Standard library only - no pip installs.
"""
import argparse, glob, http.client, json, os, re, shutil, socket, subprocess, sys, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import servers as SRV   # running web servers: find them and stop them
ROOT = os.path.dirname(HERE)                      # the folder that holds server-suite/ and apps/
PORT = int(os.environ.get("SERVER_ROOM_PORT", "8410"))
VERSION = "1.1"
DEMO = False

# ------------------------------------------------------------------ the suite's apps
# id, desktop launcher id, ports to look on, page-title pattern (so two apps on 8080 aren't mixed up),
# systemd unit (for always-on services), folder under apps/ that may be served to the browser
APPS = [
    dict(id="raidforge", desktop="raidforge", ports=[8484], title=r"raid", folder="raidforge"),
    dict(id="poddeck", desktop="poddeck", ports=[8070], title=r"poddeck", folder="poddeck"),
    dict(id="pimesh", desktop="", ports=[8470], title=r"pimesh", unit="pimesh.service", folder="pimesh"),
    dict(id="netsentry", desktop="netsentry", ports=[8775], title=r"netsentry", folder="netsentry"),
    dict(id="netpulse", desktop="netpulse", ports=[8790, 8791, 8792, 8793, 8794, 8795], title=r"netpulse", folder="netpulse"),
    dict(id="pidirstat", desktop="pidirstat", ports=[8088, 8089, 8090, 9000], title=r"dirstat", folder="pidirstat"),
    dict(id="wiki", desktop="blueprint-wiki", ports=[8080, 8081, 8082, 8083], title=r"blueprint", folder="blueprint-wiki"),
    dict(id="taskmgr", desktop="rpi500-taskmgr", ports=[8090, 8091], title=r"task manager", unit="rpi500-web.service", folder="task-manager"),
    dict(id="wifishare", desktop="wifi-share", ports=[], folder="wifi-share"),
    dict(id="latch", desktop="", ports=[], folder="latch", static=True),
    dict(id="shelf", desktop="", ports=[8080, 8081, 8000], title=r"shelf"),
    dict(id="tidy", desktop="tidy-suite-server", ports=[8780, 8781, 8782], title=r"tidy suite",
         unit="user:tidy-suite.service", root_folder="tidy-suite"),
    dict(id="pip", desktop="pip-voice", ports=[8765], title=r"\bpip\b", folder="pip"),
    dict(id="pilot", desktop="pironman-pilot", ports=[47821, 47822, 47823, 47824], title=r"pironman pilot",
         unit="pironman-pilot.service", folder="pironman-pilot", needs="pironman"),
    dict(id="vncturbo", desktop="vnc-turbo", ports=[], proc="vnc_turbo.py", folder="vnc-turbo"),
    dict(id="pistartup", desktop="pistartup", ports=[], proc="pistartup.py", folder="pistartup"),
    dict(id="pisnip", desktop="pisnip", ports=[], proc="pisnip", folder="pisnip"),
]
APP_BY_ID = {a["id"]: a for a in APPS}

# friendly names for the running-servers bar: (page-title pattern, usual ports, name, systemd unit)
SERVER_NAMES = [
    (r"raid ?watch", [8484], "RAID Watch", None), (r"poddeck", [8070], "PodDeck", "user:poddeck.service"),
    (r"pimesh", [8470], "PiMesh", "pimesh.service"), (r"netsentry", [8775], "NetSentry", None),
    (r"netpulse", [8790], "NetPulse", None), (r"dirstat", [8088], "PiDirStat", None),
    (r"blueprint", [], "Blueprint Wiki", None), (r"task manager", [], "Task Manager web page", "rpi500-web.service"),
    (r"shelf", [], "The Shelf", None), (r"tidy suite", [8780], "Tidy Suite", "user:tidy-suite.service"),
    (r"\bpip\b", [8765], "Pip", None), (r"pironman pilot", [47821], "Pironman Pilot", "pironman-pilot.service"),
    (r"^\s*dashboard\s*$|pironman ?5", [34001], "Pironman dashboard (SunFounder)", "pironman5.service"),
    (r"halo studio", [8395], "Halo Studio", None), (r"pon lab", [], "PON Lab", "ponlab.service"),
    (r"pon fleet", [], "PON Fleet", "ponfleet.service"), (r"overdrive", [8500], "Overdrive", None),
    (r"uptime kuma", [3001], "Uptime Kuma", None), (r"frostfall", [], "Frostfall Cabins", None),
    (r"dead mall", [], "Dead Mall Arena", None), (r"my apps", [], "My Apps", None),
]
SERVER_UNIT = {n: u for _, _, n, u in SERVER_NAMES if u}
SERVER_WARN = {"Pironman dashboard (SunFounder)": "This is SunFounder's case service: stopping it also stops the case fans, LEDs and OLED until it restarts.",
               "PiMesh": "This Pi drops out of your PiMesh dashboard until it restarts.",
               "Pironman Pilot": "The case falls back to SunFounder's fan settings until it restarts.",
               "Tidy Suite": "Everyone using the Tidy Suite from their phone or PC is cut off until it starts again."}


def running_servers():
    if DEMO:
        return demo_servers()
    d = SRV.scan([(rx, pp, n) for rx, pp, n, _ in SERVER_NAMES])
    for s in d["servers"]:
        if s["name"] in SERVER_WARN:
            s["warn"] = SERVER_WARN[s["name"]]
    return d


_DEMO_SERVERS = [
    dict(port=8070, name="PodDeck", title="PodDeck", proc="python3", local_only=False),
    dict(port=8080, name="Blueprint Wiki", title="Blueprint Wiki", proc="python3", local_only=False),
    dict(port=8470, name="PiMesh", title="PiMesh", proc="python3", local_only=False, warn=SERVER_WARN["PiMesh"]),
    dict(port=8775, name="NetSentry", title="NetSentry", proc="python3", local_only=True),
    dict(port=8780, name="Tidy Suite", title="Tidy Suite", proc="python3", local_only=False, warn=SERVER_WARN["Tidy Suite"]),
    dict(port=3001, name="Uptime Kuma", title="Uptime Kuma", proc="rootlessport", local_only=False),
    dict(port=8410, name="Server Room", title="Server Room", proc="python3", local_only=True, stoppable=False, why=SRV.PROTECTED[8410]),
]


def demo_servers():
    out = []
    for s in _DEMO_SERVERS:
        s = dict(s)
        s.setdefault("stoppable", True)
        s.update(url="http://127.0.0.1:%d/" % s["port"], lan=None if s["local_only"] else "http://192.168.1.50:%d/" % s["port"], status=200)
        out.append(s)
    return {"servers": out, "remote": [dict(port=22, name="SSH"), dict(port=5900, name="VNC")], "ip": "192.168.1.50"}


def stop_server(port):
    if DEMO:
        for s in _DEMO_SERVERS:
            if s["port"] == port and s.get("stoppable", True):
                _DEMO_SERVERS.remove(s)
                return True, "Demo: pretended to stop %s." % s["name"]
        return False, "That one can't be stopped from here."
    cur = next((s for s in running_servers()["servers"] if s["port"] == port), None)
    if not cur:
        return False, "That server isn't running any more."
    if not cur.get("stoppable"):
        return False, cur.get("why") or "That one can't be stopped from here."
    try:
        return SRV.stop(port, cur["name"], SERVER_UNIT.get(cur["name"]))
    except Exception as e:
        return False, "Couldn't stop it: %s" % e
SERVE_FOLDERS = {a["folder"] for a in APPS if a.get("folder")}


def has_pironman():
    """A SunFounder Pironman case: its software or Pironman Pilot is on this Pi."""
    return bool(shutil.which("pironman5") or os.path.exists("/opt/pironman-pilot/pilot.py")
                or os.path.exists("/etc/systemd/system/pironman5.service")
                or os.path.exists("/lib/systemd/system/pironman5.service"))


def run(cmd, timeout=6):
    """Run a command, return (code, stdout). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except Exception:
        return -1, ""


def read(path, default=""):
    try:
        with open(path, "r", errors="replace") as f:
            return f.read()
    except Exception:
        return default


def tcp_open(port, host="127.0.0.1", timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


_title_cache = {}


def page_title(port):
    hit = _title_cache.get(port)
    if hit and time.time() - hit[0] < 20:
        return hit[1]
    title = ""
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=1.2)
        c.request("GET", "/", headers={"User-Agent": "ServerRoom"})
        r = c.getresponse()
        body = r.read(65536).decode("utf-8", "replace")
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        title = m.group(1).strip() if m else ""
        if not title and r.status in (301, 302, 401):
            title = "(sign-in page)"
        c.close()
    except Exception:
        title = ""
    _title_cache[port] = (time.time(), title)
    return title


def unit_active(unit):
    if unit.startswith("user:"):
        code, out = run(["systemctl", "--user", "is-active", unit[5:]], 3)
    else:
        code, out = run(["systemctl", "is-active", unit], 3)
    return out == "active"


def launcher_exists(desktop_id):
    return any(os.path.exists(os.path.join(d, desktop_id + ".desktop"))
               for d in (os.path.expanduser("~/.local/share/applications"), "/usr/share/applications"))


def app_status():
    out = {}
    used = set()
    for a in APPS:
        s = dict(id=a["id"], up=False, url="", installed=False)
        if a.get("needs") == "pironman" and not has_pironman():
            s["hidden"] = True
        if a.get("static"):
            s["installed"] = os.path.exists(os.path.join(ROOT, "apps", a["folder"]))
            out[a["id"]] = s
            continue
        s["installed"] = bool((a.get("desktop") and launcher_exists(a["desktop"]))
                              or (a.get("unit") and run(["systemctl", "cat", a["unit"]], 3)[0] == 0)
                              or (a.get("folder") and os.path.isdir(os.path.join(ROOT, "apps", a["folder"])) and a["id"] != "shelf"))
        for p in a["ports"]:
            if p in used or not tcp_open(p):
                continue
            t = page_title(p)
            if a.get("title") and not re.search(a["title"], t, re.I):
                continue
            s.update(up=True, url="http://%s:%d/" % ("127.0.0.1", p), port=p)
            used.add(p)
            break
        if not s["up"] and a.get("unit") and unit_active(a["unit"]) and a["ports"]:
            s.update(up=True, url="http://127.0.0.1:%d/" % a["ports"][0], port=a["ports"][0])
        prog = a.get("proc") or {"raidforge": "raidforge.py", "wifishare": "wifi_share.py"}.get(a["id"])
        if not s["up"] and prog:
            # desktop windows: running if the program is in the process list
            if run(["pgrep", "-f", prog], 2)[0] == 0:
                s["up"] = True
        out[a["id"]] = s
    return out


def launch(app_id):
    a = APP_BY_ID.get(app_id)
    if not a:
        return False, "Unknown app."
    if a.get("unit") and not a.get("desktop"):
        return False, "%s runs as a background service. Install it with install-server-suite.sh, then it starts with the Pi." % app_id
    d_id = a.get("desktop")
    if not d_id:
        return False, "This one opens in the browser - just click it."
    for d in (os.path.expanduser("~/.local/share/applications"), "/usr/share/applications"):
        path = os.path.join(d, d_id + ".desktop")
        if os.path.exists(path):
            break
    else:
        return False, "No launcher yet. Run install-server-suite.sh (or Set Up My Apps.sh) first."
    scope = ["systemd-run", "--user", "--scope", "--quiet", "--collect"] if shutil.which("systemd-run") else []
    for cmd in (["gtk-launch", d_id], ["gio", "launch", path]):
        if shutil.which(cmd[0]):
            if scope and run(scope + ["true"], 5)[0] == 0:
                cmd = scope + cmd
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return True, "Starting... give it a few seconds."
    return False, "Couldn't find gtk-launch. Start it from its Desktop icon."


# ------------------------------------------------------------------ server check-up
OK, WARN, BAD, INFO = "ok", "warn", "bad", "info"


def chk(cid, group, title, status, detail, fix="", cmd=""):
    return dict(id=cid, group=group, title=title, status=status, detail=detail, fix=fix, cmd=cmd)


def sshd_option(name, default):
    """First value wins in sshd_config, and the .d drop-ins are read first (Debian Include at the top)."""
    files = sorted(glob.glob("/etc/ssh/sshd_config.d/*.conf")) + ["/etc/ssh/sshd_config"]
    for f in files:
        for line in read(f).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("match "):
                break          # stop at Match blocks; they only apply to some users
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[0].lower() == name.lower():
                return parts[1].strip().strip('"').lower()
    return default


_slow = {"at": 0, "data": {}}
_slow_lock = threading.Lock()


def slow_checks():
    """apt / eeprom checks are slow, so they run in the background every 15 minutes."""
    data = {}
    code, out = run(["apt", "list", "--upgradable"], 60)
    if code == 0:
        lines = [l for l in out.splitlines() if "/" in l and "upgradable" in l]
        data["upgradable"] = len(lines)
        data["upgradable_names"] = [l.split("/")[0] for l in lines[:12]]
        data["security"] = sum(1 for l in lines if "-security" in l)
    if shutil.which("rpi-eeprom-update"):
        code, out = run(["rpi-eeprom-update"], 20)
        data["eeprom"] = "UPDATE AVAILABLE" in out.upper() if out else None
    with _slow_lock:
        _slow["data"] = data
        _slow["at"] = time.time()


def slow_loop():
    while True:
        try:
            slow_checks()
        except Exception as e:
            print("slow check error:", e, file=sys.stderr)
        time.sleep(900)


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return ("%.0f %s" if u in ("B", "KB") else "%.1f %s") % (n, u)
        n /= 1024.0


def checkup():
    if DEMO:
        return demo_checkup()
    C = []
    model = read("/proc/device-tree/model").strip("\x00\n ") or "Unknown computer"
    mem_kb = int((re.search(r"MemTotal:\s+(\d+)", read("/proc/meminfo")) or [0, 0])[1])
    is_pi = "raspberry pi" in model.lower()

    # --- hardware ------------------------------------------------------------
    C.append(chk("model", "Hardware", "This computer", INFO,
                 "%s with %.0f GB of memory." % (model, mem_kb / 1048576.0)
                 + ("" if re.search(r"Pi (5|500)", model) else " The suite is made for the Pi 5 and Pi 500; most of it still works here.")))

    t = read("/sys/class/thermal/thermal_zone0/temp").strip()
    if t.isdigit():
        c = int(t) / 1000.0
        if c < 70:
            C.append(chk("temp", "Hardware", "Temperature", OK, "%.0f °C - nice and cool." % c))
        elif c < 80:
            C.append(chk("temp", "Hardware", "Temperature", WARN, "%.0f °C - warm. The Pi slows itself down at 85 °C." % c,
                         "Give it the Active Cooler or a case with a fan, and keep the vents clear."))
        else:
            C.append(chk("temp", "Hardware", "Temperature", BAD, "%.0f °C - too hot. It's throttling, so everything runs slower." % c,
                         "Add cooling right away (Active Cooler, Pironman case, or a fan) and check the fan is spinning."))

    if shutil.which("vcgencmd"):
        code, out = run(["vcgencmd", "get_throttled"], 3)
        m = re.search(r"0x([0-9a-fA-F]+)", out)
        if m:
            v = int(m.group(1), 16)
            if v & 0x1:
                C.append(chk("power", "Hardware", "Power supply", BAD, "The power is too low RIGHT NOW. Drives can drop off and files can get damaged.",
                             "Use the official 27 W USB-C supply (5 V / 5 A). Powered drives need their own power, not the Pi's USB."))
            elif v & 0x10000:
                C.append(chk("power", "Hardware", "Power supply", WARN, "The power dipped too low at some point since the last restart.",
                             "Use the official 27 W USB-C supply (5 V / 5 A), and give USB drives their own power (a powered hub or dock)."))
            elif v & 0x40000 or v & 0x4:
                C.append(chk("power", "Hardware", "Power supply", WARN, "Power is fine, but the Pi has slowed itself down (heat) since the last restart.",
                             "Improve cooling so it can stay at full speed."))
            else:
                C.append(chk("power", "Hardware", "Power supply", OK, "No low-power or slow-down events since the last restart."))
        usb_max = run(["vcgencmd", "get_config", "usb_max_current_enable"], 3)[1]
        if is_pi and re.search(r"Pi (5|500)", model) and usb_max.endswith("=0"):
            C.append(chk("usbpower", "Hardware", "USB power for drives", INFO,
                         "The USB ports are limited to 600 mA in total, which is not enough for bus-powered hard drives or SSDs.",
                         "With the official 27 W supply this lifts on its own. Otherwise use powered drives or a powered hub."))

    fan = glob.glob("/sys/devices/platform/cooling_fan/hwmon/*/fan1_input")
    if fan:
        rpm = read(fan[0]).strip()
        if rpm.isdigit():
            C.append(chk("fan", "Hardware", "Fan", INFO, "Spinning at %s RPM." % rpm if int(rpm) > 0 else "Fan is plugged in and resting (the Pi is cool enough)."))

    # --- storage -------------------------------------------------------------
    code, src = run(["findmnt", "-no", "SOURCE", "/"], 3)
    if src:
        if "mmcblk" in src:
            C.append(chk("boot", "Storage", "System drive", WARN,
                         "The system runs from the SD card (%s). SD cards wear out and fail under server work like logs and databases." % src,
                         "Move the system to an NVMe or USB SSD (SD Card Copier in the Accessories menu), or use RAID Forge's 'Move system to RAID'. Keep the SD card as a spare."))
        elif src.startswith("/dev/md"):
            C.append(chk("boot", "Storage", "System drive", OK, "The system runs from a RAID array (%s), so one drive can fail without taking the Pi down." % src))
        else:
            C.append(chk("boot", "Storage", "System drive", OK, "The system runs from %s - an SSD or USB drive, not the SD card." % src))

    seen = set()
    for line in read("/proc/mounts").splitlines():
        f = line.split()
        if len(f) < 3 or f[2] not in ("ext4", "btrfs", "xfs", "vfat", "exfat", "f2fs", "ntfs3", "fuseblk"):
            continue
        dev, mnt = f[0], f[1].replace("\\040", " ")
        if dev in seen or mnt.startswith(("/boot", "/snap", "/run/user")):
            continue
        seen.add(dev)
        try:
            st = os.statvfs(mnt)
        except Exception:
            continue
        total = st.f_blocks * st.f_frsize
        if total < 512 * 1024 * 1024:
            continue
        free = st.f_bavail * st.f_frsize
        used_pct = 100 - (free * 100.0 / total)
        label = "System drive (/)" if mnt == "/" else "Drive at " + mnt
        msg = "%.0f%% full - %s free of %s." % (used_pct, human(free), human(total))
        if used_pct >= 90:
            C.append(chk("disk:" + mnt, "Storage", label, BAD, msg + " Programs and databases can break when it fills.",
                         "Open PiDirStat to see what's using the space. Clearing old logs and apt's cache is a quick win.",
                         "sudo journalctl --vacuum-size=200M && sudo apt-get clean"))
        elif used_pct >= 80:
            C.append(chk("disk:" + mnt, "Storage", label, WARN, msg, "Open PiDirStat to see what's growing."))
        else:
            C.append(chk("disk:" + mnt, "Storage", label, OK, msg))

    md = read("/proc/mdstat")
    arrays = re.findall(r"^(md\d+)\s*:\s*(\w+)\s+(\w+)(.*?)(?=^md\d+\s*:|\Z)", md, re.M | re.S)
    if arrays:
        for name, state, level, rest in arrays:
            m = re.search(r"\[(\d+)/(\d+)\]\s*\[([U_]+)\]", rest)
            rebuild = re.search(r"(recovery|resync|reshape|check)\s*=\s*([\d.]+%)", rest)
            if m and "_" in m.group(3):
                C.append(chk("raid:" + name, "Storage", "RAID " + name, BAD,
                             "%s is missing a drive (%s of %s working). One more failure could lose data." % (name, m.group(2), m.group(1)),
                             "Open RAID Forge > My Arrays and use 'Swap a failed drive'. 'Find the failed drive' blinks the healthy ones."))
            elif rebuild:
                C.append(chk("raid:" + name, "Storage", "RAID " + name, WARN,
                             "%s is busy: %s %s done. It's safe to use, just slower." % (name, rebuild.group(1), rebuild.group(2))))
            else:
                C.append(chk("raid:" + name, "Storage", "RAID " + name, OK, "%s (%s) is healthy, all drives working." % (name, level)))
    else:
        C.append(chk("raid", "Storage", "RAID", INFO, "No RAID arrays on this Pi.",
                     "Want a drive to be able to fail without losing anything? RAID Forge sets up RAID 1, 5, 6 or 10 with a few clicks."))

    code, out = run(["journalctl", "--disk-usage"], 6)
    m = re.search(r"([\d.]+)\s*([KMGT])", out or "")
    if m:
        size = float(m.group(1)) * {"K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[m.group(2)]
        if size > 1.5e9:
            C.append(chk("logs", "Storage", "System logs", WARN, "Logs are using %s%sB." % (m.group(1), m.group(2)),
                         "Trim them, and cap them for good by setting SystemMaxUse=200M in /etc/systemd/journald.conf.",
                         "sudo journalctl --vacuum-size=200M"))
        else:
            C.append(chk("logs", "Storage", "System logs", OK, "Logs are using %s%sB." % (m.group(1), m.group(2))))

    # --- security ------------------------------------------------------------
    ssh_on = run(["systemctl", "is-active", "ssh"], 3)[1] == "active" or run(["systemctl", "is-active", "sshd"], 3)[1] == "active" or tcp_open(22)
    if not ssh_on:
        C.append(chk("ssh", "Security", "SSH (remote terminal)", INFO, "SSH is off. That's the safest, but you'll need it to manage a server without a screen.",
                     "Turn it on in Raspberry Pi Configuration > Interfaces, then set up a key (see the next check)."))
    else:
        pw = sshd_option("PasswordAuthentication", "yes")
        root = sshd_option("PermitRootLogin", "prohibit-password")
        keys = os.path.exists(os.path.expanduser("~/.ssh/authorized_keys"))
        if root == "yes":
            C.append(chk("sshroot", "Security", "SSH root login", BAD, "Anyone can try to log in as root with a password.",
                         "Turn it off: add 'PermitRootLogin no' to /etc/ssh/sshd_config.d/10-server-room.conf, then restart SSH.",
                         "echo 'PermitRootLogin no' | sudo tee -a /etc/ssh/sshd_config.d/10-server-room.conf && sudo systemctl restart ssh"))
        if pw != "no":
            C.append(chk("sshpw", "Security", "SSH login", WARN,
                         "SSH accepts passwords, so anyone on your network can keep guessing." + (" You already have an SSH key set up." if keys else ""),
                         ("Since your key works, turn passwords off:" if keys else
                          "From your PC run  ssh-copy-id " + os.environ.get("USER", "pi") + "@<this Pi>  and check you can log in with the key. Then turn passwords off:"),
                         "echo 'PasswordAuthentication no' | sudo tee /etc/ssh/sshd_config.d/10-server-room.conf && sudo systemctl restart ssh"))
        else:
            C.append(chk("sshpw", "Security", "SSH login", OK, "SSH only accepts keys - password guessing can't get in."))
        if not shutil.which("fail2ban-server"):
            C.append(chk("fail2ban", "Security", "Block password guessing", WARN if pw != "no" else INFO,
                         "fail2ban isn't installed. It locks out anyone who gets the password wrong over and over.",
                         "Install it - it protects SSH as soon as it's on.",
                         "sudo apt-get install -y fail2ban"))
        else:
            act = run(["systemctl", "is-active", "fail2ban"], 3)[1] == "active"
            C.append(chk("fail2ban", "Security", "Block password guessing", OK if act else WARN,
                         "fail2ban is " + ("on and watching SSH." if act else "installed but not running."),
                         "" if act else "Start it:", "" if act else "sudo systemctl enable --now fail2ban"))

    ufw_on = "ENABLED=yes" in read("/etc/ufw/ufw.conf")
    if ufw_on:
        C.append(chk("firewall", "Security", "Firewall", OK, "The ufw firewall is on."))
    elif shutil.which("ufw") or os.path.exists("/usr/sbin/ufw"):
        C.append(chk("firewall", "Security", "Firewall", WARN, "ufw is installed but switched off.",
                     "Allow SSH first so you don't lock yourself out, then switch it on. Add 'sudo ufw allow <port>' for each app others use.",
                     "sudo ufw allow ssh && sudo ufw allow from 192.168.0.0/16 && sudo ufw enable"))
    else:
        C.append(chk("firewall", "Security", "Firewall", WARN, "No firewall. Every app listening on this Pi can be reached by any device on your network.",
                     "Install ufw, allow SSH and your home network, then switch it on.",
                     "sudo apt-get install -y ufw && sudo ufw allow ssh && sudo ufw allow from 192.168.0.0/16 && sudo ufw enable"))

    code, out = run(["ss", "-tlnH"], 4)
    open_ports = sorted({int(l.split()[3].rsplit(":", 1)[1]) for l in out.splitlines()
                         if len(l.split()) > 3 and not re.match(r"(127\.|\[::1\]|::1)", l.split()[3])} - {0}) if out else []
    if open_ports:
        C.append(chk("ports", "Security", "Open to the network", INFO,
                     "%d port%s can be reached from other devices: %s." % (len(open_ports), "" if len(open_ports) == 1 else "s", ", ".join(map(str, open_ports[:20]))),
                     "Only open what you use. Never forward these on your router - use Tailscale or a VPN to reach the Pi from outside."))

    if os.path.exists("/etc/sudoers.d/010_pi-nopasswd"):
        C.append(chk("sudo", "Security", "sudo password", INFO, "Your account can run admin commands without typing a password.",
                     "Handy, but anything that gets in as you is also in charge of the whole Pi. To require the password:",
                     "sudo rm /etc/sudoers.d/010_pi-nopasswd"))

    # --- updates -------------------------------------------------------------
    with _slow_lock:
        sd = dict(_slow["data"]); at = _slow["at"]
    lists = glob.glob("/var/lib/apt/lists/*_InRelease")
    last = max((os.path.getmtime(f) for f in lists), default=0)
    days = (time.time() - last) / 86400 if last else 999
    if "upgradable" in sd:
        n = sd["upgradable"]
        if n == 0 and days < 14:
            C.append(chk("updates", "Updates", "Software updates", OK, "Everything is up to date."))
        elif n == 0:
            C.append(chk("updates", "Updates", "Software updates", WARN, "It's been %d days since the Pi checked for updates." % days,
                         "Check and install:", "sudo apt-get update && sudo apt-get full-upgrade -y"))
        else:
            sec = sd.get("security", 0)
            C.append(chk("updates", "Updates", "Software updates", BAD if sec else WARN,
                         "%d update%s waiting%s: %s%s." % (n, "" if n == 1 else "s", (" (%d security)" % sec) if sec else "",
                                                        ", ".join(sd.get("upgradable_names", [])), "..." if n > 12 else ""),
                         "Install them (Task Manager's 'Update everything' does this too):", "sudo apt-get update && sudo apt-get full-upgrade -y"))
    elif at == 0:
        C.append(chk("updates", "Updates", "Software updates", INFO, "Still checking... refresh in a minute."))

    auto = read("/etc/apt/apt.conf.d/20auto-upgrades")
    if os.path.exists("/usr/bin/unattended-upgrade") and re.search(r'Unattended-Upgrade\s+"1"', auto):
        C.append(chk("auto", "Updates", "Automatic security updates", OK, "Security fixes install by themselves every day."))
    else:
        C.append(chk("auto", "Updates", "Automatic security updates", WARN, "Security fixes only arrive when you remember to update.",
                     "Turn on automatic security updates:",
                     "sudo apt-get install -y unattended-upgrades && sudo dpkg-reconfigure -f noninteractive unattended-upgrades"))

    if os.path.exists("/var/run/reboot-required"):
        C.append(chk("reboot", "Updates", "Restart needed", WARN, "An update is waiting for a restart to finish installing.",
                     "Restart when nobody is using the Pi:", "sudo reboot"))
    if sd.get("eeprom") is True:
        C.append(chk("eeprom", "Updates", "Bootloader (EEPROM)", WARN, "A newer bootloader is available. They fix NVMe, USB boot and power bugs.",
                     "Install it, then restart:", "sudo rpi-eeprom-update -a && sudo reboot"))
    elif sd.get("eeprom") is False:
        C.append(chk("eeprom", "Updates", "Bootloader (EEPROM)", OK, "The bootloader is up to date."))

    # --- reliability ---------------------------------------------------------
    code, out = run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"], 3)
    if out:
        C.append(chk("time", "Reliability", "Clock", OK if out == "yes" else WARN,
                     "The clock is set from the internet." if out == "yes" else "The clock isn't synced. Logs, certificates and schedules can go wrong.",
                     "" if out == "yes" else "Turn on time sync:", "" if out == "yes" else "sudo timedatectl set-ntp true"))

    code, out = run(["systemctl", "--failed", "--no-legend", "--plain"], 4)
    failed = [l.split()[0] for l in out.splitlines() if l.strip()] if code == 0 else []
    if failed:
        C.append(chk("failed", "Reliability", "Background services", WARN,
                     "%d service%s failed: %s." % (len(failed), "" if len(failed) == 1 else "s", ", ".join(failed[:8])),
                     "See why (swap in the name), or switch it off in PiStartup if you don't need it:", "systemctl status " + failed[0]))
    elif code == 0:
        C.append(chk("failed", "Reliability", "Background services", OK, "No background services have failed."))

    wd = ""
    for f in ["/etc/systemd/system.conf"] + sorted(glob.glob("/etc/systemd/system.conf.d/*.conf")):
        m = re.search(r"^\s*RuntimeWatchdogSec\s*=\s*(\S+)", read(f), re.M)
        if m:
            wd = m.group(1)
    if wd and wd not in ("0", "off"):
        C.append(chk("watchdog", "Reliability", "Freeze protection", OK, "The hardware watchdog will restart the Pi if it ever freezes (%s)." % wd))
    elif os.path.exists("/dev/watchdog"):
        C.append(chk("watchdog", "Reliability", "Freeze protection", WARN, "If the Pi locks up, it stays locked up until someone pulls the plug.",
                     "Turn on the built-in hardware watchdog so it restarts itself:",
                     "sudo mkdir -p /etc/systemd/system.conf.d && printf '[Manager]\\nRuntimeWatchdogSec=15\\n' | sudo tee /etc/systemd/system.conf.d/watchdog.conf && sudo systemctl daemon-reexec"))

    up = float((read("/proc/uptime").split() or ["0"])[0])
    C.append(chk("uptime", "Reliability", "Uptime", INFO, "Running for %d days, %d hours." % (up // 86400, (up % 86400) // 3600)))

    tools = [t for t in ("restic", "borg", "rsnapshot", "rclone", "duplicati", "timeshift", "rpi-clone", "kopia") if shutil.which(t)]
    timers = run(["systemctl", "list-timers", "--all", "--no-legend", "--plain"], 4)[1]
    crons = read("/etc/crontab") + "".join(read(f) for f in glob.glob("/etc/cron.d/*"))
    scheduled = bool(re.search(r"backup|restic|borg|rsnapshot|rclone|kopia", timers + crons, re.I))
    if tools and scheduled:
        C.append(chk("backup", "Reliability", "Backups", OK, "A backup tool (%s) is installed and scheduled." % ", ".join(tools)))
    elif tools:
        C.append(chk("backup", "Reliability", "Backups", WARN, "%s is installed, but nothing seems to run it on a schedule." % ", ".join(tools),
                     "Set it to run every night with a systemd timer or cron job, and test a restore once."))
    else:
        C.append(chk("backup", "Reliability", "Backups", WARN, "No backup tool found. RAID keeps you running when a drive dies, but it can't undo a deleted file, a bad update or ransomware.",
                     "Copy the important folders to another computer or a USB drive you unplug. restic is simple and works great on a Pi:",
                     "sudo apt-get install -y restic"))

    code, out = run(["hostname", "-I"], 3)
    ips = out.split()
    C.append(chk("ip", "Reliability", "Network address", INFO,
                 ("This Pi is at " + ", ".join(ips[:3]) + ".") if ips else "No network address yet.",
                 "Reserve this address for the Pi in your router (DHCP reservation), so bookmarks and SSH keep working."))
    return C


def demo_checkup():
    return [
        chk("model", "Hardware", "This computer", INFO, "Raspberry Pi 5 Model B Rev 1.0 with 8 GB of memory. (Demo - pretend data)"),
        chk("temp", "Hardware", "Temperature", OK, "52 °C - nice and cool."),
        chk("power", "Hardware", "Power supply", WARN, "The power dipped too low at some point since the last restart.",
            "Use the official 27 W USB-C supply (5 V / 5 A), and give USB drives their own power (a powered hub or dock)."),
        chk("fan", "Hardware", "Fan", INFO, "Spinning at 3120 RPM."),
        chk("boot", "Storage", "System drive", WARN, "The system runs from the SD card (/dev/mmcblk0p2). SD cards wear out and fail under server work like logs and databases.",
            "Move the system to an NVMe or USB SSD (SD Card Copier in the Accessories menu), or use RAID Forge's 'Move system to RAID'. Keep the SD card as a spare."),
        chk("disk:/", "Storage", "System drive (/)", OK, "41% full - 33.1 GB free of 57.3 GB."),
        chk("disk:/srv/raid", "Storage", "Drive at /srv/raid", WARN, "86% full - 1.1 TB free of 7.3 TB.", "Open PiDirStat to see what's growing."),
        chk("raid:md0", "Storage", "RAID md0", BAD, "md0 is missing a drive (3 of 4 working). One more failure could lose data.",
            "Open RAID Forge > My Arrays and use 'Swap a failed drive'. 'Find the failed drive' blinks the healthy ones."),
        chk("logs", "Storage", "System logs", OK, "Logs are using 312.0MB."),
        chk("sshpw", "Security", "SSH login", WARN, "SSH accepts passwords, so anyone on your network can keep guessing.",
            "From your PC run  ssh-copy-id pi@<this Pi>  and check you can log in with the key. Then turn passwords off:",
            "echo 'PasswordAuthentication no' | sudo tee /etc/ssh/sshd_config.d/10-server-room.conf && sudo systemctl restart ssh"),
        chk("fail2ban", "Security", "Block password guessing", WARN, "fail2ban isn't installed. It locks out anyone who gets the password wrong over and over.",
            "Install it - it protects SSH as soon as it's on.", "sudo apt-get install -y fail2ban"),
        chk("firewall", "Security", "Firewall", OK, "The ufw firewall is on."),
        chk("ports", "Security", "Open to the network", INFO, "5 ports can be reached from other devices: 22, 5900, 8070, 8080, 8470.",
            "Only open what you use. Never forward these on your router - use Tailscale or a VPN to reach the Pi from outside."),
        chk("updates", "Updates", "Software updates", WARN, "7 updates waiting: chromium, firefox, libcamera0.3, raspi-firmware, rpi-eeprom...",
            "Install them (Task Manager's 'Update everything' does this too):", "sudo apt-get update && sudo apt-get full-upgrade -y"),
        chk("auto", "Updates", "Automatic security updates", OK, "Security fixes install by themselves every day."),
        chk("eeprom", "Updates", "Bootloader (EEPROM)", OK, "The bootloader is up to date."),
        chk("time", "Reliability", "Clock", OK, "The clock is set from the internet."),
        chk("failed", "Reliability", "Background services", OK, "No background services have failed."),
        chk("watchdog", "Reliability", "Freeze protection", WARN, "If the Pi locks up, it stays locked up until someone pulls the plug.",
            "Turn on the built-in hardware watchdog so it restarts itself:",
            "sudo mkdir -p /etc/systemd/system.conf.d && printf '[Manager]\\nRuntimeWatchdogSec=15\\n' | sudo tee /etc/systemd/system.conf.d/watchdog.conf && sudo systemctl daemon-reexec"),
        chk("uptime", "Reliability", "Uptime", INFO, "Running for 23 days, 4 hours."),
        chk("backup", "Reliability", "Backups", WARN, "No backup tool found. RAID keeps you running when a drive dies, but it can't undo a deleted file, a bad update or ransomware.",
            "Copy the important folders to another computer or a USB drive you unplug. restic is simple and works great on a Pi:", "sudo apt-get install -y restic"),
        chk("ip", "Reliability", "Network address", INFO, "This Pi is at 192.168.1.50.",
            "Reserve this address for the Pi in your router (DHCP reservation), so bookmarks and SSH keep working."),
    ]


def demo_apps():
    up = {"poddeck": 8070, "pimesh": 8470, "wiki": 8080, "netsentry": 8775}
    up["tidy"] = 8780
    return {a["id"]: dict(id=a["id"], up=a["id"] in up, url=("http://127.0.0.1:%d/" % up[a["id"]]) if a["id"] in up else "",
                          installed=a["id"] != "shelf") for a in APPS}


# ------------------------------------------------------------------ web server
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
         ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".json": "application/json", ".pdf": "application/pdf",
         ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = "ServerRoom/" + VERSION

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200, cors=False):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if cors:   # only the harmless "are you there?" ping is readable from other pages
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def local_host_ok(self):
        # refuse pages reached through another name (stops DNS-rebinding tricks)
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost", "[::1]")

    def send_file(self, path):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        p = unquote(u.path)
        if p == "/api/ping":
            return self.send_json({"app": "server-room", "version": VERSION}, cors=True)
        if not self.local_host_ok():
            return self.send_error(403)
        if p in ("/", "/index.html"):
            return self.send_file(os.path.join(HERE, "Server Room.html"))
        if p == "/api/checkup":
            return self.send_json({"checks": checkup(), "demo": DEMO, "at": time.time()})
        if p == "/api/apps":
            return self.send_json({"apps": demo_apps() if DEMO else app_status()})
        if p == "/api/servers":
            return self.send_json(running_servers())
        # a few static files: the suite folder, its icon, and the suite apps' own folders
        parts = p.strip("/").split("/")
        base = None
        if parts[0] == "server-suite":
            base = HERE
        elif parts[0] == "apps" and len(parts) > 2 and parts[1] in SERVE_FOLDERS:
            base = os.path.join(ROOT, "apps", parts[1])
            parts = parts[1:]
        elif parts[0] == "thumbs" and len(parts) == 2:
            base = os.path.join(ROOT, "thumbs")
        elif parts[0] == "tidy-suite" and len(parts) > 1 and parts[1] != "Saved work" and not p.endswith(".py"):
            base = os.path.join(ROOT, "tidy-suite")
        if base:
            full = os.path.realpath(os.path.join(base, *parts[1:]))
            if full.startswith(os.path.realpath(base) + os.sep) and os.path.isfile(full):
                return self.send_file(full)
        self.send_error(404)

    def do_POST(self):
        if not self.local_host_ok() or self.headers.get("X-Server-Room") != "1":
            return self.send_error(403)
        u = urlparse(self.path)
        try:
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 4096)) or b"{}")
        except Exception:
            body = {}
        if u.path == "/api/stop":
            try:
                port = int(body.get("port"))
            except Exception:
                return self.send_json({"ok": False, "msg": "Which server?"})
            ok, msg = stop_server(port)
            return self.send_json({"ok": ok, "msg": msg})
        if u.path == "/api/stopall":
            done, failed = [], []
            for s in [x for x in running_servers()["servers"] if x.get("stoppable")]:
                ok, msg = stop_server(s["port"])
                (done if ok else failed).append(s["name"] if ok else "%s (%s)" % (s["name"], msg))
            msg = ("Stopped " + ", ".join(done) + "." if done else "Nothing was stopped.") + \
                  ((" Couldn't stop: " + "; ".join(failed)) if failed else "")
            return self.send_json({"ok": not failed, "msg": msg, "stopped": done})
        if u.path == "/api/start":
            if DEMO:
                return self.send_json({"ok": True, "msg": "Demo mode - pretending to start it."})
            ok, msg = launch(str(body.get("id", "")))
            return self.send_json({"ok": ok, "msg": msg})
        self.send_error(404)


def main():
    global DEMO, PORT
    ap = argparse.ArgumentParser(description="Server Room - Pi Server Suite hub")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--open", action="store_true", help="open the browser")
    ap.add_argument("--demo", action="store_true", help="pretend data (try it anywhere)")
    a = ap.parse_args()
    DEMO, PORT = a.demo, a.port
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        if tcp_open(PORT):
            print("Server Room is already running: http://127.0.0.1:%d/" % PORT)
            if a.open:
                webbrowser.open("http://127.0.0.1:%d/" % PORT)
            return
        raise
    if not DEMO:
        threading.Thread(target=slow_loop, daemon=True).start()
    url = "http://127.0.0.1:%d/" % PORT
    print("Server Room is running: " + url + ("  (demo)" if DEMO else ""))
    print("Only this Pi can open it. Leave this window open, or install it to start with the Pi.")
    if a.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
