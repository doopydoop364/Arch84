"""Flash repositories: packages stored as calculator modules (tools/ar84pack.py + pacman)."""
import importlib
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, "tools")
from test_pacman import mk, run
import ar84pack
from A84PL import is_part


def purge():
    for n in list(sys.modules):
        if is_part(n) or n == "R84REG" or (n.startswith("QR") and n[2:].isupper()):
            del sys.modules[n]


class Base(unittest.TestCase):
    def setUp(self):
        purge()
        self.dir = tempfile.TemporaryDirectory()
        self.mods = os.path.join(self.dir.name, "mods")
        os.makedirs(self.mods)
        sys.path.insert(0, self.mods)
        self.sh, self.t = mk()
        self.v = self.sh.vfs
        self.pk = {}

    def tearDown(self):
        sys.path.remove(self.mods)
        purge()
        self.dir.cleanup()

    def r(self, line):
        return run(self.sh, self.t, line)

    def make(self, name, ver, deps=(), size=10, desc="d"):
        base = "/tmp/%s%s" % (name, ver.replace(".", ""))
        for d in (base, base + "/usr", base + "/usr/bin"):
            if not self.v.exists(d):
                self.v.mkdir(d)
        self.v.write(base + "/usr/bin/" + name, ("echo %s %s\n" % (name, ver)) * size)
        flags = " ".join("-d '" + d + "'" for d in deps)
        self.assertIn("built", self.r("makepkg %s %s %s %s %s" % (flags, base, name, ver, desc)))
        p = "/var/cache/pacman/pkg/%s-%s.ar84" % (name, ver)
        out = os.path.join(self.dir.name, "%s-%s.ar84" % (name, ver))
        with open(out, "w", encoding="utf-8") as f:
            f.write(self.v.read(p))
        self.v.remove(p)                                 # only the flash copy remains
        self.pk.setdefault("all", []).append(out)
        return out

    def publish(self, repo, files, part_chars=ar84pack.PART_CHARS, also=()):
        mods = ar84pack.build_repo(repo, files, self.mods, part_chars)
        names = sorted(set([repo] + list(also) + [n[2:-3].lower() for n in os.listdir(self.mods) if n.startswith("QR")]))
        mods["R84REG.py"] = ar84pack.registry_source(names)
        for fn, text in mods.items():
            with open(os.path.join(self.mods, fn), "w", encoding="utf-8") as f:
                f.write(text)
        importlib.invalidate_caches()
        return mods


class FlashTests(Base):
    def test_sync_list_search_info(self):
        a = self.make("aa", "1", desc="first tool")
        b = self.make("bb", "2", deps=["aa"], desc="second")
        self.publish("mine", [a, b])
        self.assertEqual(self.r("pacman -Sy"), "synchronized 2 packages\n")
        self.assertEqual(self.r("pacman -Sl"), "aa 1\nbb 2\n")
        self.assertEqual(self.r("pacman -Ss first"), "aa 1\n    first tool\n")
        info = self.r("pacman -Si bb")
        self.assertIn("Depends On  : aa", info)
        self.assertIn("Repository  : mine", info)

    def test_install_with_dependencies_from_flash_leaves_nothing_in_memory(self):
        a = self.make("aa", "1")
        b = self.make("bb", "2", deps=["aa"])
        self.publish("mine", [a, b])
        self.r("pacman -Sy")
        out = self.r("pacman -S bb")
        self.assertIn("installed aa 1", out)
        self.assertIn("installed bb 2", out)
        self.assertEqual(self.r("bb"), "bb 2\n" * 10)
        self.assertEqual(self.r("pacman -Qd"), "aa 1\n")
        self.assertEqual(self.r("pacman -Qk"), "aa: 1 total files, 0 altered files\nbb: 1 total files, 0 altered files\n")
        self.assertEqual([n for n in sys.modules if is_part(n)], [])
        self.assertNotIn("R84REG", sys.modules)
        self.assertEqual(self.v.listdir("/var/cache/pacman/pkg") if self.v.isdir("/var/cache/pacman/pkg") else [], [])
        self.assertEqual(self.r("pacman -Rns bb"), "removed bb 2\nremoved aa 1\n")

    def test_dependencies_across_repositories(self):
        a = self.make("aa", "1")
        b = self.make("bb", "1", deps=["aa>=1"])
        self.publish("core", [a])
        self.publish("extra", [b])
        self.assertEqual(self.r("pacman -Sy"), "synchronized 2 packages\n")
        self.assertIn("Repository  : core", self.r("pacman -Si aa"))
        self.assertEqual(self.r("pacman -S bb").count("installed"), 2)

    def test_missing_dependency_fails_cleanly(self):
        b = self.make("bb", "1", deps=["nothere"])
        self.publish("mine", [b])
        self.r("pacman -Sy")
        out = self.r("pacman -S bb")
        self.assertIn("target not found: nothere", out)
        self.assertEqual(self.r("pacman -Q"), "")
        self.assertFalse(self.v.exists("/usr/bin/bb"))
        self.assertFalse(self.v.exists("/var/lib/pacman/pacman.lock"))

    def test_multi_part_packages(self):
        a = self.make("big", "1", size=120)
        mods = self.publish("mine", [a], part_chars=500)
        parts = [f for f in mods if f.startswith("K")]
        self.assertGreater(len(parts), 3)
        self.assertTrue(all(len(open(os.path.join(self.mods, f)).read()) < 1500 for f in parts))
        self.r("pacman -Sy")
        self.assertIn("installed big 1", self.r("pacman -S big"))
        self.assertEqual(self.v.read("/usr/bin/big"), "echo big 1\n" * 120)
        self.assertEqual(self.r("pacman -Qk big"), "big: 1 total files, 0 altered files\n")

    def test_missing_part_and_corrupt_part(self):
        a = self.make("big", "1", size=120)
        mods = self.publish("mine", [a], part_chars=500)
        parts = sorted(f for f in mods if f.startswith("K"))
        self.r("pacman -Sy")
        os.rename(os.path.join(self.mods, parts[2]), os.path.join(self.mods, parts[2] + ".gone"))
        importlib.invalidate_caches()
        out = self.r("pacman -S big")
        self.assertIn("is not on the calculator", out)
        self.assertEqual(self.r("pacman -Q"), "")
        os.rename(os.path.join(self.mods, parts[2] + ".gone"), os.path.join(self.mods, parts[2]))
        importlib.invalidate_caches()
        path = os.path.join(self.mods, parts[1])
        with open(path) as f:
            text = f.read().replace("echo big", "echo baggy", 1)
        with open(path, "w") as f:
            f.write(text)
        purge()
        out = self.r("pacman -S big")
        self.assertIn("error:", out)
        self.assertEqual(self.r("pacman -Q"), "")
        self.assertFalse(self.v.exists("/usr/bin/big"))
        self.assertEqual([n for n in sys.modules if is_part(n)], [])

    def test_no_registry_and_broken_repository(self):
        self.assertEqual(self.r("pacman -Sl"), "")
        self.assertFalse(self.v.exists("/var/lib/pacman/sync/repo.db"))       # nothing to remember
        a = self.make("aa", "1")
        self.publish("mine", [a], also=["ghost"])                               # ghost has no index module
        out = self.r("pacman -Sy")
        self.assertEqual(out, "synchronized 1 packages (1 skipped)\n")

    def test_garbage_in_index_is_skipped(self):
        a = self.make("aa", "1")
        self.publish("mine", [a])
        p = os.path.join(self.mods, "QRMINE.py")
        with open(p, "w") as f:
            f.write("ROWS = (('aa', '1', 'K000000', 1, '', 'ok'), ('Bad Name', '1', 'K000000', 1, '', ''), ('x', '1', 'nope', 1, '', ''), ('y', '1', 'K000000', 99, '', ''), 5, ('z',))\n")
        purge()
        importlib.invalidate_caches()
        out = self.r("pacman -Sy")
        self.assertIn("synchronized 1 packages (5 skipped)", out)

    def test_flash_upgrade_and_local_priority(self):
        a1 = self.make("aa", "1")
        self.publish("mine", [a1])
        self.r("pacman -Sy")
        self.r("pacman -S aa")
        a2 = self.make("aa", "2")
        self.publish("mine", [a1, a2])
        self.r("pacman -Sy")
        self.assertEqual(self.r("pacman -Qu"), "aa 1 -> 2\n")
        self.assertIn("upgraded aa 1 -> 2", self.r("pacman -Su"))
        self.assertEqual(self.r("aa"), "echo aa 2\n".replace("echo ", "") * 10)

    def test_local_copy_wins_at_the_same_version(self):
        a = self.make("aa", "1")
        self.publish("mine", [a])
        with open(a, encoding="utf-8") as f:
            self.v.mkdir("/var/cache/pacman") if not self.v.exists("/var/cache/pacman") else None
            self.v.mkdir("/var/cache/pacman/pkg") if not self.v.exists("/var/cache/pacman/pkg") else None
            self.v.write("/var/cache/pacman/pkg/aa-1.ar84", f.read())
        self.assertEqual(self.r("pacman -Sy"), "synchronized 2 packages\n")
        self.assertIn("Repository  : local", self.r("pacman -Si aa"))

    def test_sc_leaves_flash_alone(self):
        a = self.make("aa", "1")
        self.publish("mine", [a])
        self.r("pacman -Sy")
        self.assertIn("cache cleaned: 0 packages", self.r("pacman -Sc"))
        self.assertEqual(self.r("pacman -Sl"), "aa 1\n")


class PackToolTests(Base):
    def test_module_names_are_calculator_names(self):
        a = self.make("aa", "1", size=200)
        mods = self.publish("mine", [a], part_chars=400)
        for fn in list(mods) + ["R84REG.py"]:
            self.assertTrue(re.fullmatch(r"[A-Z][A-Z0-9]{0,7}", fn[:-3]), fn)
        self.assertIn("QRMINE.py", mods)

    def test_generated_modules_compile_and_roundtrip(self):
        a = self.make("aa", "1", size=50)
        mods = self.publish("mine", [a], part_chars=300)
        text = ""
        for fn in sorted(f for f in mods if f.startswith("K")):
            ns = {}
            exec(compile(mods[fn], fn, "exec"), ns)
            text += "\n".join(ns["LINES"]) + "\n"
        self.assertEqual(text, open(a, encoding="utf-8").read())

    def test_rejects_bad_input(self):
        bad = os.path.join(self.dir.name, "bad.ar84")
        with open(bad, "w") as f:
            f.write("AR84 1\nname x\n")
        with self.assertRaises(SystemExit):
            ar84pack.build_repo("mine", [bad], self.mods)
        a = self.make("aa", "1", size=200)
        for name in ("", "UP", "toolongname", "a_b"):
            with self.assertRaises(SystemExit):
                ar84pack.build_repo(name, [a], self.mods)
        with self.assertRaises(SystemExit):
            ar84pack.build_repo("mine", [a, a], self.mods)                     # duplicate package
        with self.assertRaises(SystemExit):
            ar84pack.build_repo("mine", [a], self.mods, part_chars=1)         # more than 9 parts

    def test_registry_from_device_listing(self):
        self.assertEqual(ar84pack.device_repos(["ARCH84", "QRCORE", "QRMINE", "QR", "QRTOOLONG", "KABCDEF0", "R84REG"]), ["core", "mine"])
        self.assertEqual(ar84pack.registry_source(["b", "a", "b"]), "# Arch84 repository list (generated by ar84pack)\nREPOS = ('a', 'b', )\n")


if __name__ == "__main__":
    unittest.main()
