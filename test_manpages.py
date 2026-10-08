"""Every command has a manual page, and the pages describe real commands."""
import unittest

from testutil import *
from A84CD import all_commands
import A84C2, A84C3, A84C4, A84C5, A84C6, A84C7, A84C8, A84C9, A84CA
import A84MN
from A84SH import Shell
from A84KN import Kernel
from A84ST import MemStorage


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


class ManTests(unittest.TestCase):
    def pages(self):
        rows = []
        for chunk in A84MN.PAGES:
            for line in chunk.split("\n"):
                if line:
                    rows.append(line.split("\t"))
        return rows

    def test_every_command_has_a_page_and_every_page_a_command(self):
        names = set(all_commands())
        paged = [r[0] for r in self.pages()]
        self.assertEqual(sorted(set(paged)), sorted(paged), "duplicate pages")
        self.assertEqual(sorted(names - set(paged)), [], "commands without a page")
        self.assertEqual(sorted(set(paged) - names), [], "pages for unknown commands")

    def test_page_shape(self):
        for r in self.pages():
            self.assertEqual(len(r), 3, r)
            self.assertTrue(r[1].split()[0] in (r[0], "[", "pacman") or r[0] in r[1], r)
            self.assertTrue(r[2].strip() != "", r)
            self.assertLessEqual(len(r[2]), 260, r[0])
        # chunks stay small so the module loads on a fragmented heap
        self.assertTrue(all(len(c) < 1100 for c in A84MN.PAGES))

    def test_usage_lines_agree_with_the_commands(self):
        # flags promised by a page must be understood by the command
        sh = Shell(Kernel(MemStorage()), T())
        sh.vfs.write("/home/evo/f", "b\na\n")
        for line in ("ls -a", "ls -l", "mkdir -p d/e", "cp -r d d2", "rm -rf d2", "head -n 1 f", "tail -n 1 f",
                     "sort -r f", "sort -n f", "sort -u f", "wc -l f", "wc -w f", "wc -c f", "grep -i A f",
                     "grep -v a f", "grep -n a f", "grep -c a f", "uniq -c f", "uniq -d f", "tee -a g < f",
                     "du -s", "echo -n hi", "history -c", "sync", "uname -a", "uname -s", "uname -n", "uname -r"):
            t = sh.term
            t.text = ""
            sh.execute(line)
            self.assertNotIn("invalid option", t.text, line)

    def test_man_and_help(self):
        sh = Shell(Kernel(MemStorage()), T())
        sh.execute("man ls")
        self.assertTrue(sh.term.text.startswith("ls - list a directory"))
        sh.term.text = ""
        sh.execute("help cp")
        self.assertIn("usage: cp [-r] SRC... DEST", sh.term.text)
        sh.term.text = ""
        sh.execute("man -k archive")
        self.assertIn("archive - ", sh.term.text)
        self.assertIn("fsck - ", sh.term.text)
        sh.term.text = ""
        sh.execute("man nosuch")
        self.assertIn("no such command", sh.term.text)
        sh.term.text = ""
        sh.execute("man")
        self.assertIn("usage: man", sh.term.text)

    def test_module_is_generated_from_the_text_file(self):
        import subprocess
        import sys
        r = subprocess.run([sys.executable, "tools/genman.py", "--check"])
        self.assertEqual(r.returncode, 0, "A84MN.py is stale: run python3 tools/genman.py")

    def test_man_unloads_itself(self):
        import sys
        sh = Shell(Kernel(MemStorage()), T())
        sh.execute("man ls")
        self.assertNotIn("A84MN", sys.modules)


if __name__ == "__main__":
    unittest.main()
