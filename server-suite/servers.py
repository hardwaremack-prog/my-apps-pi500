"""
Running servers for Server Room: finds every web server on this Pi and can stop one.

Finds them by listening TCP port (ss, or /proc when ss is missing), reads each page's title,
and names it from the suite's app list when it can. Stopping works out what owns the port:
  - a systemd service      -> systemctl stop   (user services directly; system services through
                              polkit or passwordless sudo, which Raspberry Pi OS has by default)
  - a Podman/Docker container -> podman/docker stop of that container
  - a plain program        -> SIGTERM, then SIGKILL if it won't close
Standard library only.
"""
import http.client, json, os, re, shutil, signal, socket, subprocess, threading, time

# ports never offered for stopping: Server Room itself and the My Apps helper (it also runs Web access)
PROTECTED = {8410: "That's Server Room itself.", 8399: "That's the My Apps server-lights helper.",
             8400: "That's My Apps web access. Switch it off in My Apps (Web access)."}
REMOTE = {22: "SSH", 445: "File sharing (Samba)", 139: "File sharing (Samba)", 3389: "Remote Desktop"}
SKIP = {53, 111, 631, 4713, 5353}      # DNS, rpcbind, printer queue, sound server, mDNS
CONTAINER_PROCS = {"rootlessport", "rootlessport-child", "conmon", "podman", "docker-proxy",
                   "containerd-shim", "slirp4netns", "pasta"}

_titles = {}
_lock = threading.Lock()


def run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def listening():
    """{port: {"proc": program name, "local": True if only this Pi can reach it}}"""
    out = run(["ss", "-ltnpH"]) or run(["ss", "-ltnp"])
    ports = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or not parts[0].startswith("LISTEN"):
            continue
        addr, _, p = parts[3].rpartition(":")
        try:
            port = int(p)
        except ValueError:
            continue
        local = bool(re.match(r"^(127\.|\[::1\]|::1|\[::ffff:127\.)", addr))
        m = re.search(r'\(\("([^"]+)"', line)
        e = ports.setdefault(port, {"proc": "", "local": True})
        e["local"] = e["local"] and local
        if m and not e["proc"]:
            e["proc"] = m.group(1)
    if not ports:   # no "ss": read the kernel's socket table directly
        for fn in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                for line in open(fn).read().splitlines()[1:]:
                    f = line.split()
                    if len(f) > 3 and f[3] == "0A":
                        a, p = f[1].split(":")
                        local = a in ("0100007F", "00000000000000000000000001000000")
                        e = ports.setdefault(int(p, 16), {"proc": "", "local": True})
                        e["local"] = e["local"] and local
            except OSError:
                pass
    return ports


def http_probe(port, timeout=1.2):
    """(status, title) if the port answers like a web server, else None."""
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        c.request("GET", "/", headers={"User-Agent": "ServerRoom", "Accept": "text/html,*/*"})
        r = c.getresponse()
        body = r.read(65536).decode("utf-8", "replace")
        c.close()
        m = re.search(r"<title[^>]*>([^<]{1,120})</title>", body, re.I)
        return r.status, (m.group(1).strip() if m else "")
    except Exception:
        return None


def scan(names=None):
    """Every web server on this Pi (newest scan). names: [(title regex, ports, friendly name)]"""
    now = time.time()
    ports = listening()
    ip = lan_ip()
    out = []
    for p in sorted(ports):
        if p in SKIP or p in REMOTE or 5900 <= p <= 5910:
            continue
        with _lock:
            t = _titles.get(p)
        if not t or now - t[0] > 20:
            r = http_probe(p)
            t = (now, r[0] if r else 0, r[1] if r else None)
            with _lock:
                _titles[p] = t
        if t[2] is None:
            continue            # not a web server
        status, title, proc = t[1], t[2], ports[p]["proc"]
        if not title and status >= 400 and not proc:
            continue            # an unnamed helper port that isn't a real page
        name = ""
        for rx, pp, nm in (names or []):
            if (title and re.search(rx, title, re.I)) or (not title and p in pp):
                name = nm
                break
        name = name or (title if title and len(title) <= 40 else "") or (proc and proc + " web server") or "Port %d" % p
        s = dict(port=p, name=name, title=title or "", proc=proc, status=status,
                 url="http://127.0.0.1:%d/" % p, lan=None if ports[p]["local"] else "http://%s:%d/" % (ip, p),
                 local_only=ports[p]["local"], stoppable=p not in PROTECTED)
        if p in PROTECTED:
            s["why"] = PROTECTED[p]
        out.append(s)
    remote = [dict(port=p, name=REMOTE[p]) for p in sorted(ports) if p in REMOTE and p != 139]
    vnc = next((p for p in sorted(ports) if 5900 <= p <= 5910), None)
    if vnc:
        remote.append(dict(port=vnc, name="VNC"))
    with _lock:
        for p in list(_titles):
            if p not in ports:
                del _titles[p]
    return {"servers": out, "remote": remote, "ip": ip}


# ------------------------------------------------------------------ stopping
def port_pids(port):
    """[(pid, program)] listening on this TCP port (asks sudo -n when the owner is hidden)."""
    def parse(out):
        found = []
        for line in out.splitlines():
            if not line.startswith("LISTEN"):
                continue
            try:
                if int(line.split()[3].rsplit(":", 1)[1]) != port:
                    continue
            except (ValueError, IndexError):
                continue
            for name, pid in re.findall(r'\("([^"]+)",pid=(\d+)', line):
                if (int(pid), name) not in found:
                    found.append((int(pid), name))
        return found
    got = parse(run(["ss", "-ltnpH"]))
    if not got and shutil.which("sudo"):
        got = parse(run(["sudo", "-n", "ss", "-ltnpH"]))
    if not got:
        got = proc_pids(port)
    return got


def proc_pids(port):
    inodes = set()
    for fn in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            for line in open(fn).read().splitlines()[1:]:
                f = line.split()
                if len(f) > 9 and f[3] == "0A" and int(f[1].rsplit(":", 1)[1], 16) == port:
                    inodes.add("socket:[%s]" % f[9])
        except OSError:
            pass
    found = []
    if not inodes:
        return found
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            for fd in os.listdir("/proc/%s/fd" % pid):
                if os.readlink("/proc/%s/fd/%s" % (pid, fd)) in inodes:
                    found.append((int(pid), open("/proc/%s/comm" % pid).read().strip()))
                    break
        except OSError:
            continue
    return found


def unit_of(pid):
    """('system'|'user', 'name.service') if systemd runs this program as a service, else (None, None)."""
    try:
        cg = open("/proc/%d/cgroup" % pid).read()
    except OSError:
        return None, None
    m = re.search(r"/user@\d+\.service/.*?([^/]+\.service)\s*$", cg, re.M)
    if m:
        return "user", m.group(1)
    m = re.search(r"/system\.slice/(?:.*/)?([^/]+\.service)\s*$", cg, re.M)
    if m:
        return "system", m.group(1)
    return None, None


def sudo_ok(cmd, timeout=40):
    return bool(shutil.which("sudo")) and subprocess.run(["sudo", "-n"] + cmd, capture_output=True,
                                                         timeout=timeout).returncode == 0


NEEDS_OK = ("%s runs as a system service, so stopping it needs your OK once. Run install-server-suite.sh "
            "again (it asks for your password one time), or stop it in a Terminal:  sudo systemctl stop %s")


def stop_unit(scope, unit, name):
    if scope == "user":
        run(["systemctl", "--user", "stop", unit], timeout=30)
        return True, ""
    r = subprocess.run(["systemctl", "--no-ask-password", "stop", unit], capture_output=True, text=True, timeout=40)
    if r.returncode == 0 or sudo_ok(["systemctl", "stop", unit]):
        return True, ""
    return False, NEEDS_OK % (name, unit)


def unit_enabled(scope, unit):
    return run(["systemctl"] + (["--user"] if scope == "user" else []) + ["is-enabled", unit]).strip() == "enabled"


def still_listening(port, wait=5.0):
    end = time.time() + wait
    while time.time() < end:
        if port not in listening():
            return False
        time.sleep(0.3)
    return True


def container_on(port):
    """(tool, container id, name, use_sudo) publishing this port, if any."""
    for tool, sudo in (("podman", False), ("docker", False), ("docker", True)):
        if not shutil.which(tool):
            continue
        cmd = ["sudo", "-n", tool] if sudo else [tool]
        out = run(cmd + ["ps", "--format", "{{.ID}}\t{{.Names}}\t{{.Ports}}"], 10)
        for line in out.splitlines():
            f = line.split("\t")
            if len(f) >= 3 and re.search(r":%d->" % port, f[2]):
                return tool, f[0], f[1], sudo
    return None


def stop(port, name, known_unit=None):
    """(ok, message)"""
    port = int(port)
    if port in PROTECTED:
        return False, PROTECTED[port]
    if port in REMOTE or 5900 <= port <= 5910:
        return False, "Remote access is switched off in Raspberry Pi Configuration > Interfaces, so you don't lock yourself out."
    pids = port_pids(port)
    if any(pid == os.getpid() for pid, _ in pids):
        return False, PROTECTED[8410]
    if not pids or {p for _, p in pids} & CONTAINER_PROCS:
        c = container_on(port)
        if c:
            tool, cid, cname, sudo = c
            cmd = (["sudo", "-n"] if sudo else []) + [tool, "stop", cid]
            if subprocess.run(cmd, capture_output=True, timeout=60).returncode == 0:
                return True, "Stopped the %s container. Start it again in PodDeck (or: %s start %s)." % (cname, tool, cname)
            return False, "Couldn't stop the %s container. Stop it in PodDeck." % cname
        if pids:
            return False, "%s runs in a container. Stop it in PodDeck." % name
    units, loose = [], []
    for pid, prog in pids:
        scope, unit = unit_of(pid)
        if unit in ("server-room.service", "myapps-status.service"):
            return False, "That one is part of Server Room or My Apps."
        if unit:
            if (scope, unit) not in units:
                units.append((scope, unit))
        else:
            loose.append(pid)
    if not pids and known_unit:
        scope, unit = ("user", known_unit[5:]) if known_unit.startswith("user:") else ("system", known_unit)
        if run(["systemctl"] + (["--user"] if scope == "user" else []) + ["is-active", unit]).strip() == "active":
            units.append((scope, unit))
    if not pids and not units:
        return False, ("%s belongs to the system. Stop it in a Terminal with sudo, or restart the Pi." % name
                       if owned_by_root(port) else
                       "Couldn't tell which program runs %s. Close its window, or restart the Pi." % name)
    boot = False
    for scope, unit in units:
        ok, why = stop_unit(scope, unit, name)
        if not ok:
            return False, why
        boot = boot or unit_enabled(scope, unit)
    for pid in loose:
        try:
            os.kill(pid, signal.SIGTERM)
        except PermissionError:
            if not sudo_ok(["kill", "-TERM", str(pid)]):
                return False, "%s was started as root. Close it where it was started, or restart the Pi." % name
        except ProcessLookupError:
            pass
    if still_listening(port):
        for pid in loose:
            try:
                os.kill(pid, signal.SIGKILL)
            except PermissionError:
                sudo_ok(["kill", "-KILL", str(pid)])
            except ProcessLookupError:
                pass
        if still_listening(port, 3):
            return False, "%s is still running. Try again, or restart the Pi." % name
    with _lock:
        _titles.pop(port, None)
    msg = "Stopped %s." % name
    if known_unit == "pironman5.service" or any(u == "pironman5.service" for _, u in units):
        msg += " The case fans run at their default until it's back."
    if boot:
        msg += " It starts again by itself when the Pi restarts."
    return True, msg


def owned_by_root(port):
    for fn in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            for line in open(fn).read().splitlines()[1:]:
                f = line.split()
                if len(f) > 7 and f[3] == "0A" and int(f[1].rsplit(":", 1)[1], 16) == port:
                    return f[7] == "0"
        except OSError:
            pass
    return False
