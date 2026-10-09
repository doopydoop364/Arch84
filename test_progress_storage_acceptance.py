"""Acceptance tests for archive rejection and truncated VFS persistence data.

These tests prove narrowly specified conditions, not streaming installation
memory bounds or full transaction atomicity on the calculator.
"""
import unittest

from A84FS import VFS
from A84PM import MAGIC, Sum, PkgError
from A84PS import scan
from A84CY import fs_stream
from A84CZ import decode_stream


class PackageAcceptance(unittest.TestCase):
    def setUp(self):
        self.vfs = VFS()
        self.vfs.reset_default()
        self.path = "/home/evo/test.ar84"

    def package(self, records):
        checksum = Sum()
        for line in records:
            checksum.add(line + "\n")
        return "\n".join(records + ["END\t1\t" + checksum.hex()]) + "\n"

    def test_truncated_archive_rejected(self):
        self.vfs.write(self.path, MAGIC + "\nname demo\nversion 1\n")
        with self.assertRaises(PkgError):
            scan(self.vfs, self.path)

    def test_checksum_mismatch_rejected(self):
        self.vfs.write(self.path, MAGIC + "\nname demo\nversion 1\nEND\t0\twrong-checksum\n")
        with self.assertRaises(PkgError):
            scan(self.vfs, self.path)

    def test_path_traversal_rejected(self):
        records = [MAGIC, "name demo", "version 1", "D\t/usr/../etc/malicious"]
        self.vfs.write(self.path, self.package(records))
        with self.assertRaises(PkgError):
            scan(self.vfs, self.path)

    def test_valid_package_scans(self):
        records = [MAGIC, "name demo", "version 1", "D\t/usr/demo"]
        self.vfs.write(self.path, self.package(records))
        meta = scan(self.vfs, self.path)
        self.assertEqual(meta["name"], "demo")
        self.assertEqual(meta["dirs"], ["/usr/demo"])


class StorageAcceptance(unittest.TestCase):
    def test_interrupted_serialized_stream_is_rejected(self):
        vfs = VFS()
        vfs.reset_default()
        vfs.write("/home/evo/important", "important text " * 25)
        raw = b"".join(fs_stream(vfs))
        self.assertGreater(len(raw), 10)
        for cut in (0, 1, len(raw) // 2, len(raw) - 1):
            with self.subTest(cut=cut):
                with self.assertRaises(ValueError):
                    decode_stream([raw[:cut]])
        restored = decode_stream([raw])
        self.assertEqual(restored.read("/home/evo/important"), vfs.read("/home/evo/important"))


if __name__ == "__main__":
    unittest.main()
