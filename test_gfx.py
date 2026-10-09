"""Painting tests for the colour terminal (A84GX): a model screen simulates the
display rules and is compared with what the terminal MEANS to show after every
paint; plus call-count and flicker checks. Run: python3 test_gfx.py"""
import importlib.util
import random
import subprocess
import sys
import unittest

sys.path.insert(0, ".")
from A84FS import ERR
import A84GX
from A84GX import GfxTerm, COL, CW, CH, CURH, TEXT_DY, POST_STEP
from testutil import FakeTI
import A84KN
from A84ST import MemStorage
from A84SH import Shell

COLS_PX = 320
ROWS = 11
SPIN = ("*     ", "**    ", "***   ", " ***  ", "  *** ", "   ***", "    **", "     *")
GARBLE = "#"


class ModelTD:
    """Display rules: cells of 10x18 px; draw_text is transparent (it only draws glyph
    pixels), so drawing a glyph over a DIFFERENT glyph without erasing garbles it;
    fill_rect erases (and the white cursor block is a fill with white)."""
    def __init__(self):
        self.color = (0, 0, 0)
        self.cells = {}          # (row, col) -> (char, colour) or None; bg: set of white cells
        self.white = set()
        self.calls = 0
        self.log = []

    def set_color(self, r, g, b):
        self.calls += 1
        self.color = (r, g, b)

    def fill_rect(self, x, y, w, h):
        self.calls += 1
        self.log.append(("fill", x, y, w, h, self.color))
        # the real ti_draw raises "Width cannot be negative" for w <= 0 (seen on the calculator)
        assert w > 0 and h > 0, ("fill_rect with an empty/negative size", x, y, w, h)
        assert x % CW == 0 and w % CW == 0 and y % CH == 0 and h in (CH, CURH, 240), (x, y, w, h)
        for row in range(y // CH, (y + h + CH - 1) // CH):
            for col in range(x // CW, (x + w) // CW):
                if h == 240 or True:
                    self.cells.pop((row, col), None)
                    self.white.discard((row, col))
                    if self.color == (225, 225, 225):
                        self.white.add((row, col))

    def draw_text(self, x, y, t):
        self.calls += 1
        self.log.append(("text", x, y, t, self.color))
        assert t != "", ("draw_text with an empty string", x, y)
        assert x % CW == 0 and (y - TEXT_DY) % CH == 0, (x, y)
        row = (y - TEXT_DY) // CH
        assert 0 <= row < ROWS and x + CW * len(t) <= COLS_PX, (x, y, t)
        for k, ch in enumerate(t):
            if ch == " ":
                continue
            key = (row, x // CW + k)
            cur = self.cells.get(key)
            if cur is None or cur == (ch, self.color):
                self.cells[key] = (ch, self.color)
            else:
                self.cells[key] = (GARBLE, self.color)       # glyph over a different glyph

    def snapshot(self):
        return dict(self.cells), set(self.white)


def expected(prev):
    """What the rows in `prev` (lists of (text, colour key)) should look like."""
    cells = {}
    white = set()
    for i, r in enumerate(prev):
        k = 0
        for text, c in r:
            for ch in text:
                if c == "c":
                    white.add((i, k))
                    if ch != " ":
                        cells[(i, k)] = (ch, (0, 0, 0))
                elif ch != " ":
                    cells[(i, k)] = (ch, COL[c])
                k += 1
    return cells, white


class Ti:
    def get_key(self, w):
        return 0

    def disp_clr(self):
        pass


def new_term(td=None):
    td = td or ModelTD()
    t = GfxTerm(Ti(), td)
    t.reset()
    return t, td


def check(testcase, term, td, msg=""):
    cells, white = td.snapshot()
    ecells, ewhite = expected(term.prev)
    testcase.assertEqual(cells, ecells, msg)
    testcase.assertEqual(white, ewhite, msg)


class ModelTests(unittest.TestCase):
    def test_model_catches_a_missing_erase(self):
        # sanity-check the model itself: drawing over a different glyph is flagged
        td = ModelTD()
        td.draw_text(0, TEXT_DY, "a")
        td.draw_text(0, TEXT_DY, "b")
        self.assertEqual(td.cells[(0, 0)][0], GARBLE)

    def test_post_lines_with_tags_match(self):
        t, td = new_term()
        for i in range(30):
            t.post("[  OK  ] Started thing %d\n" % i)
            check(self, t, td, "line %d" % i)

    def test_spinner_then_ok(self):
        t, td = new_term()
        t.post("[  OK  ] first\n")
        for f in SPIN * 2:
            t.post("[" + f + "] Loading it\n", True)
            check(self, t, td, f)
        t.post("[  OK  ] Loading it\n")
        check(self, t, td)

    def test_random_operation_sequences(self):
        for seed in range(40):
            rng = random.Random(seed)
            t, td = new_term()
            sh = Shell(A84KN.Kernel(MemStorage()), t)
            ed = sh.new_editor()
            for step in range(120):
                op = rng.randrange(12)
                if op < 4:
                    n = rng.choice([1, 1, 1, 2, 3, 7])
                    txt = "".join(rng.choice(["[  OK  ] ", "[FAILED] ", "[ WARN ] ", "plain ", ERR + "err ", "x", "", "\n", ERR]) + "line%d\n" % rng.randrange(100) if rng.random() < 0.85 else rng.choice(["\n", "", "\n\n"]) for _ in range(n))
                    t.post(txt)
                elif op < 7:
                    f = rng.choice(SPIN)
                    t.post("[" + f + "] " + rng.choice(["Loading", "Saving", "Syncing"]) + " thing\n", True)
                elif op == 7:
                    t.write(rng.choice(["output line\n", "a\nb\nc\n", "x" * 70 + "\n"]))
                elif op == 8:
                    for _ in range(rng.randrange(1, 6)):
                        ed.feed(rng.choice(list("abc /.") + ["left", "right", "bs", "home", "end"]))
                    t.draw("[evo@arch84 ~]$ ", ed)
                elif op == 9:
                    t.busy()
                elif op == 10 and rng.random() < 0.3:
                    t.clear()
                    t.post("after clear\n")
                else:
                    t.mod = rng.choice(["", "2nd", "alpha", "lock"])
                    t.up = rng.random() < 0.3
                    t.draw("[evo@arch84 ~]$ ", ed)
                check(self, t, td, "seed %d step %d op %d" % (seed, step, op))


class DisplayRuleTests(unittest.TestCase):
    """Rules of the real display library, learned the hard way on the calculator."""
    def test_blank_lines_never_cause_empty_fills_when_scrolling(self):
        t, td = new_term()
        for i in range(40):
            t.post("\n" if i % 3 == 0 else "text %d\n" % i)      # blank rows in the mix
            check(self, t, td, i)

    def test_a_blank_row_replaced_by_text_and_back(self):
        t, td = new_term()
        t.post("first\n")
        t.post("\n")
        t.post("[*     ] busy\n", True)
        t.post("[  OK  ] busy\n")
        t.post("\n")
        t.post("x\n")
        check(self, t, td)

    def test_an_error_inside_the_display_library_does_not_crash_the_terminal(self):
        t, td = new_term()
        t.post("[  OK  ] one\n")
        real = td.fill_rect
        boom = [1]
        def flaky(x, y, w, h):
            if boom[0]:
                boom[0] = 0
                raise Exception("Width cannot be negative.")
            return real(x, y, w, h)
        td.fill_rect = flaky
        t.post("[*     ] two\n", True)
        t.post("[  OK  ] two\n")                    # triggers the erase that fails once
        t.post("three\n")
        td.fill_rect = real
        check(self, t, td)                           # it recovered with a full repaint

    def test_a_persistently_broken_display_does_not_loop_or_crash(self):
        t, td = new_term()
        def dead(x, y, w, h):
            raise Exception("display gone")
        td.fill_rect = dead
        for i in range(30):
            t.post("line %d\n" % i)                 # must keep working (best effort)
        self.assertEqual(t.lines[-1], "line 29")


class FlickerTests(unittest.TestCase):
    def setUp(self):
        self.t, self.td = new_term()
        self.t.post("[  OK  ] done before\n")

    def fills(self, since):
        return [e for e in self.td.log[since:] if e[0] == "fill"]

    def test_a_frame_change_never_blanks_the_whole_line(self):
        self.t.post("[*     ] Loading the thing\n", True)
        for i in range(1, 9):
            n = len(self.td.log)
            self.t.post("[" + SPIN[i % 8] + "] Loading the thing\n", True)
            for e in self.fills(n):
                self.assertLessEqual(e[3], 2 * CW, "frame %d erased %d px of the row" % (i, e[3]))
            check(self, self.t, self.td, "frame %d" % i)

    def test_a_frame_change_draws_only_the_changed_cells(self):
        self.t.post("[*     ] Loading the thing\n", True)
        n = len(self.td.log)
        self.t.post("[**    ] Loading the thing\n", True)
        texts = [e for e in self.td.log[n:] if e[0] == "text"]
        self.assertEqual([e[3] for e in texts], ["*"])             # one cell, not the line
        self.assertEqual(texts[0][1], 2 * CW)

    def test_pending_to_ok_redraws_only_the_six_cell_tag(self):
        self.t.post("[***   ] Loading the thing\n", True)
        n = len(self.td.log)
        self.t.post("[  OK  ] Loading the thing\n")
        f = self.fills(n)
        self.assertEqual([(e[1], e[3]) for e in f][:1], [(CW, 6 * CW)])
        self.assertTrue(all(e[3] <= 6 * CW for e in f))
        check(self, self.t, self.td)

    def test_text_beside_the_tag_is_not_touched(self):
        self.t.post("[*     ] Loading the thing\n", True)
        n = len(self.td.log)
        self.t.post("[**    ] Loading the thing\n", True)
        for e in self.td.log[n:]:
            if e[0] == "text":
                self.assertLess(e[1], 8 * CW)                      # nothing from " Loading the thing" onwards

    def test_new_rows_on_a_blank_screen_are_not_erased(self):
        t, td = new_term()
        before = len([e for e in td.log if e[0] == "fill"])
        t.post("[  OK  ] hello\n")
        t.post("plain line\n")
        self.assertEqual(len([e for e in td.log if e[0] == "fill"]) - before, 0)

    def test_erase_is_only_as_wide_as_the_old_row(self):
        t, td = new_term()
        t.post("short\n")
        t.post("[*     ] x\n", True)
        n = len(td.log)
        t.post("another quite long line here\n")        # replaces the pending row only
        for e in td.log[n:]:
            if e[0] == "fill":
                self.assertLessEqual(e[3], 10 * CW)


class CostTests(unittest.TestCase):
    """The same boot, painted by the previous GfxTerm (from git) and by this one."""
    @classmethod
    def setUpClass(cls):
        src = subprocess.run(["git", "show", "HEAD:A84GX.py"], capture_output=True, text=True).stdout
        cls.old = None
        if "def paint" in src and "def cells" not in src:
            spec = importlib.util.spec_from_loader("A84GX_OLD", loader=None)
            mod = importlib.util.module_from_spec(spec)
            exec(compile(src, "A84GX_OLD", "exec"), mod.__dict__)
            cls.old = mod

    def boot_calls(self, cls):
        td = ModelTD()
        t = cls(Ti(), td)
        t.reset()
        base = td.calls
        for i in range(40):
            t.post("[  OK  ] Started service number %d\n" % i)
        return td.calls - base

    def test_a_boot_that_scrolls_costs_far_fewer_draw_calls(self):
        if self.old is None:
            self.skipTest("previous A84GX not available from git HEAD")
        old = self.boot_calls(self.old.GfxTerm)
        new = self.boot_calls(GfxTerm)
        self.assertLess(new, old * 0.45, "old %d new %d" % (old, new))      # measured: 978 -> 357

    def test_spinner_costs_few_calls_per_frame(self):
        t, td = new_term()
        t.post("[*     ] Loading\n", True)
        base = td.calls
        for i in range(1, 17):
            t.post("[" + SPIN[i % 8] + "] Loading\n", True)
        self.assertLess((td.calls - base) / 16.0, 7)              # about a cell or two per frame

    def test_a_full_scroll_repaint_is_about_half_the_calls(self):
        # 11 coloured boot lines repainted from scratch: one erase + one draw per colour per row
        t, td = new_term()
        for i in range(11):
            t.post("[  OK  ] Started service number %d\n" % i)
        n = td.calls
        t.vis = None
        t.prev = []
        t.reset()
        n = td.calls
        t.paint([A84GX.line_segs("[  OK  ] Started service %d" % i) for i in range(11)])
        self.assertLessEqual(td.calls - n, 11 * 4)                # old code: 11 rows x 10 calls


class PageScrollTests(unittest.TestCase):
    def test_the_boot_view_scrolls_by_pages_not_lines(self):
        t, td = new_term()
        repaints = 0
        for i in range(60):
            n = len([e for e in td.log if e[0] == "fill"])
            t.post("[  OK  ] line %d\n" % i)
            check(self, t, td, i)
            if len([e for e in td.log if e[0] == "fill"]) - n >= 6:
                repaints += 1
            # the newest line is always on screen, as the last row with text
            self.assertEqual(t.lines[-1], "[  OK  ] line %d" % i)
            visible = [r for r in t.prev if r]
            self.assertEqual("".join(x for x, c in visible[-1]), "[  OK  ] line %d" % i)
            if i >= ROWS:
                self.assertGreaterEqual(len(visible), ROWS - POST_STEP)
        self.assertLessEqual(repaints, 60 // POST_STEP + 2)        # not one per line

    def test_lines_stay_in_order_and_contiguous(self):
        t, td = new_term()
        for i in range(45):
            t.post("L%02d\n" % i)
            shown = ["".join(x for x, c in r) for r in t.prev if r]
            nums = [int(s[1:]) for s in shown]
            self.assertEqual(nums, list(range(nums[0], nums[0] + len(nums))))
            self.assertEqual(nums[-1], i)

    def test_pending_line_is_shown_below_the_lines_even_on_a_full_screen(self):
        t, td = new_term()
        for i in range(ROWS):
            t.post("L%02d\n" % i)
        t.post("[***   ] working\n", True)
        check(self, t, td)
        last = "".join(x for x, c in [r for r in t.prev if r][-1])
        self.assertEqual(last, "[***   ] working")
        self.assertEqual(len([r for r in t.prev if r]), ROWS)

    def test_a_big_batch_shows_its_newest_lines(self):
        t, td = new_term()
        t.post("".join("B%02d\n" % i for i in range(30)))
        shown = ["".join(x for x, c in r) for r in t.prev if r]
        self.assertEqual(shown[-1], "B29")
        check(self, t, td)

    def test_prompt_view_is_unaffected_and_post_after_it_recovers(self):
        t, td = new_term()
        sh = Shell(A84KN.Kernel(MemStorage()), t)
        for i in range(8):
            t.post("boot %d\n" % i)
        t.draw("[evo@arch84 ~]$ ", sh.new_editor())
        self.assertIsNone(t.vis)
        check(self, t, td)
        for i in range(30):
            t.post("after %d\n" % i)
            check(self, t, td)

    def test_clear_resets_the_boot_view(self):
        t, td = new_term()
        for i in range(20):
            t.post("L%d\n" % i)
        t.clear()
        self.assertIsNone(t.vis)
        t.post("fresh\n")
        check(self, t, td)
        self.assertEqual(len([r for r in t.prev if r]), 1)


if __name__ == "__main__":
    unittest.main()
