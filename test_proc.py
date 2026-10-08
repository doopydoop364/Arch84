"""Generated /proc and /dev files."""
import unittest

from testutil import *
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


def mk(ms=None):
    t = T()
    return Shell(Kernel(ms or MemStorage()), t), t


def run(sh, t, line):
    t.text = ""
    sh.execute(line)
    return t.text


class ProcTests(unittest.TestCase):
    def setUp(self):
        self.ms = MemStorage()
        self.sh, self.t = mk(self.ms)

    def r(self, line):
        return run(self.sh, self.t, line)

    def test_listing_and_reading(self):
        self.assertEqual(self.r("ls /proc"), "meminfo  modules  mounts  uptime  version\n")
        self.assertIn("Arch84 0.0.7", self.r("cat /proc/version"))
        self.assertIn("rootfs / vfs rw", self.r("cat /proc/mounts"))
        self.assertIn("A84KN", self.r("cat /proc/modules"))
        self.assertEqual(self.r("ls -a /dev"), "null\n")
        self.assertEqual(self.r("ls /"), "bin/  boot/  dev/  etc/  home/  proc/  root/  run/  tmp/  usr/  var/\n")

    def test_commands_work_on_generated_files(self):
        self.assertEqual(self.r("grep -c Arch84 /proc/version"), "1\n")
        self.assertEqual(self.r("cat /proc/version | wc -l").strip(), "1")
        self.r("cp /proc/version /tmp/v")
        self.assertEqual(self.sh.vfs.read("/tmp/v"), self.sh.vfs.read("/proc/version"))
        self.assertIn("/proc/uptime", self.r("find /proc -type f"))
        self.assertIn("/proc", self.r("find / -name proc"))
        self.assertEqual(self.r("cat /proc"), "E:cat: /proc: Is a directory\n")
        self.assertIn("No such file", self.r("cat /proc/nothere"))

    def test_read_only(self):
        for line in ("echo x > /proc/new", "touch /proc/version", "rm /proc/version", "mkdir /proc/x",
                     "mv /proc/version /tmp/q", "cp /etc/hostname /proc/h", "echo x >> /proc/uptime",
                     "mkdir /dev/x", "touch /dev/zero", "echo x > /dev/tty"):
            self.assertIn("Read-only file system", self.r(line), line)
        self.assertEqual(self.sh.vfs.listdir("/proc"), ["meminfo", "modules", "mounts", "uptime", "version"])

    def test_dev_null(self):
        self.assertEqual(self.r("echo hi > /dev/null"), "")
        self.assertEqual(self.r("echo hi >> /dev/null"), "")
        self.assertEqual(self.r("cat /dev/null"), "")
        self.assertEqual(self.r("cat /etc/hostname > /dev/null; echo done"), "done\n")
        self.assertEqual(self.sh.status, 0)
        self.assertEqual(self.sh.vfs.size("/dev/null"), 0)

    def test_nothing_is_stored(self):
        self.r("cat /proc/version > /dev/null")
        self.r("cp /proc/uptime /tmp/u")
        self.sh.k.sync()
        tree = walk(Kernel(self.ms).vfs)
        self.assertEqual([p for p in tree if p.startswith("/proc/") or p.startswith("/dev/")], [])
        self.assertIsNone(tree["/proc"])
        self.assertIsNone(tree["/dev"])

    def test_without_a_provider_the_dirs_are_empty(self):
        v = VFS()
        v.reset_default()
        self.assertEqual(v.listdir("/proc"), [])
        self.assertIsNone(v.get("/proc/version"))

    def test_uptime_and_meminfo_have_the_expected_shape(self):
        up = self.r("cat /proc/uptime").split()
        self.assertEqual(len(up), 2)
        float(up[0])
        mem = self.r("cat /proc/meminfo")
        self.assertTrue(mem.startswith("MemTotal:") or mem == "unavailable\n")

    def test_installed_packages_cannot_target_them(self):
        from A84PM import ok_path
        self.assertFalse(ok_path("/proc/x"))
        self.assertFalse(ok_path("/dev/null"))


if __name__ == "__main__":
    unittest.main()
