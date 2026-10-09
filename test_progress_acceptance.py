"""Narrow CI acceptance checks for A84VM; not device-level proof."""
import unittest
from A84VM import Pager, MemBackend


class FailingBackend(MemBackend):
    def __init__(self):
        super().__init__()
        self.fail = True

    def put(self, data, old):
        if self.fail:
            raise OSError("simulated storage failure")
        return super().put(data, old)


class VirtualMemoryAcceptance(unittest.TestCase):
    def test_bounded_resident_pages_and_reload(self):
        pager = Pager(MemBackend(), page=128, window=2, low=0)
        pages = []
        for number in range(12):
            pid = pager.new_page()
            pager.write(pid, 0, bytes((number + 1,)) * 128)
            pages.append(pid)
            self.assertLessEqual(len(pager.res), 2)
        self.assertGreater(pager.evicts, 0)
        for number, pid in enumerate(pages):
            self.assertEqual(pager.read(pid, 0, 128), bytes((number + 1,)) * 128)
            self.assertLessEqual(len(pager.res), 2)

    def test_dirty_eviction_write_failure_retains_page(self):
        backend = FailingBackend()
        pager = Pager(backend, page=64, window=1, low=0)
        first = pager.new_page()
        data = b"data that must not disappear"
        pager.write(first, 0, data)
        with self.assertRaises(OSError):
            pager.evict()
        self.assertIn(first, pager.res)
        self.assertTrue(pager.use[first] & 1)
        self.assertEqual(pager.read(first, 0, len(data)), data)
        backend.fail = False
        self.assertTrue(pager.evict())
        self.assertEqual(pager.read(first, 0, len(data)), data)


if __name__ == "__main__":
    unittest.main()
