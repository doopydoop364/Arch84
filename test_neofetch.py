import unittest

import test_arch84 as T
from A84FS import BLK, CLR, ERR
from A84UI import strip
from A84GX import line_segs, COL


class NeofetchTests(unittest.TestCase):
    def test_strip_removes_colour_markers_and_error_mark(self):
        self.assertEqual(strip(CLR + "bOS " + CLR + "wArch84"), "OS Arch84")
        self.assertEqual(strip(ERR + "oops"), "oops")
        self.assertEqual(strip("plain"), "plain")

    def test_line_segs_colours(self):
        segs = line_segs(CLR + "bOS " + CLR + "wArch84")
        self.assertEqual(segs, [("OS ", "b"), ("Arch84", "w")])
        self.assertEqual(line_segs("x" + CLR + "gy"), [("x", "w"), ("y", "g")])
        self.assertEqual(line_segs(CLR + "?z"), [("z", "w")])       # unknown colour: white
        for _, c in line_segs(CLR + "rA" + CLR + "yB"):
            self.assertIn(c, COL)

    def test_command_prints_the_arch_logo_and_facts_that_fit_the_screen(self):
        sh, t = T.mk()
        out = T.run(sh, t, "neofetch")
        lines = [l for l in out.split("\n") if l != ""]
        text = strip(out)
        self.assertIn("OS Arch84", text)
        self.assertIn("Host TI-84 Evo", text)
        self.assertIn("/_-''    ''-_\\", text)         # the classic Arch base
        self.assertIn("|84|", text)                    # the bite holds the 84
        self.assertLessEqual(len(lines), 8)            # leaves a row for the prompt
        for l in lines:
            self.assertLessEqual(len(strip(l)), 31, l)

    def test_facts_start_in_one_column_after_the_logo(self):
        sh, t = T.mk()
        rows = [strip(l) for l in T.run(sh, t, "neofetch").split("\n") if l != ""]
        for r in rows[:6]:
            self.assertEqual(r[14], " ", r)            # the gap after the 14-wide logo
            self.assertNotEqual(r[15], " ", r)         # the facts all start in column 15

    def test_palette_is_the_terminals_own_colours_as_solid_blocks(self):
        sh, t = T.mk()
        self.assertNotIn(BLK, T.run(sh, t, "neofetch"))        # a terminal without colour: no palette row
        t.palette = lambda: "rgbd"                             # a terminal that reports its colours
        out = T.run(sh, t, "neofetch")
        last = out.split("\n")[-2]
        self.assertEqual(last, " " * 15 + CLR + "r" + BLK * 2 + CLR + "g" + BLK * 2
                         + CLR + "b" + BLK * 2 + CLR + "d" + BLK * 2)
        t.palette = lambda: "rgybmnwdddd"                      # more colours than fit: the first 7
        last = T.run(sh, t, "neofetch").split("\n")[-2]
        self.assertEqual(last.count(BLK), 14)
        self.assertLessEqual(len(strip(last)), 31)

    def test_real_terminal_palette_is_its_colour_table(self):
        from A84GX import GfxTerm, COL
        t = GfxTerm(None, None)
        self.assertEqual(t.palette(), "rgybmnw")
        for c in t.palette():
            self.assertIn(c, COL)

    def test_disk_shows_the_saved_copy(self):
        sh, t = T.mk()
        self.assertIn("Disk unsaved", strip(T.run(sh, t, "neofetch")))
        sh.k.sync()
        out = strip(T.run(sh, t, "neofetch"))
        self.assertRegex(out, r"Disk \d+B 1blk")

    def test_greeting_runs_at_login_and_hushlogin_turns_it_off(self):
        sh, t = T.mk()
        t.raw = ""
        sh.greet()
        self.assertIn("Arch84", strip(t.raw))
        sh2, t2 = T.mk()
        sh2.vfs.write("/home/evo/.hushlogin", "")
        t2.raw = ""
        sh2.greet()
        self.assertEqual(t2.raw, "")

    def test_greeting_that_cannot_load_is_silent(self):
        import A84SH
        sh, t = T.mk()
        t.raw = ""
        real = A84SH.load_command
        def boom(name):
            raise MemoryError()
        A84SH.load_command = boom
        try:
            sh.greet()
        finally:
            A84SH.load_command = real
        self.assertEqual(t.raw, "")


if __name__ == "__main__":
    unittest.main()
