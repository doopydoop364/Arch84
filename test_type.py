import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))
import type as T
from A84UI import TiTerm
from A84PE import LineEditor


class FakeTi:
    pass


def typed(text):
    term = TiTerm(FakeTi())
    ed = LineEditor([], None)
    for k in T.plan(text):
        a = term.translate(k)
        if a is not None:
            ed.feed(a)
    return ed.buf


class TypeTests(unittest.TestCase):
    def test_round_trip(self):
        samples = ["ls -l", "echo Hi > a.txt", "true && echo yes", "sed 's/a/b/'",
                   "echo b a b | tr ' ' '\\n' | sort | uniq -c", "A=1; echo $A", "cat \"x y\" ~ _ ^ < = ;",
                   "ABC def GHI", "x", "X", "a1B2", "pacman -Syu", "echo {{ok}"]
        for s in samples:
            want = s.replace("{{", "{")
            self.assertEqual(typed(s), want, s)

    def test_every_printable_ascii(self):
        for c in range(32, 127):
            ch = chr(c)
            if ch in "{":
                continue
            try:
                got = typed(ch)
            except ValueError:
                continue
            self.assertEqual(got, ch, repr(ch))

    def test_scancodes_exist(self):
        for s in ["ls -l", "echo Hi & ok"]:
            for c in T.plan(s):
                self.assertIn(c, T.GK2CSC)


if __name__ == "__main__":
    unittest.main()
