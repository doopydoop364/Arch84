"""The launcher must draw its splash BEFORE compiling any module, show a line per
module ("Filesystem (A84FS)": what it is, then its module name), animate it,
redraw only what changed and hand the lines to the real terminal.
Run: python3 test_launcher.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

# the spec: what the launcher shows for each module, in load order
LABELS = [
    ("A84FS", "Filesystem (A84FS)"),
    ("A84CZ", "FS compression (A84CZ)"),
    ("A84ST", "List storage (A84ST)"),
    ("A84KN", "Kernel, parser (A84KN)"),
    ("A84CD", "Core commands (A84CD)"),
    ("A84CE", "Env commands (A84CE)"),
    ("A84UI", "Text terminal (A84UI)"),
    ("A84SH", "Shell, startup (A84SH)"),
    ("A84GX", "Color display (A84GX)"),
]
ORDER = [m for m, _ in LABELS]
SPIN = ["*     ", "**    ", "***   ", " ***  ", "  *** ", "   ***", "    **", "     *"]

STUB = '''
import sys, json, atexit, os
LOG = []
def _rec(kind, *a):
    LOG.append([kind, list(a), sorted(m for m in sys.modules if m.startswith("A84"))])
def set_color(r, g, b): _rec("color", r, g, b)
def fill_rect(x, y, w, h): _rec("rect", x, y, w, h)
def draw_text(x, y, t): _rec("text", x, y, t)
atexit.register(lambda: json.dump(LOG, open(os.environ["A84_DRAW_LOG"], "w")))
'''

RUNNER = '''
import sys, runpy, os, time
if os.environ.get("A84_FAKE_MS"):
    _step, _t = int(os.environ["A84_FAKE_MS"]), [0]
    def _ticks_ms():
        _t[0] += _step
        return _t[0]
    time.ticks_ms = _ticks_ms
    time.ticks_diff = lambda a, b: a - b
sys.path.insert(0, %r)
sys.path.insert(0, %r)
if len(sys.argv) > 1:
    class Block:
        def find_spec(self, name, path=None, target=None):
            if name == sys.argv[1]:
                raise MemoryError("memory allocation failed, allocating 136 bytes")
    sys.meta_path.insert(0, Block())
runpy.run_path(%r, run_name="__main__")
'''


def run_launcher(block=None, fake_ms=None):
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "ti_draw.py"), "w") as f:
            f.write(STUB)
        runner = os.path.join(d, "run.py")
        with open(runner, "w") as f:
            f.write(RUNNER % (d, HERE, os.path.join(HERE, "ARCH84.py")))
        log = os.path.join(d, "draw.json")
        env = dict(os.environ, A84_DRAW_LOG=log, PYTHONDONTWRITEBYTECODE="1")
        if fake_ms:
            env["A84_FAKE_MS"] = str(fake_ms)
        cmd = [sys.executable, runner] + ([block] if block else [])
        p = subprocess.run(cmd, cwd=HERE, input="exit\n", capture_output=True, text=True,
                           timeout=120, env=env)
        calls = []
        if os.path.exists(log):
            with open(log) as f:
                calls = json.load(f)
        return p, calls


def events(calls):
    """Decode the draw log into what the user sees, in order:
       ("title", text) | ("run", frame_index, label) | ("ok", label) | ("fail", label) | ("plain", text)
       a row is drawn as separate text calls: "[" , tag, "]" , rest."""
    out = []
    texts = [(i, c) for i, c in enumerate(calls) if c[0] == "text"]
    k = 0
    while k < len(texts):
        i, c = texts[k]
        t = c[1][2]
        if t == "[" and k + 3 < len(texts) and texts[k + 2][1][1][2] == "]":
            tag = texts[k + 1][1][1][2]
            rest = texts[k + 3][1][1][2].strip()
            loaded = texts[k + 3][1][2]
            if tag in SPIN:
                out.append(("run", SPIN.index(tag), rest, loaded, texts[k + 1][0]))
            elif tag.strip() == "OK":
                out.append(("ok", rest, loaded, texts[k + 1][0]))
            elif tag == "FAILED":
                out.append(("fail", rest, loaded, texts[k + 1][0]))
            k += 4
            continue
        out.append(("plain", t.strip(), c[2], i))
        k += 1
    return out


class SplashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.calls = run_launcher()
        cls.texts = [c for c in cls.calls if c[0] == "text"]
        cls.ev = events(cls.calls)

    def test_it_boots_and_exits_cleanly(self):
        self.assertEqual(self.p.returncode, 0, self.p.stderr[-500:])

    def test_first_thing_drawn_is_the_splash_before_any_module_loads(self):
        self.assertTrue(self.calls)
        first_text = self.texts[0]
        self.assertEqual(first_text[1][2], "Arch84 booting")
        self.assertEqual(first_text[2], [])                       # no A84 module compiled yet
        self.assertEqual(self.calls[0][0], "color")
        self.assertEqual(self.calls[1][:2], ["rect", [0, 0, 320, 240]])
        self.assertEqual(self.calls[1][2], [])

    def test_version_replaces_the_first_line_once_known(self):
        sys.path.insert(0, HERE)
        from A84FS import VERSION
        self.assertTrue(any(e[0] == "plain" and e[1] == "Arch84 " + VERSION + " booting" for e in self.ev))

    def test_the_asterisks_move_and_are_red_then_ok_is_green(self):
        frames = {e[1] for e in self.ev if e[0] == "run"}
        self.assertGreaterEqual(len(frames), 5)

        def colour_before(i):
            j = i
            while self.calls[j][0] != "color":
                j -= 1
            return tuple(self.calls[j][1])
        run = next(e for e in self.ev if e[0] == "run")
        ok = next(e for e in self.ev if e[0] == "ok")
        self.assertEqual(colour_before(run[4]), (235, 60, 60))
        self.assertEqual(colour_before(ok[3]), (0, 200, 0))

    def test_it_ends_with_an_ok_line_for_the_loaded_modules(self):
        self.assertTrue(any(e[0] == "ok" and e[1].startswith("Loaded modules") for e in self.ev))

    def test_drawing_matches_the_terminal_grid(self):
        for c in self.texts:
            x, y = c[1][0], c[1][1]
            self.assertEqual((y - 20) % 18, 0)
            self.assertEqual(x % 10, 0)
            self.assertLess((y - 20) // 18, 11)
            self.assertLessEqual(x + 10 * len(c[1][2]), 320)

    def test_lines_are_not_repeated_in_the_text_fallback_terminal(self):
        self.assertEqual(self.p.stdout.count("booting"), 1)


class PerModuleLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p, cls.calls = run_launcher()
        cls.ev = events(cls.calls)

    def test_each_module_is_named_by_what_it_is_then_its_code_name(self):
        for code, label in LABELS:
            self.assertTrue(label.endswith("(" + code + ")"))
            self.assertLessEqual(len("[  OK  ] " + label), 32, label)       # fits the 32 columns
        shown = [e[2] for e in self.ev if e[0] == "run"]
        for _, label in LABELS:
            self.assertIn(label, shown)

    def test_a_running_line_then_a_green_ok_line_for_every_module_in_order(self):
        seq = []
        for e in self.ev:
            if e[0] == "run" and (not seq or seq[-1] != ("run", e[2])):
                seq.append(("run", e[2]))
            elif e[0] == "ok" and e[1] in [l for _, l in LABELS] and ("ok", e[1]) not in seq:
                seq.append(("ok", e[1]))
        want = []
        for _, label in LABELS:
            want += [("run", label), ("ok", label)]
        self.assertEqual(seq, want)

    def test_a_module_is_reported_loaded_only_after_it_really_was(self):
        by_label = dict((l, c) for c, l in LABELS)
        for e in self.ev:
            if e[0] == "run" and e[2] in by_label:
                self.assertNotIn(by_label[e[2]], e[3], e[2] + " was already loaded when its line was drawn")
            if e[0] == "ok" and e[1] in by_label:
                self.assertIn(by_label[e[1]], e[2])

    def test_ok_lines_are_green(self):
        def colour_before(i):
            j = i
            while self.calls[j][0] != "color":
                j -= 1
            return tuple(self.calls[j][1])
        oks = [e for e in self.ev if e[0] == "ok" and e[1] in [l for _, l in LABELS]]
        self.assertGreaterEqual(len(oks), len(LABELS))
        for e in oks:
            self.assertEqual(colour_before(e[3]), (0, 200, 0))


class RedrawCostTests(unittest.TestCase):
    """Every draw call costs real time on the calculator: only changed rows may be redrawn."""
    @classmethod
    def setUpClass(cls):
        cls.p, cls.calls = run_launcher()
        cls.ev = events(cls.calls)

    def row_clears(self):
        return [c[1][1] for c in self.calls if c[0] == "rect" and c[1][3] == 18]

    def test_far_fewer_redraws_than_repainting_everything_each_step(self):
        ys = self.row_clears()
        self.assertLessEqual(len(ys), 1 + 1 + 9 * 2 + 3)
        self.assertGreater(len(ys), 9)

    def test_each_step_redraws_at_most_two_rows(self):
        marks = [e[4] for e in self.ev if e[0] == "run"]
        counts = []
        for a, b in zip(marks, marks[1:]):
            counts.append(len([c for c in self.calls[a + 1:b + 1] if c[0] == "rect" and c[1][3] == 18]))
        self.assertEqual(counts[0], 3)                  # the title gains the version number
        self.assertEqual(set(counts[1:]), {2})

    def test_nothing_ever_scrolls_or_moves(self):
        rows_of = {}
        for e in self.ev:
            if e[0] == "ok" and e[1] in [l for _, l in LABELS]:
                rows_of.setdefault(e[1], set())
        for c in self.calls:
            pass
        ok_y = {}
        texts = [c for c in self.calls if c[0] == "text"]
        for e in self.ev:
            if e[0] == "ok" and e[1] in [l for _, l in LABELS]:
                # the "[" of that row was drawn 1 text call before the tag
                idx = [i for i, c in enumerate(self.calls) if c[0] == "text"]
                y = self.calls[e[3]][1][1]
                ok_y.setdefault(e[1], set()).add(y)
        self.assertEqual(len(ok_y), len(LABELS))
        for label, ys in ok_y.items():
            self.assertEqual(len(ys), 1, label)         # always the same row
        order = sorted(list(v)[0] for v in ok_y.values())
        self.assertEqual(order, [20 + 18 * i for i in range(1, 10)])
        self.assertLess(max(c[1][1] for c in texts), 11 * 18 + 20)

    def test_the_summary_lands_on_the_last_row_without_scrolling(self):
        summ = [e for e in self.ev if e[0] == "ok" and e[1].startswith("Loaded modules")]
        self.assertEqual({self.calls[e[3]][1][1] for e in summ}, {20 + 18 * 10})

    def test_redundant_colour_calls_are_skipped(self):
        colours = [tuple(c[1]) for c in self.calls if c[0] == "color"]
        for a, b in zip(colours, colours[1:]):
            self.assertNotEqual(a, b)


class AnimationSpeedTests(unittest.TestCase):
    def first_frames(self, calls):
        fr = {}
        for e in events(calls):
            if e[0] == "run":
                fr.setdefault(e[2], e[1])               # first draw of each step
        return [fr[l] for _, l in LABELS]

    def deltas(self, fake_ms):
        p, calls = run_launcher(fake_ms=fake_ms)
        self.assertEqual(p.returncode, 0, p.stderr[-300:])
        idxs = self.first_frames(calls)
        return [(b - a) % 8 for a, b in zip(idxs, idxs[1:])]

    def test_without_a_clock_it_moves_one_frame_per_module(self):
        p, calls = run_launcher()
        idxs = self.first_frames(calls)
        self.assertEqual([(b - a) % 8 for a, b in zip(idxs, idxs[1:])], [1] * 8)

    def test_it_advances_by_the_time_that_passed(self):
        self.assertEqual(self.deltas(250), [2] * 8)             # 250 ms = 2 frames of 90 ms
        self.assertEqual(self.deltas(1000), [11 % 8] * 8)       # a 1 s module = 11 frames
        self.assertEqual(self.deltas(40), [1] * 8)              # fast steps still move one


class FailureTests(unittest.TestCase):
    def test_out_of_memory_while_loading_shows_which_module_and_still_raises(self):
        p, calls = run_launcher(block="A84CZ")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("MemoryError", p.stderr)
        ev = events(calls)
        self.assertTrue(any(e[0] == "run" and e[2] == "FS compression (A84CZ)" for e in ev))
        fails = [e for e in ev if e[0] == "fail"]
        self.assertTrue(fails and fails[-1][1] == "FS compression (A84CZ)", fails)
        plains = [e[1] for e in ev if e[0] == "plain"]
        self.assertTrue(any(t.startswith("memory allocation failed") for t in plains), plains[-4:])
        self.assertFalse(any(e[0] == "run" and e[2] == "List storage (A84ST)" for e in ev))   # stopped there


class NoDisplayTests(unittest.TestCase):
    def test_without_ti_draw_nothing_changes(self):
        p = subprocess.run([sys.executable, os.path.join(HERE, "ARCH84.py")], cwd=HERE,
                           input="echo ok\nexit\n", capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr[-400:])
        self.assertIn("ok\n", p.stdout)
        self.assertEqual(p.stdout.count("booting"), 1)


if __name__ == "__main__":
    unittest.main()
