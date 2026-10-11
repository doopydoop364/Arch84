"""Read-only Arch84 import/boot heap profile for the TI-84 Evo Python app.

Run outside Arch84. No filesystem save, list write, or USB operation occurs.
This program may stop early on low memory; each completed line is useful.
"""
import gc
import sys

MODULES = ("A84FS", "A84CZ", "A84ST", "A84KN", "A84CD", "A84CE",
           "A84UI", "A84SH", "A84GX")


def metric(name):
    fn = getattr(gc, name, None)
    return fn() if callable(fn) else None


def mark(name):
    before = metric("mem_free")
    gc.collect()
    print("EVO_PROFILE " + name + "=" + str(before) + "/" + str(metric("mem_free"))
          + "/" + str(metric("mem_alloc")))


def bounded_block():
    free = metric("mem_free")
    if free is None:
        return "unavailable"
    cap = min(4096, free // 8)
    lo, hi = 0, cap + 1
    while hi - lo > 64:
        mid = (lo + hi) // 2
        try:
            block = bytearray(mid)
            block = None
            lo = mid
        except MemoryError:
            hi = mid
        gc.collect()
    return str(lo) + "/" + str(cap)


def main():
    print("EVO_PROFILE runtime=" + sys.implementation.name)
    mark("start")
    for name in MODULES:
        try:
            __import__(name)
        except (ImportError, MemoryError) as exc:
            print("EVO_PROFILE stopped=" + name + ":" + type(exc).__name__)
            return
        try:
            mark(name)
        except MemoryError:
            print("EVO_PROFILE stopped=" + name + ":MemoryError")
            return
    try:
        from A84KN import Kernel
        from A84ST import make_storage
        from A84SH import Shell
        from A84UI import PlainTerm
        kernel = Kernel(make_storage())
        mark("kernel")
        shell = Shell(kernel, PlainTerm())
        mark("shell")
        shell = None
        kernel = None
        mark("released")
        print("EVO_PROFILE block=" + bounded_block())
    except Exception as exc:
        print("EVO_PROFILE stopped=boot:" + type(exc).__name__)


if __name__ == "__main__" or sys.implementation.name == "tipython":
    main()
