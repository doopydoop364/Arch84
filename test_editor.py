"""The `edit` command: A84ED state machine and A84EV driver."""
import random
import unittest

from testutil import *
from A84ED import Editor, MAXLINES
from A84UI import TiTerm
from A84GX import GfxTerm
from A84SH import Shell
from A84KN import Kernel
from A84ST import MemStorage
import A84EV


def keys_for(text):
    """raw key codes typing `text` (lower-case letters via alpha, a few symbols)"""
    from A84UI import NORM, LET_CODES
    out = []
    for ch in text:
        if "a" <= ch <= "z":
            out += [31, LET_CODES[ord(ch) - 97]]
        else:
            out.append({v: k for k, v in NORM.items()}[ch])
    return out


ENTER, BS, CLEAR, LEFT, RIGHT, UP, DOWN = 105, 23, 45, 24, 26, 25, 34


class FakeTI:
    def __init__(self, keys):
        self.keys = list(keys)
        self.screen = {}
        self.cleared = 0

    def get_key(self, w):
        if w == 0:
            return 0
        if not self.keys:
            raise EOFError()
        return self.keys.pop(0)

    def disp_clr(self):
        self.cleared += 1
        self.screen = {}

    def disp_at(self, row, text, align):
        self.screen[row] = text


class FakeTD:
    def __init__(self):
        self.texts = []

    def set_color(self, *a): pass
    def fill_rect(self, *a): pass
    def draw_text(self, x, y, t): self.texts.append((x, y, t))


class Out:
    pass


def shell(keys, gfx=False):
    ti = FakeTI(keys)
    term = GfxTerm(ti, FakeTD()) if gfx else TiTerm(ti)
    sh = Shell(Kernel(MemStorage()), term)
    return sh, term, ti


class StateMachineTests(unittest.TestCase):
    def ed(self, lines=None, **kw):
        return Editor("f", lines if lines is not None else [""], **kw)

    def type(self, e, s):
        for ch in s:
            e.key("enter" if ch == "\n" else ch)

    def test_typing_and_enter(self):
        e = self.ed()
        self.type(e, "ab\ncd")
        self.assertEqual(e.lines, ["ab", "cd"])
        self.assertEqual((e.row, e.col), (1, 2))
        self.assertTrue(e.dirty)

    def test_split_and_join(self):
        e = self.ed(["hello"])
        e.key("right"); e.key("right")
        e.key("enter")
        self.assertEqual(e.lines, ["he", "llo"])
        e.key("bs")
        self.assertEqual(e.lines, ["hello"])
        self.assertEqual(e.col, 2)
        e.key("end"); e.key("del")                      # nothing to join
        self.assertEqual(e.lines, ["hello"])

    def test_delete_joins_next_line(self):
        e = self.ed(["ab", "cd"])
        e.key("end"); e.key("del")
        self.assertEqual(e.lines, ["abcd"])

    def test_movement_wraps_and_clamps(self):
        e = self.ed(["abc", "", "x"])
        e.key("end"); e.key("right")
        self.assertEqual((e.row, e.col), (1, 0))
        e.key("left")
        self.assertEqual((e.row, e.col), (0, 3))
        e.key("down"); e.key("down")
        self.assertEqual((e.row, e.col), (2, 0))
        e.key("down")
        self.assertEqual(e.row, 2)
        e.key("up"); e.key("up"); e.key("up")
        self.assertEqual(e.row, 0)

    def test_scrolling_keeps_cursor_visible(self):
        e = self.ed(["l%d" % i for i in range(40)], rows=9)
        for _ in range(25):
            e.key("down")
        self.assertTrue(e.top <= e.row < e.top + 9)
        e.key("pgdn")
        self.assertTrue(e.top <= e.row < e.top + 9)
        for _ in range(6):
            e.key("pgup")
        self.assertEqual(e.row, 0)
        self.assertEqual(e.top, 0)

    def test_horizontal_scroll(self):
        e = self.ed(["x" * 100], cols=20)
        e.key("end")
        r, c = e.cursor()
        self.assertTrue(0 <= c < 20)
        self.assertEqual(len(e.window()[0]), 20 - 0 if e.left + 20 <= 100 else 100 - e.left)
        e.key("home")
        self.assertEqual(e.left, 0)

    def test_commands(self):
        e = self.ed(["one", "two", "three", "two"])
        e.key("clear"); self.type(e, "3"); e.key("enter")
        self.assertEqual(e.row, 2)
        e.key("clear"); self.type(e, "/two"); e.key("enter")
        self.assertEqual(e.row, 3)
        e.key("clear"); self.type(e, "n"); e.key("enter")           # wraps to the first "two"
        self.assertEqual(e.row, 1)
        e.key("clear"); self.type(e, "/zzz"); e.key("enter")
        self.assertEqual(e.msg, "not found")
        e.key("clear"); self.type(e, "d"); e.key("enter")
        self.assertEqual(e.lines, ["one", "three", "two"])
        e.key("clear"); self.type(e, "p"); e.key("enter")
        self.assertEqual(e.lines, ["one", "three", "two", "two"])        # pasted below the cursor

    def cmd(self, e, text):
        e.key("clear")
        self.type(e, text)
        e.key("enter")

    def test_undo_groups_typing_and_is_a_toggle(self):
        e = self.ed(["abc"])
        e.key("end")
        self.type(e, "def")
        self.cmd(e, "u")
        self.assertEqual(e.lines, ["abc"])                  # the whole word, not one letter
        self.cmd(e, "u")
        self.assertEqual(e.lines, ["abcdef"])               # u again = redo
        e.key("home")
        self.type(e, "X")                                   # a move starts a new group
        self.cmd(e, "u")
        self.assertEqual(e.lines, ["abcdef"])

    def test_undo_restores_structure_and_cursor(self):
        e = self.ed(["one", "two", "three"])
        e.key("down")
        self.cmd(e, "d")
        self.assertEqual(e.lines, ["one", "three"])
        self.cmd(e, "u")
        self.assertEqual(e.lines, ["one", "two", "three"])
        self.assertEqual(e.row, 1)
        e.key("end"); e.key("enter")
        self.assertEqual(len(e.lines), 4)
        self.cmd(e, "u")
        self.assertEqual(e.lines, ["one", "two", "three"])
        e.key("home"); e.key("bs")                          # joins with the line above
        self.assertEqual(e.lines, ["onetwo", "three"])
        self.cmd(e, "u")
        self.assertEqual(e.lines, ["one", "two", "three"])
        self.cmd(e, "%s/o/0/")
        self.assertEqual(e.lines, ["0ne", "tw0", "three"])
        self.cmd(e, "u")
        self.assertEqual(e.lines, ["one", "two", "three"])
        self.cmd(e, "y"); self.cmd(e, "p")
        self.assertEqual(len(e.lines), 4)
        self.cmd(e, "u")
        self.assertEqual(len(e.lines), 3)

    def test_nothing_to_undo(self):
        e = self.ed(["x"])
        self.cmd(e, "u")
        self.assertEqual(e.msg, "nothing to undo")
        self.assertEqual(e.lines, ["x"])

    def test_delete_last_line_and_paste(self):
        e = self.ed(["only"])
        e.key("clear"); self.type(e, "d"); e.key("enter")
        self.assertEqual(e.lines, [""])
        e.key("clear"); self.type(e, "p"); e.key("enter")
        self.assertEqual(e.lines, ["", "only"])

    def test_substitute(self):
        e = self.ed(["a b a", "a"])
        e.key("clear"); self.type(e, "s/a/X/"); e.key("enter")
        self.assertEqual(e.lines, ["X b X", "a"])
        e.key("clear"); self.type(e, "%s/X/yy/"); e.key("enter")
        self.assertEqual(e.lines, ["yy b yy", "a"])
        e.key("clear"); self.type(e, "s/q/z/"); e.key("enter")
        self.assertEqual(e.msg, "not found")

    def test_quit_rules(self):
        e = self.ed(["x"])
        e.key("clear"); self.type(e, "q"); e.key("enter")
        self.assertEqual(e.act, "q")
        e.key("a")
        e.key("clear"); self.type(e, "q"); e.key("enter")
        self.assertIsNone(e.act)
        self.assertIn("unsaved", e.msg)
        e.key("clear"); self.type(e, "q!"); e.key("enter")
        self.assertEqual(e.act, "q!")

    def test_command_line_editing(self):
        e = self.ed()
        e.key("clear"); self.type(e, "wx"); e.key("bs"); e.key("bs"); e.key("bs")
        self.assertIsNone(e.cmd)
        e.key("clear"); self.type(e, "w"); e.key("clear")
        self.assertIsNone(e.cmd)
        self.assertIsNone(e.act)

    def test_chunks_roundtrip(self):
        for lines, text in ((["a", "b"], "a\nb\n"), ([""], ""), (["a", ""], "a\n"), (["", ""], "\n"), (["a", "", "b"], "a\n\nb\n")):
            e = self.ed(lines)
            self.assertEqual("".join(e.chunks()), text)
        e = self.ed(["x" * 700, "y" * 700])
        self.assertTrue(all(len(c) <= 1500 for c in e.chunks()))

    def test_line_limit(self):
        e = self.ed(["x"] * MAXLINES)
        e.key("enter")
        self.assertEqual(len(e.lines), MAXLINES)

    def test_random_keys_keep_invariants(self):
        rng = random.Random(5)
        acts = ["left", "right", "up", "down", "home", "end", "pgup", "pgdn", "enter", "bs", "del",
                "tab", "clear", "a", "b", " ", "/", "1", "d", "p", "n", "s", "%"]
        for _ in range(200):
            e = self.ed(["abc", "", "x" * 50], cols=10, rows=4)
            for _ in range(120):
                e.key(rng.choice(acts))
                self.assertTrue(0 <= e.row < len(e.lines))
                self.assertTrue(0 <= e.col <= len(e.lines[e.row]))
                self.assertTrue(e.top <= e.row < e.top + 4, (e.top, e.row))
                self.assertTrue(e.left <= e.col <= e.left + 10)
                r, c = e.cursor()
                self.assertTrue(0 <= r < 4 and 0 <= c <= 10)
                self.assertTrue(len(e.status()) <= 10)


class DriverTests(unittest.TestCase):
    def run_edit(self, keys, setup=None, name="note", gfx=False):
        sh, term, ti = shell(keys, gfx)
        if setup:
            setup(sh.vfs)
        out = Out()
        sh.out = lambda t: None
        errs = []
        sh.err = errs.append
        st = A84EV.cmd_edit(sh, [name])
        return sh, st, errs, ti

    def test_create_save_quit(self):
        keys = keys_for("hi") + [ENTER] + keys_for("yo") + [CLEAR] + keys_for("wq") + [ENTER]
        sh, st, errs, ti = self.run_edit(keys)
        self.assertEqual(st, 0)
        self.assertEqual(sh.vfs.read("/home/evo/note"), "hi\nyo\n")

    def test_edit_existing_and_save_keeps_file_on_quit_bang(self):
        keys = keys_for("zz") + [CLEAR] + keys_for("qq") + [ENTER]
        sh, st, errs, ti = self.run_edit(keys, lambda v: v.write("/home/evo/note", "orig\n"))
        self.assertEqual(sh.vfs.read("/home/evo/note"), "orig\n")

    def test_save_as_and_continue(self):
        keys = keys_for("a") + [CLEAR] + keys_for("w other") + [ENTER] + keys_for("b") + [CLEAR] + keys_for("wq") + [ENTER]
        sh, st, errs, ti = self.run_edit(keys)
        self.assertEqual(sh.vfs.read("/home/evo/other"), "a\n")
        self.assertEqual(sh.vfs.read("/home/evo/note"), "ab\n")

    def test_directory_and_usage_and_too_big(self):
        sh, st, errs, ti = self.run_edit([], name="/etc")
        self.assertEqual(st, 1)
        self.assertIn("Is a directory", errs[0])
        sh, st, errs, ti = self.run_edit([], lambda v: v.write("/home/evo/big", "x" * (A84EV.MAXCHARS + 1)), name="big")
        self.assertIn("too large", errs[0])
        sh, term, ti = shell([])
        errs = []
        sh.err = errs.append
        self.assertEqual(A84EV.cmd_edit(sh, []), 1)
        self.assertIn("usage", errs[0])

    def test_plain_terminal_refused(self):
        from A84UI import PlainTerm
        sh = Shell(Kernel(MemStorage()), PlainTerm())
        errs = []
        sh.err = errs.append
        self.assertEqual(A84EV.cmd_edit(sh, ["f"]), 1)
        self.assertIn("calculator terminal", errs[0])

    def test_input_ends_cleanly_when_keys_run_out(self):
        sh, st, errs, ti = self.run_edit(keys_for("abc"))
        self.assertEqual(st, 1)
        self.assertFalse(sh.vfs.exists("/home/evo/note"))      # never saved

    def test_screen_text_mode_shows_text_and_status(self):
        keys = keys_for("hello")
        sh, st, errs, ti = self.run_edit(keys)
        rows = [ti.screen[i] for i in sorted(ti.screen)]
        self.assertTrue(rows[0].startswith("hello|"))
        self.assertTrue(rows[1].startswith("~"))
        self.assertIn("note 1:6 *", rows[-2])
        self.assertTrue(all(len(r) <= 31 for r in rows))

    def test_gfx_terminal_draws(self):
        keys = keys_for("hello")
        sh, st, errs, ti = self.run_edit(keys, gfx=True)
        drawn = [t for _, _, t in sh.term.td.texts]
        self.assertIn("hello", drawn)

    def test_failed_save_leaves_the_old_file(self):
        keys = keys_for("new") + [CLEAR] + keys_for("w") + [ENTER]
        sh, term, ti = shell(keys)
        sh.vfs.write("/home/evo/note", "old\n")
        orig = A84EV.dchunks
        A84EV.dchunks = lambda it: (_ for _ in ()).throw(MemoryError())
        try:
            sh.err = lambda t: None
            A84EV.cmd_edit(sh, ["note"])
        finally:
            A84EV.dchunks = orig
        self.assertEqual(sh.vfs.read("/home/evo/note"), "old\n")

    def test_big_file_roundtrip_shape(self):
        text = "".join("line %d with some text\n" % i for i in range(200))
        keys = [CLEAR] + keys_for("w") + [ENTER, CLEAR] + keys_for("q") + [ENTER]
        sh, st, errs, ti = self.run_edit(keys, lambda v: v.write("/home/evo/note", text))
        node = sh.vfs.get("/home/evo/note")
        from A84FS import dnew
        self.assertEqual(node.data, dnew(text))         # canonical shape (pieces)
        self.assertEqual(sh.vfs.read("/home/evo/note"), text)

    def test_registered_lazily_and_runs_through_the_shell(self):
        from A84CD import LAZY
        self.assertEqual(LAZY["edit"], "A84EV")
        keys = keys_for("x") + [CLEAR] + keys_for("wq") + [ENTER]
        sh, term, ti = shell(keys)
        sh.execute("edit via")
        self.assertEqual(sh.vfs.read("/home/evo/via"), "x\n")
        self.assertEqual(sh.status, 0)


if __name__ == "__main__":
    unittest.main()
