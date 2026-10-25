#!/usr/bin/env python3
"""Dead Mall Arena — LAN server.

One small program that serves the game to every browser on your home network
and relays live multiplayer traffic between them over WebSockets.
Python standard library only (3.8+). No internet connection needed.

    python3 server.py              # serve on port 8090
    python3 server.py --port 9000  # start looking at another port
If the port is already taken, the server tries the next one up (8091, 8092, ...)
and prints the address it ended up on.
    python3 server.py --open       # also open the game in this computer's browser
"""
import argparse
import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import signal
import socket
import struct
import sys
import time
import webbrowser
from urllib.parse import unquote, urlparse

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MSG = 64 * 1024
MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg",
    ".svg": "image/svg+xml", ".woff2": "font/woff2", ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8", ".pdf": "application/pdf",
}


def lan_addresses():
    """Best guess at this machine's LAN IPv4 addresses (works with no internet)."""
    found = []
    for probe in ("10.255.255.255", "192.168.255.255", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 1))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


class Player:
    def __init__(self, writer):
        self.writer = writer
        self.id = None
        self.name = "Operator"
        self.joined = time.time()
        self.alive = True
        self.away = False   # browser tab hidden: it can't run the aliens while it's asleep

    def send_raw(self, frame):
        if not self.alive:
            return
        try:
            if self.writer.transport.get_write_buffer_size() > 4 * 1024 * 1024:
                # this browser stopped reading — drop it rather than buffer forever
                self.alive = False
                self.writer.close()
                return
            self.writer.write(frame)
        except Exception:
            self.alive = False

    def send(self, obj):
        self.send_raw(ws_frame(json.dumps(obj, separators=(",", ":")).encode()))


def ws_frame(payload, opcode=0x1):
    n = len(payload)
    if n < 126:
        head = struct.pack("!BB", 0x80 | opcode, n)
    elif n < 65536:
        head = struct.pack("!BBH", 0x80 | opcode, 126, n)
    else:
        head = struct.pack("!BBQ", 0x80 | opcode, 127, n)
    return head + payload


class Arena:
    def __init__(self, port):
        self.port = port
        self.players = {}   # id -> Player
        self.host = None
        self.started = time.time()

    def urls(self):
        return ["http://%s:%d" % (ip, self.port) for ip in lan_addresses()]

    def roster(self):
        return [{"id": p.id, "name": p.name} for p in self.players.values()]

    def broadcast(self, obj, exclude=None):
        frame = ws_frame(json.dumps(obj, separators=(",", ":")).encode())
        for p in list(self.players.values()):
            if p is not exclude:
                p.send_raw(frame)

    def pick_host(self):
        old = self.host
        cur = self.players.get(self.host)
        if cur is None or cur.away:
            awake = [p for p in self.players.values() if not p.away]
            pool = awake or ([cur] if cur else list(self.players.values()))
            self.host = min(pool, key=lambda p: p.joined).id if pool else None
        if self.host != old and self.host:
            self.broadcast({"t": "host", "d": {"id": self.host}})
            print("  host is now %s" % self.players[self.host].name, flush=True)

    def join(self, player, pid, name):
        if pid in self.players and self.players[pid] is not player:
            # same browser reconnecting: retire the stale socket
            stale = self.players[pid]
            stale.alive = False
            try:
                stale.writer.close()
            except Exception:
                pass
        fresh = player.id is None
        player.id, player.name = pid, name
        self.players[pid] = player
        if self.host not in self.players:
            self.host = pid
        if fresh:
            player.send({"t": "welcome", "d": {"you": pid, "host": self.host, "players": self.roster(),
                                                "server": {"urls": self.urls(), "port": self.port}}})
            self.broadcast({"t": "join", "d": {"id": pid, "name": name}}, exclude=player)
            print("  + %s joined (%d in the mall)" % (name, len(self.players)), flush=True)
        else:
            self.broadcast({"t": "join", "d": {"id": pid, "name": name}})

    def leave(self, player):
        if player.id and self.players.get(player.id) is player:
            del self.players[player.id]
            self.broadcast({"t": "leave", "d": {"id": player.id}})
            print("  - %s left (%d in the mall)" % (player.name, len(self.players)), flush=True)
            self.pick_host()

    def relay(self, player, msg):
        if not player.id:
            return
        msg["from"] = player.id
        to = msg.pop("to", None)
        frame = ws_frame(json.dumps(msg, separators=(",", ":")).encode())
        if to:
            target = self.players.get(to)
            if target:
                target.send_raw(frame)
        else:
            for p in list(self.players.values()):
                if p is not player:
                    p.send_raw(frame)


async def read_frame(reader):
    """Returns (opcode, payload) for one complete message, handling fragmentation."""
    chunks, first_op = [], None
    while True:
        b1, b2 = await reader.readexactly(2)
        fin, op = b1 & 0x80, b1 & 0x0F
        masked, n = b2 & 0x80, b2 & 0x7F
        if n == 126:
            n = struct.unpack("!H", await reader.readexactly(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", await reader.readexactly(8))[0]
        if n > MAX_MSG * 4:
            raise ValueError("frame too large")
        mask = await reader.readexactly(4) if masked else b"\0\0\0\0"
        data = bytearray(await reader.readexactly(n))
        if masked:
            for i in range(n):
                data[i] ^= mask[i & 3]
        if op >= 0x8:          # control frames can arrive between fragments
            return op, bytes(data)
        if first_op is None:
            first_op = op
        chunks.append(bytes(data))
        if fin:
            return first_op, b"".join(chunks)


async def serve_ws(arena, reader, writer, headers):
    key = headers.get("sec-websocket-key", "")
    accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
    writer.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
    await writer.drain()
    player = Player(writer)
    try:
        while player.alive:
            op, data = await read_frame(reader)
            if op == 0x8:
                break
            if op == 0x9:
                player.send_raw(ws_frame(data, 0xA))
                continue
            if op != 0x1 or len(data) > MAX_MSG:
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(msg, dict) or not isinstance(msg.get("t"), str):
                continue
            if msg["t"] == "away":
                player.away = bool((msg.get("d") or {}).get("away"))
                if player.id:
                    arena.pick_host()
                continue
            if msg["t"] == "hello":
                d = msg.get("d") or {}
                pid = str(d.get("id") or "")[:48]
                name = str(d.get("name") or "Operator").strip()[:16] or "Operator"
                if pid.startswith("p_"):
                    arena.join(player, pid, name)
                continue
            arena.relay(player, msg)
            await writer.drain() if writer.transport.get_write_buffer_size() > 256 * 1024 else None
    except (asyncio.IncompleteReadError, ConnectionError, ValueError, OSError):
        pass
    finally:
        player.alive = False
        arena.leave(player)
        try:
            writer.close()
        except Exception:
            pass


async def serve_file(writer, path, head_only):
    rel = unquote(urlparse(path).path).lstrip("/") or "index.html"
    full = os.path.realpath(os.path.join(ROOT, rel))
    if not full.startswith(os.path.realpath(ROOT)) or not os.path.isfile(full):
        body = b"Not found"
        writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
        return
    ext = os.path.splitext(full)[1].lower()
    ctype = MIME.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
    with open(full, "rb") as f:
        body = f.read()
    cache = "no-cache" if ext in (".html", ".js") else "max-age=3600"
    writer.write(("HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %d\r\nCache-Control: %s\r\n"
                  "Connection: close\r\n\r\n" % (ctype, len(body), cache)).encode())
    if not head_only:
        writer.write(body)


async def handle(arena, reader, writer):
    try:
        request = await asyncio.wait_for(reader.readline(), 15)
        parts = request.decode("latin-1").split()
        if len(parts) < 2:
            writer.close()
            return
        method, path = parts[0], parts[1]
        headers = {}
        while True:
            line = await asyncio.wait_for(reader.readline(), 15)
            if line in (b"\r\n", b"\n", b""):
                break
            k, _, v = line.decode("latin-1").partition(":")
            headers[k.strip().lower()] = v.strip()
        if urlparse(path).path == "/ws" and headers.get("upgrade", "").lower() == "websocket":
            await serve_ws(arena, reader, writer, headers)
            return
        if urlparse(path).path == "/status":
            body = json.dumps({"players": arena.roster(), "host": arena.host, "urls": arena.urls()}).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body) + body)
        elif method in ("GET", "HEAD"):
            await serve_file(writer, path, method == "HEAD")
        else:
            writer.write(b"HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
    except (asyncio.TimeoutError, ConnectionError, OSError, asyncio.IncompleteReadError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def keepalive(arena):
    ping = ws_frame(b"", 0x9)
    while True:
        await asyncio.sleep(20)
        for p in list(arena.players.values()):
            p.send_raw(ping)


async def main():
    ap = argparse.ArgumentParser(description="Dead Mall Arena LAN server")
    ap.add_argument("--port", type=int, default=8090, help="first port to try (default 8090)")
    ap.add_argument("--tries", type=int, default=20, help="how many ports to try, counting up from --port")
    ap.add_argument("--open", action="store_true", help="open the game in this computer's browser")
    ap.add_argument("--quality", default="", help="graphics preset for the browser opened with --open (ultra, high, medium, pi)")
    args = ap.parse_args()

    arena = Arena(args.port)
    server = None
    for port in range(args.port, args.port + max(1, args.tries)):
        try:
            # asyncio's defaults are right here: on Linux/Mac a port that is merely cooling down from the
            # last run can be reused, but one another program is listening on still fails; on Windows
            # ports are never shared, so a port in use always fails
            server = await asyncio.start_server(lambda r, w: handle(arena, r, w), host="0.0.0.0", port=port)
            break
        except OSError as e:
            print("  port %d is already in use — trying %d" % (port, port + 1), flush=True)
    if server is None:
        print("Could not find a free port between %d and %d. Close other programs or try --port 9000"
              % (args.port, args.port + max(1, args.tries) - 1))
        sys.exit(1)
    arena.port = port
    # tell the launch scripts which port we ended up on
    port_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server-port.txt")
    try:
        with open(port_file, "w") as f:
            f.write(str(port))
    except OSError:
        pass
    asyncio.ensure_future(keepalive(arena))
    print()
    print("  DEAD MALL ARENA — LAN server running")
    print("  ------------------------------------")
    if port != args.port:
        print("  (port %d was taken, so this game is on port %d)" % (args.port, port))
    print("  On this computer:   http://localhost:%d" % port)
    for u in arena.urls():
        print("  Friends on your network:   %s" % u)
    print("  Leave this window open while you play. Ctrl+C to stop.")
    print(flush=True)
    if args.open:
        url = "http://localhost:%d/%s" % (port, ("?q=" + args.quality) if args.quality else "")
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        async with server:
            await server.serve_forever()
    finally:
        try:
            os.remove(port_file)
        except OSError:
            pass


if __name__ == "__main__":
    # closing the Pi launcher sends SIGTERM: treat it like Ctrl+C so the port note gets cleaned up
    try:
        signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    except (ValueError, AttributeError, OSError):
        pass
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  server stopped")
