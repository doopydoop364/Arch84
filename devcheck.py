# Send as A84CHK (python3 evo_usb.py devcheck.py A84CHK). One-off diagnostic for
# storage v2; deploy.py does not send it. Writes only to scratch lists ZTM/T0xxx
# and READS the real save (A84/S0xxx) without ever syncing.
import gc
try:
    from time import ticks_ms, ticks_diff
except ImportError:
    from time import time as _tm
    def ticks_ms(): return int(_tm() * 1000)
    def ticks_diff(a, b): return a - b
import ti_system as ti
from A84KN import Kernel
from A84ST import make_storage
from A84CZ import fs_measure
from A84TX import CHECKS, real_scratch_check


def heap():
    gc.collect()
    if hasattr(gc, "mem_free"):
        return gc.mem_free()
    return 0


print("heap", heap())
for label, fn in CHECKS:
    t0 = ticks_ms()
    try:
        r = "ok  " if fn() else "FAIL"
    except Exception as e:
        r = "EXC " + repr(e)[:18]
    print(r, label[:17], ticks_diff(ticks_ms(), t0), "ms")
print("heap", heap())
input("enter=next")
t0 = ticks_ms()
try:
    r = real_scratch_check(ti)
    print("real lists", r, ticks_diff(ticks_ms(), t0), "ms")
except Exception as e:
    print("real lists EXC", repr(e)[:40])
print("-- dry boot of real save")
k = Kernel(make_storage(), lambda s, p=False: p or print(s.rstrip()))
print("nodes", k.vfs.count(), "ok", k.sync_ok, "dirty", k.vfs.dirty)
t0 = ticks_ms()
raw, stored = fs_measure(k.vfs)
print("v2 would be", raw, "->", stored, "B", ticks_diff(ticks_ms(), t0), "ms")
print("heap", heap(), "(nothing synced)")
