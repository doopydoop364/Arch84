"""pacman / makepkg and the .ar84 package format (A84PM PD PI PB PX)."""
import random
import unittest

from testutil import *
from A84SH import Shell
from A84KN import Kernel
from A84ST import MemStorage
from A84PM import PkgError, Sum, esc, ok_path, ok_name, ok_ver, vkey, MAGIC, scan
import A84PI


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


def mk(storage=None):
    t = T()
    sh = Shell(Kernel(storage or MemStorage()), t)
    return sh, t


def run(sh, t, line):
    t.text = ""
    sh.execute(line)
    return t.text


def pkg_lines(name, version, entries, desc="", depends=(), chunk=256):
    """valid package lines; entries: ("D", path) | ("F", path, text)"""
    lines = [MAGIC, "name " + name, "version " + version]
    if desc:
        lines.append("desc " + esc(desc))
    if depends:
        lines.append("depends " + " ".join(depends))
    n = 0
    for e in entries:
        n += 1
        if e[0] == "D":
            lines.append("D\t" + e[1])
        else:
            s = Sum()
            s.add(e[2])
            lines.append("F\t%s\t%d\t%s" % (e[1], len(e[2]), s.hex()))
            for i in range(0, len(e[2]), chunk):
                lines.append("+\t" + esc(e[2][i:i + chunk]))
    return lines, n


def seal(lines, n, bad_sum=False, bad_n=None):
    tot = Sum()
    for l in lines:
        tot.add(l + "\n")
    return lines + ["END\t%d\t%s" % (n if bad_n is None else bad_n, "0-0" if bad_sum else tot.hex())]


def pkg_text(name, version, entries, **kw):
    seal_kw = {k: kw.pop(k) for k in ("bad_sum", "bad_n") if k in kw}
    lines, n = pkg_lines(name, version, entries, **kw)
    return "\n".join(seal(lines, n, **seal_kw)) + "\n"


def install_text(sh, text, path="/home/evo/p.ar84"):
    sh.vfs.write(path, text)
    return A84PI.install(sh.vfs, path)


BASIC = [("D", "/usr/bin"), ("D", "/opt/hi"), ("F", "/usr/bin/hi", "echo hi $1\n"), ("F", "/opt/hi/data", "d\ta\\b\n\x01é€")]


class FormatTests(unittest.TestCase):
    def test_name_version_path_rules(self):
        for n in ("a", "foo-bar", "x.y_z+1", "0ad"):
            self.assertTrue(ok_name(n), n)
        for n in ("", "-a", "A", "a b", "a/b", "x" * 25, "é"):
            self.assertFalse(ok_name(n), n)
        for v in ("1", "1.0.2", "r5_a+b", "2024Q1"):
            self.assertTrue(ok_ver(v), v)
        for v in ("", "1-2", "a b", "1" * 17, "é"):
            self.assertFalse(ok_ver(v), v)
        good = ["/usr/bin/x", "/opt/a/b", "/etc/x.conf", "/home/evo/x", "/var/lib/foo/x", "/usr/share/a b"]
        bad = ["usr/bin/x", "/usr/bin/../x", "/usr/./x", "/usr//x", "/usr/x/", "/", "/usr", "/etc", "/dev/x", "/proc/x",
               "/tmp/x", "/boot/x", "/run/x", "/root/x", "/etc/version", "/etc/hostname", "/etc/profile", "/etc/clock",
               "/home/evo/.profile", "/home/evo/.ashrc", "/home/evo/.ash_history", "/var/lib/pacman/local/x/files",
               "/var/lib/pacman", "/var/cache/pacman/pkg/x", "/usr/b\tin/x", "/usr/b\nin/x", "/" + "a" * 200]
        for p in good:
            self.assertTrue(ok_path(p), p)
        for p in bad:
            self.assertFalse(ok_path(p), p)

    def test_version_ordering(self):
        order = ["0.9", "1.0", "1.0.1", "1.2", "1.10", "2"]
        for i in range(len(order) - 1):
            self.assertLess(vkey(order[i]), vkey(order[i + 1]), order[i])

    def test_scan_reports_everything(self):
        sh, t = mk()
        sh.vfs.write("/home/evo/p.ar84", pkg_text("demo", "1.2", BASIC, desc="A\tdemo\nx", depends=("a", "b")))
        m = scan(sh.vfs, "/home/evo/p.ar84")
        self.assertEqual((m["name"], m["version"], m["desc"], m["depends"]), ("demo", "1.2", "A\tdemo\nx", ["a", "b"]))
        self.assertEqual(m["dirs"], ["/usr/bin", "/opt/hi"])
        self.assertEqual([f[0] for f in m["files"]], ["/usr/bin/hi", "/opt/hi/data"])


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()

    def r(self, line):
        return run(self.sh, self.t, line)

    def snap(self):
        return walk(self.sh.vfs)

    def test_install_query_remove_roundtrip(self):
        before = self.snap()
        meta, old = install_text(self.sh, pkg_text("demo", "1.0", BASIC, desc="demo pkg"))
        self.assertIsNone(old)
        self.assertEqual(self.sh.vfs.read("/opt/hi/data"), "d\ta\\b\n\x01é€")
        self.assertEqual(self.r("pacman -Q"), "demo 1.0\n")
        self.assertIn("Description : demo pkg", self.r("pacman -Qi demo"))
        self.assertEqual(self.r("pacman -Ql demo"), "demo /usr/bin/hi\ndemo /opt/hi/data\n")
        self.assertEqual(self.r("pacman -Qk demo"), "demo: 2 total files, 0 altered files\n")
        self.assertEqual(self.r("pacman -Qo /usr/bin/hi"), "/usr/bin/hi is owned by demo 1.0\n")
        self.assertEqual(self.r("hi there"), "hi there\n")
        self.assertEqual(self.r("pacman -R demo"), "removed demo 1.0\n")
        after = self.snap()
        after.pop("/home/evo/p.ar84", None); before.pop("/home/evo/p.ar84", None)
        # only the empty pacman database directories remain from the install
        for k in list(after):
            if k.startswith("/var/lib/pacman"):
                after.pop(k)
        self.assertEqual(after, before)

    def test_created_dirs_are_removed_existing_dirs_kept(self):
        install_text(self.sh, pkg_text("demo", "1.0", BASIC))
        self.assertTrue(self.sh.vfs.isdir("/opt/hi"))
        self.r("pacman -R demo")
        self.assertFalse(self.sh.vfs.exists("/opt/hi"))
        self.assertTrue(self.sh.vfs.isdir("/usr/bin"))
        self.assertFalse(self.sh.vfs.exists("/opt"))                # /opt was created by the package too
        self.sh.vfs.mkdir("/opt")
        install_text(self.sh, pkg_text("demo", "1.0", BASIC))
        self.sh.vfs.write("/opt/hi/mine", "user file")
        self.r("pacman -R demo")
        self.assertTrue(self.sh.vfs.isfile("/opt/hi/mine"))         # a dir with foreign content stays

    def test_upgrade_removes_stale_files_and_updates_db(self):
        install_text(self.sh, pkg_text("demo", "1.0", BASIC))
        v2 = [("D", "/usr/bin"), ("F", "/usr/bin/hi", "echo v2\n"), ("F", "/usr/bin/new", "echo new\n")]
        meta, old = install_text(self.sh, pkg_text("demo", "2.0", v2))
        self.assertEqual(old, "1.0")
        self.assertFalse(self.sh.vfs.exists("/opt/hi/data"))
        self.assertFalse(self.sh.vfs.exists("/opt/hi"))
        self.assertEqual(self.r("hi"), "v2\n")
        self.assertEqual(self.r("pacman -Q"), "demo 2.0\n")
        self.assertEqual(self.r("pacman -Qk demo"), "demo: 2 total files, 0 altered files\n")
        meta, old = install_text(self.sh, pkg_text("demo", "1.0", BASIC))      # downgrade
        self.assertEqual(old, "2.0")
        self.assertFalse(self.sh.vfs.exists("/usr/bin/new"))

    def test_conflicts(self):
        self.sh.vfs.write("/usr/bin/hi", "mine")
        with self.assertRaises(PkgError) as c:
            install_text(self.sh, pkg_text("demo", "1.0", BASIC))
        self.assertIn("exists in filesystem", str(c.exception))
        self.assertEqual(self.sh.vfs.read("/usr/bin/hi"), "mine")
        self.sh.vfs.remove("/usr/bin/hi")
        install_text(self.sh, pkg_text("demo", "1.0", BASIC))
        with self.assertRaises(PkgError) as c:
            install_text(self.sh, pkg_text("other", "1.0", [("F", "/usr/bin/hi", "x")]))
        self.assertIn("owned by demo", str(c.exception))
        self.sh.vfs.mkdir("/usr/bin/adir")
        with self.assertRaises(PkgError):
            install_text(self.sh, pkg_text("o2", "1", [("F", "/usr/bin/adir", "x")]))
        self.sh.vfs.write("/opt/f", "x")
        with self.assertRaises(PkgError):
            install_text(self.sh, pkg_text("o3", "1", [("F", "/opt/f/inner", "x")]))
        self.assertEqual(self.r("pacman -Q"), "demo 1.0\n")

    def test_dependencies(self):
        with self.assertRaises(PkgError) as c:
            install_text(self.sh, pkg_text("app", "1", [("F", "/usr/bin/app", "x")], depends=("lib",)))
        self.assertIn("missing dependency: lib", str(c.exception))
        install_text(self.sh, pkg_text("lib", "1", [("F", "/usr/lib/lib.txt", "L")]))
        install_text(self.sh, pkg_text("app", "1", [("F", "/usr/bin/app", "x")], depends=("lib",)))
        self.assertIn("required by app", self.r("pacman -R lib"))
        self.assertTrue(self.sh.vfs.exists("/usr/lib/lib.txt"))
        self.r("pacman -R app")
        self.assertIn("removed lib", self.r("pacman -R lib"))

    def test_repo_install_resolves_dependencies_and_picks_latest(self):
        v = self.sh.vfs
        v.mkdir("/tmp/s")
        for name, ver, deps, body in (("lib", "1.9", "", "old"), ("lib", "1.10", "", "new"), ("app", "1", "-d lib", "app")):
            for d in ("/tmp/s/usr", "/tmp/s/usr/bin"):
                if not v.exists(d):
                    v.mkdir(d)
            v.write("/tmp/s/usr/bin/" + name, body)
            self.assertIn("built", self.r("makepkg %s /tmp/s %s %s" % (deps, name, ver)).replace("makepkg: ", ""))
            v.remove("/tmp/s/usr/bin/" + name)
        out = self.r("pacman -S app")
        self.assertEqual(out, "installed lib 1.10 (1 files)\ninstalled app 1 (1 files)\n")
        self.assertEqual(v.read("/usr/bin/lib"), "new")
        self.assertEqual(self.r("pacman -Sl"), "app 1\nlib 1.10\nlib 1.9\n")
        self.assertIn("target not found: nosuch", self.r("pacman -S nosuch"))

    def test_dependency_loop_is_reported(self):
        v = self.sh.vfs
        for name, dep in (("a", "b"), ("b", "a")):
            v.write("/home/evo/x", "x")
            v.mkdir("/tmp/" + name); v.mkdir("/tmp/%s/usr" % name); v.write("/tmp/%s/usr/%s" % (name, name), name)
            self.r("makepkg -d %s /tmp/%s %s 1" % (dep, name, name))
        self.assertIn("dependency loop", self.r("pacman -S a"))

    def test_verify_detects_changes(self):
        install_text(self.sh, pkg_text("demo", "1.0", BASIC))
        self.sh.vfs.write("/usr/bin/hi", "echo hi $1\n")           # same text: fine
        self.assertIn("0 altered", self.r("pacman -Qk"))
        self.sh.vfs.write("/usr/bin/hi", "echo ho $1\n")
        self.assertIn("(modified)", self.r("pacman -Qk demo"))
        self.sh.vfs.remove("/opt/hi/data")
        out = self.r("pacman -Qk demo")
        self.assertIn("(missing)", out)
        self.assertIn("2 altered", out)
        self.assertEqual(self.sh.status, 1)

    def test_state_survives_sync_and_reload(self):
        ms = MemStorage()
        sh, t = mk(ms)
        install_text(sh, pkg_text("demo", "1.0", BASIC))
        sh.k.sync()
        sh2, t2 = mk(ms)
        self.assertEqual(run(sh2, t2, "pacman -Qk demo"), "demo: 2 total files, 0 altered files\n")
        self.assertEqual(run(sh2, t2, "hi z"), "hi z\n")
        self.assertEqual(run(sh2, t2, "pacman -R demo"), "removed demo 1.0\n")

    def test_big_and_odd_data_roundtrip(self):
        rng = random.Random(3)
        data = "".join(rng.choice("ab\\\n\t\r é€漢.") for _ in range(5000))
        install_text(self.sh, pkg_text("blob", "1", [("F", "/opt/blob", data)]))
        self.assertEqual(self.sh.vfs.read("/opt/blob"), data)
        from A84FS import dnew
        self.assertEqual(self.sh.vfs.get("/opt/blob").data, dnew(data))
        install_text(self.sh, pkg_text("empty", "1", [("F", "/opt/empty", "")]))
        self.assertEqual(self.sh.vfs.read("/opt/empty"), "")


class RejectTests(unittest.TestCase):
    """every malformed package must fail with PkgError and change nothing"""

    def setUp(self):
        self.sh, self.t = mk()
        install_text(self.sh, pkg_text("keep", "1", [("F", "/opt/keep", "k")]))
        self.before = walk(self.sh.vfs)

    def reject(self, text, expect=None):
        self.sh.vfs.write("/home/evo/bad.ar84", text)
        self.before["/home/evo/bad.ar84"] = text
        with self.assertRaises(PkgError) as c:
            A84PI.install(self.sh.vfs, "/home/evo/bad.ar84")
        if expect:
            self.assertIn(expect, str(c.exception))
        self.assertEqual(walk(self.sh.vfs), self.before)

    def test_bad_paths(self):
        for p in ("usr/x", "/usr/../etc/x", "/dev/x", "/proc/x", "/etc/version", "/etc/profile", "/tmp/x",
                  "/var/lib/pacman/local/keep/files", "/var/cache/pacman/pkg/x", "/usr", "/", "/home/evo/.ash_history"):
            self.reject(pkg_text("bad", "1", [("F", p, "x")]), "path not allowed")
            self.reject(pkg_text("bad", "1", [("D", p)]), "path not allowed")

    def test_bad_header_values(self):
        self.reject(pkg_text("Bad", "1", [("F", "/opt/x", "x")]), "bad package name")
        self.reject(pkg_text("bad", "1-2", [("F", "/opt/x", "x")]), "bad package version")
        self.reject(pkg_text("bad", "1", [("F", "/opt/x", "x")], depends=("A b",)), "dependency")

    def test_structure_errors(self):
        ok_lines, n = pkg_lines("bad", "1", [("F", "/opt/x", "hello")])
        self.reject("", "empty")
        self.reject("not a package\n", "not an .ar84")
        self.reject("\n".join(ok_lines) + "\n", "truncated")
        self.reject("\n".join(seal(ok_lines, n, bad_sum=True)) + "\n", "checksum")
        self.reject("\n".join(seal(ok_lines, n, bad_n=5)) + "\n", "entry count")
        self.reject("\n".join(seal(ok_lines, n)) + "\nextra\n", "after END")
        lines = list(ok_lines)
        lines[4] = "+\t" + esc("hellx")                       # data differs from the file sum
        self.reject("\n".join(seal(lines, n)) + "\n", "file checksum")
        lines = list(ok_lines)
        lines[3] = lines[3].replace("\t5\t", "\t4\t")
        self.reject("\n".join(seal(lines, n)) + "\n", "size mismatch")
        lines = [ok_lines[0], "D\t/opt/d"] + ok_lines[1:]
        self.reject("\n".join(seal(lines, n + 1)) + "\n", "missing name")

    def test_duplicates_and_nesting(self):
        self.reject(pkg_text("bad", "1", [("F", "/opt/x", "a"), ("F", "/opt/x", "b")]), "duplicate")
        self.reject(pkg_text("bad", "1", [("F", "/opt/x", "a"), ("D", "/opt/x")]), "duplicate")
        self.reject(pkg_text("bad", "1", [("F", "/opt/x", "a"), ("F", "/opt/x/y", "b")]), "file used as directory")

    def test_limits(self):
        self.reject(pkg_text("bad", "1", [("F", "/opt/f%d" % i, "x") for i in range(301)]), "too many")
        self.reject(pkg_text("bad", "1", [("F", "/opt/big", "x" * 20001)]), "too large")

    def test_header_after_entries_and_bad_escape(self):
        lines, n = pkg_lines("bad", "1", [("F", "/opt/x", "a")])
        lines.append("desc late")
        self.reject("\n".join(seal(lines, n)) + "\n", "header after")
        s = Sum(); s.add("a")
        lines = [MAGIC, "name bad", "version 1", "F\t/opt/x\t1\t" + s.hex(), "+\ta\\q"]
        self.reject("\n".join(seal(lines, 1)) + "\n")

    def test_package_cannot_overwrite_itself(self):
        text = pkg_text("bad", "1", [("F", "/home/evo/bad.ar84", "x")])
        self.reject(text, "contains itself")

    def test_nothing_of_a_conflicting_package_is_written(self):
        self.sh.vfs.write("/opt/clash", "mine")
        self.before = walk(self.sh.vfs)
        self.reject(pkg_text("bad", "1", [("D", "/opt/newdir"), ("F", "/opt/newdir/a", "a"), ("F", "/opt/clash", "x")]),
                    "exists in filesystem")

    def test_random_damage_never_corrupts(self):
        good = pkg_text("fz", "1.0", BASIC, desc="d", depends=("keep",))
        rng = random.Random(8)
        installed = rejected = 0
        for _ in range(500):
            lines = good.split("\n")
            kind = rng.randrange(6)
            i = rng.randrange(len(lines))
            if kind == 0:
                del lines[i]
            elif kind == 1:
                lines.insert(i, lines[rng.randrange(len(lines))])
            elif kind == 2 and lines[i]:
                j = rng.randrange(len(lines[i]))
                lines[i] = lines[i][:j] + rng.choice("x\t \\/.0") + lines[i][j + 1:]
            elif kind == 3:
                lines[i], lines[rng.randrange(len(lines))] = lines[rng.randrange(len(lines))], lines[i]
            elif kind == 4 and lines[i]:
                lines[i] = lines[i][:rng.randrange(len(lines[i]))]
            else:
                lines = lines[:rng.randrange(len(lines))]
            text = "\n".join(lines)
            sh, t = mk()
            install_text(sh, pkg_text("keep", "1", [("F", "/opt/keep", "k")]))
            snap = walk(sh.vfs)
            sh.vfs.write("/home/evo/p.ar84", text)
            snap["/home/evo/p.ar84"] = text
            try:
                meta, old = A84PI.install(sh.vfs, "/home/evo/p.ar84")
                installed += 1
                for p, size, s in meta["files"]:
                    self.assertTrue(sh.vfs.isfile(p))
                self.assertIn(run(sh, t, "pacman -Qk fz"), ("fz: 2 total files, 0 altered files\n",))
            except PkgError:
                rejected += 1
                self.assertEqual(walk(sh.vfs), snap, text)
        self.assertGreater(rejected, 300)


class RollbackTests(unittest.TestCase):
    def test_failure_midway_restores_everything(self):
        for fail_at in range(1, 9):
            sh, t = mk()
            install_text(sh, pkg_text("demo", "1.0", BASIC))
            sh.vfs.write("/home/evo/keepme", "mine")
            v2 = [("D", "/usr/bin"), ("D", "/opt/newd"), ("F", "/usr/bin/hi", "echo v2 " * 40),
                  ("F", "/opt/newd/file", "n" * 700), ("F", "/opt/hi/data", "changed")]
            sh.vfs.write("/home/evo/p2.ar84", pkg_text("demo", "2.0", v2))
            before = walk(sh.vfs)
            real = sh.vfs.append
            count = [0]

            def flaky(path, data, real=real, count=count, fail_at=fail_at):
                if not path.startswith("/home/evo/p2") and not path.startswith("/var/lib"):
                    count[0] += 1
                    if count[0] == fail_at:
                        raise MemoryError()
                return real(path, data)
            sh.vfs.append = flaky
            try:
                A84PI.install(sh.vfs, "/home/evo/p2.ar84")
                done = True
            except PkgError as e:
                done = False
                self.assertIn("rolled back", str(e))
            sh.vfs.append = real
            if not done:
                self.assertEqual(walk(sh.vfs), before, fail_at)
        self.assertTrue(True)

    def test_database_write_failure_rolls_back(self):
        sh, t = mk()
        sh.vfs.write("/home/evo/p.ar84", pkg_text("demo", "1.0", BASIC))
        before = walk(sh.vfs)
        real = A84PI.db_write
        A84PI.db_write = lambda vfs, meta: (_ for _ in ()).throw(MemoryError())
        try:
            with self.assertRaises(PkgError):
                A84PI.install(sh.vfs, "/home/evo/p.ar84")
        finally:
            A84PI.db_write = real
        after = walk(sh.vfs)
        for k in list(after):
            if k.startswith("/var/lib/pacman"):
                after.pop(k)
        for k in list(before):
            if k.startswith("/var/lib/pacman"):
                before.pop(k)
        self.assertEqual(after, before)


class MakepkgTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()
        self.v = self.sh.vfs

    def r(self, line):
        return run(self.sh, self.t, line)

    def stage(self):
        for d in ("/tmp/s", "/tmp/s/usr", "/tmp/s/usr/bin", "/tmp/s/opt", "/tmp/s/opt/app", "/tmp/s/opt/app/empty"):
            self.v.mkdir(d)
        self.v.write("/tmp/s/usr/bin/tool", "echo tool\n")
        self.v.write("/tmp/s/opt/app/readme", "r" * 600)

    def test_build_scan_install(self):
        self.stage()
        out = self.r("makepkg /tmp/s tool 0.1 A tool for tests")
        self.assertEqual(out, "built /var/cache/pacman/pkg/tool-0.1.ar84 (2 files, 610 chars)\n")
        m = scan(self.v, "/var/cache/pacman/pkg/tool-0.1.ar84")
        self.assertEqual(m["desc"], "A tool for tests")
        self.assertEqual(m["dirs"], ["/opt/app", "/opt/app/empty", "/usr/bin"])
        self.assertIn("installed tool 0.1", self.r("pacman -U /var/cache/pacman/pkg/tool-0.1.ar84"))
        self.assertTrue(self.v.isdir("/opt/app/empty"))
        self.assertEqual(self.v.read("/opt/app/readme"), "r" * 600)
        self.assertEqual(self.r("tool"), "tool\n")

    def test_build_errors(self):
        self.stage()
        self.assertIn("usage", self.r("makepkg /tmp/s tool"))
        self.assertIn("bad package name", self.r("makepkg /tmp/s Tool 1"))
        self.assertIn("bad package name", self.r("makepkg /tmp/s tool 1-2"))
        self.assertIn("No such file", self.r("makepkg /nodir tool 1"))
        self.v.mkdir("/tmp/s/tmp")
        self.assertIn("path not allowed", self.r("makepkg /tmp/s tool 1"))
        self.v.remove("/tmp/s/tmp")
        self.v.write("/tmp/s/usr/bin/big", "x" * 20001)
        self.assertIn("too large", self.r("makepkg /tmp/s tool 1"))

    def test_usage_and_unknown_flags(self):
        self.assertIn("usage: pacman", self.r("pacman"))
        self.assertIn("usage: pacman", self.r("pacman -X"))
        self.assertIn("no targets", self.r("pacman -U"))
        self.assertIn("No such file", self.r("pacman -U /nope.ar84"))
        self.assertIn("was not found", self.r("pacman -Qi nope"))
        self.assertIn("No package owns", self.r("pacman -Qo /etc/hostname"))


class RepoTests(unittest.TestCase):
    def setUp(self):
        self.sh, self.t = mk()
        self.v = self.sh.vfs

    def r(self, line):
        return run(self.sh, self.t, line)

    def make(self, name, ver, deps="", desc="d"):
        self.v.mkdir("/tmp/%s%s" % (name, ver)) if not self.v.exists("/tmp/%s%s" % (name, ver)) else None
        base = "/tmp/%s%s" % (name, ver)
        for d in (base + "/usr", base + "/usr/bin"):
            if not self.v.exists(d):
                self.v.mkdir(d)
        self.v.write(base + "/usr/bin/" + name, "echo %s %s\n" % (name, ver))
        self.assertIn("built", self.r("makepkg %s %s %s %s %s" % (deps, base, name, ver, desc)))

    def test_lock_blocks_and_is_released(self):
        self.make("aa", "1")
        self.assertIn("installed aa 1", self.r("pacman -S aa"))
        self.assertFalse(self.v.exists("/var/lib/pacman/pacman.lock"))
        self.assertIn("removed aa", self.r("pacman -R aa"))
        self.assertFalse(self.v.exists("/var/lib/pacman/pacman.lock"))
        self.v.write("/var/lib/pacman/pacman.lock", "x")
        out = self.r("pacman -S aa")
        self.assertIn("unable to lock database", out)
        self.assertIn("rm /var/lib/pacman/pacman.lock", out)
        self.assertTrue(self.v.exists("/var/lib/pacman/pacman.lock"))     # not ours: left alone
        self.assertFalse(self.v.exists("/usr/bin/aa"))
        self.assertEqual(self.r("pacman -Q"), "")                         # queries ignore the lock
        self.r("rm /var/lib/pacman/pacman.lock")
        self.assertIn("installed aa", self.r("pacman -S aa"))

    def test_fsck_clears_stale_lock(self):
        self.r("pacman -Q")
        self.v.mkdir("/var/lib/pacman") if not self.v.isdir("/var/lib/pacman") else None
        self.v.write("/var/lib/pacman/pacman.lock", "pacman\n")
        self.assertIn("stale pacman lock\n", self.r("fsck"))
        self.assertIn("stale pacman lock removed", self.r("fsck -r"))
        self.assertFalse(self.v.exists("/var/lib/pacman/pacman.lock"))
        self.assertIn("no problems found", self.r("fsck"))

    def test_lock_released_after_failure(self):
        self.assertIn("target not found", self.r("pacman -S nothere"))
        self.assertFalse(self.v.exists("/var/lib/pacman/pacman.lock"))
        self.assertIn("not found", self.r("pacman -R nothere"))
        self.assertFalse(self.v.exists("/var/lib/pacman/pacman.lock"))

    def test_index_search_info_and_staleness(self):
        self.make("aa", "1", desc="the first tool")
        self.make("bb", "2", "-d aa", "second")
        self.assertFalse(self.v.exists("/var/lib/pacman/sync/repo.db"))   # makepkg drops it
        self.assertEqual(self.r("pacman -Sy"), "synchronized 2 packages\n")
        self.assertTrue(self.v.isfile("/var/lib/pacman/sync/repo.db"))
        self.assertEqual(self.r("pacman -Sl"), "aa 1\nbb 2\n")
        self.assertEqual(self.r("pacman -Ss first"), "aa 1\n    the first tool\n")
        self.assertIn("Depends On  : aa", self.r("pacman -Si bb"))
        self.assertIn("not found", self.r("pacman -Si zz"))
        # a file added behind the index's back is noticed
        self.v.write("/var/cache/pacman/pkg/junk.ar84", "not a package")
        self.assertEqual(self.r("pacman -Sl"), "aa 1\nbb 2\n")
        self.assertIn("(1 skipped)", self.r("pacman -Sy"))
        self.assertIn("installed aa 1", self.r("pacman -S bb").replace("installed bb 2", ""))
        self.assertEqual(self.r("pacman -Q"), "aa 1\nbb 2\n")
        self.v.remove("/var/lib/pacman/sync/repo.db")                     # missing index: rebuilt
        self.assertEqual(self.r("pacman -Sl"), "aa 1\nbb 2\n")

    def test_upgrade(self):
        self.make("aa", "1")
        self.make("cc", "1")
        self.r("pacman -S aa cc")
        self.assertEqual(self.r("pacman -Qu"), "")
        self.make("aa", "1.1")
        self.make("cc", "0.9")
        self.assertEqual(self.r("pacman -Qu"), "aa 1 -> 1.1\n")
        out = self.r("pacman -Syu")
        self.assertIn("upgraded aa 1 -> 1.1", out)
        self.assertEqual(self.r("pacman -Qu"), "")
        self.assertEqual(self.r("aa"), "aa 1.1\n")
        self.assertEqual(self.r("pacman -Su"), "nothing to do\n")
        self.assertFalse(self.v.exists("/var/lib/pacman/pacman.lock"))


class TabAndHelpTests(unittest.TestCase):
    def test_commands_are_lazy_and_listed(self):
        from A84CD import LAZY, all_commands
        self.assertEqual(LAZY["pacman"], "A84PX")
        self.assertEqual(LAZY["makepkg"], "A84PX")
        self.assertIn("pacman", all_commands())


if __name__ == "__main__":
    unittest.main()
