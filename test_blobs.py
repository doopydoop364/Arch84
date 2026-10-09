"""Files whose text is kept in calculator lists (A84BL) instead of the heap. Desktop tests with the
in-memory list store. Run: python3 test_blobs.py"""
import sys
import unittest

sys.path.insert(0, ".")
import test_arch84 as T
from A84FS import VFS, VFSError, dlen, dpieces, dtext, StorageError
from A84KN import Kernel
from A84ST import MemStorage
from testutil import FakeTI, ti_store
import A84BL

TEXT = "".join("line %d: some text with é and € in it\n" % i for i in range(120))      # ~4.5 KB, multibyte


def mk():
    sh, t = T.mk()
    sh.vfs.mkdir("/home/evo/d")
    return sh, t


def data(sh, path):
    return sh.vfs._file(path).data


class ExternalTests(unittest.TestCase):
    def test_a_file_moves_into_lists_and_reads_back_whole(self):
        sh, t = mk()
        sh.vfs.write("/home/evo/f", TEXT)
        self.assertTrue(sh.vfs.externalize("/home/evo/f"))
        d = data(sh, "/home/evo/f")
        self.assertIsInstance(d, A84BL.Ext)
        self.assertEqual(sh.vfs.read("/home/evo/f"), TEXT)
        self.assertEqual(dlen(d), len(TEXT))
        self.assertEqual(sh.vfs.size("/home/evo/f"), len(TEXT))
        self.assertEqual("".join(dpieces(d)), TEXT)
        self.assertEqual(list(sh.vfs.lines("/home/evo/f"))[:2], TEXT.split("\n")[:2])
        self.assertGreater(len(d.ids), 5)                           # several lists
        self.assertTrue(all(len(p) > 0 for p in dpieces(d)))

    def test_nothing_of_the_text_stays_in_the_heap(self):
        sh, t = mk()
        sh.vfs.write("/home/evo/f", TEXT)
        sh.vfs.externalize("/home/evo/f")
        d = data(sh, "/home/evo/f")
        self.assertFalse(isinstance(d, (str, list)))
        self.assertEqual(sorted(vars(d)), ["ids", "n", "store"])

    def test_pieces_can_be_iterated_more_than_once(self):
        sh, t = mk()
        sh.vfs.write("/home/evo/f", TEXT)
        sh.vfs.externalize("/home/evo/f")
        p = dpieces(data(sh, "/home/evo/f"))
        self.assertEqual("".join(p), "".join(p))

    def test_small_files_and_missing_files_stay(self):
        sh, t = mk()
        sh.vfs.write("/home/evo/s", "tiny\n")
        self.assertFalse(sh.vfs.externalize("/home/evo/s"))
        self.assertIsInstance(data(sh, "/home/evo/s"), str)
        self.assertFalse(sh.vfs.externalize("/home/evo/nothing"))
        self.assertFalse(sh.vfs.externalize("/home/evo/d"))
        sh.vfs.write("/home/evo/m", "x" * 250)
        self.assertTrue(sh.vfs.externalize("/home/evo/m"))
        self.assertFalse(sh.vfs.externalize("/home/evo/m"))            # already external

    def test_multibyte_text_is_never_split_inside_a_character(self):
        sh, t = mk()
        for k in range(1, 4):
            text = ("a" * k + "€é\U0001F600") * 200
            sh.vfs.write("/home/evo/u", text)
            sh.vfs.externalize("/home/evo/u")
            self.assertEqual(sh.vfs.read("/home/evo/u"), text)

    def test_exactly_one_list_boundary(self):
        sh, t = mk()
        for n in (A84BL.PER - 1, A84BL.PER, A84BL.PER + 1, 2 * A84BL.PER):
            sh.vfs.write("/home/evo/b", "y" * n)
            sh.vfs.externalize("/home/evo/b")
            self.assertEqual(sh.vfs.read("/home/evo/b"), "y" * n)

    def test_without_a_store_nothing_happens(self):
        v = VFS()
        v.reset_default()
        v.write("/tmp/x", "z" * 500)
        self.assertFalse(v.externalize("/tmp/x"))


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()
        self.sh.vfs.write("/home/evo/f", TEXT)
        self.sh.vfs.externalize("/home/evo/f")

    def r(self, line):
        return T.run(self.sh, self.t, line)

    def test_commands_read_it(self):
        self.assertEqual(self.r("cat f"), TEXT)
        self.assertEqual(self.r("wc -l f"), "120 f\n")
        self.assertEqual(self.r("head -n 1 f"), TEXT.split("\n")[0] + "\n")
        self.assertEqual(self.r("grep -c 'line 7' f"), "11\n")
        self.assertEqual(self.r("cat f | wc -l"), "120\n")
        self.assertEqual(self.r("wc -c < f"), str(len(TEXT)) + "\n")
        self.assertIn("f", self.r("ls"))
        self.assertIn(str(len(TEXT)), self.r("du f"))

    def test_copies_share_the_lists(self):
        self.r("cp f g")
        self.assertIs(data(self.sh, "/home/evo/g"), data(self.sh, "/home/evo/f"))
        self.assertEqual(self.r("cat g"), TEXT)
        self.r("mv g h")
        self.assertEqual(self.r("cat h"), TEXT)
        self.r("rm f")
        self.assertEqual(self.r("cat h"), TEXT)

    def test_writing_to_it_brings_the_text_back_into_the_heap(self):
        self.r("echo more >> f")
        self.assertIsInstance(data(self.sh, "/home/evo/f"), (str, list))
        self.assertEqual(self.r("cat f"), TEXT + "more\n")
        self.r("echo new > f")
        self.assertEqual(self.r("cat f"), "new\n")

    def test_copy_of_an_external_file_is_independent_after_a_write(self):
        self.r("cp f g")
        self.r("echo x >> g")
        self.assertEqual(self.r("cat f"), TEXT)
        self.assertEqual(self.r("cat g"), TEXT + "x\n")

    def test_the_editor_loads_and_saves_it(self):
        text = self.sh.vfs.read("/home/evo/f")
        self.assertEqual(text, TEXT)
        self.sh.vfs.write("/home/evo/f", text.replace("line 1:", "LINE 1:"))
        self.assertIn("LINE 1:", self.r("cat f"))

    def test_a_damaged_list_is_reported_not_crashed_on(self):
        st = self.sh.k.storage
        first = data(self.sh, "/home/evo/f").ids[2]
        del st.d["X%04d" % first]
        out = self.r("cat f")
        self.assertIn("Input/output error", out)
        st.d["X%04d" % first] = [1.5, 2.5, 3.5]                    # foreign data in its place
        self.assertIn("Input/output error", self.r("cat f"))

    def test_fsck_checks_the_lists(self):
        out = self.r("fsck")
        self.assertIn("files in lists: ok (1 files", out)
        st = self.sh.k.storage
        del st.d["X%04d" % data(self.sh, "/home/evo/f").ids[0]]
        out = self.r("fsck")
        self.assertIn("file /home/evo/f: DAMAGED", out)
        self.assertEqual(self.sh.status, 1)

    def test_df_counts_the_file(self):
        out = self.r("df")
        self.assertIn("rootfs", out)

    def test_archive_packs_and_restores_an_external_file(self):
        self.r("mkdir -p proj")
        self.r("cp f proj/big")
        out = self.r("archive create a proj")
        self.assertIn("archived 1 files", out)
        self.assertNotIn("big", self.r("ls proj"))
        self.r("archive extract a")
        self.assertEqual(self.r("cat proj/big"), TEXT)


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.ti = FakeTI()
        self.k = Kernel(ti_store(self.ti))
        self.k.vfs.write("/home/evo/f", TEXT)
        self.k.vfs.externalize("/home/evo/f")

    def test_the_save_records_list_numbers_not_text(self):
        raw, stored, blocks, warns = self.k.sync()
        self.assertLess(raw, 400)                                    # the text is 4.5 KB: it is not in the save
        self.assertEqual(warns, [])

    def test_it_comes_back_after_a_restart(self):
        self.k.sync()
        k2 = Kernel(ti_store(self.ti))
        d = k2.vfs._file("/home/evo/f").data
        self.assertIsInstance(d, A84BL.Ext)
        self.assertEqual(k2.vfs.read("/home/evo/f"), TEXT)
        self.assertEqual(d.ids, self.k.vfs._file("/home/evo/f").data.ids)
        self.assertTrue(k2.vfs.ext)

    def test_a_number_is_not_reused_until_a_save_without_it(self):
        self.k.sync()
        old = list(self.k.vfs._file("/home/evo/f").data.ids)
        self.k.vfs.remove("/home/evo/f")
        self.k.vfs.write("/home/evo/g", "q" * 900)
        self.k.vfs.externalize("/home/evo/g")
        new = self.k.vfs._file("/home/evo/g").data.ids
        self.assertFalse(set(old) & set(new))                       # the saved tree still needs them
        k2 = Kernel(ti_store(self.ti))                              # a restart before the next sync ...
        self.assertEqual(k2.vfs.read("/home/evo/f"), TEXT)          # ... finds the old file intact
        self.k.sync()                                               # now the old numbers are free
        self.k.vfs.write("/home/evo/h", "r" * 900)
        self.k.vfs.externalize("/home/evo/h")
        self.assertTrue(set(old) & set(self.k.vfs._file("/home/evo/h").data.ids))

    def test_numbers_freed_during_a_session_come_back_after_the_next_save(self):
        old = list(self.k.vfs._file("/home/evo/f").data.ids)          # f is external, never saved
        self.k.vfs.write("/home/evo/f", "z" * 900)                     # replaced: its lists are garbage now
        self.k.vfs.externalize("/home/evo/f")
        mid = self.k.vfs._file("/home/evo/f").data.ids
        self.assertFalse(set(old) & set(mid))                          # (not reused yet: kept until the next save)
        self.k.sync()
        self.k.vfs.write("/home/evo/f", "y" * 900)
        self.k.vfs.externalize("/home/evo/f")
        self.assertTrue(set(old) & set(self.k.vfs._file("/home/evo/f").data.ids))

    def test_foreign_lists_are_not_overwritten(self):
        st = self.k.storage
        st.put("X0000", [7.5, 8.5, 9.5])
        k2 = Kernel(ti_store(self.ti))
        k2.vfs.write("/home/evo/n", "n" * 700)
        k2.vfs.externalize("/home/evo/n")
        self.assertNotIn(0, k2.vfs._file("/home/evo/n").data.ids)
        self.assertEqual(st.get("X0000"), [7.5, 8.5, 9.5])

    def test_full_lists_leave_the_file_in_the_heap(self):
        st = self.k.storage
        real = st.put

        def full(name, elems):
            raise ValueError("List length > 100.")
        st.put = full
        try:
            self.k.vfs.write("/home/evo/w", "w" * 900)
            self.assertFalse(self.k.vfs.externalize("/home/evo/w"))
        finally:
            st.put = real
        self.assertEqual(self.k.vfs.read("/home/evo/w"), "w" * 900)

    def test_verify_after_a_save_compares_external_files(self):
        raw, stored, blocks, warns = self.k.sync()
        self.assertEqual(warns, [])                                  # same_tree ran over Ext data too
        self.assertTrue(self.k.vfs.ext)

    def test_a_file_in_lists_replaced_by_text_and_saved_roundtrips(self):
        self.k.sync()
        self.k.vfs.write("/home/evo/f", "short\n")
        self.k.sync()
        k2 = Kernel(ti_store(self.ti))
        self.assertEqual(k2.vfs.read("/home/evo/f"), "short\n")


class PackageTests(unittest.TestCase):
    def test_installed_files_database_and_download_live_in_lists(self):
        sh, t = mk()
        r = lambda line: T.run(sh, t, line)
        r("mkdir -p pk/usr/bin")
        r("echo 'echo from a package' > pk/usr/bin/hello")
        r("seq 200 > pk/usr/bin/numbers")
        r("makepkg pk big 1.0 a package with a bigger file")
        r("pacman -U /var/cache/pacman/pkg/big-1.0.ar84")
        v = sh.vfs
        self.assertIsInstance(v._file("/usr/bin/numbers").data, A84BL.Ext)      # >= 200 chars: in lists
        self.assertIsInstance(v._file("/usr/bin/hello").data, str)               # tiny: stays
        self.assertTrue(v.isfile("/var/lib/pacman/local/big"))                  # one node per package: no directory
        self.assertIsInstance(v._file("/var/lib/pacman/local/big").data, (A84BL.Ext, str))
        self.assertEqual(r("wc -l /usr/bin/numbers"), "200 /usr/bin/numbers\n")
        self.assertEqual(r("pacman -Qk big"), "big: 2 total files, 0 altered files\n")
        self.assertIn("big 1.0", r("pacman -Q"))
        r("pacman -R big")
        self.assertFalse(v.exists("/usr/bin/numbers"))


class DbFormatTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()
        self.r = lambda line: T.run(self.sh, self.t, line)
        self.r("mkdir -p pk/usr/bin pk/usr/share/x")
        self.r("echo 'echo v1' > pk/usr/bin/tool")
        self.r("seq 100 > pk/usr/share/x/data")
        self.r("makepkg -d other pk tool 1.0 a tool")
        self.r("mkdir -p q/usr/bin")
        self.r("echo 'echo other' > q/usr/bin/other")
        self.r("makepkg q other 2.0")

    def test_an_installed_package_is_a_single_file(self):
        self.r("pacman -U /var/cache/pacman/pkg/other-2.0.ar84")
        self.r("pacman -U /var/cache/pacman/pkg/tool-1.0.ar84")
        v = self.sh.vfs
        self.assertEqual(sorted(v.listdir("/var/lib/pacman/local")), ["other", "tool"])
        self.assertTrue(v.isfile("/var/lib/pacman/local/tool"))
        self.assertFalse(v.isdir("/var/lib/pacman/local/tool"))
        text = v.read("/var/lib/pacman/local/tool")
        self.assertIn("name tool\nversion 1.0\n", text)
        self.assertIn("depends other\n%files\n", text)
        self.assertEqual(self.r("pacman -Q"), "other 2.0\ntool 1.0\n")
        self.assertIn("/usr/share/x/data", self.r("pacman -Ql tool"))
        self.assertEqual(self.r("pacman -Qo /usr/bin/tool"), "/usr/bin/tool is owned by tool 1.0\n")
        self.assertEqual(self.r("pacman -Qk tool"), "tool: 2 total files, 0 altered files\n")

    def test_reason_changes_keep_the_file_list(self):
        self.r("pacman -U /var/cache/pacman/pkg/other-2.0.ar84")
        self.r("pacman -U /var/cache/pacman/pkg/tool-1.0.ar84")
        self.r("pacman -S other")                                          # naming it makes it explicit
        self.assertIn("/usr/bin/other", self.r("pacman -Ql other"))
        self.assertEqual(self.r("pacman -Qk other"), "other: 1 total files, 0 altered files\n")

    def test_older_directory_entries_are_still_understood_and_replaced(self):
        self.r("pacman -U /var/cache/pacman/pkg/other-2.0.ar84")
        v = self.sh.vfs
        text = v.read("/var/lib/pacman/local/other")                       # rebuild it in the old layout
        head, _, files = text.partition("%files\n")
        v.remove("/var/lib/pacman/local/other")
        v.mkdir("/var/lib/pacman/local/other")
        v.write("/var/lib/pacman/local/other/desc", head)
        v.write("/var/lib/pacman/local/other/files", files)
        self.assertEqual(self.r("pacman -Q"), "other 2.0\n")
        self.assertIn("/usr/bin/other", self.r("pacman -Ql other"))
        self.assertEqual(self.r("pacman -Qo /usr/bin/other"), "/usr/bin/other is owned by other 2.0\n")
        self.assertIn("no problems found", self.r("fsck"))
        self.r("pacman -U /var/cache/pacman/pkg/other-2.0.ar84")           # a reinstall writes the new layout
        self.assertTrue(v.isfile("/var/lib/pacman/local/other"))
        self.assertEqual(self.r("pacman -Q"), "other 2.0\n")
        self.r("mkdir /var/lib/pacman/local/zz")                            # an empty directory entry: reported
        self.assertIn("database entry incomplete", self.r("fsck"))
        self.r("rmdir /var/lib/pacman/local/zz")

    def test_removing_an_older_directory_entry(self):
        self.r("pacman -U /var/cache/pacman/pkg/other-2.0.ar84")
        v = self.sh.vfs
        text = v.read("/var/lib/pacman/local/other")
        head, _, files = text.partition("%files\n")
        v.remove("/var/lib/pacman/local/other")
        v.mkdir("/var/lib/pacman/local/other")
        v.write("/var/lib/pacman/local/other/desc", head)
        v.write("/var/lib/pacman/local/other/files", files)
        self.assertEqual(self.r("pacman -R other"), "removed other 2.0\n")
        self.assertEqual(self.r("ls /var/lib/pacman/local"), "")
        self.assertFalse(v.exists("/usr/bin/other"))

    def test_fewer_nodes_per_package_than_before(self):
        self.r("pacman -U /var/cache/pacman/pkg/other-2.0.ar84")       # (the first install also creates the database folders)
        before = self.count()
        self.r("pacman -U /var/cache/pacman/pkg/tool-1.0.ar84")
        # tool: /usr/bin/tool, /usr/share/x/data, the directory /usr/share/x, and ONE database file
        self.assertEqual(self.count() - before, 4)

    def count(self):
        n = 0
        stack = [self.sh.vfs.root]
        while stack:
            x = stack.pop()
            n += 1
            if x.is_dir:
                stack.extend(x.children.values())
        return n


class RandomTests(unittest.TestCase):
    """Random file operations with files moving in and out of lists, saves and reloads; every
    file is checked against a plain dict model after every step."""
    def run_seed(self, seed, steps=250):
        import random
        rng = random.Random(seed)
        ti = FakeTI()
        k = Kernel(ti_store(ti))
        sh = T.Shell(k, T.CaptureTerm())
        model = {}
        saved = {}                                  # what the last save holds (a crash comes back to it)
        names = ["f%d" % i for i in range(8)]
        alphabet = "abc \u00e9\u20ac\n"
        for step in range(steps):
            op = rng.choice(["write", "write", "append", "ext", "ext", "cp", "mv", "rm", "sync", "reload", "crash"])
            n = rng.choice(names)
            p = "/home/evo/" + n
            if op == "write":
                text = "".join(rng.choice(alphabet) for _ in range(rng.choice([5, 150, 400, 900, 2000])))
                k.vfs.write(p, text)
                model[n] = text
            elif op == "append" and n in model:
                text = "".join(rng.choice(alphabet) for _ in range(rng.choice([3, 300, 700])))
                k.vfs.append(p, text)
                model[n] += text
            elif op == "ext" and n in model:
                k.vfs.externalize(p, rng.choice([1, 100, 300]))
            elif op == "cp" and n in model:
                m = rng.choice(names)
                if m != n:
                    k.vfs.copyfile(p, "/home/evo/" + m)
                    model[m] = model[n]
            elif op == "mv" and n in model:
                m = rng.choice(names)
                if m != n:
                    k.vfs.rename(p, "/home/evo/" + m)
                    model[m] = model.pop(n)
            elif op == "rm" and n in model:
                k.vfs.remove(p)
                del model[n]
            elif op == "sync":
                k.sync()
                saved = dict(model)
            elif op == "reload":
                k.sync()
                saved = dict(model)
                k = Kernel(ti_store(ti))
            elif op == "crash":
                k = Kernel(ti_store(ti))            # the session is lost; the last save comes back
                model = dict(saved)
            for name, text in model.items():
                self.assertEqual(k.vfs.read("/home/evo/" + name), text, "seed %d step %d op %s" % (seed, step, op))
                self.assertEqual(k.vfs.size("/home/evo/" + name), len(text))
        k.sync()
        k2 = Kernel(ti_store(ti))
        for name, text in model.items():
            self.assertEqual(k2.vfs.read("/home/evo/" + name), text)

    def test_random_operations_with_saves_reloads_and_crashes(self):
        for seed in range(1, 25):
            self.run_seed(seed)


if __name__ == "__main__":
    unittest.main()
