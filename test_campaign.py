"""Regression tests added by the optimisation/bug-fix campaign
(docs/OPTIMIZATION_CAMPAIGN.md)."""
import random
import unittest

from testutil import *
import A84CZ
import A84KN
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


class BootLoadRetryTests(unittest.TestCase):
    def saved(self):
        ms = MemStorage()
        k = Kernel(ms)
        k.vfs.write("/tmp/keep", "data")
        k.sync()
        return ms

    def test_transient_load_memoryerror_is_retried(self):
        ms = self.saved()
        real = ms.read
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) == 1:
                raise MemoryError()
            return real()
        ms.read = flaky
        k = Kernel(ms)
        self.assertTrue(k.sync_ok)
        self.assertEqual(k.vfs.read("/tmp/keep"), "data")
        self.assertFalse(any("FAILED" in m for m in k.boot_msgs))

    def test_persistent_load_memoryerror_still_disables_saving(self):
        ms = self.saved()

        def boom():
            raise MemoryError()
        ms.read = boom
        k = Kernel(ms)
        self.assertFalse(k.sync_ok)
        self.assertTrue(any("out of memory" in m for m in k.boot_msgs))
        with self.assertRaises(StorageError):
            k.sync()


class VerifyMemoryTests(unittest.TestCase):
    def mk(self, files):
        v = VFS()
        v.reset_default()
        for p, d in files.items():
            if d is None:
                v.mkdir(p)
            else:
                v.write(p, d)
        return v

    def test_same_tree_detects_every_kind_of_difference(self):
        base = {"/tmp/a": "1", "/tmp/d": None, "/tmp/d/x": "2"}
        same = A84CZ.same_tree
        self.assertTrue(same(self.mk(base), self.mk(base)))
        for other in ({"/tmp/a": "9", "/tmp/d": None, "/tmp/d/x": "2"},       # data
                      {"/tmp/a": "1", "/tmp/d": None},                         # missing
                      {"/tmp/a": "1", "/tmp/d": None, "/tmp/d/y": "2"},        # renamed
                      {"/tmp/a": None, "/tmp/d": "z"},                         # file<->dir
                      {"/tmp/a": "1", "/tmp/d": None, "/tmp/d/x": "2", "/tmp/e": "3"}):
            self.assertFalse(same(self.mk(base), self.mk(other)), other)
            self.assertFalse(same(self.mk(other), self.mk(base)), other)

    def test_memoryerror_in_the_compare_keeps_the_save(self):
        # it used to abort the whole sync as "out of memory (nothing was changed)"
        # after every list had been written and verified
        ms = MemStorage()
        k = Kernel(ms)
        k.vfs.write("/tmp/x", "kept")
        real = A84KN.same_tree

        def boom(a, b):
            raise MemoryError()
        A84KN.same_tree = boom
        try:
            r = k.sync()
        finally:
            A84KN.same_tree = real
        self.assertIn("tree compare skipped", " ".join(r[3]))
        self.assertEqual(walk(Kernel(ms).vfs)["/tmp/x"], "kept")


class PropertyTests(unittest.TestCase):
    def test_glob_matches_fnmatch(self):
        import fnmatch
        from A84C2 import glob_match
        rng = random.Random(3)
        for _ in range(20000):
            p = "".join(rng.choice("ab*?") for _ in range(rng.randrange(0, 7)))
            s = "".join(rng.choice("abc") for _ in range(rng.randrange(0, 8)))
            self.assertEqual(glob_match(p, s), fnmatch.fnmatchcase(s, p), (p, s))

    def test_dates_match_datetime(self):
        import datetime
        from A84C5 import days_from_civil, civil_from_days
        d0 = datetime.date(1970, 1, 1)
        for i in range(0, 60000, 5):
            d = d0 + datetime.timedelta(days=i)
            self.assertEqual(days_from_civil(d.year, d.month, d.day), i)
            self.assertEqual(civil_from_days(i), (d.year, d.month, d.day))

    def test_line_editor_invariants_under_random_actions(self):
        k = Kernel(MemStorage())
        sh = Shell(k, type("T", (), {"write": lambda s, x: None,
                                      "post": lambda s, x, p=False: None})())
        sh.vfs.write("/home/evo/my file", "x")
        k.history.extend(["ls -a", "echo hi", "cat my\\ file"])
        acts = ["left", "right", "home", "end", "bs", "del", "clear", "up", "down", "tab",
                "pgup", "pgdn"] + list("ab c/\"'$~.") * 3
        rng = random.Random(11)
        for _ in range(300):
            ed = sh.new_editor()
            for _ in range(rng.randrange(1, 60)):
                ed.feed(rng.choice(acts))
                self.assertTrue(0 <= ed.pos <= len(ed.buf), (ed.buf, ed.pos))
                self.assertIsInstance(ed.hint, str)


if __name__ == "__main__":
    unittest.main()
