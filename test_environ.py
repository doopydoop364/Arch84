"""/etc/environment: system-wide variables replacing the built-in USER/HOME/PATH/... defaults."""
import unittest

from testutil import *
from A84SH import Shell
from A84KN import Kernel
from A84ST import MemStorage


class T:
    def __init__(self):
        self.text = ""
        self.lines = []

    def write(self, s):
        self.text += s.replace("\x01", "E:")

    def post(self, s, pending=False):
        self.text += s

    def busy(self): pass
    def echo(self, s): pass
    def clear(self): pass
    def close(self): pass
    def safe_key(self, tick=None): return False

    def readline(self, prompt, ed):
        return "exit"


def boot(ms, env_text=None):
    k = Kernel(ms)
    if env_text is not None:
        k.vfs.write("/etc/environment", env_text)
    t = T()
    sh = Shell(k, t)
    sh.startup()
    return sh, t


class EnvironmentTests(unittest.TestCase):
    def r(self, sh, t, line):
        t.text = ""
        sh.execute(line)
        return t.text

    def test_builtin_defaults_without_a_file(self):
        sh, t = boot(MemStorage())
        self.assertFalse(sh.vfs.exists("/etc/environment"))      # not part of the factory tree
        self.assertEqual(self.r(sh, t, "echo $USER $HOME $PATH $SHELL [$HISTSIZE]"),
                         "evo /home/evo /usr/local/bin:/usr/bin:/bin /bin/ash []\n")
        self.assertEqual(sh.k.hist_max(), 40)
        self.assertEqual(self.r(sh, t, "echo $HOME; cat /etc/profile | head -n 1"), "/home/evo\n# /etc/profile\n")

    def test_file_overrides_and_bad_lines_are_ignored(self):
        sh, t = boot(MemStorage(), "# c\nUSER=bob\nPATH=/opt/bin:/bin\n1X=no\nBAD NAME=no\n=no\nnoequals\nFOO = spaced \n")
        self.assertEqual(self.r(sh, t, "echo $USER $PATH $FOO"), "bob /opt/bin:/bin spaced\n")
        self.assertEqual(sh.prompt(), "[bob@arch84 ~]$ ")
        self.assertEqual(self.r(sh, t, "whoami"), "bob\n")
        self.assertEqual(self.r(sh, t, "printenv 1X"), "")

    def test_home_moves_cwd_tilde_and_history(self):
        ms = MemStorage()
        k = Kernel(ms)
        k.vfs.mkdir("/home/bob")
        k.vfs.write("/etc/environment", "HOME=/home/bob\nHISTSIZE=2\n")
        t = T()
        sh = Shell(k, t)
        sh.run()
        self.assertEqual(sh.cwd, "/home/bob")
        self.assertEqual(self.r(sh, t, "echo ~"), "/home/bob\n")
        self.assertEqual(sh.prompt(), "[evo@arch84 ~]$ ")
        for c in ("echo 1", "echo 2", "echo 3"):
            k.add_history(c)
        self.assertEqual(k.history, ["echo 2", "echo 3"])
        k.save_history()
        self.assertTrue(k.vfs.isfile("/home/bob/.ash_history"))

    def test_histsize_bad_values_fall_back(self):
        k = Kernel(MemStorage())
        for v in ("x", "0", "9999", "-3", ""):
            k.env["HISTSIZE"] = v
            self.assertEqual(k.hist_max(), 40)
        k.env["HISTSIZE"] = "7"
        self.assertEqual(k.hist_max(), 7)

    def test_histfile(self):
        k = Kernel(MemStorage())
        k.env["HISTFILE"] = "/tmp/h"
        k.add_history("echo x")
        k.save_history()
        self.assertEqual(k.vfs.read("/tmp/h"), "echo x\n")

    def test_missing_file_keeps_defaults(self):
        sh, t = boot(MemStorage())
        sh.k.env["USER"] = "zed"
        sh.startup()
        self.assertEqual(sh.k.env["USER"], "zed")

    def test_legacy_profile_exports_do_not_override_the_file(self):
        sh, t = boot(MemStorage(), "PATH=/opt/bin\nSHELL=/bin/sh\n")
        sh.startup()
        self.assertEqual(self.r(sh, t, "echo $PATH $SHELL"), "/opt/bin /bin/sh\n")
        sh.vfs.write("/etc/profile", "export PATH=/usr/local/bin:/usr/bin:/bin\nexport PATH=/mine\n")
        sh.startup()
        self.assertEqual(self.r(sh, t, "echo $PATH"), "/mine\n")        # other exports still apply

    def test_setenv_unsetenv_persist(self):
        ms = MemStorage()
        sh, t = boot(ms)
        self.assertEqual(self.r(sh, t, "setenv USER=bob FOO=a=b"), "")
        self.assertEqual(self.r(sh, t, "printenv USER FOO"), "bob\na=b\n")
        data = sh.vfs.read("/etc/environment")
        self.assertIn("USER=bob\n", data)
        self.assertIn("FOO=a=b\n", data)
        self.r(sh, t, "unsetenv FOO")
        self.assertNotIn("FOO", sh.vfs.read("/etc/environment"))
        self.assertEqual(self.r(sh, t, "printenv FOO; echo $?"), "1\n")
        sh.execute("sync")
        sh2, t2 = boot(ms)
        self.assertEqual(self.r(sh2, t2, "echo $USER"), "bob\n")

    def test_setenv_rejects_bad_input(self):
        sh, t = boot(MemStorage())
        before = sh.vfs.exists("/etc/environment")
        for line in ("setenv", "setenv 1A=x", "setenv A-B=x", "setenv NOEQ", "setenv HOME=rel", "unsetenv 1A", "unsetenv"):
            self.assertIn("E:", self.r(sh, t, line), line)
        self.assertEqual(sh.vfs.exists("/etc/environment"), before)

    def test_unset_is_session_only(self):
        sh, t = boot(MemStorage())
        self.r(sh, t, "setenv USER=bob")
        self.r(sh, t, "unset USER")
        self.assertEqual(self.r(sh, t, "echo [$USER]"), "[]\n")
        self.assertIn("USER=bob", sh.vfs.read("/etc/environment"))

    def test_pacman_protects_the_configured_home(self):
        sh, t = boot(MemStorage())
        sh.k.env["HOME"] = "/home/bob"
        self.r(sh, t, "pacman -Q")
        import A84PM
        self.assertFalse(A84PM.ok_path("/home/bob/.profile"))
        self.assertFalse(A84PM.ok_path("/home/evo/.profile"))
        self.assertTrue(A84PM.ok_path("/home/bob/data"))
        A84PM.HOMEDIR[0] = "/home/evo"


if __name__ == "__main__":
    unittest.main()
