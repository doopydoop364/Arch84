# micropython -X heapsize=N emu/mp/time_probe.py NFILES  -- HOST ms (relative only)
import sys, gc, os
from time import ticks_ms, ticks_diff
sys.path.insert(0, "."); sys.path.insert(0, "emu")
import ti_system
ti_system.LISTDIR = "/tmp/ld5"
try: os.mkdir("/tmp/ld5")
except OSError: pass
for f in os.listdir("/tmp/ld5"): os.remove("/tmp/ld5/" + f)
from A84ST import make_storage
from A84KN import Kernel
from A84CZ import lz_compress, lz_decompress
import A84CD, A84CE, A84UI, A84SH
n = int(sys.argv[1])
k = Kernel(make_storage(), lambda s, p=False: None)
for i in range(n):
    k.vfs.write("/home/evo/f%d" % i, "file %d with some text to compress compress compress\n" % i)
def t(label, f, reps=10):
    gc.collect(); t0 = ticks_ms()
    for _ in range(reps): r = f()
    print("%-18s %7.1f ms" % (label, ticks_diff(ticks_ms(), t0) / reps))
    return r
k.vfs.dirty = True
t("sync", lambda: k.sync())
t("boot(load)", lambda: Kernel(make_storage(), lambda s, p=False: None))
raw = (b"the quick brown fox jumps over the lazy dog\n" * 24)[:1024]
c = t("lz_compress 1KB", lambda: lz_compress(raw), 30)
t("lz_decompress 1KB", lambda: lz_decompress(c, len(raw)), 30)
