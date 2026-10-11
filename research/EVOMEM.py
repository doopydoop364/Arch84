"""Standalone, bounded TI-84 Evo Python heap probe.

Run as a Python program, outside Arch84. Output lines begin EVO_MEM so they
can be copied into tools/evo_research.py parse. No calculator data is written.
The allocation result is a lower bound within MAX_PROBE, not total RAM.
"""
import gc
import sys

MAX_PROBE = 8192
CHURN_COUNT = 12
CHURN_BYTES = 128


def metric(name):
    fn = getattr(gc, name, None)
    if fn is None:
        return None
    try:
        return fn()
    except Exception:
        return None


def collect():
    fn = getattr(gc, "collect", None)
    if fn is not None:
        fn()


def free():
    return metric("mem_free")


def delta(factory):
    collect()
    before = free()
    try:
        obj = factory()
        after = free()
        obj = None
    except MemoryError:
        collect()
        return "allocation_failed"
    collect()
    restored = free()
    if before is None or after is None or restored is None:
        return "unavailable"
    return str(before - after) + ",restored=" + str(restored - before)


def alloc_ok(n):
    try:
        obj = bytearray(n)
        obj = None
        collect()
        return True
    except MemoryError:
        collect()
        return False


def allocation_bound(initial_free, cap=MAX_PROBE):
    # Never ask for more than one eighth of the reported free heap.
    if initial_free is None:
        return 0, 0, False
    cap = min(cap, max(0, initial_free // 8))
    cap = max(0, cap)
    if cap == 0:
        return 0, 0, False
    if alloc_ok(cap):
        return cap, cap, True
    lo = 0
    hi = cap
    while hi - lo > 64:
        mid = (lo + hi) // 2
        if alloc_ok(mid):
            lo = mid
        else:
            hi = mid
    return lo, cap, False


def churn():
    collect()
    before = free()
    try:
        blocks = [bytearray(CHURN_BYTES) for _ in range(CHURN_COUNT)]
        during = free()
        blocks = None
    except MemoryError:
        blocks = None
        during = None
    collect()
    after = free()
    if before is None or during is None or after is None:
        return "unavailable"
    return str(before - during) + ",restored=" + str(after - before)


def probe():
    rows = []
    def add(k, v):
        rows.append((k, str(v)))

    add("runtime", getattr(sys.implementation, "name", "unknown"))
    add("gc_mem_free_api", int(callable(getattr(gc, "mem_free", None))))
    add("gc_mem_alloc_api", int(callable(getattr(gc, "mem_alloc", None))))
    add("gc_collect_api", int(callable(getattr(gc, "collect", None))))
    add("sys_getsizeof_api", int(callable(getattr(sys, "getsizeof", None))))
    try:
        import micropython
        add("micropython_mem_info_api",
            int(callable(getattr(micropython, "mem_info", None))))
    except ImportError:
        add("micropython_mem_info_api", 0)
    add("free_before_gc", metric("mem_free"))
    collect()
    f = free()
    add("free_after_gc", f)
    add("alloc_after_gc", metric("mem_alloc"))
    add("bytearray_256_delta", delta(lambda: bytearray(256)))
    add("list_32_delta", delta(lambda: list(range(32))))
    add("dict_16_delta", delta(lambda: dict((i, i) for i in range(16))))
    add("vfs_nodes_8_delta", delta(lambda: [("f" + str(i), "", 0) for i in range(8)]))
    add("churn_12x128_delta", churn())
    collect()
    available = free()
    if available is None:
        lo = cap = "unavailable"
        capped = False
    else:
        lo, cap, capped = allocation_bound(available)
    add("single_object_lower_bound", lo)
    add("single_object_probe_cap", cap)
    add("single_object_cap_reached", int(capped))
    add("free_final", free())
    # Fits a 32-column screen: free / allocatable lower bound / probe cap.
    add("sum", str(f) + "/" + str(lo) + "/" + str(cap))
    return rows


def main():
    for key, value in probe():
        print("EVO_MEM " + key + "=" + value)


if __name__ == "__main__" or sys.implementation.name == "tipython":
    main()
