"""Network bridge tests. The calculator side (A84NT/A84NC) and the real bridge code
(tools/a84bridge.py) run against a simulated calculator: its screen frame is what the bridge
reads, its key queue is what the bridge types into. Downloads come from a local web server.
No hardware needed. Run: python3 test_net.py"""
import collections
import gzip
import http.server
import os
import random
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, ".")
sys.path.insert(0, "tools")
import a84bridge
import a84screen
import csc
import test_arch84 as T
import A84NT


# ---------------------------------------------------------------- the simulated calculator
class SimTi:
    """get_key(0) as the calculator gives it: a key is down for one call, then released."""
    def __init__(self, drop=0.0, seed=1):
        self.q = collections.deque()
        self.pending_release = False
        self.rng = random.Random(seed)
        self.drop = drop
        self.lock = threading.Lock()
        self.presses = 0

    def push(self, code):
        with self.lock:
            self.presses += 1
            if self.drop and self.rng.random() < self.drop:
                return                      # a lost key press
            self.q.append(code)

    def get_key(self, wait):
        if self.pending_release:
            self.pending_release = False
            return 0
        with self.lock:
            if self.q:
                self.pending_release = True
                return self.q.popleft()
        time.sleep(0.0004)
        return 0


class SimTerm(T.CaptureTerm):
    def __init__(self, ti):
        T.CaptureTerm.__init__(self)
        self.ti = ti
        self.rows = None
        self.frames = 0

    def show_rows(self, rows):
        self.rows = list(rows)
        self.frames += 1

    def end_frame(self):
        self.rows = None


class SimScreen:
    def __init__(self, term):
        self.term = term

    def frame(self):
        rows = self.term.rows
        if rows is None:
            return None
        syms = []
        for r in rows[1:]:
            for ch in r[1:]:
                i = A84NT.ALPHA.find(ch)
                syms.append(i)
        if len(syms) < 12 or -1 in syms[:12]:
            return None
        n = (A84NT.from_symbols(syms[:12])[5] << 8) | A84NT.from_symbols(syms[:12])[6]
        need = ((11 + n) * 8 + 4) // 5
        if need > len(syms) or -1 in syms[:need]:
            return None
        return A84NT.parse(A84NT.from_symbols(syms[:need]))


class SimKeys:
    def __init__(self, ti):
        self.ti = ti
        self.sent = 0

    def send(self, symbols):
        for s in symbols:
            self.sent += 1
            self.ti.push(A84NT.KEYS[s])
        t0 = time.time()                       # real USB paces the keys: return once they are consumed
        while self.ti.q and time.time() - t0 < 30:
            time.sleep(0.0005)


class Server:
    def __init__(self, files):
        self.files = files
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/redir":
                    self.send_response(302)
                    self.send_header("Location", "http://evil.example/x")
                    self.end_headers()
                    return
                body = outer.files.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class Rig:
    """A calculator shell + a bridge thread watching its screen and typing into its keys."""
    def __init__(self, files=None, hosts=("127.0.0.1",), drop=0.0, clock=None, bridge=True):
        self.server = Server(files or {})
        self.ti = SimTi(drop)
        self.sh, _ = T.mk()
        self.t = SimTerm(self.ti)
        self.sh.term = self.t
        self.keys = SimKeys(self.ti)
        kw = {"clock": clock} if clock else {}
        self.bridge = a84bridge.Bridge(SimScreen(self.t), self.keys, hosts,
                                       sleep=lambda s: time.sleep(s / 60.0), settle=0.03, **kw)
        self.stop = threading.Event()
        self.thread = None
        if bridge:
            self.thread = threading.Thread(target=self.loop, daemon=True)
            self.thread.start()

    def loop(self):
        while not self.stop.is_set():
            try:
                self.bridge.poll_once()
            except Exception as e:
                print("bridge error", repr(e))
            time.sleep(0.005)

    def run(self, line):
        return T.run(self.sh, self.t, line)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(3)
        self.server.close()


# ---------------------------------------------------------------- codec and screen
class CodecTests(unittest.TestCase):
    def test_frames_roundtrip_and_damage_is_detected(self):
        f = A84NT.build(A84NT.T_REQ, 123456, b"hello world")
        self.assertEqual(A84NT.parse(f), (A84NT.T_REQ, 123456, b"hello world"))
        bad = bytearray(f)
        bad[9] ^= 1
        self.assertIsNone(A84NT.parse(bytes(bad)))
        self.assertIsNone(A84NT.parse(f[:-1]))
        self.assertIsNone(A84NT.parse(b"\x00" + f[1:]))

    def test_symbols_roundtrip_for_every_length(self):
        for n in range(0, 40):
            data = bytes((i * 91 + n) % 256 for i in range(n))
            syms = A84NT.to_symbols(data)
            self.assertTrue(all(0 <= s < 32 for s in syms))
            self.assertEqual(A84NT.from_symbols(syms)[:n], data)

    def test_the_largest_request_fits_the_screen(self):
        payload = bytes(range(A84NT.MAXPAYLOAD))
        rows = A84NT.frame_rows(A84NT.build(A84NT.T_REQ, 1, payload))
        self.assertEqual(len(rows), A84NT.ROWS)
        for r in rows:
            self.assertEqual(len(r), A84NT.COLS + 1)           # a blank first cell + 30 symbols
            self.assertEqual(r[0], " ")
        self.assertEqual(A84NT.parse(A84NT.from_symbols(
            [A84NT.ALPHA.index(c) for r in rows for c in r[1:]])), (A84NT.T_REQ, 1, payload))

    def test_the_symbol_keys_are_safe(self):
        self.assertEqual(len(set(A84NT.KEYS)), 32)
        for bad in (105, 45, 21, 31, 22, 23, 32):              # Enter CLEAR 2nd alpha mode del + the keepalive key
            self.assertNotIn(bad, A84NT.KEYS)
        for k in A84NT.KEYS:
            self.assertIn(k, csc.GK2CSC)                        # and every one can be injected

    def test_utf8_split(self):
        s = "a\u20acb".encode()
        self.assertEqual(A84NT.utf8_split(s[:2]), (b"a", b"\xe2"))
        self.assertEqual(A84NT.utf8_split(s[:3]), (b"a", b"\xe2\x82"))
        self.assertEqual(A84NT.utf8_split(s[:4]), (s[:4], b""))
        self.assertEqual(A84NT.utf8_split(b""), (b"", b""))


def render(rows):
    """Draw text rows (a frame) into a 320x240 RGB565 screenshot with the learned glyph shapes."""
    t = a84screen.templates()
    shape = {sym: bytes.fromhex(h) for h, sym in t.items()}
    img = bytearray(320 * 240 * 2)
    for r, text in enumerate(rows):
        for c, ch in enumerate(text):
            i = A84NT.ALPHA.find(ch)
            if i < 0:
                continue
            bits = shape[i]
            for k, b in enumerate(bits):
                if b:
                    y = a84screen.CANVAS_Y + r * 18 + 1 + k // 10
                    x = c * 10 + k % 10
                    o = (y * 320 + x) * 2
                    img[o] = 0xFF
                    img[o + 1] = 0xFF
    return bytes(img)


class ScreenTests(unittest.TestCase):
    def test_the_learned_glyphs_read_the_real_calculator_screenshot(self):
        rgb = gzip.open("tools/fixtures/glyphs.rgb.gz").read()       # a screenshot from a TI-84 Evo
        self.assertEqual(a84screen.read_symbols(rgb, rows=[0]), list(range(30)))
        self.assertEqual(a84screen.read_symbols(rgb, rows=[1]), list(range(2, 32)))

    def test_every_symbol_has_its_own_shape(self):
        self.assertEqual(len(set(a84screen.templates().values())), 32)

    def test_a_frame_survives_being_drawn_and_read_back(self):
        payload = bytes((i * 7) % 256 for i in range(150))
        rows = ["NET test CLEAR=quit"] + A84NT.frame_rows(A84NT.build(A84NT.T_REQ, 424242, payload))
        self.assertEqual(a84screen.read_frame(render(rows)), (A84NT.T_REQ, 424242, payload))

    def test_a_blank_or_foreign_screen_is_no_frame(self):
        self.assertIsNone(a84screen.read_frame(bytes(320 * 240 * 2)))
        rows = ["hello"] + ["0123456789ABCDEFGHJKLMNPQRSTUV"] * 10
        self.assertIsNone(a84screen.read_frame(render(rows)))      # symbols, but not a frame

    def test_a_half_drawn_frame_is_not_misread(self):
        rows = ["NET x"] + A84NT.frame_rows(A84NT.build(A84NT.T_REQ, 7, bytes(range(100))))
        rows[3] = " " * 31                                          # a row missing
        self.assertIsNone(a84screen.read_frame(render(rows)))


# ---------------------------------------------------------------- the bridge
class BridgeUnitTests(unittest.TestCase):
    def mk(self, **kw):
        t = SimTerm(SimTi())
        return a84bridge.Bridge(SimScreen(t), SimKeys(t.ti), **kw)

    def test_small_answers_are_one_chunk_and_compressible_ones_shrink(self):
        p = a84bridge.chunk_payloads(b"\x00pong")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0][:5], bytes((0, 0, 0, 0, 5)))
        big = b"abcabcabc" * 100
        p = a84bridge.chunk_payloads(big)
        self.assertEqual(len(p), 3)                                   # 300 raw bytes per chunk
        self.assertEqual(p[0][2], 1)                                  # compressed
        self.assertLess(len(p[0]), 100)
        self.assertEqual(a84bridge.chunk_payloads(b"")[0], bytes(5))

    def test_the_calculators_decoder_reads_the_bridges_chunks(self):
        from A84CZ import lz_decompress
        data = bytes(random.Random(3).randrange(256) for _ in range(40)) + b"hello hello hello hello " * 12
        out = b""
        for p in a84bridge.chunk_payloads(data):
            raw = lz_decompress(p, (p[3] << 8) | p[4], 5) if p[2] == 1 else p[5:]
            out += raw
        self.assertEqual(out, data)

    def test_operations(self):
        b = self.mk(fetch=lambda url: b"body of " + url.encode(), hosts=("doopydoop364.github.io",))
        self.assertEqual(b.handle(A84NT.OP_PING, b"")[:6], b"\x00pong ")
        self.assertEqual(b.handle(A84NT.OP_ECHO, b"abc"), b"\x00abc")
        self.assertIn(b"arch84-bridge", b.handle(A84NT.OP_STAT, b""))
        self.assertEqual(b.handle(A84NT.OP_GET, b"https://doopydoop364.github.io/x"), b"\x00body of https://doopydoop364.github.io/x")
        self.assertEqual(b.handle(99, b"")[0], a84bridge.UNKNOWN_OP)
        self.assertEqual(b.handle(A84NT.OP_GET, b"\xff\xfe")[0], a84bridge.BAD_REQUEST)

    def test_time_answer_has_epoch_and_offset(self):
        b = self.mk(clock=lambda: 1760000000.0)
        f = b.handle(A84NT.OP_TIME, b"")[1:].decode().split(" ")
        self.assertEqual(int(f[0]), 1760000000)
        int(f[1])

    def test_only_allowed_https_hosts(self):
        b = self.mk()
        for url in ("https://evil.example/a", "ftp://doopydoop364.github.io/a", "file:///etc/passwd"):
            r = b.handle(A84NT.OP_GET, url.encode())
            self.assertEqual(r[0], a84bridge.DENIED, url)

    def test_the_cache_serves_repeat_requests_without_refetching(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return b"q" * 100
        b = self.mk(fetch=fetch, hosts=("h.example",))
        b.handle(A84NT.OP_GET, b"https://h.example/f")
        b.handle(A84NT.OP_GET, b"https://h.example/f")
        self.assertEqual(len(calls), 1)

    def test_a_request_is_served_once(self):
        b = self.mk()
        t = b.screen.term
        t.show_rows(["NET"] + A84NT.frame_rows(A84NT.build(A84NT.T_REQ, 77, bytes((A84NT.OP_ECHO,)) + b"x")))
        self.assertIsNone(b.screen.frame() and None)
        # nobody types the answer in this unit test: delivery gives up after its retries, but the
        # request is marked handled either way
        b.sleep = lambda s: None
        b.settle = 0
        t.end_frame()
        self.assertFalse(b.poll_once())                            # the screen shows no request
        t.show_rows(["NET"] + A84NT.frame_rows(A84NT.build(A84NT.T_REQ, 77, bytes((A84NT.OP_ECHO,)) + b"x")))
        b.deliver = lambda seq, resp: True
        self.assertTrue(b.poll_once())
        self.assertFalse(b.poll_once())                            # same seq: not served again


# ---------------------------------------------------------------- the whole path
class FastNet:
    pass


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.rig = Rig({"/small": b"hello from the web\n",
                        "/big": ("0123456789" * 80 + "\u00e9" * 600 + "end\n").encode("utf-8"),
                        "/utf": ("\u20ac" * 700).encode("utf-8")})
        self.base = self.rig.server.base

    def tearDown(self):
        self.rig.close()

    def test_ping(self):
        out = self.rig.run("ping")
        self.assertIn("bridge: pong 2.0", out)
        self.assertIn("ms", out)

    def test_net_status(self):
        out = self.rig.run("net")
        self.assertIn("bridge: up", out)
        self.assertIn("hosts 127.0.0.1", out)

    def test_curl_prints_the_page(self):
        self.assertEqual(self.rig.run("curl " + self.base + "/small"), "hello from the web\n")

    def test_wget_saves_a_file_and_uses_the_url_name(self):
        out = self.rig.run("wget " + self.base + "/small")
        self.assertIn("saved /home/evo/small (19 bytes)", out)
        self.assertEqual(self.rig.run("cat small"), "hello from the web\n")
        self.rig.run("wget -q -O copy.txt " + self.base + "/small")
        self.assertEqual(self.rig.run("cat copy.txt"), "hello from the web\n")

    def test_a_body_of_several_chunks_arrives_whole(self):
        body = self.rig.server.files["/big"].decode("utf-8")
        self.rig.run("wget -q -O big " + self.base + "/big")
        from A84FS import dtext
        self.assertEqual(dtext(self.rig.sh.vfs._file("/home/evo/big").data), body)

    def test_multibyte_characters_are_never_split_between_chunks(self):
        body = self.rig.server.files["/utf"].decode("utf-8")
        self.rig.run("wget -q -O utf " + self.base + "/utf")
        from A84FS import dtext
        self.assertEqual(dtext(self.rig.sh.vfs._file("/home/evo/utf").data), body)

    def test_http_errors_and_denied_hosts_are_reported(self):
        self.assertIn("http error: 404", self.rig.run("curl " + self.base + "/missing"))
        self.assertIn("denied: host not allowed: example.org", self.rig.run("curl http://example.org/"))

    def test_a_failed_download_leaves_no_file(self):
        self.rig.run("wget " + self.base + "/missing")
        self.assertNotIn("missing", self.rig.run("ls"))

    def test_a_redirect_to_another_host_is_refused(self):
        self.assertIn("denied", self.rig.run("curl " + self.base + "/redir"))

    def test_ntpdate_sets_the_clock(self):
        self.rig.bridge.clock = lambda: 1760000000.0
        out = self.rig.run("ntpdate")
        self.assertRegex(out, r"(Wed|Thu) Oct\s+(8|9) \d\d:\d\d:\d\d 2025")

    def test_usage_errors(self):
        self.assertIn("usage", self.rig.run("wget"))
        self.assertIn("usage", self.rig.run("curl"))
        self.assertIn("usage", self.rig.run("ping -c x"))
        self.assertIn("usage", self.rig.run("wget ftp://x/y"))
        self.assertIn("usage", self.rig.run("net x"))
        self.assertIn("usage", self.rig.run("ntpdate x"))

    def test_the_screen_is_handed_back_to_the_terminal(self):
        self.rig.run("ping")
        self.assertIsNone(self.rig.t.rows)                 # end_frame was called

    def test_requests_are_served_one_after_another(self):
        for i in range(3):
            self.assertIn("pong", self.rig.run("ping"))
        for _ in range(100):
            if self.rig.bridge.served == 3:
                break
            time.sleep(0.02)
        self.assertEqual(self.rig.bridge.served, 3)


class PackageTests(unittest.TestCase):
    """pacman -Sy / -S against a mirror: the repository is built by tools/mkrepo.py from repo/src."""
    @classmethod
    def setUpClass(cls):
        import mkrepo
        cls.tmp = tempfile.TemporaryDirectory()
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            mkrepo.build_all(os.path.join("repo", "src"), cls.tmp.name)
        cls.files = {}
        for f in os.listdir(cls.tmp.name):
            cls.files["/pkgs/" + f] = open(os.path.join(cls.tmp.name, f), "rb").read()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.rig = Rig(dict(self.files))
        self.rig.sh.vfs.mkdir("/etc/pacman.d")
        self.rig.sh.vfs.write("/etc/pacman.d/mirror", self.rig.server.base + "/pkgs\n")

    def tearDown(self):
        self.rig.close()

    def test_sy_downloads_the_index_and_ss_lists_it(self):
        out = self.rig.run("pacman -Sy")
        self.assertIn("downloaded the package index (5 packages)", out)
        self.assertIn("synchronized 5 packages", out)
        out = self.rig.run("pacman -Ss cow")
        self.assertIn("cowsay 1.0", out)
        self.assertIn("cowfortune 1.0", out)
        self.assertIn("Repository  : net", self.rig.run("pacman -Si cowsay"))

    def test_s_installs_a_package_and_its_dependencies_from_the_mirror(self):
        self.rig.run("pacman -Sy")
        out = self.rig.run("pacman -S cowfortune")
        self.assertIn("installed cowsay 1.0", out)
        self.assertIn("installed fortune 1.0", out)
        self.assertIn("installed cowfortune 1.0", out)
        self.assertEqual(self.rig.run("pacman -Q"), "cowfortune 1.0\ncowsay 1.0\nfortune 1.0\n")
        out = self.rig.run("cowfortune")
        self.assertIn("very patient computer", out)         # fortune 2 ...
        self.assertIn("< moo >", out)                       # ... and the cow
        self.assertIn("(oo)", out)
        self.assertIn("-w |", out)

    def test_each_package_works(self):
        self.rig.run("pacman -Sy")
        self.rig.run("pacman -S hello ascii")
        self.assertIn("Hello from the Arch84 repository!", self.rig.run("hello"))
        out = self.rig.run("ascii")
        self.assertIn("(95 printable characters)", out)
        self.assertEqual(self.rig.run("pacman -S fortune"), "installed fortune 1.0 (2 files)\n")
        self.assertEqual(self.rig.run("fortune"), "The best RAM is the RAM you did not need.\n")

    def test_the_download_is_not_kept_after_installing_and_a_reinstall_downloads_it_again(self):
        self.rig.run("pacman -Sy")
        self.rig.run("pacman -S hello")
        self.assertEqual(self.rig.run("ls /var/cache/pacman/pkg"), "")        # the mirror has it again
        self.rig.run("pacman -R hello")
        self.assertEqual(self.rig.run("pacman -S hello"), "installed hello 1.0 (1 files)\n")
        self.assertEqual(self.rig.run("ls /var/cache/pacman/pkg"), "")

    def test_a_corrupted_download_is_refused(self):
        self.rig.run("pacman -Sy")
        good = self.rig.server.files["/pkgs/hello-1.0.ar84"]
        self.rig.server.files["/pkgs/hello-1.0.ar84"] = good.replace(b"Hello", b"Jello")
        out = self.rig.run("pacman -S hello")
        self.assertIn("corrupted download", out)
        self.assertNotIn("hello-1.0.ar84", self.rig.run("ls /var/cache/pacman/pkg"))
        self.assertEqual(self.rig.run("pacman -Q"), "")

    def test_a_missing_package_file_is_a_clear_error(self):
        self.rig.run("pacman -Sy")
        del self.rig.server.files["/pkgs/ascii-1.0.ar84"]
        self.rig.bridge.cache.clear()
        out = self.rig.run("pacman -S ascii")
        self.assertIn("cannot download ascii-1.0.ar84", out)
        self.assertIn("http error: 404", out)

    def test_unknown_package_and_an_index_that_is_not_one(self):
        self.rig.run("pacman -Sy")
        self.assertIn("target not found: nothing", self.rig.run("pacman -S nothing"))
        self.rig.server.files["/pkgs/index"] = b"<html>not an index</html>\n"
        self.rig.bridge.cache.clear()
        self.assertIn("not a package index", self.rig.run("pacman -Sy"))

    def test_a_local_copy_wins_at_the_same_version(self):
        self.rig.run("pacman -Sy")
        self.assertIn("Repository  : net", self.rig.run("pacman -Si hello"))
        self.rig.run("mkdir -p /var/cache/pacman/pkg")
        self.rig.run("wget -q -O /var/cache/pacman/pkg/hello-1.0.ar84 " + self.rig.server.base + "/pkgs/hello-1.0.ar84")
        self.rig.run("pacman -Sy")
        self.assertIn("Repository  : local", self.rig.run("pacman -Si hello"))
        self.assertEqual(self.rig.run("pacman -S hello"), "installed hello 1.0 (1 files)\n")
        self.assertIn("hello-1.0.ar84", self.rig.run("ls /var/cache/pacman/pkg"))   # a local file is left alone

    def test_offline_sy_is_quiet_on_a_text_terminal_and_clear_with_the_bridge_off(self):
        sh, t = T.mk()
        self.assertEqual(T.run(sh, t, "pacman -Sy"), "synchronized 0 packages\n")      # no network, no warning
        rig = Rig(bridge=False)
        real = A84NT.ms_since
        A84NT.ms_since = lambda t0: 10 ** 9
        try:
            out = rig.run("pacman -Sy")
            self.assertIn("warning: package index not downloaded: no answer from the bridge", out)
        finally:
            A84NT.ms_since = real
            rig.close()


class RobustnessTests(unittest.TestCase):
    def test_the_screen_is_given_back_when_the_calculator_runs_out_of_memory(self):
        rig = Rig({"/f": b"x" * 2000})
        try:
            def boom(text):
                raise MemoryError()
            import A84NT as N
            real = N.fetch_text
            sh = rig.sh
            with self.assertRaises(MemoryError):
                N.fetch_text(sh, rig.server.base + "/f", boom)
            self.assertIsNone(rig.t.rows)               # the request frame is gone: the bridge sees it and stops
        finally:
            rig.close()

    def test_a_damaged_frame_does_not_swallow_the_frames_behind_it(self):
        ti = SimTi()
        sh, _ = T.mk()
        term = SimTerm(ti)
        sh.term = term
        seq = 9
        sync = list(A84NT.SYNC)

        def data(idx, payload):
            return sync + A84NT.frame_symbols(A84NT.T_DATA, seq, bytes((idx >> 8, idx & 255, 0, 0, len(payload))) + payload)
        bad = data(1, b"damaged")
        bad[20] ^= 5                                              # one symbol wrong in the middle
        stream = ([3, 7, 1] + data(0, b"first") + bad + data(2, b"too early") + data(1, b"second")
                  + sync + A84NT.frame_symbols(A84NT.T_FIN, seq, bytes((0, 2, 1))))
        for s in stream:
            ti.push(A84NT.KEYS[s])
        got = []
        A84NT.wait_for_answer(sh, seq, got.append, "NET", 5.0, 5.0)
        self.assertEqual(got, [b"first", b"second"])              # in order, the damaged and the early one dropped

    def test_resend_survives_several_lossy_runs(self):
        for seed in (1, 2, 3):
            rig = Rig({"/f": bytes((i * 7) % 251 for i in range(900)).hex().encode()}, drop=0.003)
            rig.ti.rng.seed(seed)
            try:
                out = rig.run("wget -q -O f " + rig.server.base + "/f")
                self.assertEqual(out, "", "seed %d" % seed)
                from A84FS import dtext
                self.assertEqual(dtext(rig.sh.vfs._file("/home/evo/f").data).encode(),
                                 bytes((i * 7) % 251 for i in range(900)).hex().encode())
            finally:
                rig.close()

    def test_the_bridge_stops_typing_when_the_calculator_has_left(self):
        t = SimTerm(SimTi())

        class NullKeys:
            def send(self, symbols):
                pass
        screen = SimScreen(t)
        b = a84bridge.Bridge(screen, NullKeys(), sleep=lambda s: None, settle=0)
        t.show_rows(["NET"] + A84NT.frame_rows(A84NT.build(A84NT.T_REQ, 55, b"\x01")))
        sent = []
        real_send = b.send_frame

        def send(ftype, seq, payload):
            sent.append(ftype)
            if len(sent) == 1:
                t.end_frame()                            # the calculator quits after the first frame
            real_send(ftype, seq, payload)
        b.send_frame = send
        self.assertFalse(b.deliver(55, bytes(2000)))       # many chunks
        self.assertEqual(sent, [A84NT.T_DATA])              # and nothing after the screen went away

    def test_lost_key_presses_are_resent(self):
        rig = Rig({"/big": ("hello world %d\n" % 12345 * 80).encode()}, drop=0.004, clock=None)
        try:
            out = rig.run("wget -q -O big " + rig.server.base + "/big")
            self.assertEqual(out, "")
            from A84FS import dtext
            self.assertEqual(dtext(rig.sh.vfs._file("/home/evo/big").data), ("hello world %d\n" % 12345 * 80))
            self.assertGreater(rig.ti.presses, 0)
        finally:
            rig.close()

    def test_no_bridge_gives_a_clear_error_and_does_not_hang(self):
        rig = Rig(bridge=False)
        real = A84NT.ms_since
        A84NT.ms_since = lambda t0: 10 ** 9
        try:
            out = rig.run("ping")
            self.assertIn("no answer from the bridge", out)
            self.assertEqual(rig.sh.status, 1)
            self.assertIn("bridge: not responding", rig.run("net"))
            self.assertIn("no answer from the bridge", rig.run("wget http://127.0.0.1:1/x"))
            self.assertIsNone(rig.t.rows)                   # the frame is taken down again
        finally:
            A84NT.ms_since = real
            rig.close()

    def test_clear_cancels_the_wait(self):
        rig = Rig(bridge=False)
        try:
            rig.ti.push(45)                                 # CLEAR
            out = rig.run("ping")
            self.assertIn("cancelled", out)
            self.assertIsNone(rig.t.rows)
        finally:
            rig.close()

    def test_the_keepalive_key_is_ignored_by_every_arch84_key_table(self):
        import A84UI
        key = csc.CSC[a84bridge.KEEPALIVE_KEY]
        for table in (A84UI.NORM, A84UI.ACT, A84UI.ALPHA, A84UI.SEC, A84UI.ACT2):
            self.assertNotIn(key, table)
        self.assertNotIn(key, A84NT.KEYS)

    def test_stray_keys_before_the_answer_are_ignored(self):
        rig = Rig()
        try:
            for k in (32, 21, 21, 64, 81, 105):               # keepalive, 2nd 2nd, some keys, Enter
                rig.ti.push(k)
            self.assertIn("pong", rig.run("ping"))
        finally:
            rig.close()

    def test_the_text_terminal_says_it_needs_the_color_terminal(self):
        sh, t = T.mk()
        out = T.run(sh, t, "ping")
        self.assertIn("needs the color terminal", out)


if __name__ == "__main__":
    unittest.main()
