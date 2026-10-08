"""Tests for deploy.py backups. Run: python3 test_deploy.py"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deploy
import evo_usb


def source(name):
    with open(os.path.join(HERE, name + ".py")) as f:
        return f.read()


class BackupTests(unittest.TestCase):
    def test_names_are_valid_and_distinct(self):
        names = [deploy.bak_name(n) for n in deploy.MODULES + [deploy.LAUNCHER]]
        self.assertEqual(len(set(names)), len(names))
        for n in names:
            self.assertTrue(evo_usb.is_valid_evo_python_name(n), n)
            self.assertLessEqual(len(n), 8)
            self.assertTrue(n.endswith("BAK"))
        self.assertEqual(deploy.bak_name("ARCH84"), "ARC84BAK")
        self.assertEqual(deploy.bak_name("A84FS"), "A84FSBAK")
        self.assertFalse(evo_usb.is_valid_evo_python_name("ARCH84BAK"))   # why the launcher is special

    def test_every_module_reference_is_renamed(self):
        stray = re.compile(r"\b(" + "|".join(deploy.MODULES) + r")\b")
        for n in deploy.MODULES + [deploy.LAUNCHER]:
            out = deploy.bak_source(source(n))
            self.assertTrue(out.startswith(deploy.HEADER))
            self.assertEqual(stray.findall(out), [], n)
            compile(out, n + "BAK", "exec")

    def test_original_sources_untouched_by_renaming(self):
        text = source("A84SH")
        deploy.bak_source(text)
        self.assertIn("from A84FS import", text)
        self.assertNotIn("BAK", text)

    def test_backup_system_runs_standalone(self):
        with tempfile.TemporaryDirectory() as d:
            for n in deploy.MODULES:
                with open(os.path.join(d, deploy.bak_name(n) + ".py"), "w") as f:
                    f.write(deploy.bak_source(source(n)))
            with open(os.path.join(d, "ARC84BAK.py"), "w") as f:
                f.write(deploy.bak_source(source("ARCH84")))
            # the originals must NOT be importable from here: only *BAK modules exist
            self.assertFalse(any(os.path.exists(os.path.join(d, n + ".py")) for n in deploy.MODULES))
            p = subprocess.run([sys.executable, "ARC84BAK.py"], cwd=d, timeout=60,
                               input="pwd\nmkdir x\necho hi > x/f\ncat x/f\nselftest\nexit\n",
                               capture_output=True, text=True,
                               env={"PYTHONPATH": "", "PATH": os.environ.get("PATH", ""),
                                    "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("/home/evo", p.stdout)
            self.assertIn("hi\n", p.stdout)
            self.assertRegex(p.stdout, r"selftest: (\d+)/\1 passed, 0 lowmem, 0 untested")
            self.assertNotIn("FAIL", p.stdout)
            self.assertIn("Reached target Shutdown", p.stdout)
            self.assertEqual(p.stderr, "")

    def test_dry_run_lists_everything(self):
        p = subprocess.run([sys.executable, os.path.join(HERE, "deploy.py"), "--dry-run"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        for n in deploy.MODULES + [deploy.LAUNCHER]:
            self.assertIn(n, p.stdout)
            self.assertIn(deploy.bak_name(n), p.stdout)


if __name__ == "__main__":
    unittest.main()
