#!/usr/bin/env python3
"""PiStartup - see everything that starts with your Raspberry Pi and switch it off/on.

Covers:
  * Desktop autostart apps   (/etc/xdg/autostart, ~/.config/autostart)
  * labwc / LXDE / Wayfire autostart lines (your own files are editable,
    the system desktop files are shown as locked so you can't break the desktop)
  * @reboot jobs in your crontab
  * Background services       (systemd system + user services)
  * /etc/rc.local commands    (shown, read-only)

Every change is reversible from the app.
"""
import os
import re
import json
import shutil
import subprocess
import configparser
import tkinter as tk
from tkinter import ttk, messagebox

HOME = os.path.expanduser("~")
CFG_DIR = os.path.join(HOME, ".config", "pistartup")
STATE_FILE = os.path.join(CFG_DIR, "disabled_services.json")
USER_AUTOSTART = os.path.join(HOME, ".config", "autostart")
SYS_AUTOSTART = "/etc/xdg/autostart"
MARK = "#[PiStartup-off] "
MARKT = MARK.strip()

DESKTOP = "Desktop app"
SERVICE = "Background service"

# Services that would stop the Pi booting to a usable desktop - never touch.
LOCKED_SVC = ("dbus", "systemd-", "getty@", "serial-getty@", "autovt@", "lightdm",
              "gdm", "sddm", "polkit", "user@", "udisks2", "keyboard-setup",
              "console-setup")

# Services you *can* switch off, but should know what happens.
CAUTION_SVC = {
    "ssh": "You won't be able to SSH into this Pi after the next reboot.",
    "networkmanager": "Wi-Fi and Ethernet will be off after the next reboot.",
    "dhcpcd": "Networking will probably stop working after the next reboot.",
    "wpa_supplicant": "Wi-Fi may stop working after the next reboot.",
    "bluetooth": "Bluetooth keyboards, mice and speakers will stop working.",
    "hciuart": "Bluetooth will stop working.",
    "wayvnc": "VNC remote desktop won't start, so you can't remote in.",
    "vncserver": "VNC remote desktop won't start, so you can't remote in.",
    "avahi-daemon": "You won't be able to reach this Pi by its name.local address.",
    "pipewire": "Sound will stop working.",
    "wireplumber": "Sound will stop working.",
    "pulseaudio": "Sound will stop working.",
    "cron": "Scheduled jobs (including @reboot jobs) won't run.",
    "raspi-config": "Raspberry Pi CPU governor/boot tweaks won't be applied.",
    "rsyslog": "System logs won't be written to /var/log.",
}

# ---------------------------------------------------------------- helpers

def run(cmd, timeout=20, inp=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=inp)
        return r.returncode, r.stdout, r.stderr
    except Exception as ex:  # command missing, timeout, ...
        return 1, "", str(ex)


def root_run(args):
    """Run as root: passwordless sudo first (Pi default), then pkexec prompt."""
    rc, _, err = run(["sudo", "-n"] + args)
    if rc == 0:
        return True, ""
    if shutil.which("pkexec"):
        rc, _, err = run(["pkexec"] + args, timeout=180)
        if rc == 0:
            return True, ""
    return False, (err.strip() or "Permission denied")


def load_state():
    try:
        with open(STATE_FILE) as f:
            d = json.load(f)
            return {"system": list(d.get("system", [])), "user": list(d.get("user", []))}
    except Exception:
        return {"system": [], "user": []}


def save_state(d):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(d, f, indent=2)


def backup_once(path):
    bak = path + ".pistartup.bak"
    if os.path.exists(path) and not os.path.exists(bak):
        try:
            shutil.copy2(path, bak)
        except OSError:
            pass


def parse_dur(s):
    mult = {"h": 3600, "min": 60, "s": 1, "ms": 0.001, "us": 1e-6, "µs": 1e-6}
    return sum(float(n) * mult[u] for n, u in re.findall(r"([\d.]+)\s*(min|ms|us|µs|s|h)", s))


def fmt_dur(sec):
    if sec <= 0:
        return ""
    return f"{sec:.1f}s" if sec >= 1 else f"{sec * 1000:.0f}ms"


def boot_times(user=False):
    cmd = ["systemd-analyze"] + (["--user"] if user else []) + ["blame", "--no-pager"]
    rc, out, _ = run(cmd)
    times = {}
    if rc == 0:
        for ln in out.splitlines():
            p = ln.split()
            if len(p) >= 2:
                times[p[-1]] = parse_dur(" ".join(p[:-1]))
    return times


def pretty_cmd_name(cmd):
    skip = {"lwrespawn", "exec", "sudo", "nohup", "env", "sh", "bash", "-c"}
    for tok in cmd.lstrip("@").split():
        if tok in skip or re.match(r"^[A-Za-z_]+=", tok):
            continue
        return os.path.basename(tok.strip("'\"&"))
    return cmd[:30]


class Entry:
    def __init__(self, kind, group, name, detail, enabled, source,
                 locked=False, lock_reason="", caution="", **extra):
        self.kind = kind            # xdg | line | cron | sys | user | info
        self.group = group
        self.name = name
        self.detail = detail
        self.enabled = enabled
        self.source = source
        self.locked = locked
        self.lock_reason = lock_reason
        self.caution = caution
        self.extra = extra
        self.boot = 0.0

    @property
    def key(self):
        return f"{self.kind}|{self.source}|{self.extra.get('cmd', self.name)}"

    @property
    def type_label(self):
        return {"xdg": "Autostart app", "line": "Autostart command", "cron": "Cron @reboot",
                "sys": "System service", "user": "User service",
                "info": "rc.local"}[self.kind]


# ---------------------------------------------------------------- scanners

def read_desktop(path):
    cp = configparser.RawConfigParser(strict=False)
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8")
    except Exception:
        return {}
    return dict(cp.items("Desktop Entry")) if cp.has_section("Desktop Entry") else {}


def scan_xdg():
    files = {}
    for d in (SYS_AUTOSTART, USER_AUTOSTART):
        try:
            for fn in os.listdir(d):
                if fn.endswith(".desktop"):
                    files.setdefault(fn, {})["sys" if d == SYS_AUTOSTART else "user"] = os.path.join(d, fn)
        except OSError:
            pass
    desk = [d.lower() for d in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d]
    out = []
    for fn, paths in files.items():
        path = paths.get("user") or paths.get("sys")
        data = read_desktop(path)
        if not data:
            continue
        only = [d.lower() for d in data.get("OnlyShowIn", "").split(";") if d]
        nots = [d.lower() for d in data.get("NotShowIn", "").split(";") if d]
        if desk and ((only and not any(d in only for d in desk)) or any(d in nots for d in desk)):
            continue  # meant for some other desktop, never runs here
        enabled = (data.get("Hidden", "false").lower() != "true"
                   and data.get("X-GNOME-Autostart-enabled", "true").lower() != "false")
        caution = ""
        if "polkit" in fn.lower():
            caution = "Admin password prompts may stop appearing on the desktop."
        out.append(Entry("xdg", DESKTOP, data.get("Name", fn[:-8]),
                         data.get("Comment") or data.get("Exec", ""), enabled, path,
                         caution=caution, file=fn, sys_path=paths.get("sys"),
                         exec=data.get("Exec", "")))
    return out


def scan_line_file(path, locked, section=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    out, cur = [], None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if section is not None:
            if s.startswith("[") and s.endswith("]"):
                cur = s[1:-1].strip()
                continue
            if cur != section:
                continue
        if not s:
            continue
        if s.startswith(MARKT):
            cmd, enabled = s[len(MARKT):].strip(), False
        elif s.startswith("#"):
            continue
        else:
            cmd, enabled = s, True
        if section is not None and "=" in cmd:
            name, _, body = cmd.partition("=")
            name, body = name.strip(), body.strip()
        else:
            name, body = pretty_cmd_name(cmd), cmd
        out.append(Entry("line", DESKTOP, name, body, enabled, path, locked=locked,
                         lock_reason="Part of the core Raspberry Pi desktop - switching it "
                                     "off could leave you with no panel or desktop." if locked else "",
                         line=i, cmd=cmd))
    return out


def scan_lines():
    out = []
    out += scan_line_file(os.path.join(HOME, ".config/labwc/autostart"), False)
    out += scan_line_file(os.path.join(HOME, ".config/lxsession/LXDE-pi/autostart"), False)
    out += scan_line_file(os.path.join(HOME, ".config/lxsession/LXDE/autostart"), False)
    out += scan_line_file(os.path.join(HOME, ".config/wayfire.ini"), False, section="autostart")
    out += scan_line_file("/etc/xdg/labwc/autostart", True)
    out += scan_line_file("/etc/xdg/lxsession/LXDE-pi/autostart", True)
    return out


def scan_cron():
    rc, out, _ = run(["crontab", "-l"])
    if rc != 0:
        return []
    res = []
    for i, ln in enumerate(out.splitlines()):
        s = ln.strip()
        if s.startswith(MARKT):
            rest, enabled = s[len(MARKT):].strip(), False
        elif s.startswith("#"):
            continue
        else:
            rest, enabled = s, True
        if not rest.startswith("@reboot"):
            continue
        cmd = rest[len("@reboot"):].strip()
        res.append(Entry("cron", SERVICE, pretty_cmd_name(cmd), cmd, enabled, "your crontab",
                         line=i, cmd=rest))
    return res


def scan_rclocal():
    out = []
    try:
        with open("/etc/rc.local", encoding="utf-8", errors="replace") as f:
            for ln in f:
                s = ln.strip()
                if not s or s.startswith("#") or s == "exit 0":
                    continue
                out.append(Entry("info", SERVICE, pretty_cmd_name(s), s, True, "/etc/rc.local",
                                 locked=True, cmd=s,
                                 lock_reason="Runs from /etc/rc.local. To stop it, put a # in front "
                                             "of the line: sudo nano /etc/rc.local"))
    except OSError:
        pass
    return out


def scan_services(user=False):
    base = ["systemctl"] + (["--user"] if user else [])
    rc, out, _ = run(base + ["list-unit-files", "--type=service", "--no-legend", "--no-pager"])
    if rc != 0:
        return []
    remembered = set(load_state()["user" if user else "system"])
    names = []
    for ln in out.splitlines():
        p = ln.split()
        if len(p) >= 2 and p[0].endswith(".service"):
            if p[1] == "enabled" or (p[1] == "disabled" and p[0] in remembered):
                names.append((p[0], p[1] == "enabled"))
    if not names:
        return []
    rc, out, _ = run(base + ["show", "-p", "Id", "-p", "Description", "-p", "FragmentPath",
                             "--no-pager"] + [n for n, _ in names], timeout=40)
    blocks, cur = [], {}
    for ln in out.splitlines() + [""]:
        if not ln.strip():
            if cur:
                blocks.append(cur)
            cur = {}
            continue
        k, _, v = ln.partition("=")
        cur[k] = v
    info = dict(zip([n for n, _ in names], blocks)) if len(blocks) == len(names) else \
        {b.get("Id"): b for b in blocks}
    times = boot_times(user)
    res = []
    for n, enabled in names:
        stem = n[:-8]
        low = stem.lower()
        locked = any(low.startswith(p) for p in LOCKED_SVC)
        caution = next((msg for k, msg in CAUTION_SVC.items() if low.startswith(k)), "")
        b = info.get(n, {})
        e = Entry("user" if user else "sys", SERVICE, stem, b.get("Description", ""), enabled,
                  b.get("FragmentPath") or n, locked=locked,
                  lock_reason="Core system service - the Pi needs this to boot properly." if locked else "",
                  caution=caution, unit=n, cmd=n)
        e.boot = times.get(n, 0.0)
        res.append(e)
    return res


def scan_all():
    return (scan_xdg() + scan_lines() + scan_cron() + scan_rclocal()
            + scan_services(False) + scan_services(True))


# ---------------------------------------------------------------- toggles

def write_hidden(path, hidden):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    out, in_main = [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith("["):
            in_main = s == "[Desktop Entry]"
            out.append(ln)
            if in_main:
                out.append(f"Hidden={'true' if hidden else 'false'}")
            continue
        if in_main and (s.startswith("Hidden=") or s.startswith("X-GNOME-Autostart-enabled=")):
            continue
        out.append(ln)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def set_enabled(e, on):
    try:
        if e.kind == "xdg":
            user_path = os.path.join(USER_AUTOSTART, e.extra["file"])
            if not os.path.exists(user_path):
                os.makedirs(USER_AUTOSTART, exist_ok=True)
                shutil.copy(e.extra["sys_path"], user_path)
            write_hidden(user_path, not on)
            return True, ""

        if e.kind == "line":
            with open(e.source, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
            i = e.extra["line"]
            if i >= len(lines) or e.extra["cmd"] not in lines[i]:
                return False, "The file changed since it was read. Press Refresh and try again."
            backup_once(e.source)
            s = lines[i].lstrip()
            lines[i] = s[len(MARKT):].lstrip() if on else MARK + s
            with open(e.source, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return True, ""

        if e.kind == "cron":
            rc, out, err = run(["crontab", "-l"])
            if rc != 0:
                return False, err
            lines = out.splitlines()
            i = e.extra["line"]
            if i >= len(lines) or e.extra["cmd"] not in lines[i]:
                return False, "Your crontab changed. Press Refresh and try again."
            s = lines[i].lstrip()
            lines[i] = s[len(MARKT):].lstrip() if on else MARK + s
            rc, _, err = run(["crontab", "-"], inp="\n".join(lines) + "\n")
            return rc == 0, err

        if e.kind in ("sys", "user"):
            unit = e.extra["unit"]
            verb = "enable" if on else "disable"
            if e.kind == "user":
                rc, _, err = run(["systemctl", "--user", verb, unit])
                ok = rc == 0
            else:
                ok, err = root_run(["systemctl", verb, unit])
            if ok:
                st = load_state()
                lst = st["user" if e.kind == "user" else "system"]
                if on and unit in lst:
                    lst.remove(unit)
                elif not on and unit not in lst:
                    lst.append(unit)
                save_state(st)
            return ok, err
    except Exception as ex:
        return False, str(ex)
    return False, "This item can't be changed from here."


# ---------------------------------------------------------------- UI

BG, PANEL, PANEL2 = "#141922", "#1c2330", "#252e3e"
FG, MUTED = "#e8ebf1", "#8a94a6"
ACCENT, ACCENT_HI = "#d6335a", "#e84a70"
ON, OFF, LOCK, WARN = "#4cc38a", "#e8a33d", "#6f7a8c", "#f0b44c"
FONT = "DejaVu Sans"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PiStartup")
        self.geometry("1040x660")
        self.minsize(760, 480)
        self.configure(bg=BG)
        self.entries, self.by_iid = [], {}
        self.current = None
        self.sort_col, self.sort_rev = None, False
        self._style()
        self._build()
        self.after(60, self.refresh)

    def _style(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL,
                     font=(FONT, 10), borderwidth=0)
        st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                     rowheight=30, borderwidth=0)
        st.map("Treeview", background=[("selected", "#2f3c56")], foreground=[("selected", FG)])
        st.configure("Treeview.Heading", background=BG, foreground=MUTED, relief="flat",
                     font=(FONT, 9, "bold"), padding=(6, 6))
        st.map("Treeview.Heading", background=[("active", PANEL)])
        st.configure("TButton", background=PANEL2, foreground=FG, padding=(14, 8))
        st.map("TButton", background=[("active", "#323d52"), ("disabled", PANEL)],
               foreground=[("disabled", MUTED)])
        st.configure("Accent.TButton", background=ACCENT, foreground="white",
                     font=(FONT, 10, "bold"))
        st.map("Accent.TButton", background=[("active", ACCENT_HI), ("disabled", "#3a2731")],
               foreground=[("disabled", "#9a7d86")])
        st.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=FG, padding=7)
        st.configure("TCombobox", fieldbackground=PANEL, background=PANEL2, foreground=FG,
                     arrowcolor=FG, padding=5)
        st.map("TCombobox", fieldbackground=[("readonly", PANEL)],
               foreground=[("readonly", FG)], selectbackground=[("readonly", PANEL)])
        st.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=BG, arrowcolor=MUTED)
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    def _build(self):
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(head, text="PiStartup", bg=BG, fg=FG, font=(FONT, 20, "bold")).pack(side="left")
        self.summary = tk.StringVar(value="Looking at what starts with your Pi…")
        tk.Label(head, textvariable=self.summary, bg=BG, fg=MUTED,
                 font=(FONT, 10)).pack(side="left", padx=14, pady=(8, 0))

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=18, pady=(4, 10))
        self.q = tk.StringVar()
        self.q.trace_add("write", lambda *_: self.render())
        tk.Label(bar, text="Search", bg=BG, fg=MUTED).pack(side="left")
        ttk.Entry(bar, textvariable=self.q, width=28).pack(side="left", padx=(6, 14))
        self.filter = tk.StringVar(value="Everything")
        cb = ttk.Combobox(bar, textvariable=self.filter, state="readonly", width=20,
                          values=["Everything", "Desktop apps", "Background services",
                                  "Switched off", "Slowest at boot"])
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda *_: self.render())
        ttk.Button(bar, text="⟳  Refresh", command=self.refresh).pack(side="right")

        mid = tk.Frame(self, bg=BG)
        mid.pack(fill="both", expand=True, padx=18)
        cols = ("status", "name", "type", "boot", "detail")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        for c, label, w, stretch in (("status", "STATUS", 96, False), ("name", "NAME", 210, False),
                                     ("type", "TYPE", 140, False), ("boot", "BOOT TIME", 86, False),
                                     ("detail", "WHAT IT IS", 380, True)):
            self.tree.heading(c, text=label, anchor="w", command=lambda c=c: self.sort_by(c))
            self.tree.column(c, width=w, stretch=stretch, anchor="w")
        self.tree.tag_configure("on", foreground=FG)
        self.tree.tag_configure("off", foreground=OFF)
        self.tree.tag_configure("locked", foreground=LOCK)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", lambda e: self.on_toggle())

        card = tk.Frame(self, bg=PANEL, highlightthickness=0)
        card.pack(fill="x", padx=18, pady=12)
        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill="x", padx=16, pady=12)
        left = tk.Frame(inner, bg=PANEL)
        left.pack(side="left", fill="both", expand=True)
        self.d_name = tk.Label(left, text="Pick something from the list", bg=PANEL, fg=FG,
                               font=(FONT, 13, "bold"), anchor="w")
        self.d_name.pack(fill="x")
        self.d_meta = tk.Label(left, text="", bg=PANEL, fg=MUTED, anchor="w", justify="left")
        self.d_meta.pack(fill="x", pady=(2, 0))
        self.d_text = tk.Label(left, text="", bg=PANEL, fg=FG, anchor="w", justify="left",
                               wraplength=640)
        self.d_text.pack(fill="x", pady=(6, 0))
        self.d_warn = tk.Label(left, text="", bg=PANEL, fg=WARN, anchor="w", justify="left",
                               wraplength=640)
        self.d_warn.pack(fill="x", pady=(6, 0))
        right = tk.Frame(inner, bg=PANEL)
        right.pack(side="right", padx=(16, 0))
        self.btn = ttk.Button(right, text="Turn off at startup", style="Accent.TButton",
                              command=self.on_toggle, state="disabled", width=22)
        self.btn.pack(fill="x")
        self.btn_open = ttk.Button(right, text="Open file location", command=self.on_open,
                                   state="disabled")
        self.btn_open.pack(fill="x", pady=(8, 0))
        card.bind("<Configure>", lambda ev: (self.d_text.configure(wraplength=max(300, ev.width - 300)),
                                             self.d_warn.configure(wraplength=max(300, ev.width - 300))))

        self.status = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status, bg=BG, fg=MUTED, anchor="w").pack(
            fill="x", padx=18, pady=(0, 10))

    # -------------------------------------------------- data
    def refresh(self, keep=None):
        keep = keep or (self.current.key if self.current else None)
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.entries = scan_all()
        finally:
            self.config(cursor="")
        on = sum(1 for e in self.entries if e.enabled)
        off = sum(1 for e in self.entries if not e.enabled)
        self.summary.set(f"{on} things start with this Pi  ·  {off} switched off")
        self.render(keep)

    def sorted_entries(self):
        if self.filter.get() == "Slowest at boot":
            return sorted(self.entries, key=lambda e: -e.boot)
        if self.sort_col:
            keyf = {"status": lambda e: (e.locked, not e.enabled),
                    "name": lambda e: e.name.lower(),
                    "type": lambda e: e.type_label,
                    "boot": lambda e: e.boot,
                    "detail": lambda e: e.detail.lower()}[self.sort_col]
            return sorted(self.entries, key=keyf, reverse=self.sort_rev)
        order = {"xdg": 0, "line": 1, "cron": 2, "user": 3, "sys": 4, "info": 5}
        return sorted(self.entries, key=lambda e: (e.locked, order[e.kind], e.name.lower()))

    def render(self, keep=None):
        keep = keep or (self.current.key if self.current else None)
        q, f = self.q.get().lower().strip(), self.filter.get()
        self.tree.delete(*self.tree.get_children())
        self.by_iid.clear()
        sel = None
        for e in self.sorted_entries():
            if f == "Desktop apps" and e.group != DESKTOP:
                continue
            if f == "Background services" and e.group != SERVICE:
                continue
            if f == "Switched off" and e.enabled:
                continue
            if f == "Slowest at boot" and e.boot <= 0:
                continue
            if q and q not in f"{e.name} {e.detail} {e.type_label}".lower():
                continue
            status = "Locked" if e.locked else ("●  On" if e.enabled else "○  Off")
            tag = "locked" if e.locked else ("on" if e.enabled else "off")
            iid = self.tree.insert("", "end", tags=(tag,), values=(
                status, e.name, e.type_label, fmt_dur(e.boot), e.detail))
            self.by_iid[iid] = e
            if keep and e.key == keep:
                sel = iid
        if sel:
            self.tree.selection_set(sel)
            self.tree.see(sel)
        else:
            self.show(None)

    def sort_by(self, col):
        self.sort_rev = not self.sort_rev if self.sort_col == col else False
        self.sort_col = col
        self.render()

    # -------------------------------------------------- details / actions
    def on_select(self, _=None):
        s = self.tree.selection()
        self.show(self.by_iid.get(s[0]) if s else None)

    def show(self, e):
        self.current = e
        if not e:
            self.d_name.config(text="Pick something from the list")
            self.d_meta.config(text="Double-click a row to switch it on or off.")
            self.d_text.config(text="")
            self.d_warn.config(text="")
            self.btn.config(state="disabled", text="Turn off at startup")
            self.btn_open.config(state="disabled")
            return
        state = "starts at boot" if e.enabled else "switched off"
        boot = f"  ·  took {fmt_dur(e.boot)} at last boot" if e.boot else ""
        self.d_name.config(text=e.name)
        self.d_meta.config(text=f"{e.type_label}  ·  {state}{boot}\n{e.source}")
        self.d_text.config(text=e.detail or e.extra.get("exec", ""))
        if e.locked:
            self.d_warn.config(text="🔒  " + e.lock_reason, fg=LOCK)
            self.btn.config(state="disabled", text="Locked")
        else:
            self.d_warn.config(text=("⚠  " + e.caution) if e.caution else "", fg=WARN)
            self.btn.config(state="normal",
                            text="Turn off at startup" if e.enabled else "Turn on at startup")
        self.btn_open.config(state="normal" if os.path.exists(e.source) else "disabled")

    def on_toggle(self):
        e = self.current
        if not e or e.locked:
            return
        turn_on = not e.enabled
        if not turn_on and e.caution:
            if not messagebox.askyesno("Are you sure?",
                                       f"Switch off “{e.name}” at startup?\n\n{e.caution}\n\n"
                                       "You can switch it back on here any time.", icon="warning"):
                return
        ok, err = set_enabled(e, turn_on)
        if ok:
            when = "the next time you log in" if e.group == DESKTOP else "the next time you boot"
            self.status.set(f"“{e.name}” will {'start' if turn_on else 'no longer start'} — "
                            f"takes effect {when}.")
        else:
            messagebox.showerror("Couldn't change that", err or "Something went wrong.")
        self.refresh(keep=e.key)

    def on_open(self):
        e = self.current
        if e and os.path.exists(e.source):
            folder = os.path.dirname(os.path.realpath(e.source))
            try:
                subprocess.Popen(["xdg-open", folder])
            except OSError as ex:
                messagebox.showerror("Couldn't open folder", str(ex))


if __name__ == "__main__":
    App().mainloop()
