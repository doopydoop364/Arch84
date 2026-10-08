"""Tests for storage v2: packing, LZSS, record codec, lists, migration.
Run: python3 test_storage.py"""
import hashlib
import random
import unittest

from testutil import *
import A84KN
import A84CZ

FACTORY1_SHA = "85ddc45390713e9feddddc61289cad98fb1027af681c78832e0e17724ecdb5a0"


def rm_tree(v, path):
    if v.isdir(path):
        for n in v.listdir(path):
            rm_tree(v, path.rstrip("/") + "/" + n)
    v.remove(path)


def roundtrip(v):
    back = decode_stream(fs_stream(v))
    return back


class PackTests(unittest.TestCase):
    def test_roundtrip_edges(self):
        for bs in (b"\x00" * 5, b"\xff" * 5, b"\x80\x00\x00\x00\x01", b"abcdeABCDE",
                   bytes(range(250)), bytes([255, 0] * 25)):
            self.assertEqual(bytes(unpack5(pack5(bs))), bs)

    def test_random(self):
        rng = random.Random(5)
        for _ in range(50):
            bs = bytes(rng.randrange(256) for _ in range(5 * rng.randrange(1, 60)))
            self.assertEqual(bytes(unpack5(pack5(bs))), bs)

    def test_values_are_half_integers_below_46_bits(self):
        for x in pack5(b"\xff" * 10):
            self.assertEqual(x % 1, 0.5)
            self.assertLess(x, 2 ** 41)

    def test_out_of_range_element_rejected(self):
        with self.assertRaises(StorageError):
            unpack5([2 ** 41 + 0.5])
        with self.assertRaises(StorageError):
            unpack5([-1.5])

    def test_unpack_survives_flaky_truncation(self):
        # a half value read back slightly low still decodes to the same int
        for v in (1, 12345678901, 2 ** 40 - 1):
            self.assertEqual(bytes(unpack5([v + 0.4999])), bytes(unpack5([v + 0.5])))


class LzTests(unittest.TestCase):
    def check(self, d):
        c = lz_compress(d)
        self.assertEqual(lz_decompress(c, len(d)), d)
        return c

    def test_basic_shapes(self):
        self.assertEqual(self.check(b""), b"")
        self.check(b"a")
        self.check(b"ab")
        self.check(b"abc")
        self.check(b"a" * 5000 if False else b"a" * 2048)
        self.check(b"abcabcabcabc" * 100)
        self.check(bytes(range(256)) * 8)

    def test_compresses_repetitive_data(self):
        d = b"the quick brown fox " * 100
        self.assertLess(len(self.check(d)), len(d) // 3)
        z = bytes(2048)
        self.assertLess(len(self.check(z)), 300)

    def test_fuzz(self):
        rng = random.Random(1)
        for i in range(120):
            n = rng.choice([1, 2, 3, 7, 8, 9, 17, 100, 511, 1024, 2047, 2048])
            kind = i % 4
            if kind == 0:
                d = bytes(rng.randrange(256) for _ in range(n))
            elif kind == 1:
                words = [b"ls ", b"cd ", b"echo ", b"\n", b"hello", b"x"]
                d = b"".join(rng.choice(words) for _ in range(n))[:n]
            elif kind == 2:
                d = bytes([rng.randrange(3)] * n)
            else:
                d = bytes(rng.randrange(4) for _ in range(n))
            self.check(d)

    def test_window_boundary_and_max_match(self):
        pat = b"XYZW"
        for gap in (4090, 4094, 4095, 4096, 4097, 4100):
            filler = bytes((i * 7 + 1) % 251 + 2 for i in range(gap))
            self.check(pat + filler + pat * 6)
        self.check(b"q" * 17 + b"r" + b"q" * 18 + b"q" * 19)

    def test_decompress_rejects_garbage(self):
        good = lz_compress(b"hello hello hello hello")
        with self.assertRaises(ValueError):
            lz_decompress(good[:-1], 23)           # truncated
        with self.assertRaises(ValueError):
            lz_decompress(b"\x00\xff\xff", 5)      # offset before the start
        with self.assertRaises(ValueError):
            lz_decompress(good, 10)                # output longer than announced
        with self.assertRaises(ValueError):
            lz_decompress(b"", 3)

    def test_decompress_never_raises_other_errors_on_noise(self):
        rng = random.Random(9)
        for _ in range(300):
            n = rng.randrange(0, 40)
            c = bytes(rng.randrange(256) for _ in range(n))
            try:
                lz_decompress(c, rng.randrange(1, 60))
            except ValueError:
                pass

    def test_frames_raw_when_incompressible(self):
        rng = random.Random(2)
        raw = bytes(rng.randrange(256) for _ in range(2048))
        fr = make_frame(raw, None)
        self.assertEqual(fr[0], 0)
        self.assertEqual(len(fr), 5 + 2048)
        txt = b"hello world, " * 150
        fr = make_frame(txt, None)
        self.assertEqual(fr[0], 1)
        self.assertLess(len(fr), len(txt))

    def test_memory_error_falls_back_to_raw_frame(self):
        real = A84CZ.lz_compress
        def boom(d):
            raise MemoryError()
        A84CZ.lz_compress = boom
        try:
            v = VFS()
            v.reset_default()
            v.write("/home/evo/n.txt", "hello " * 300)
            frames = list(fs_stream(v))
            self.assertTrue(all(f[0] == 0 for f in frames))
            self.assertTrue(same_tree(decode_stream(frames), v))
        finally:
            A84CZ.lz_compress = real


class CodecTests(unittest.TestCase):
    def fresh(self):
        v = VFS()
        v.reset_default()
        return v

    def test_factory_is_frozen(self):
        self.assertEqual(
            hashlib.sha256(repr((FACTORY1_DIRS, FACTORY1_FILES)).encode()).hexdigest(),
            FACTORY1_SHA,
            "FACTORY1 changed: old saves rebuild their defaults from it. Add "
            "FACTORY2 instead (and keep FACTORY1) rather than editing it.")

    def test_factory_matches_current_defaults(self):
        # if this fails the shipped defaults changed: decide on a factory 2
        self.assertTrue(same_tree(factory_vfs(1), self.fresh()))
        self.assertEqual(list(FACTORY1_DIRS), DEFAULT_DIRS)

    def test_fresh_filesystem_is_nearly_empty(self):
        v = self.fresh()
        raw, stored = fs_measure(v)
        self.assertLess(raw, 20)
        self.assertLess(stored, 30)
        back = roundtrip(v)
        self.assertTrue(same_tree(back, v))

    def test_fresh_filesystem_has_no_records(self):
        rd = Rd(fs_stream(self.fresh()))
        self.assertEqual(bytes(rd.take(3)), b"R2\x01")
        self.assertEqual(rd.byte(), 69)
        self.assertEqual(rd.varint(), 0)

    def test_version_file_is_not_stored_and_follows_running_version(self):
        v = self.fresh()
        self.assertNotIn(b"0.0.7", b"".join(fs_stream(v)))
        back = roundtrip(v)
        self.assertEqual(back.read("/etc/version"), VERSION + "\n")

    def test_changed_default_file_and_new_files(self):
        v = self.fresh()
        v.write("/etc/hostname", "box\n")
        v.write("/home/evo/a.txt", "hi\n")
        v.mkdir("/home/evo/proj")
        v.write("/home/evo/proj/b.txt", "")
        back = roundtrip(v)
        self.assertTrue(same_tree(back, v))
        self.assertEqual(back.read("/etc/hostname"), "box\n")

    def test_deleting_defaults_is_persisted(self):
        v = self.fresh()
        v.remove("/home/evo/.ashrc")
        v.remove("/etc/hostname")
        rm_tree(v, "/var")
        back = roundtrip(v)
        self.assertTrue(same_tree(back, v))
        self.assertFalse(back.exists("/var"))
        self.assertFalse(back.exists("/etc/hostname"))
        self.assertTrue(back.exists("/home/evo/.profile"))

    def test_kind_swaps_on_factory_paths(self):
        cases = []
        def a(v):                      # dir replaced by a file
            rm_tree(v, "/tmp")
            v.write("/tmp", "now a file")
        def b(v):                      # file replaced by a directory with content
            v.remove("/etc/hostname")
            v.mkdir("/etc/hostname")
            v.write("/etc/hostname/x", "y")
        def c(v):                      # directory deleted and recreated empty
            rm_tree(v, "/home/evo")
            v.mkdir("/home/evo")
        def d(v):                      # recreated with only some of the old children
            rm_tree(v, "/usr")
            v.mkdir("/usr")
            v.mkdir("/usr/bin")
            v.write("/usr/new", "n")
        def e(v):                      # whole subtree gone, parent kept
            rm_tree(v, "/var/log")
            rm_tree(v, "/var/lib")
            rm_tree(v, "/var/cache")
        def f(v):                      # home profile files turned into dirs
            v.remove("/home/evo/.ashrc")
            v.mkdir("/home/evo/.ashrc")
            v.remove("/home/evo/.profile")
            v.write("/home/evo/.profile", "different\n")
        for fn in (a, b, c, d, e, f):
            v = self.fresh()
            fn(v)
            self.assertTrue(same_tree(roundtrip(v), v), fn.__name__)

    def test_chunk_boundary_sizes(self):
        rng = random.Random(3)
        for size in (0, 1, 2, 1023, 1024, 1025, 2040, 2044, 2045, 2047, 2048, 2049,
                     2050, 4095, 4096, 4097, 5000, 8192, 70000):
            v = self.fresh()
            v.write("/home/evo/big", rnd_text(rng, size, "abcdefgh \n"))
            v.write("/home/evo/after", "tail")
            frames = list(fs_stream(v))
            self.assertTrue(all(len(f) <= 5 + CHUNK for f in frames), size)
            self.assertTrue(same_tree(decode_stream(frames), v), size)

    def test_multibyte_text_crossing_slices_and_chunks(self):
        for ch in ("é", "€", "漢", "😀"):
            for size in (1, 511, 512, 513, 1023, 1024, 1025, 3000):
                v = self.fresh()
                v.write("/home/evo/u", ch * size)
                self.assertTrue(same_tree(roundtrip(v), v), (ch, size))
        v = self.fresh()
        v.mkdir("/home/evo/dir é€漢")
        v.write("/home/evo/dir é€漢/file\twith tab", "line1\nline2\r\n\x00\x01end")
        self.assertTrue(same_tree(roundtrip(v), v))

    def test_random_filesystems(self):
        rng = random.Random(7)
        paths = ["/etc/hostname", "/etc/profile", "/home/evo/.ashrc", "/home/evo/.profile",
                 "/tmp", "/var/log", "/var/lib", "/usr/share", "/home/evo", "/home",
                 "/a", "/a/b", "/a/b/c", "/home/evo/n1", "/home/evo/n1/n2", "/tmp/x",
                 "/var/log/y", "/x y", "/home/evo/proj", "/home/evo/proj/f"]
        for seed in range(40):
            v = self.fresh()
            for _ in range(rng.randrange(1, 60)):
                p = rng.choice(paths)
                op = rng.randrange(5)
                try:
                    if op == 0:
                        v.mkdir(p)
                    elif op == 1:
                        v.write(p, rnd_text(rng, rng.choice([0, 1, 5, 300, 2500])))
                    elif op == 2:
                        rm_tree(v, p)
                    elif op == 3:
                        v.touch(p)
                    else:
                        v.rename(p, rng.choice(paths))
                except VFSError:
                    pass
            self.assertTrue(same_tree(roundtrip(v), v), "seed %d" % seed)

    def test_compression_ratio_on_text_like_data(self):
        rng = random.Random(1)
        words = "the quick brown fox jumps over lazy dog math physics homework notes todo".split()
        v = self.fresh()
        v.mkdir("/home/evo/notes")
        for i in range(12):
            body = "\n".join(" ".join(rng.choice(words) for _ in range(8)) for _ in range(6))
            v.write("/home/evo/notes/n%02d.txt" % i, body + "\n")
        for i in range(6):
            v.write("/home/evo/hw%d.py" % i, "def f(x):\n    return x * x + %d\n\nprint(f(3))\n" % i)
        raw, stored = fs_measure(v)
        self.assertGreater(raw, 3000)
        self.assertLess(stored, raw * 0.6)

    def test_stream_stats_match_frames(self):
        v = self.fresh()
        v.write("/home/evo/f", "z" * 5000)
        stats = [0, 0]
        frames = list(fs_stream(v, stats))
        self.assertEqual(stats[1], sum(len(f) for f in frames))
        self.assertEqual(stats[0], sum((f[1] << 8) | f[2] for f in frames))

    def stream_bytes(self, v):
        return b"".join(fs_stream(v))

    def test_truncated_streams_raise_valueerror_only(self):
        v = self.fresh()
        v.write("/home/evo/f", "hello world " * 40)
        v.mkdir("/home/evo/d")
        data = self.stream_bytes(v)
        for cut in list(range(0, len(data), 7)) + [len(data) - 1]:
            with self.assertRaises(ValueError, msg=cut):
                decode_stream([data[:cut]])

    def test_corrupt_streams_never_raise_other_exceptions(self):
        v = self.fresh()
        v.write("/home/evo/f", "hello world " * 40)
        v.mkdir("/home/evo/d")
        data = bytearray(self.stream_bytes(v))
        rng = random.Random(4)
        for _ in range(400):
            d = bytearray(data)
            for _ in range(rng.randrange(1, 4)):
                d[rng.randrange(len(d))] = rng.randrange(256)
            try:
                decode_stream([bytes(d)])
            except ValueError:
                pass

    def test_stream_split_into_odd_pieces_decodes(self):
        v = self.fresh()
        v.write("/home/evo/f", "hello world " * 400)
        data = self.stream_bytes(v)
        for step in (1, 3, 5, 99, 1000):
            pieces = [data[i:i + step] for i in range(0, len(data), step)]
            self.assertTrue(same_tree(decode_stream(iter(pieces)), v), step)

    def frame(self, raw):
        return bytes([0, len(raw) >> 8, len(raw) & 255, len(raw) >> 8, len(raw) & 255]) + raw

    def test_malicious_records_are_rejected(self):
        hdr = b"R2\x01"
        bad = {
            "huge name": hdr + b"D\x00" + bytes([0xff, 0xff, 0x03]) + b"x",
            "zero name": hdr + b"D\x00\x00",
            "huge file": hdr + b"F\x00\x01a" + bytes([0xff, 0xff, 0xff, 0x7f]),
            "bad parent": hdr + b"D\x63\x01a",
            "slash name": hdr + b"D\x00\x03a/b",
            "dot name": hdr + b"D\x00\x02..",
            "count mismatch": hdr + b"E\x05",
            "unknown record": hdr + b"Q\x00\x01a",
            "duplicate dir": hdr + b"D\x00\x01aD\x00\x01aE\x02",
            "file over dir": hdr + b"D\x00\x01aF\x00\x01a\x00E\x02",
            "bad utf8": hdr + b"F\x00\x01a\x02\xff\xfeE\x01",
            "bad header": b"R3\x01E\x00",
            "unknown factory": b"R2\x09E\x00",
            "overlong varint": hdr + b"D" + bytes([0x80] * 8),
        }
        for name, raw in bad.items():
            with self.assertRaises(ValueError, msg=name):
                decode_stream([self.frame(raw)])
        ok = hdr + b"D\x00\x01aF\x13\x01b\x02hiE\x02"
        # sanity: the same helper accepts a valid stream (parent index 19 = dir 'a')
        self.assertTrue(decode_stream([self.frame(ok)]).read("/a/b") == "hi")

    def test_x_record_for_missing_child_is_tolerated(self):
        raw = b"R2\x01X\x00\x03zzzE\x01"
        self.assertTrue(same_tree(decode_stream([self.frame(raw)]), self.fresh()))

    def test_bad_frames(self):
        for fr in (b"\x05\x00\x01\x00\x01x", b"\x00\x00\x00\x00\x00", b"\x00\xff\xff\x00\x01x",
                   b"\x00\x00\x03\x00\x02ab", b"\x01\x00\x05\x00\x01x"):
            with self.assertRaises(ValueError):
                decode_stream([fr])


class Utf8Tests(unittest.TestCase):
    SAMPLES = ("", "a", "é", "€", "漢", "😀", "a€b😀c漢d", "é" * 7, "😀" * 5, "x" * 5 + "漢")

    def test_cut_never_splits_a_character(self):
        for s in self.SAMPLES:
            b = s.encode()
            for p in range(len(b) + 1):
                piece = b[:p]
                cut = utf8_cut(piece)
                self.assertLessEqual(cut, p)
                piece[:cut].decode()                       # must be valid on its own
                self.assertLessEqual(len(piece) - cut, 3)  # carry is at most a partial char

    def test_take_text_at_every_split_point(self):
        for s in self.SAMPLES:
            b = s.encode()
            for p in range(len(b) + 1):
                # two raw frames split at byte p
                frames = []
                for part in (b[:p], b[p:]):
                    if part:
                        frames.append(bytes([0, len(part) >> 8, len(part) & 255,
                                             len(part) >> 8, len(part) & 255]) + part)
                rd = Rd(frames)
                self.assertEqual(rd.take_text(len(b)), s)

    def test_take_text_rejects_truncated_or_invalid_utf8(self):
        for raw in (b"\xe2\x82", b"\xff\xfe", b"a\xc3", b"\x80"):
            fr = bytes([0, 0, len(raw), 0, len(raw)]) + raw
            with self.assertRaises(ValueError):
                Rd([fr]).take_text(len(raw))
            with self.assertRaises(ValueError):
                decode_stream([bytes([0, 0, 3 + 3 + len(raw), 0, 3 + 3 + len(raw)])
                               + b"R2\x01F\x00\x01a" + bytes([len(raw)]) + raw + b"E\x01"])

    def test_large_text_file_is_decoded_in_pieces(self):
        v = VFS()
        v.reset_default()
        v.write("/home/evo/big", ("é€漢😀 abc\n" * 4000))
        self.assertTrue(same_tree(decode_stream(fs_stream(v)), v))


class StorageTests(unittest.TestCase):
    def stream(self, n, seed=0):
        rng = random.Random(seed)
        return bytes(rng.randrange(256) for _ in range(n))

    def write(self, store, data, step=97):
        w = store.writer()
        for i in range(0, len(data), step):
            w.feed(data[i:i + step])
        w.finish()
        self.assertEqual(b"".join(w.readback()), data)
        return w.commit()

    def read_all(self, store):
        got = store.read()
        self.assertIsNotNone(got)
        self.assertEqual(got[0], 2)
        return b"".join(got[1])

    def test_roundtrip_multiblock_and_limits(self):
        ti = FakeTI()
        st = ti_store(ti)
        for n in (0, 1, 4, 5, 6, 494, 495, 496, 989, 990, 4000):
            data = self.stream(n, n)
            self.write(st, data, step=1 + n % 211)
            self.assertEqual(self.read_all(st), data, n)
        for name, v in ti.lists.items():
            self.assertLessEqual(len(v), 100, name)

    def test_never_stores_risky_plain_integers(self):
        ti = FakeTI(flaky=True)
        st = ti_store(ti)
        for seed in range(6):
            self.write(st, self.stream(3000, seed))
            self.assertEqual(self.read_all(st), self.stream(3000, seed))
        self.assertEqual(ti.big_ints, 0)

    def test_empty_stream_and_missing_store(self):
        st = ti_store(FakeTI())
        self.assertIsNone(st.read())
        self.write(st, b"")
        self.assertEqual(self.read_all(st), b"")

    def test_slot_flip_and_old_slot_shrunk(self):
        ti = FakeTI()
        st = ti_store(ti)
        self.write(st, self.stream(2500, 1))
        s1 = int(ti.lists["A84"][2])
        nb1 = int(ti.lists["A84"][3])
        self.assertGreater(nb1, 3)
        self.write(st, self.stream(100, 2))
        s2 = int(ti.lists["A84"][2])
        self.assertNotEqual(s1, s2)
        for i in range(nb1):
            self.assertEqual(len(ti.lists[block_name(s1, i)]), 1)
        self.write(st, self.stream(3000, 3))
        self.assertEqual(int(ti.lists["A84"][2]), s1)

    def test_commit_returns_block_count(self):
        st = ti_store(FakeTI())
        nb, warns = self.write(st, self.stream(1000, 4))
        self.assertEqual(nb, -(-1000 // 5 // 99))
        self.assertEqual(warns, [])

    def test_failure_mid_write_keeps_previous_save(self):
        ti = FakeTI()
        st = ti_store(ti)
        old = self.stream(2000, 5)
        self.write(st, old)
        before = {k: list(v) for k, v in ti.lists.items()}
        ti.fail_after = len(ti.stores) + 2
        w = st.writer()
        with self.assertRaises(StorageError):
            w.feed(self.stream(4000, 6))
            w.finish()
        ti.fail_after = None
        self.assertEqual(ti.lists["A84"], before["A84"])
        self.assertEqual(self.read_all(st), old)

    def test_failure_at_commit_keeps_previous_save(self):
        ti = FakeTI()
        st = ti_store(ti)
        old = self.stream(900, 7)
        self.write(st, old)
        w = st.writer()
        w.feed(self.stream(900, 8))
        w.finish()
        ti.fail_after = len(ti.stores)       # the meta write fails
        with self.assertRaises(StorageError):
            w.commit()
        ti.fail_after = None
        self.assertEqual(self.read_all(st), old)

    def test_foreign_meta_is_never_overwritten(self):
        ti = FakeTI()
        ti.lists["A84"] = [1, 2, 3]
        st = ti_store(ti)
        with self.assertRaises(StorageError):
            st.read()
        with self.assertRaises(StorageError):
            st.writer()
        self.assertEqual(ti.lists["A84"], [1, 2, 3])
        self.assertEqual(ti.stores, [])

    def test_foreign_data_list_is_never_overwritten(self):
        ti = FakeTI()
        ti.lists["S0000"] = [5, 6]
        st = ti_store(ti)
        with self.assertRaises(StorageError):
            self.write(st, self.stream(100, 9))
        self.assertEqual(ti.lists["S0000"], [5, 6])
        self.assertNotIn("A84", ti.lists)

    def test_read_detects_corruption(self):
        ti = FakeTI()
        st = ti_store(ti)
        data = self.stream(1500, 10)
        self.write(st, data)
        slot = int(ti.lists["A84"][2])
        good = {k: list(v) for k, v in ti.lists.items()}
        def reset():
            ti.lists = {k: list(v) for k, v in good.items()}
        def consume():
            return b"".join(st.read()[1])
        ti.lists[block_name(slot, 1)][5] += 1.0           # flipped value
        with self.assertRaises(StorageError):
            consume()
        reset()
        del ti.lists[block_name(slot, 1)]                  # missing block
        with self.assertRaises(StorageError):
            consume()
        reset()
        ti.lists[block_name(slot, 0)][0] = 99.5            # wrong magic
        with self.assertRaises(StorageError):
            consume()
        reset()
        ti.lists[block_name(slot, 0)][3] = 2.0 ** 41 + 0.5  # out of range
        with self.assertRaises(StorageError):
            consume()
        reset()
        ti.lists["A84"][1] = 9.5                            # unknown version
        with self.assertRaises(StorageError):
            st.read()
        reset()
        ti.lists["A84"][3] = 1000.5                         # absurd block count
        with self.assertRaises(StorageError):
            st.read()
        reset()
        ti.lists["A84"][4] += 1                             # longer than stored
        with self.assertRaises(StorageError):
            consume()
        reset()
        ti.lists["A84"][5] += 1                             # wrong checksum
        with self.assertRaises(StorageError):
            consume()
        reset()
        self.assertEqual(consume(), data)

    def test_half_value_read_slightly_low_is_harmless(self):
        ti = FakeTI()
        st = ti_store(ti)
        data = self.stream(800, 11)
        self.write(st, data)
        for name in list(ti.lists):
            if name.startswith("S"):
                ti.lists[name] = ti.lists[name][:1] + [x - 0.0001 for x in ti.lists[name][1:]]
        self.assertEqual(self.read_all(st), data)

    def test_memstorage_uses_the_same_code(self):
        ms = MemStorage()
        self.write(ms, self.stream(1200, 12))
        self.assertEqual(self.read_all(ms), self.stream(1200, 12))
        self.assertEqual(ms.kind, "memory")
        for v in ms.d.values():
            self.assertLessEqual(len(v), 100)

    def test_too_large_filesystem_is_refused(self):
        ti = FakeTI()
        st = ti_store(ti)
        w = st.writer()
        with self.assertRaises(StorageError):
            for i in range(1100):
                w.feed(bytes(495))


class KernelSyncTests(unittest.TestCase):
    def kernel(self, ti=None):
        ti = ti or FakeTI()
        return Kernel(ti_store(ti)), ti

    def test_sync_reload_roundtrip_and_numbers(self):
        k, ti = self.kernel()
        k.vfs.write("/home/evo/a.txt", "hello world\n" * 100)
        raw, stored, blocks, warns = k.sync()
        self.assertGreater(raw, 1000)
        self.assertLess(stored, raw)
        self.assertEqual(warns, [])
        k2 = Kernel(ti_store(ti))
        self.assertTrue(same_tree(k2.vfs, k.vfs))
        self.assertTrue(any("Restored fs" in m for m in k2.boot_msgs))
        self.assertFalse(k2.vfs.dirty)

    def test_verify_stops_a_bad_write_before_commit(self):
        k, ti = self.kernel()
        k.vfs.write("/home/evo/a.txt", "good\n")
        k.sync()
        before = {n: list(v) for n, v in ti.lists.items()}
        k.vfs.write("/home/evo/a.txt", "newer " * 200)
        def corrupt(name, data):
            if name != "A84" and name.startswith("S") and len(data) > 2:
                data[2] = data[2] + 1.0
            return data
        ti.hook = corrupt
        with self.assertRaises(StorageError) as cm:
            k.sync()
        self.assertIn("verify failed", str(cm.exception))
        ti.hook = None
        self.assertEqual(ti.lists["A84"], before["A84"])            # still the old save
        k2 = Kernel(ti_store(ti))
        self.assertEqual(k2.vfs.read("/home/evo/a.txt"), "good\n")

    def test_verify_catches_a_dropped_block(self):
        k, ti = self.kernel()
        k.vfs.write("/home/evo/big", "q" * 6000 + "".join(chr(33 + i % 90) for i in range(3000)))
        k.sync()
        k.vfs.write("/home/evo/big", "r" * 6000 + "".join(chr(33 + (i * 7) % 90) for i in range(3000)))
        real = ti.store_list
        def dropper(name, data):
            if name.endswith("001") and name.startswith("S"):
                return real(name, [8484.5])           # block 1 silently truncated
            return real(name, data)
        k.storage.put = dropper
        with self.assertRaises(StorageError):
            k.sync()

    def test_verify_low_memory_warns_but_saves(self):
        k, ti = self.kernel()
        k.vfs.write("/home/evo/a", "x" * 100)
        real = A84KN.decode_stream
        def lowmem(chunks):
            raise ValueError("fs stream: MemoryError()")
        A84KN.decode_stream = lowmem
        try:
            raw, stored, blocks, warns = k.sync()
        finally:
            A84KN.decode_stream = real
        self.assertTrue(any("low memory" in w for w in warns))
        self.assertEqual(Kernel(ti_store(ti)).vfs.read("/home/evo/a"), "x" * 100)

    def test_verify_low_memory_still_checks_the_checksum(self):
        k, ti = self.kernel()
        k.vfs.write("/home/evo/a", "x" * 100)
        k.sync()
        k.vfs.write("/home/evo/a", "y" * 3000)
        real = A84KN.decode_stream
        A84KN.decode_stream = lambda c: (_ for _ in ()).throw(ValueError("fs stream: MemoryError()"))
        def corrupt(name, data):
            if name != "A84" and name.startswith("S") and len(data) > 2:
                data[1] = data[1] + 1.0
            return data
        ti.hook = corrupt
        try:
            with self.assertRaises(StorageError):
                k.sync()
        finally:
            A84KN.decode_stream = real
            ti.hook = None

    def test_corrupt_save_disables_sync_and_is_not_overwritten(self):
        k, ti = self.kernel()
        k.vfs.write("/home/evo/p", "precious\n")
        k.sync()
        slot = int(ti.lists["A84"][2])
        ti.lists[block_name(slot, 0)][1] += 1.0
        before = {n: list(v) for n, v in ti.lists.items()}
        k2 = Kernel(ti_store(ti))
        self.assertFalse(k2.sync_ok)
        self.assertTrue(any("[FAILED]" in m for m in k2.boot_msgs))
        with self.assertRaises(StorageError):
            k2.sync()
        self.assertEqual(ti.lists, before)

    def test_garbage_that_passes_checksum_is_reported_as_corrupt_fs(self):
        ti = FakeTI()
        st = ti_store(ti)
        w = st.writer()
        w.feed(b"\x00\x03\x00\x00\x00R3\x01E\x00")      # a valid frame holding a bad record stream
        w.finish()
        w.commit()
        k = Kernel(ti_store(ti))
        self.assertFalse(k.sync_ok)
        self.assertTrue(any("[FAILED] Corrupt fs" in m for m in k.boot_msgs))
        self.assertTrue(k.vfs.isfile("/etc/hostname"))              # still usable

    def test_unsupported_version_disables_sync(self):
        ms = MemStorage()
        bad_version(ms)
        before = {n: list(v) for n, v in ms.d.items()}
        k = Kernel(ms)
        self.assertFalse(k.sync_ok)
        self.assertEqual(ms.d, before)


class MemoryFailureTests(unittest.TestCase):
    def test_memoryerror_while_saving_becomes_storageerror_and_keeps_old_save(self):
        ti = FakeTI()
        k = Kernel(ti_store(ti))
        k.vfs.write("/home/evo/a", "good")
        k.sync()
        before = {n: list(v) for n, v in ti.lists.items()}
        k.vfs.write("/home/evo/a", "changed" * 50)
        real = A84KN.fs_stream
        def boom(vfs, stats=None):
            raise MemoryError()
            yield b""
        A84KN.fs_stream = boom
        try:
            with self.assertRaises(StorageError) as cm:
                k.sync()
        finally:
            A84KN.fs_stream = real
        self.assertIn("out of memory", str(cm.exception))
        self.assertEqual(ti.lists["A84"], before["A84"])
        self.assertEqual(Kernel(ti_store(ti)).vfs.read("/home/evo/a"), "good")

    def test_memoryerror_midway_through_the_write(self):
        ti = FakeTI()
        k = Kernel(ti_store(ti))
        k.vfs.write("/home/evo/a", "good")
        k.sync()
        k.vfs.write("/home/evo/a", "x" * 3000)
        n = [0]
        real = ti.store_list
        def flaky(name, data):
            n[0] += 1
            if n[0] == 2:
                raise MemoryError()
            return real(name, data)
        k.storage.put = flaky
        with self.assertRaises(StorageError):
            k.sync()
        k.storage.put = real
        self.assertEqual(Kernel(ti_store(ti)).vfs.read("/home/evo/a"), "good")

    def test_boot_reports_out_of_memory_and_disables_saving(self):
        ti = FakeTI()
        k = Kernel(ti_store(ti))
        k.vfs.write("/home/evo/a", "precious")
        k.sync()
        before = {n: list(v) for n, v in ti.lists.items()}
        real = A84KN.decode_stream
        def lowmem(chunks):
            raise ValueError("fs stream: MemoryError()")
        A84KN.decode_stream = lowmem
        try:
            k2 = Kernel(ti_store(ti))
        finally:
            A84KN.decode_stream = real
        self.assertFalse(k2.sync_ok)
        self.assertTrue(any("[FAILED] Load fs: out of memory" in m for m in k2.boot_msgs))
        self.assertFalse(any("Corrupt" in m for m in k2.boot_msgs))
        self.assertEqual(ti.lists, before)

    def test_boot_message_includes_the_allocation_size(self):
        self.assertEqual(A84KN.need_bytes("MemoryError('memory allocation failed, allocating 4801 bytes',)"),
                         " (needed 4801 B)")
        self.assertEqual(A84KN.need_bytes("MemoryError()"), "")
        self.assertEqual(A84KN.need_bytes("allocating 12"), "")
        ti = FakeTI()
        k = Kernel(ti_store(ti))
        k.vfs.write("/home/evo/a", "precious")
        k.sync()
        real = A84KN.decode_stream
        def lowmem(chunks):
            raise ValueError("fs stream: MemoryError('memory allocation failed, allocating 4801 bytes',)")
        A84KN.decode_stream = lowmem
        try:
            k2 = Kernel(ti_store(ti))
        finally:
            A84KN.decode_stream = real
        self.assertTrue(any("out of memory (needed 4801 B)" in m for m in k2.boot_msgs))

    def test_memoryerror_in_storage_read_is_handled(self):
        class Boom(MemStorage):
            def read(self):
                raise MemoryError()
        k = Kernel(Boom())
        self.assertFalse(k.sync_ok)
        self.assertTrue(any("out of memory" in m for m in k.boot_msgs))


class MigrationTests(unittest.TestCase):
    def legacy(self, flaky_checksum=0):
        v = VFS()
        v.reset_default()
        v.mkdir("/home/evo/old")
        v.write("/home/evo/old/notes.txt", "from the v1 days\n" * 20)
        v.write("/etc/hostname", "legacybox\n")
        text = encode_fs(v)
        ti = FakeTI()
        put_v1(ti.store_list, text, flaky_checksum=flaky_checksum)
        return v, ti, text

    def test_v1_save_loads_and_upgrades_on_sync(self):
        v, ti, text = self.legacy()
        old_blocks = int(ti.lists["A84"][3])
        k = Kernel(ti_store(ti))
        self.assertTrue(any("Restored fs" in m for m in k.boot_msgs))
        self.assertTrue(any("Upgrading filesystem to v2" in m for m in k.boot_msgs))
        self.assertTrue(same_tree(k.vfs, v))
        self.assertTrue(k.vfs.dirty)                 # exit would write v2
        raw, stored, blocks, warns = k.sync()
        self.assertEqual(int(ti.lists["A84"][1]), 2)
        for i in range(old_blocks):                  # old lists shrunk
            self.assertEqual(len(ti.lists[block_name(0, i)]), 1)
        k2 = Kernel(ti_store(ti))
        self.assertFalse(any("Upgrading" in m for m in k2.boot_msgs))
        self.assertTrue(same_tree(k2.vfs, k.vfs))     # k gained ~/.ash_history on sync
        self.assertEqual(k2.vfs.read("/etc/hostname"), "legacybox\n")
        self.assertEqual(k2.vfs.read("/home/evo/old/notes.txt"), "from the v1 days\n" * 20)
        self.assertLess(stored, len(text))           # smaller than the old text format

    def test_v2_is_much_smaller_in_list_elements(self):
        v, ti, text = self.legacy()
        old_elems = sum(len(l) for n, l in ti.lists.items() if n.startswith("S"))
        k = Kernel(ti_store(ti))
        k.sync()
        new_elems = sum(len(l) for n, l in ti.lists.items()
                        if n.startswith("S") and len(l) > 1)
        self.assertLess(new_elems * 3, old_elems)

    def test_legacy_checksum_read_back_one_low_is_accepted(self):
        v, ti, text = self.legacy(flaky_checksum=-1)
        k = Kernel(ti_store(ti))
        self.assertTrue(k.sync_ok)
        self.assertTrue(same_tree(k.vfs, v))

    def test_legacy_wrong_checksum_is_rejected_and_untouched(self):
        for off in (-2, 1, 5):
            v, ti, text = self.legacy(flaky_checksum=off)
            before = {n: list(x) for n, x in ti.lists.items()}
            k = Kernel(ti_store(ti))
            self.assertFalse(k.sync_ok, off)
            self.assertTrue(any("[FAILED] Load fs" in m for m in k.boot_msgs))
            self.assertEqual(ti.lists, before)

    def test_legacy_corrupt_text_is_rejected(self):
        v, ti, text = self.legacy()
        ti.lists["S0000"][4] += 3
        k = Kernel(ti_store(ti))
        self.assertFalse(k.sync_ok)

    def test_migrated_empty_filesystem(self):
        v = VFS()
        ti = FakeTI()
        put_v1(ti.store_list, encode_fs(v))
        k = Kernel(ti_store(ti))
        self.assertTrue(k.vfs.isdir("/home/evo"))    # repaired
        self.assertTrue(any("Repaired" in m for m in k.boot_msgs))
        k.sync()
        self.assertTrue(same_tree(Kernel(ti_store(ti)).vfs, k.vfs))


if __name__ == "__main__":
    unittest.main()
