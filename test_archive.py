"""archive command: files leave the heap into lists and come back intact."""
import unittest

from testutil import *
from A84SH import Shell
from A84KN import Kernel
from A84ST import MemStorage
import A84AR
import A84AX


class T:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s.replace("\x01", "E:")

    def post(self, s, pending=False):
        pass

    def busy(self):
        pass

    def clear(self):
        pass


def mk(ms=None):
    t = T()
    sh = Shell(Kernel(ms or MemStorage()), t)
    return sh, t


def run(sh, t, line):
    t.text = ""
    sh.execute(line)
    return t.text


def populate(v):
    v.mkdir("/home/evo/docs")
    v.mkdir("/home/evo/docs/sub")
    v.write("/home/evo/docs/a.txt", "hello\n" * 80)
    v.write("/home/evo/docs/sub/b", "é€漢\t\\ \n")
    v.write("/home/evo/docs/empty", "")
    v.write("/home/evo/big", "0123456789" * 400)       # stored as pieces
    v.write("/tmp/t1", "tmp file")


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.ms = MemStorage()
        self.sh, self.t = mk(self.ms)
        populate(self.sh.vfs)

    def r(self, line):
        return run(self.sh, self.t, line)

    def tree(self, paths):
        w = walk(self.sh.vfs)
        return {k: v for k, v in w.items() if any(k == p or k.startswith(p + "/") for p in paths)}

    def test_create_extract_roundtrip(self):
        paths = ["/home/evo/docs", "/home/evo/big", "/tmp/t1"]
        want = self.tree(paths)
        out = self.r("archive create old docs big /tmp/t1")
        self.assertIn("archived 5 files", out)
        for p in paths:
            self.assertFalse(self.sh.vfs.exists(p), p)
        self.assertTrue(any(k.startswith("Q0") for k in self.ms.d))
        self.assertIn("old: 5 files", self.r("archive list"))
        self.assertEqual(self.r("archive check"), "old: ok\n")
        self.assertIn("restored 5 files", self.r("archive extract old"))
        self.assertEqual(self.tree(paths), want)
        from A84FS import dnew
        self.assertEqual(self.sh.vfs.get("/home/evo/big").data, dnew("0123456789" * 400))
        self.assertEqual(self.r("archive list"), "")

    def test_frees_heap_objects_and_survives_reload(self):
        self.r("archive create old docs big")
        sh2, t2 = mk(self.ms)                      # a fresh boot from the saved state
        self.assertFalse(sh2.vfs.exists("/home/evo/docs"))
        self.assertIn("old: 4 files", run(sh2, t2, "archive list"))
        self.assertEqual(run(sh2, t2, "archive check"), "old: ok\n")
        run(sh2, t2, "archive extract old")
        self.assertEqual(sh2.vfs.read("/home/evo/docs/a.txt"), "hello\n" * 80)
        sh3, t3 = mk(self.ms)                      # and the extract was saved too
        self.assertEqual(sh3.vfs.read("/home/evo/docs/sub/b"), "é€漢\t\\ \n")

    def test_keep_flag_and_delete(self):
        self.r("archive create a docs")
        self.assertIn("restored", self.r("archive extract -k a"))
        self.assertIn("a: 3 files", self.r("archive list"))
        self.sh.vfs.remove("/home/evo/docs/empty")
        self.r("rm -r docs")
        self.assertIn("restored", self.r("archive extract a"))
        self.assertTrue(self.sh.vfs.exists("/home/evo/docs/empty"))
        self.r("archive create b big")
        self.assertEqual(self.r("archive delete b"), "deleted b\n")
        self.assertEqual(self.r("archive list"), "")
        self.assertIn("no such archive", self.r("archive extract b"))

    def test_refusals_change_nothing(self):
        before = walk(self.sh.vfs)
        for line, msg in (("archive create x /etc/profile", "not allowed"),
                          ("archive create x /etc", "not allowed"),
                          ("archive create x /", "not allowed"),
                          ("archive create x /home/evo", "system directory"),
                          ("archive create x /home/evo/.ashrc", "system file"),
                          ("archive create x nosuch", "no such file"),
                          ("archive create Bad docs", "bad archive name"),
                          ("archive create x docs docs/sub", "overlapping"),
                          ("archive create x /var/lib/archive", "not allowed"),
                          ("archive create x", "usage"),
                          ("archive", "usage"),
                          ("archive nonsense", "unknown operation")):
            self.assertIn(msg, self.r(line), line)
        self.r("cd docs")
        self.assertIn("current directory", self.r("archive create x /home/evo/docs"))
        self.assertEqual(walk(self.sh.vfs), before)
        self.assertFalse([k for k in self.ms.d if k.startswith("Q")])

    def test_name_and_extract_conflicts(self):
        self.r("archive create a docs")
        self.assertIn("archive exists", self.r("archive create a big"))
        self.sh.vfs.mkdir("/home/evo/docs")
        self.assertIn("already exists", self.r("archive extract a"))
        self.assertTrue(self.sh.vfs.isdir("/home/evo/docs"))

    def test_up_to_ten_archives(self):
        for i in range(10):
            self.sh.vfs.write("/tmp/f%d" % i, "x%d" % i)
            self.assertIn("archived", self.r("archive create n%d /tmp/f%d" % (i, i)))
        self.sh.vfs.write("/tmp/more", "m")
        self.assertIn("too many", self.r("archive create n10 /tmp/more"))
        self.r("archive delete n3")
        self.assertIn("archived", self.r("archive create again /tmp/more"))      # reuses the free id

    def test_sync_failure_keeps_the_archive_and_the_saved_copy(self):
        # low memory during the final save: the files are already out of RAM, the
        # saved copy still has them, and the next successful sync commits the change
        self.sh.k.sync()
        saved = {k: list(v) for k, v in self.ms.d.items() if k[0] in "SA" and not k.startswith("A84Q")}
        real = self.sh.k.sync
        self.sh.k.sync = lambda force=False: (_ for _ in ()).throw(A84AR.StorageError("out of memory (x)"))
        out = self.r("archive create x docs big")
        self.sh.k.sync = real
        self.assertIn("warning: not saved yet", out)
        self.assertFalse(self.sh.vfs.exists("/home/evo/docs"))
        self.assertIn("x: 4 files", self.r("archive list"))
        ms2 = MemStorage()
        ms2.d = {k: list(v) for k, v in self.ms.d.items()}
        sh2, t2 = mk(ms2)                            # power cut now: the old saved copy comes back
        self.assertEqual(sh2.vfs.read("/home/evo/docs/a.txt"), "hello\n" * 80)
        self.assertEqual(run(sh2, t2, "archive list"), "")
        self.assertIn("leftover data of no archive", run(sh2, t2, "fsck"))
        self.r("sync")                                # but a retry commits
        sh3, t3 = mk(self.ms)
        self.assertFalse(sh3.vfs.exists("/home/evo/docs"))
        self.assertEqual(run(sh3, t3, "archive check"), "x: ok\n")

    def test_extract_whose_save_fails_never_loses_the_archive(self):
        self.r("archive create x docs big")                  # committed
        real = self.sh.k.sync
        self.sh.k.sync = lambda force=False: (_ for _ in ()).throw(A84AR.StorageError("out of memory (x)"))
        out = self.r("archive extract x")
        self.sh.k.sync = real
        self.assertIn("warning: not saved yet", out)
        self.assertTrue(self.sh.vfs.exists("/home/evo/docs"))        # restored in RAM
        ms2 = MemStorage()
        ms2.d = {k: list(v) for k, v in self.ms.d.items()}
        sh2, t2 = mk(ms2)                                            # power cut now
        self.assertFalse(sh2.vfs.exists("/home/evo/docs"))           # saved copy: still archived
        self.assertEqual(run(sh2, t2, "archive check"), "x: ok\n")   # and its lists are intact
        self.assertIn("restored", run(sh2, t2, "archive extract x"))
        self.assertEqual(sh2.vfs.read("/home/evo/docs/a.txt"), "hello\n" * 80)

    def test_delete_whose_save_fails_keeps_the_lists(self):
        self.r("archive create x docs")
        real = self.sh.k.sync
        self.sh.k.sync = lambda force=False: (_ for _ in ()).throw(A84AR.StorageError("out of memory (x)"))
        self.assertIn("warning", self.r("archive delete x"))
        self.sh.k.sync = real
        self.assertGreater(len(self.ms.d["Q0000"]), 2)               # not shrunk before the save
        self.r("sync")                                               # (data stays until the next archive reuses the id)

    def test_power_cut_between_lists_and_sync_loses_nothing(self):
        # lists written, files still in the saved filesystem: simulate by failing the sync hard
        sh_saved = self.sh
        sh_saved.k.sync()
        saved = {k: list(v) for k, v in self.ms.d.items()}
        real = sh_saved.k.sync
        sh_saved.k.sync = lambda force=False: (_ for _ in ()).throw(SystemExit)
        with self.assertRaises(SystemExit):
            self.r("archive create x docs big")
        sh_saved.k.sync = real
        ms2 = MemStorage()
        ms2.d = {k: list(v) for k, v in self.ms.d.items()}
        sh2, t2 = mk(ms2)                          # boot after the "power cut": old saved state
        self.assertEqual(sh2.vfs.read("/home/evo/docs/a.txt"), "hello\n" * 80)
        self.assertEqual(run(sh2, t2, "archive list"), "")

    def test_corrupt_archive_is_detected(self):
        self.r("archive create a docs")
        lst = self.ms.d["Q0000"]
        lst[3] = lst[3] + 1.0
        self.assertIn("a:", self.r("archive check"))
        self.assertEqual(self.sh.status, 1)
        out = self.r("archive extract a")
        self.assertIn("damaged", out)
        self.assertFalse(self.sh.vfs.exists("/home/evo/docs"))      # nothing half-restored
        self.assertIn("a: 3 files", self.r("archive list"))         # catalogue kept

    def test_low_memory_on_extract_reports_and_keeps_archive(self):
        self.r("archive create a docs big")
        import A84CZ
        real = A84CZ.Rd                     # A84AX re-imports it each time it is loaded

        def boom(chunks):
            raise MemoryError()
        A84CZ.Rd = boom
        try:
            out = self.r("archive extract a")
        finally:
            A84CZ.Rd = real
        self.assertIn("not enough free RAM", out)
        self.assertIn("a: 4 files", self.r("archive list"))
        self.assertIn("restored", self.r("archive extract a"))

    def test_foreign_list_is_never_overwritten(self):
        self.ms.d["Q0000"] = [5.0, 6.0]            # someone else's list with our name
        out = self.r("archive create a docs")
        self.assertIn("not ours", out)
        self.assertTrue(self.sh.vfs.exists("/home/evo/docs"))
        self.assertEqual(self.ms.d["Q0000"], [5.0, 6.0])

    def test_modules_unload_after_use(self):
        import sys
        from A84CD import COMMANDS
        self.r("archive list")
        for m in ("A84AX", "A84AR", "A84AE", "A84AI"):
            self.assertNotIn(m, sys.modules)
        self.assertNotIn("archive", COMMANDS)
        self.assertIn("usage", self.r("archive"))          # and it comes back on demand

    def test_registered_lazily(self):
        from A84CD import LAZY
        self.assertEqual(LAZY["archive"], "A84AX")



class FsckTests(unittest.TestCase):
    def setUp(self):
        self.ms = MemStorage()
        self.sh, self.t = mk(self.ms)
        populate(self.sh.vfs)

    def r(self, line):
        return run(self.sh, self.t, line)

    def test_clean_system(self):
        self.sh.k.sync()
        out = self.r("fsck")
        self.assertIn("filesystem: saved copy ok", out)
        self.assertIn("system files: ok", out)
        self.assertIn("no problems found", out)
        self.assertEqual(self.sh.status, 0)

    def test_nothing_saved_yet(self):
        self.assertIn("nothing saved yet", self.r("fsck"))

    def test_leftover_archive_lists_are_found_and_cleared(self):
        self.r("archive create a docs")
        e = A84AR.read_index(self.sh.vfs)[0]
        # lose the catalogue entry (as after a failed sync that left the lists behind)
        A84AR.write_index(self.sh.vfs, [])
        out = self.r("fsck")
        self.assertIn("leftover data of no archive", out)
        self.assertEqual(self.sh.status, 1)
        out = self.r("fsck -r")
        self.assertIn("cleared 1 lists", out)
        self.assertEqual(self.ms.d["Q0000"], [8484.5])
        self.assertIn("no problems found", self.r("fsck"))

    def test_damaged_archive_and_saved_copy(self):
        self.r("archive create a docs")
        self.ms.d["Q0000"][2] += 1.0
        out = self.r("fsck")
        self.assertIn("archive a: DAMAGED", out)
        self.sh.k.sync()
        live = [k for k in self.ms.d if k[0] == "S" and len(self.ms.d[k]) > 2][0]
        self.ms.d[live][1] += 1.0
        self.assertIn("DAMAGED", self.r("fsck"))

    def test_missing_system_files_repair(self):
        self.sh.vfs.remove("/etc/hostname")
        self.assertIn("system files missing: /etc/hostname", self.r("fsck"))
        self.assertIn("repaired", self.r("fsck -r"))
        self.assertTrue(self.sh.vfs.isfile("/etc/hostname"))

    def test_package_files_missing(self):
        import test_pacman as tp
        tp.install_text(self.sh, tp.pkg_text("demo", "1.0", tp.BASIC))
        self.assertIn("packages: 1 installed, 0 files missing", self.r("fsck"))
        self.sh.vfs.remove("/usr/bin/hi")
        out = self.r("fsck")
        self.assertIn("package demo: missing /usr/bin/hi", out)
        self.assertEqual(self.sh.status, 1)

    def test_usage(self):
        self.assertIn("usage", self.r("fsck -x"))

if __name__ == "__main__":
    unittest.main()
