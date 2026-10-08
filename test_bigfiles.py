"""Tests for chunked (big) file storage. Run: python3 test_bigfiles.py"""
import random
import tracemalloc
import unittest

from testutil import *
import A84FS
import A84CZ
import A84SH
from A84CD import *
from A84SH import *
import A84C2


class Term:
    def __init__(self):
        self.writes = []
        self.text = ""

    def write(self, t):
        self.writes.append(len(t))
        t = t.replace(ERR, "")
        self.text += t if t.endswith("\n") or t == "" else t + "\n"

    def echo(self, t):
        pass

    def post(self, t, pending=False):
        pass

    def busy(self):
        pass

    def clear(self):
        pass

    def close(self):
        pass

    def safe_key(self, tick=None):
        return False


def mk():
    t = Term()
    return Shell(Kernel(MemStorage()), t), t


def run(sh, t, line):
    t.text = ""
    t.writes = []
    sh.execute(line)
    return t.text


def canonical(d):
    # the invariant everything relies on
    if isinstance(d, str):
        return len(d) <= BIGMIN
    if len(d) < 3:
        return False
    for p in d[:-1]:
        if len(p) != SPLIT:
            return False
    return 1 <= len(d[-1]) <= SPLIT and isinstance(d, list)


def all_canonical(vfs):
    ok = True
    st = [vfs.root]
    while st:
        n = st.pop()
        if n.is_dir:
            st.extend(n.children.values())
        elif not canonical(n.data):
            ok = False
    return ok


def text(rng, n):
    return "".join(rng.choice("abcdefgh \n") for _ in range(n))


class DataTests(unittest.TestCase):
    def test_threshold_and_shapes(self):
        self.assertEqual(dnew(""), "")
        self.assertEqual(dnew("a" * BIGMIN), "a" * BIGMIN)
        d = dnew("a" * (BIGMIN + 1))
        self.assertIsInstance(d, list)
        self.assertEqual([len(p) for p in d], [SPLIT, SPLIT, 1])
        self.assertEqual(dlen(d), BIGMIN + 1)
        self.assertEqual(dtext(d), "a" * (BIGMIN + 1))

    def test_canonical_for_many_sizes(self):
        rng = random.Random(1)
        for n in list(range(0, 20)) + [BIGMIN - 1, BIGMIN, BIGMIN + 1, 2 * SPLIT, 3 * SPLIT,
                                       3 * SPLIT + 1, 10000, 50000]:
            s = text(rng, n)
            d = dnew(s)
            self.assertTrue(canonical(d), n)
            self.assertEqual(dtext(d), s)
            self.assertEqual(dlen(d), n)

    def test_append_keeps_canonical_and_matches_dnew(self):
        rng = random.Random(2)
        for _ in range(60):
            parts = [text(rng, rng.choice([0, 1, 5, 100, 1023, 1024, 1025, 3000])) for _ in range(rng.randrange(1, 8))]
            d = ""
            for p in parts:
                d = dappend(d, p)
                self.assertTrue(canonical(d))
            self.assertEqual(d, dnew("".join(parts)))     # same text -> same representation

    def test_dchunks_equals_dnew_for_any_piece_sizes(self):
        rng = random.Random(3)
        for _ in range(60):
            s = text(rng, rng.choice([0, 7, 2048, 2049, 5000, 9000]))
            pieces = []
            i = 0
            while i < len(s):
                k = rng.choice([1, 3, 100, 777, 1024, 3000])
                pieces.append(s[i:i + k])
                i += k
            self.assertEqual(dchunks(iter(pieces)), dnew(s))

    def test_iter_lines_matches_split(self):
        rng = random.Random(4)
        for _ in range(60):
            s = text(rng, rng.choice([0, 1, 30, 2048, 2049, 6000]))
            want = s.split("\n")
            if want and want[-1] == "":
                want.pop()
            self.assertEqual(list(iter_lines(dnew(s))), want)
        self.assertEqual(list(iter_lines("\n")), [""])
        self.assertEqual(list(iter_lines("a\n\nb")), ["a", "", "b"])
        self.assertEqual(list(iter_lines("")), [])
        long = "x" * 5000
        self.assertEqual(list(iter_lines(dnew(long))), [long])        # one huge line

    def test_pieces_snapshot_is_independent(self):
        d = dnew("a" * 5000)
        snap = dpieces(d)
        dappend(d, "b" * 3000)
        self.assertEqual(dlen(snap), 5000)


class VfsBigTests(unittest.TestCase):
    def test_write_read_size_lines(self):
        v = VFS()
        v.reset_default()
        s = "line one\n" * 1000
        v.write("/tmp/b", s)
        self.assertIsInstance(v.get("/tmp/b").data, list)
        self.assertEqual(v.read("/tmp/b"), s)
        self.assertEqual(v.size("/tmp/b"), len(s))
        self.assertEqual(list(v.lines("/tmp/b")), ["line one"] * 1000)
        v.write("/tmp/b", "tiny")
        self.assertEqual(v.get("/tmp/b").data, "tiny")

    def test_append_to_big_file_touches_only_the_tail(self):
        v = VFS()
        v.reset_default()
        v.write("/tmp/b", "z" * 10000)
        first = v.get("/tmp/b").data[0]
        for i in range(50):
            v.append("/tmp/b", "tail%d\n" % i)
        d = v.get("/tmp/b").data
        self.assertIs(d[0], first)                 # earlier pieces untouched
        self.assertTrue(canonical(d))
        self.assertEqual(v.read("/tmp/b"), "z" * 10000 + "".join("tail%d\n" % i for i in range(50)))

    def test_small_file_growing_past_the_limit(self):
        v = VFS()
        v.reset_default()
        for i in range(500):
            v.append("/tmp/g", "0123456789")
        self.assertTrue(canonical(v.get("/tmp/g").data))
        self.assertEqual(v.read("/tmp/g"), "0123456789" * 500)

    def test_copyfile_shares_pieces_and_is_independent(self):
        v = VFS()
        v.reset_default()
        v.write("/tmp/a", "q" * 20000)
        v.copyfile("/tmp/a", "/tmp/b")
        a = v.get("/tmp/a").data
        b = v.get("/tmp/b").data
        self.assertEqual(a, b)
        self.assertIsNot(a, b)
        self.assertTrue(all(x is y for x, y in zip(a, b)))     # zero extra data memory
        v.append("/tmp/b", "extra")
        self.assertEqual(v.read("/tmp/a"), "q" * 20000)         # original unaffected
        v.append("/tmp/a", "more")
        self.assertEqual(v.read("/tmp/b"), "q" * 20000 + "extra")
        v.write("/tmp/s", "small")
        v.copyfile("/tmp/s", "/tmp/s2")
        v.append("/tmp/s2", "!")
        self.assertEqual(v.read("/tmp/s"), "small")
        with self.assertRaises(VFSError):
            v.copyfile("/tmp", "/tmp/x")
        with self.assertRaises(VFSError):
            v.copyfile("/tmp/a", "/nope/x")

    def test_rename_moves_the_data(self):
        v = VFS()
        v.reset_default()
        v.write("/tmp/a", "m" * 9000)
        v.rename("/tmp/a", "/var/a")
        self.assertEqual(v.size("/var/a"), 9000)


class CodecBigTests(unittest.TestCase):
    def big_fs(self, size=20000, seed=1):
        v = VFS()
        v.reset_default()
        rng = random.Random(seed)
        v.write("/home/evo/big", text(rng, size))
        v.write("/home/evo/small", "tiny")
        v.mkdir("/home/evo/d")
        v.write("/home/evo/d/b2", "é€漢" * (size // 5))
        return v

    def test_roundtrip_keeps_canonical_pieces(self):
        for size in (2049, 3000, 20000, 150000):
            v = self.big_fs(size)
            back = decode_stream(fs_stream(v))
            self.assertTrue(same_tree(back, v), size)
            self.assertTrue(all_canonical(back), size)
            self.assertIsInstance(back.get("/home/evo/big").data, list)

    def test_save_and_load_never_join_a_file(self):
        v = self.big_fs(30000)
        real = (A84FS.dtext, A84CZ.dtext)
        def boom(d):
            raise AssertionError("a big file was joined into one string")
        A84FS.dtext = A84CZ.dtext = boom
        try:
            frames = list(fs_stream(v))
            back = decode_stream(frames)
        finally:
            A84FS.dtext, A84CZ.dtext = real
        self.assertTrue(same_tree(back, v))

    def test_random_big_filesystems(self):
        rng = random.Random(9)
        for seed in range(25):
            v = VFS()
            v.reset_default()
            for i in range(rng.randrange(1, 6)):
                p = "/home/evo/f%d" % i
                v.write(p, text(rng, rng.choice([0, 100, 2048, 2049, 5000, 30000])))
                for _ in range(rng.randrange(0, 4)):
                    v.append(p, text(rng, rng.choice([1, 50, 1500, 4000])))
                if rng.random() < 0.3:
                    v.copyfile(p, "/tmp/c%d" % i)
            back = decode_stream(fs_stream(v))
            self.assertTrue(same_tree(back, v), seed)
            self.assertTrue(all_canonical(back), seed)

    def peaks(self, size):
        v = self.big_fs(size)
        tracemalloc.start()
        for fr in fs_stream(v):
            pass                                # frames are dropped, as storage does
        _, peak_save = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        frames = list(fs_stream(v))
        tracemalloc.start()
        back = decode_stream(iter(frames))
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertTrue(same_tree(back, v))
        return peak_save, peak - cur

    def test_transient_memory_does_not_grow_with_file_size(self):
        # a joined 300 KB string would add 300 KB+ to the peak; chunked work is flat
        small_save, small_load = self.peaks(30000)
        big_save, big_load = self.peaks(300000)
        self.assertLess(big_save, small_save * 1.25 + 20000)
        self.assertLess(big_load, small_load * 1.25 + 20000)
        self.assertLess(big_load, 150000)

    def test_frames_stay_small_for_huge_files(self):
        v = self.big_fs(400000)
        for fr in fs_stream(v):
            self.assertLessEqual(len(fr), 5 + CHUNK)

    def test_big_file_through_storage_and_kernel(self):
        ti = FakeTI()
        k = Kernel(ti_store(ti))
        k.vfs.write("/home/evo/big", "0123456789abcdef\n" * 2000)
        k.sync()
        k2 = Kernel(ti_store(ti))
        self.assertTrue(k2.sync_ok)
        self.assertTrue(same_tree(k2.vfs, k.vfs))
        self.assertEqual(k2.vfs.size("/home/evo/big"), 17 * 2000)


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()

    def r(self, line):
        return run(self.sh, self.t, line)

    def make_big(self, name="big", lines=800):
        text = "".join("row %04d the quick brown fox\n" % i for i in range(lines))
        self.sh.vfs.write("/home/evo/" + name, text)
        return text

    def test_cat_big_file_exact_and_streamed(self):
        text = self.make_big()
        self.assertIsInstance(self.sh.vfs.get("/home/evo/big").data, list)
        out = self.r("cat big")
        self.assertEqual(out, text)
        self.assertGreater(len(self.t.writes), 5)             # flushed in batches
        self.assertLess(max(self.t.writes), 1024 + 64)

    def test_cat_missing_newline_and_empty(self):
        self.sh.vfs.write("/home/evo/a", "x" * 5000)           # one huge line, no newline
        self.assertEqual(self.r("cat a"), "x" * 5000 + "\n")
        self.sh.vfs.write("/home/evo/e", "")
        self.assertEqual(self.r("cat e"), "")
        self.sh.vfs.write("/home/evo/n", "\n")
        self.assertEqual(self.r("cat n"), "\n")

    def test_redirect_streams_and_matches(self):
        text = self.make_big()
        self.r("cat big > copy")
        self.assertEqual(self.sh.vfs.read("/home/evo/copy"), text)
        self.assertTrue(all_canonical(self.sh.vfs))
        self.r("cat big big > double")
        self.assertEqual(self.sh.vfs.read("/home/evo/double"), text + text)
        self.r("cat big >> double")
        self.assertEqual(self.sh.vfs.read("/home/evo/double"), text * 3)
        self.assertTrue(all_canonical(self.sh.vfs))

    def test_redirect_batches_are_small(self):
        self.make_big()
        sizes = []
        real = self.sh.vfs.append
        def spy(path, data):
            sizes.append(len(data))
            return real(path, data)
        self.sh.vfs.append = spy
        self.r("cat big > copy")
        self.sh.vfs.append = real
        self.assertLess(max(sizes), 1024 + 64)
        self.assertGreater(len(sizes), 5)

    def test_cat_file_onto_itself_terminates(self):
        text = self.make_big("s", 200)
        self.r("cat s >> s")
        self.assertEqual(self.sh.vfs.read("/home/evo/s"), text * 2)
        self.r("cat s > s")                      # a real shell truncates first, too
        self.assertEqual(self.sh.vfs.read("/home/evo/s"), "")

    def test_redirect_target_opened_before_the_command(self):
        self.assertEqual(self.r("echo hi > /nodir/x"), "ash: /nodir/x: No such file or directory\n")
        self.assertEqual(self.sh.status, 1)
        self.assertEqual(self.r("mkdir shouldnotexist > /nodir/x").count("ash:"), 1)
        self.assertFalse(self.sh.vfs.exists("/home/evo/shouldnotexist"))
        self.r("echo old > t")
        self.r("cat nothere > t")                # error, but the target was truncated
        self.assertEqual(self.sh.vfs.read("/home/evo/t"), "")

    def test_head_tail_on_big_file(self):
        text = self.make_big(lines=900)
        lines = text.split("\n")[:-1]
        self.assertEqual(self.r("head -n 3 big"), "".join(l + "\n" for l in lines[:3]))
        self.assertEqual(self.r("tail -n 3 big"), "".join(l + "\n" for l in lines[-3:]))
        self.assertEqual(self.r("tail -n 0 big"), "")
        self.assertEqual(self.r("head -n 0 big"), "")
        out = self.r("tail -n 500 big")
        self.assertEqual(out, "".join(l + "\n" for l in lines[-500:]))
        self.assertEqual(len(self.r("head big").split("\n")) - 1, 10)
        self.assertIn("==> big <==", self.r("head -n 1 big big"))

    def test_grep_wc_sort_du_on_big_file(self):
        text = self.make_big(lines=700)
        self.assertEqual(self.r("grep 0699 big"), "row 0699 the quick brown fox\n")
        self.assertEqual(self.r("grep -c fox big"), "700\n")
        self.assertEqual(self.r("grep -n 0003 big"), "4:row 0003 the quick brown fox\n")
        self.assertEqual(self.r("wc -l big"), "700 big\n")
        self.assertEqual(self.r("wc -w big"), "%d big\n" % (700 * 6))
        self.assertEqual(self.r("wc -c big"), "%d big\n" % len(text))
        self.assertEqual(self.r("du -s big"), "%6d big\n" % len(text))
        self.assertEqual(self.r("sort -r big").split("\n")[0], "row 0699 the quick brown fox")
        self.assertEqual(self.r("sort big big").split("\n")[:2], ["row 0000 the quick brown fox"] * 2)

    def test_cp_and_mv_big_files(self):
        text = self.make_big()
        self.r("cp big copy")
        self.assertEqual(self.sh.vfs.read("/home/evo/copy"), text)
        a = self.sh.vfs.get("/home/evo/big").data
        b = self.sh.vfs.get("/home/evo/copy").data
        self.assertTrue(all(x is y for x, y in zip(a, b)))
        self.r("echo more >> copy")
        self.assertEqual(self.sh.vfs.read("/home/evo/big"), text)
        self.r("mkdir d")
        self.r("cp big d")
        self.r("mv copy d/moved")
        self.assertEqual(self.sh.vfs.read("/home/evo/d/moved"), text + "more\n")
        self.assertEqual(self.sh.vfs.size("/home/evo/d/big"), len(text))
        self.assertIn("omitting directory", self.r("cp d x"))

    def test_echo_append_many_times(self):
        for i in range(300):
            self.sh.execute("echo line number %d >> log" % i)
        text = "".join("line number %d\n" % i for i in range(300))
        self.assertEqual(self.sh.vfs.read("/home/evo/log"), text)
        self.assertTrue(canonical(self.sh.vfs.get("/home/evo/log").data))
        self.assertEqual(self.r("tail -n 1 log"), "line number 299\n")

    def test_find_and_ls_unaffected(self):
        self.make_big()
        self.assertEqual(self.r("find . -name big"), "./big\n")
        self.assertIn("big", self.r("ls"))

    def test_streaming_cat_uses_little_memory(self):
        self.make_big(lines=10000)            # ~290 KB
        tracemalloc.start()
        self.r("cat big > copy")
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLess(peak - cur, 60000)    # beyond the copy it created: only batches

    def test_cp_costs_no_data_memory(self):
        self.make_big(lines=10000)
        tracemalloc.start()
        self.r("cp big copy")
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLess(peak, 20000)          # shares the pieces

    def test_after_a_big_file_the_shell_still_saves_and_reloads(self):
        text = self.make_big(lines=1500)
        ms = MemStorage()
        self.sh.k.storage = ms
        self.sh.execute("sync")
        k2 = Kernel(ms)
        self.assertEqual(k2.vfs.read("/home/evo/big"), text)


if __name__ == "__main__":
    unittest.main()
