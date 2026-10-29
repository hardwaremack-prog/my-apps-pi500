#!/usr/bin/env python3
"""
Tidy Suite server for Raspberry Pi / Linux / Mac (the Python twin of "Start Tidy Suite.ps1").

Serves this folder so every Tidy Suite app runs from one web address:
    on this Pi:            http://localhost:8780
    on your home network:  http://<this Pi's address>:8780   (shown when it starts)

Server mode: each person's work is saved in the "Saved work" folder next to this file,
so they can pick up on any device. Opening an app file directly still works on its own.

    python3 tidy_server.py                start and open the browser
    python3 tidy_server.py --local-only   only this Pi can open the suite
    python3 tidy_server.py --port 8781    use a different port (each port keeps its own saved work)
    python3 tidy_server.py --no-browser   don't open the browser (used when it starts with the Pi)

Standard library only. Uses the same "Saved work" layout as the Windows version, so the folder
can be copied between a PC and a Pi.
"""
import argparse, json, mimetypes, os, re, socket, sys, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(ROOT, "Saved work")
HOME_PAGE = next((p for p in ("index.html", "Open Tidy Suite.html") if os.path.exists(os.path.join(ROOT, p))), "index.html")
BLOCKED = {".ps1", ".bat", ".cmd", ".exe", ".lnk", ".py", ".sh"}
TYPES = {".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp", ".ico": "image/x-icon",
         ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
         ".csv": "text/csv; charset=utf-8", ".woff": "font/woff", ".woff2": "font/woff2", ".mp3": "audio/mpeg",
         ".wav": "audio/wav", ".mp4": "video/mp4"}
USER_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
MAX_BODY = 60 * 1024 * 1024
LOCK = threading.Lock()


def hexkey(s):
    return s.encode("utf-8").hex().upper()


def unhex(h):
    return bytes.fromhex(h).decode("utf-8", "replace")


def write_safe(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


class Handler(BaseHTTPRequestHandler):
    server_version = "TidySuite/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8", head=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        if not head and body:
            self.wfile.write(body)

    # ---------------------------------------------------------------- saved work API
    def api(self, method):
        u = urllib.parse.urlsplit(self.path)
        route = u.path[5:].strip("/")
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query, keep_blank_values=True).items()}
        body = ""
        if method in ("PUT", "POST"):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                return self.send(413, '{"error":"too large"}')
            body = self.rfile.read(n).decode("utf-8", "replace") if n else ""
        uid = q.get("user", "")
        if uid and not USER_RE.match(uid):
            return self.send(400, '{"error":"bad person"}')
        udir = os.path.join(STORE, uid) if uid else None
        with LOCK:
            if route == "hello":
                return self.send(200, json.dumps({"suite": "tidy", "version": 1, "computer": socket.gethostname()}))
            if route == "users":
                f = os.path.join(STORE, "people.json")
                if method == "GET":
                    return self.send(200, read_text(f)) if os.path.exists(f) else self.send(404, "null")
                if method == "PUT":
                    write_safe(f, body)
                    return self.send(200, '{"ok":true}')
            if route == "data" and uid:
                if method == "GET":
                    if not os.path.isdir(udir):
                        return self.send(404, "{}")
                    out = {}
                    for name in os.listdir(udir):
                        if name.endswith(".txt"):
                            try:
                                out[unhex(name[:-4])] = read_text(os.path.join(udir, name))
                            except ValueError:
                                pass
                    return self.send(200, json.dumps(out, ensure_ascii=False))
                if method == "DELETE":
                    if os.path.isdir(udir):
                        for name in os.listdir(udir):
                            os.remove(os.path.join(udir, name))
                        os.rmdir(udir)
                    return self.send(200, '{"ok":true}')
            if route == "item" and uid:
                key = q.get("key", "")
                if key and len(key) <= 200:
                    f = os.path.join(udir, hexkey(key) + ".txt")
                    if method == "PUT":
                        write_safe(f, body)
                        return self.send(200, '{"ok":true}')
                    if method == "DELETE":
                        if os.path.exists(f):
                            os.remove(f)
                        return self.send(200, '{"ok":true}')
        return self.send(400, '{"error":"unknown request"}')

    # ---------------------------------------------------------------- files
    def serve(self, head=False):
        path_part = urllib.parse.urlsplit(self.path).path
        if path_part.startswith("/api/"):
            return self.api("GET")
        rel = urllib.parse.unquote(path_part).lstrip("/") or HOME_PAGE
        full = os.path.realpath(os.path.join(ROOT, rel))
        if os.path.isdir(full):
            leaf = os.path.basename(full).lower()
            for idx in ("index.html", leaf + ".html"):
                if os.path.isfile(os.path.join(full, idx)):
                    full = os.path.join(full, idx)
                    break
        root = os.path.realpath(ROOT) + os.sep
        store = os.path.realpath(STORE) + os.sep
        ext = os.path.splitext(full)[1].lower()
        if not full.startswith(root) or full.startswith(store) or not os.path.isfile(full) or ext in BLOCKED:
            msg = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>Not found</title>"
                   "<body style='font-family:system-ui;padding:40px'><h1>Not found</h1><p>There's no <b>%s</b> in the Tidy Suite folder.</p>"
                   "<p><a href='/'>Go to the Tidy Suite home page</a></p>") % rel.replace("&", "&amp;").replace("<", "&lt;")
            return self.send(404, msg, "text/html; charset=utf-8", head)
        with open(full, "rb") as f:
            data = f.read()
        self.send(200, data, TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream", head)

    def do_GET(self):
        self.serve()

    def do_HEAD(self):
        self.serve(head=True)

    def do_PUT(self):
        if self.path.startswith("/api/"):
            return self.api("PUT")
        self.send(405, "Only GET is supported", "text/plain")

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            return self.api("DELETE")
        self.send(405, "Only GET is supported", "text/plain")


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(i for i in ips if not i.startswith(("127.", "169.254.")))


def main():
    ap = argparse.ArgumentParser(description="Tidy Suite server")
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--local-only", action="store_true", help="only this computer can open the suite")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    local = "http://localhost:%d/" % a.port
    try:
        srv = ThreadingHTTPServer(("127.0.0.1" if a.local_only else "0.0.0.0", a.port), Handler)
    except OSError:
        try:
            import urllib.request
            if b"Tidy Suite" in urllib.request.urlopen(local, timeout=3).read():
                print("Tidy Suite is already running at " + local)
                if not a.no_browser:
                    webbrowser.open(local)
                return
        except Exception:
            pass
        print("Port %d is being used by another program." % a.port)
        print("Close that program, or start the suite with:  --port 8781")
        print("(A different port starts with fresh saved work, so stick with one port.)")
        sys.exit(1)
    print("\n  Tidy Suite is running")
    print("  On this Pi:        " + local)
    if not a.local_only:
        for ip in lan_ips():
            print("  On your network:   http://%s:%d/" % (ip, a.port))
        print("  Phones and computers on the same Wi-Fi can open that address.")
    print("  Server mode: everyone's work is saved in the 'Saved work' folder here.")
    print("  Leave this running while you use the apps. Ctrl+C stops it.\n")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(local)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
