import unittest

from A84FS import VFS, VFSError


class TransactionTests(unittest.TestCase):
    def test_rollback_restores_replace_rename_delete_and_directories(self):
        v = VFS()
        v.reset_default()
        v.write("/home/evo/old", "old" * 500)
        v.write("/home/evo/gone", "keep")
        v.dirty = False
        tx = v.begin_transaction()
        v.write("/home/evo/old", "replacement")
        v.rename("/home/evo/old", "/home/evo/new")
        v.remove("/home/evo/gone")
        v.mkdir("/home/evo/dir")
        v.write("/home/evo/dir/file", "temporary")
        tx.rollback()
        self.assertEqual(v.read("/home/evo/old"), "old" * 500)
        self.assertEqual(v.read("/home/evo/gone"), "keep")
        self.assertFalse(v.exists("/home/evo/new"))
        self.assertFalse(v.exists("/home/evo/dir"))
        self.assertFalse(v.dirty)

    def test_commit_and_bounds(self):
        v = VFS()
        v.reset_default()
        tx = v.begin_transaction(limit=1)
        with self.assertRaises(VFSError):
            v.begin_transaction()
        v.write("/home/evo/a", "a")
        with self.assertRaises(VFSError):
            v.write("/home/evo/b", "b")
        tx.rollback()
        self.assertFalse(v.exists("/home/evo/a"))
        tx = v.begin_transaction()
        v.write("/home/evo/a", "a")
        tx.commit()
        self.assertEqual(v.read("/home/evo/a"), "a")


if __name__ == "__main__":
    unittest.main()
