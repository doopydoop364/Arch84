# Memory-pressure test of the pager: run with a small-heap MicroPython (not CPython), e.g.
#   MICROPYPATH=.:emu micropython -X heapsize=300k test_vm_pressure.py
import gc
import os
from A84VM import Pager, FileBackend

if not hasattr(gc, "mem_free"):
    print("test_vm_pressure: needs MicroPython (gc.mem_free); skipped")
else:
    be = FileBackend(open, os.remove, page=1024)
    p = Pager(be, page=1024, window=100000)         # no window limit: only memory pressure evicts
    gc.collect()
    before = gc.mem_free()
    npg = before // 1024 + 100                      # more pages than the heap could ever hold
    ids = [0] * npg                                 # the caller's own table, allocated up front
    for i in range(npg):
        k = p.new_page()
        ids[i] = k
        p.write(k, 0, bytes([i % 250 + 1]) * 300)
    assert p.evicts > 0 and len(p.res) < len(ids)
    for i in range(len(ids)):
        assert p.read(ids[i], 0, 300) == bytes([i % 250 + 1]) * 300, i
    n = len(p.res)
    big = p.guard(bytearray, before // 4)           # a request that only fits after eviction
    assert len(big) == before // 4 and len(p.res) < n
    print("test_vm_pressure ok:", len(ids), "pages on", before, "free; evicts", p.evicts)
    for k in ids:
        p.free_page(k)
    for f in os.listdir("."):
        if f.startswith("swap") and f.endswith(".dat"):
            os.remove(f)
