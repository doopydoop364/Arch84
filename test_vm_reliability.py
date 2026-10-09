import unittest

import A84VM
from A84VM import ListBackend, MemBackend, Pager


class PagerReliabilityTests(unittest.TestCase):
    def test_pinned_page_survives_eviction_and_nested_pin(self):
        p = Pager(MemBackend(), page=16, window=2)
        a = p.new_page()
        p.write(a, 0, b"keep")
        p.pin_page(a)
        p.pin_page(a)
        b = p.new_page()
        p.write(b, 0, b"drop")
        p.new_page()
        self.assertIn(a, p.res)
        self.assertNotIn(b, p.res)
        with self.assertRaises(ValueError):
            p.free_page(a)
        p.unpin_page(a)
        self.assertIn(a, p.pins)
        p.unpin_page(a)
        self.assertNotIn(a, p.pins)
        self.assertEqual(p.read(a, 0, 4), b"keep")

    def test_all_pinned_window_fails_without_exceeding_limit(self):
        p = Pager(MemBackend(), page=16, window=1)
        a = p.new_page()
        p.pin_page(a)
        with self.assertRaises(MemoryError):
            p.new_page()
        self.assertEqual(p.stats()["resident"], 1)
        self.assertEqual(p.stats()["pages"], 1)

    def test_recovery_callbacks_are_bounded(self):
        events = []
        p = Pager(MemBackend(), page=16, window=1,
                  release=lambda: events.append("cache"),
                  unload=lambda: events.append("modules"))
        calls = [0]

        def always_fails():
            calls[0] += 1
            raise MemoryError("injected")

        with self.assertRaises(MemoryError):
            p.guard(always_fails)
        self.assertEqual(events, ["cache", "modules"])
        self.assertEqual(calls[0], 3)

    def test_make_room_rejects_recursive_callback(self):
        calls = []
        p = Pager(MemBackend(), page=16, window=1, low=16)
        p.release = lambda: calls.append(p.make_room(100))
        real = A84VM.free_heap
        A84VM.free_heap = lambda: 0
        try:
            self.assertFalse(p.make_room(100))
        finally:
            A84VM.free_heap = real
        self.assertEqual(calls, [False])

    def test_failed_list_write_keeps_dirty_resident_and_old_slot(self):
        store = {}
        fail = [False]

        def put(name, values):
            if fail[0]:
                raise MemoryError("injected list failure")
            store[name] = list(values)

        be = ListBackend(put, lambda name: store[name], page=16, maxid=3)
        p = Pager(be, page=16, window=1)
        a = p.new_page()
        p.write(a, 0, b"old")
        p.flush()
        old = p.loc[a]
        p.write(a, 0, b"new")
        fail[0] = True
        with self.assertRaises(MemoryError):
            p.flush()
        self.assertEqual(p.loc[a], old)
        self.assertEqual(p.read(a, 0, 3), b"new")
        self.assertEqual(p.stats()["dirty"], 1)
        fail[0] = False
        p.flush()
        self.assertEqual(p.read(a, 0, 3), b"new")
        self.assertNotEqual(p.loc[a], old)

    def test_foreign_list_is_skipped_and_exhaustion_is_controlled(self):
        store = {"V0000": [123.5]}
        be = ListBackend(lambda name, values: store.__setitem__(name, values),
                         lambda name: store[name], page=16, maxid=1)
        p = Pager(be, page=16, window=1)
        a = p.new_page()
        p.write(a, 0, b"data")
        p.flush()
        self.assertEqual(store["V0000"], [123.5])
        self.assertEqual(p.loc[a], 1)
        p.write(a, 0, b"more")
        with self.assertRaises(MemoryError):
            p.flush()
        self.assertEqual(p.read(a, 0, 4), b"more")
        self.assertEqual(p.stats()["dirty"], 1)

    def test_partial_multilist_write_does_not_consume_slot(self):
        store = {}
        fail = [True]

        def put(name, values):
            if fail[0] and name == "V0001" and len(values) > 1:
                raise MemoryError("second chunk failed")
            store[name] = list(values)

        be = ListBackend(put, lambda name: store[name], page=600, maxid=1)
        data = bytearray(b"x" * 600)
        with self.assertRaises(MemoryError):
            be.put(data, -1)
        self.assertEqual(store["V0000"], [be.HEAD + 0.5])
        fail[0] = False
        loc = be.put(data, -1)
        self.assertEqual(loc, 0)
        out = bytearray(600)
        be.get(loc, out)
        self.assertEqual(out, data)


if __name__ == "__main__":
    unittest.main()
