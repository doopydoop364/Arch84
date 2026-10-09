#!/usr/bin/env python3
"""Arch84 network bridge: gives the calculator internet access through this computer.

The calculator cannot open a socket, and any variable transfer over USB closes the running
Python app, so the two channels are the ones that leave it alone (docs/NETWORK.md):

  calculator -> PC   Arch84 draws its request as rows of characters; this program reads the
                     screen (tools/a84screen.py) a few times a second;
  PC -> calculator   the answer is typed: key presses injected over USB (32 harmless keys carry
                     5 bits each, in checksummed, compressed frames; lost chunks are resent).

    python3 tools/a84bridge.py                  run (what the systemd user service does)
    python3 tools/a84bridge.py --allow HOST     also allow downloads from HOST

Safety: only https/http downloads from hosts on the allowlist (default
doopydoop364.github.io; ~/.config/arch84/bridge.conf "allow = host host" adds more), redirects
are re-checked against it, bodies are capped at 2 MB, nothing listens on the network, and the
calculator can ask for nothing else (no files, no commands).

Keepalive: the calculator turns itself off after a while; every few minutes the bridge presses
the one key Arch84 ignores everywhere (scancode 0x28) to keep it awake.
"""
import argparse
import logging
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import A84NT
from A84NT import T_REQ, T_STATUS, T_DATA, T_FIN

VERSION = "2.0"
KEEPALIVE_KEY = 0x28        # positional 32: not mapped by any Arch84 key table, not a symbol key
CHUNK = 300                 # raw bytes per DATA frame
MAXBODY = 2 * 1024 * 1024
DEFAULT_HOSTS = ("doopydoop364.github.io",)
OK, BAD_REQUEST, DENIED, FETCH_FAILED, HTTP_ERROR, TOO_BIG, UNKNOWN_OP = 0, 1, 2, 3, 4, 5, 6

log = logging.getLogger("a84bridge")


class Denied(Exception):
    pass


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed):
        self.allowed = allowed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urllib.parse.urlsplit(newurl).hostname
        if host not in self.allowed:
            raise Denied("redirect to a host that is not allowed: " + str(host))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def compress(piece):
    """(flag, bytes): the piece LZSS-compressed when that is smaller (the calculator's decoder)."""
    from A84CY import lz_compress
    c = bytes(lz_compress(piece))
    if len(c) < len(piece):
        return 1, c
    return 0, piece


def chunk_payloads(resp, size=CHUNK, first=0):
    """The answer cut into DATA payloads: idx(2) flag(1) rawlen(2) data (numbered from `first`)."""
    out = []
    for i in range(0, len(resp), size):
        piece = resp[i:i + size]
        flag, data = compress(piece)
        idx = first + len(out)
        out.append(bytes((idx >> 8, idx & 255, flag, len(piece) >> 8, len(piece) & 255)) + data)
    if not out and first == 0:
        out.append(bytes((0, 0, 0, 0, 0)))
    return out


def raw_length(payloads):
    return sum((p[3] << 8) | p[4] for p in payloads)


class Bridge:
    def __init__(self, screen, keys, hosts=DEFAULT_HOSTS, clock=time.time, fetch=None, ttl=90,
                 sleep=time.sleep, settle=0.9):
        self.screen = screen        # .frame() -> (type, seq, payload) or None
        self.keys = keys            # .send(symbols)
        self.hosts = set(hosts)
        self.clock = clock
        self.fetch_body = fetch or self.http_get
        self.ttl = ttl
        self.sleep = sleep
        self.settle = settle        # seconds the calculator gets to process a batch before we look
        self.cache = {}
        self.last_seq = None
        self.started = clock()
        self.served = 0

    # ---------------------------------------------------------------- network
    def http_get(self, url):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.hostname not in self.hosts:
            raise Denied("host not allowed: " + str(parts.hostname))
        opener = urllib.request.build_opener(_CheckedRedirects(self.hosts))
        req = urllib.request.Request(url, headers={"User-Agent": "Arch84-bridge/" + VERSION})
        with opener.open(req, timeout=20) as r:
            body = r.read(MAXBODY + 1)
        if len(body) > MAXBODY:
            raise OverflowError("body larger than %d bytes" % MAXBODY)
        return body

    def body(self, url):
        now = self.clock()
        hit = self.cache.get(url)
        if hit is not None and now - hit[0] < self.ttl:
            return hit[1]
        data = self.fetch_body(url)
        self.cache = {k: v for k, v in self.cache.items() if now - v[0] < self.ttl}
        self.cache[url] = (now, data)
        return data

    # ------------------------------------------------------------------ ops
    def handle(self, op, args):
        """-> the answer: one status byte, then data."""
        if op == A84NT.OP_PING:
            return bytes((OK,)) + ("pong %s %d" % (VERSION, int(self.clock()))).encode()
        if op == A84NT.OP_TIME:
            lt = time.localtime(self.clock())
            return bytes((OK,)) + ("%d %d %s" % (int(self.clock()), lt.tm_gmtoff or 0, lt.tm_zone or "")).encode()
        if op == A84NT.OP_ECHO:
            return bytes((OK,)) + args
        if op == A84NT.OP_STAT:
            return bytes((OK,)) + ("arch84-bridge %s\nup %d\nserved %d\nhosts %s" % (
                VERSION, int(self.clock() - self.started), self.served,
                " ".join(sorted(self.hosts)))).encode()
        if op == A84NT.OP_GET:
            return self.op_get(args)
        return bytes((UNKNOWN_OP,)) + b"unknown operation"

    def op_get(self, args):
        try:
            url = args.decode("utf-8")
        except UnicodeDecodeError:
            return bytes((BAD_REQUEST,)) + b"bad URL"
        try:
            return bytes((OK,)) + self.body(url)
        except Denied as e:
            return bytes((DENIED,)) + str(e).encode()[:120]
        except urllib.error.HTTPError as e:
            e.close()
            return bytes((HTTP_ERROR,)) + str(e.code).encode()
        except OverflowError as e:
            return bytes((TOO_BIG,)) + str(e).encode()[:120]
        except (urllib.error.URLError, OSError, ValueError) as e:
            return bytes((FETCH_FAILED,)) + str(e).encode("utf-8", "replace")[:120]

    # -------------------------------------------------------------- the wire
    def poll_once(self):
        """Serve the request on the screen, if there is a new one. True when one was handled."""
        fr = self.screen.frame()
        if fr is None or fr[0] != T_REQ or fr[1] == self.last_seq or len(fr[2]) < 1:
            return False
        seq, payload = fr[1], fr[2]
        self.last_seq = seq
        t0 = time.time()
        resp = self.handle(payload[0], payload[1:])
        ok = self.deliver(seq, resp)
        self.served += 1
        log.info("seq %d op %d -> status %d, %d bytes, %s (%.1fs)", seq, payload[0], resp[0], len(resp) - 1,
                 "delivered" if ok else "NOT delivered", time.time() - t0)
        return True

    def send_frame(self, ftype, seq, payload):
        self.keys.send(list(A84NT.SYNC) + A84NT.frame_symbols(ftype, seq, payload))

    def deliver(self, seq, resp):
        size = CHUNK
        chunks = chunk_payloads(resp, size)
        total = len(chunks)
        start = 0
        stuck = 0
        resend_all = True
        for attempt in range(60):
            fr = self.screen.frame()
            if fr is None or fr[1] != seq:
                if attempt > 0:
                    return True         # it had the whole answer and took the frame down
                log.warning("seq %d: the calculator left the request (nothing more is sent)", seq)
                return False
            if resend_all:
                for i in range(start, total):
                    if i > start:
                        cur = self.screen.frame()      # still waiting for us? (it gives the screen back when it quits)
                        if cur is None or cur[1] != seq:
                            log.warning("seq %d: the calculator left the request, stopping", seq)
                            return False
                    self.send_frame(T_DATA, seq, chunks[i])
                    self.sleep(0.12)                   # let the calculator decode and store the chunk
            rnd = (attempt + 1) & 255                      # the status must answer THIS round
            self.send_frame(T_FIN, seq, bytes((total >> 8, total & 255, rnd)))
            self.sleep(self.settle)
            st = None
            blank = 0
            for _ in range(6):
                st = self.screen.frame()
                if st is None:
                    blank += 1
                    if blank >= 2:
                        return True             # no frame twice in a row: the calculator finished and took it down
                else:
                    blank = 0
                if st is not None and st[0] == T_STATUS and st[1] == seq and len(st[2]) >= 4 and st[2][3] == rnd:
                    break
                st = None
                self.sleep(0.4)
            if st is None:
                stuck += 1                             # no status: the FIN itself may be lost, try it alone
                resend_all = stuck % 2 == 0
                if stuck >= 20:
                    return False
                continue
            nxt = (st[2][0] << 8) | st[2][1]
            if st[2][2] == 1 and nxt >= total:
                return True
            if nxt > start:
                stuck = 0                              # progress
            else:
                stuck += 1
                if stuck >= 2 and size > 60:           # a chunk keeps failing: send the rest in smaller pieces
                    size = max(60, size // 2)
                    off = raw_length(chunks[:nxt])
                    chunks = chunks[:nxt] + chunk_payloads(resp[off:], size, nxt)
                    total = len(chunks)
                    log.info("seq %d: chunk %d keeps failing, now %d byte chunks", seq, nxt, size)
                    stuck = 0
                if attempt >= 40:
                    return False
            log.info("seq %d: the calculator has %d of %d chunks, resending", seq, nxt, total)
            start = max(0, min(nxt, total - 1))
            resend_all = True
        return False


class RealScreen:
    def frame(self):
        import a84screen
        return a84screen.read_frame(a84screen.grab())


class RealKeys:
    def send(self, symbols):
        import evo_usb
        from csc import GK2CSC
        from usblock import usb_lock
        codes = [GK2CSC[A84NT.KEYS[s]] for s in symbols]
        for i in range(0, len(codes), 200):
            with usb_lock():
                evo_usb.send_scancodes(codes[i:i + 200], delay=0.0)


class Keepalive(threading.Thread):
    """Press the one key Arch84 ignores (0x28) now and then so the calculator does not switch itself off."""
    def __init__(self, every, press):
        super().__init__(daemon=True)
        self.every = every
        self.press = press
        self.stop = threading.Event()

    def run(self):
        while not self.stop.wait(self.every):
            try:
                self.press()
                log.debug("keepalive")
            except BaseException as e:      # SystemExit comes from evo_usb.connect()
                log.warning("keepalive failed: %s", e)


def press_keys():
    import evo_usb
    from usblock import usb_lock
    with usb_lock():
        evo_usb.send_scancodes([KEEPALIVE_KEY], delay=0.0)


def load_hosts(extra):
    hosts = list(DEFAULT_HOSTS)
    conf = os.path.expanduser("~/.config/arch84/bridge.conf")
    if os.path.isfile(conf):
        for line in open(conf):
            line = line.split("#")[0].strip()
            if line.startswith("allow"):
                hosts += line.split("=", 1)[1].split()
    return hosts + list(extra)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--allow", action="append", default=[], metavar="HOST")
    ap.add_argument("--interval", type=float, default=0.5, help="seconds between screen checks")
    ap.add_argument("--keepalive", type=float, default=150.0, help="seconds between key presses (0 = off)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    bridge = Bridge(RealScreen(), RealKeys(), load_hosts(a.allow))
    log.info("arch84-bridge %s, hosts: %s", VERSION, " ".join(sorted(bridge.hosts)))
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *x: stop.set())
    signal.signal(signal.SIGINT, lambda *x: stop.set())
    if a.keepalive:
        Keepalive(a.keepalive, press_keys).start()
    quiet = 0
    failures = 0
    while not stop.is_set():
        try:
            busy = bridge.poll_once()
            failures = 0
        except BaseException as e:          # SystemExit: evo_usb.connect() exits when the calculator is absent
            if isinstance(e, KeyboardInterrupt):
                break
            failures += 1
            if failures in (1, 10, 100):
                log.warning("calculator link: %s (retrying)", e)
            stop.wait(min(30.0, 1.0 * failures))
            continue
        quiet = 0 if busy else quiet + 1
        stop.wait(a.interval if quiet < 30 else 1.5)    # idle for a while: look less often
    log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
