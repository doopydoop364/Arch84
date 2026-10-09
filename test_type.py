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


class IdleTests(unittest.TestCase):
    def test_cursor_blink_is_not_a_change_but_new_text_is(self):
        blank = bytes(2000)
        cursor = bytearray(blank)
        for i in range(300):
            cursor[i] = 7
        text = bytes([5]) * 2000
        self.assertFalse(T._changed(blank, bytes(cursor)))
        self.assertTrue(T._changed(blank, text))
        self.assertTrue(T._changed(None, blank))

    def test_wait_idle_returns_when_only_the_cursor_blinks(self):
        frames = [bytes(2000)]
        blink = bytearray(2000)
        for i in range(300):
            blink[i] = 7
        n = [0]
        def fake():
            n[0] += 1
            return bytes(blink) if n[0] % 2 else frames[0]
        real = T.screen_bytes
        T.screen_bytes = fake
        try:
            self.assertTrue(T.wait_idle(quiet=0.05, timeout=5, poll=0.01))
        finally:
            T.screen_bytes = real

    def test_wait_idle_times_out_while_the_screen_keeps_changing(self):
        n = [0]
        def fake():
            n[0] += 1
            return bytes([n[0] % 200]) * 2000
        real = T.screen_bytes
        T.screen_bytes = fake
        try:
            self.assertFalse(T.wait_idle(quiet=0.05, timeout=0.3, poll=0.01))
        finally:
            T.screen_bytes = real


if __name__ == "__main__":
    unittest.main()
