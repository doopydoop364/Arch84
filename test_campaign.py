"""Regression tests added by the optimisation/bug-fix campaign
(docs/OPTIMIZATION_CAMPAIGN.md)."""
import random
import unittest

from testutil import *
import A84CZ
from A84SH import Shell
from A84CZ import lz_compress, lz_decompress, LZ_HASH


def colliding_trigrams():
    seen = {}
    for a in range(256):
        for b in range(0, 256, 7):
            for c in range(0, 256, 13):
                h = (a * 5 + b * 31 + c * 131) & (LZ_HASH - 1)
                if h in seen and seen[h] != (a, b, c):
                    return seen[h], (a, b, c)
                seen[h] = (a, b, c)


class LzHashTests(unittest.TestCase):
    def test_hash_collision_is_verified(self):
        t1, t2 = colliding_trigrams()
        d = bytes(t1) + b"xyz" + bytes(t2) + b"xyz" + bytes(t1) + bytes(t2)
        self.assertEqual(lz_decompress(lz_compress(d), len(d)), d)

    def test_roundtrip_boundaries(self):
        rng = random.Random(84)
        for n in list(range(0, 40)) + [255, 256, 1023, 1024, 1025, 2047, 2048, 2049, 4097]:
            for kind in range(4):
                if kind == 0:
                    d = bytes(rng.randrange(256) for _ in range(n))
                elif kind == 1:
                    d = bytes([rng.randrange(3)] * n)
                elif kind == 2:
                    d = (b"abcabcabd" * (n // 9 + 1))[:n]
                else:
                    d = bytes(rng.choice(b"ab\n ") for _ in range(n))
                c = lz_compress(d)
                self.assertEqual(lz_decompress(c, len(d)), d, (n, kind))

    def test_incompressible_overhead_bounded(self):
        rng = random.Random(1)
        d = bytes(rng.randrange(256) for _ in range(1024))
        self.assertLessEqual(len(lz_compress(d)), 1024 + 1024 // 8 + 2)

    def test_text_ratio_not_worse_than_pinned(self):
        d = open("A84SH.py", "rb").read()[:1024]
        self.assertLess(len(lz_compress(d)), 740)


class NameLimitTests(unittest.TestCase):
    """A name over 255 UTF-8 bytes used to be accepted and then made every
    sync fail ("verify failed: bad name length"), so nothing could be saved."""

    def setUp(self):
        self.v = VFS()
        self.v.reset_default()

    def test_too_long_rejected_everywhere(self):
        long = "a" * 256
        self.v.write("/tmp/ok", "x")
        for fn in (lambda: self.v.write("/tmp/" + long, "x"),
                   lambda: self.v.mkdir("/tmp/" + long),
                   lambda: self.v.touch("/tmp/" + long),
                   lambda: self.v.copyfile("/tmp/ok", "/tmp/" + long),
                   lambda: self.v.rename("/tmp/ok", "/tmp/" + long),
                   lambda: self.v.write("/tmp/" + "é" * 128, "x")):
            with self.assertRaises(VFSError) as c:
                fn()
            self.assertIn("too long", str(c.exception))
        self.assertEqual(self.v.listdir("/tmp"), ["ok"])

    def test_limit_name_saves(self):
        for name in ("a" * 255, "é" * 127 + "a"):
            self.v.write("/tmp/" + name, "x")
        ms = MemStorage()
        k = Kernel(ms)
        k.vfs = self.v
        k.sync()
        self.assertEqual(walk(Kernel(ms).vfs), walk(self.v))


class SortTieTests(unittest.TestCase):
    def test_numeric_sort_ties_use_whole_line(self):
        # sort(1) -n breaks ties by comparing the lines; MicroPython's list
        # sort is unstable so relying on input order gave arbitrary output
        k = Kernel(MemStorage())

        class T:
            text = ""
            def write(self, s): self.text += s
            def post(self, s, pending=False): pass
            def busy(self): pass
        t = T()
        sh = Shell(k, t)
        k.vfs.write("/tmp/n", "b\n10 z\n2 y\na\n10 a\n2 x\nc\n")
        sh.execute("sort -n /tmp/n")
        self.assertEqual(t.text, "a\nb\nc\n2 x\n2 y\n10 a\n10 z\n")


class SyncRetryTests(unittest.TestCase):
    def test_one_transient_memoryerror_is_retried(self):
        ms = MemStorage()
        k = Kernel(ms)
        k.vfs.write("/tmp/x", "hello")
        real = ms.writer
        calls = []

        def flaky():
            w = real()
            f = w.feed
            def feed(data):
                calls.append(1)
                if len(calls) == 1:
                    raise MemoryError()
                return f(data)
            w.feed = feed
            return w
        ms.writer = flaky
        k.sync()
        self.assertFalse(k.vfs.dirty)
        self.assertEqual(walk(Kernel(ms).vfs)["/tmp/x"], "hello")

    def test_persistent_memoryerror_still_reports_and_keeps_old_save(self):
        ms = MemStorage()
        k = Kernel(ms)
        k.vfs.write("/tmp/x", "old")
        k.sync()
        k.vfs.write("/tmp/x", "new")
        real = ms.writer

        def always():
            w = real()
            def feed(data):
                raise MemoryError()
            w.feed = feed
            return w
        ms.writer = always
        with self.assertRaises(StorageError) as c:
            k.sync()
        self.assertIn("out of memory", str(c.exception))
        self.assertTrue(k.vfs.dirty)
        self.assertEqual(walk(Kernel(ms).vfs)["/tmp/x"], "old")


class QuotedCompletionTests(unittest.TestCase):
    """Completing inside an open quote used to keep the opening quote AND
    insert a candidate that carries it: `cat "my f<Tab>` -> `cat ""my file`."""

    def setUp(self):
        k = Kernel(MemStorage())
        self.sh = Shell(k, type("T", (), {"write": lambda s, x: None, "post": lambda s, x, p=False: None})())
        self.sh.vfs.write("/home/evo/my file.txt", "x")

    def tab(self, text):
        ed = self.sh.new_editor()
        for ch in text:
            ed.feed(ch)
        ed.feed("tab")
        return ed.buf

    def test_double_quote(self):
        self.assertEqual(self.tab('cat "my f'), 'cat "my file.txt')

    def test_single_quote(self):
        self.assertEqual(self.tab("cat 'my"), "cat 'my file.txt")

    def test_unquoted_still_escapes(self):
        self.assertEqual(self.tab("cat my"), "cat my\\ file.txt")


class ClockWrapTests(unittest.TestCase):
    def test_safe_key_window_survives_counter_wrap(self):
        # ticks_ms wraps; a raw `t1 - t0 > 500` never ended after a wrap
        import A84FS
        import A84UI

        class FakeTime:
            vals = [2 ** 30 - 100]      # t0 just before the wrap, then time runs on
            n = 0
            @staticmethod
            def ticks_ms():
                v = FakeTime.vals[0] + FakeTime.n * 150
                FakeTime.n += 1
                return v % 2 ** 30

            @staticmethod
            def ticks_diff(a, b):
                d = (a - b) % 2 ** 30
                return d - 2 ** 30 if d >= 2 ** 29 else d
        real = A84FS._time
        A84FS._time = FakeTime
        try:
            class TI:
                def get_key(self, m):
                    return 0
            t = A84UI.TiTerm(TI())
            self.assertFalse(t.safe_key())      # returns (instead of looping forever)
        finally:
            A84FS._time = real


if __name__ == "__main__":
    unittest.main()
