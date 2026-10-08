# micropython -X heapsize=N emu/mp/phase_probe.py NFILES
# Bytes allocated (GC off, so churn counts) in each phase of a load+edit+sync.
import sys, gc
sys.path.insert(0, "."); sys.path.insert(0, "emu")
import ti_system
ti_system.LISTDIR = "/tmp/ld3"
import os
try:
    os.mkdir("/tmp/ld3")
except OSError:
    pass
for f in os.listdir("/tmp/ld3"):
    os.remove("/tmp/ld3/" + f)
from A84ST import make_storage
from A84KN import Kernel
from A84CZ import fs_stream
import A84CD, A84CE, A84UI, A84SH
n = int(sys.argv[1])
k = Kernel(make_storage(), lambda s, p=False: None)
for i in range(n):
    k.vfs.write("/home/evo/f%d" % i, "%d\n" % i)
k.sync()
k = None
gc.collect()

def phase(name, f):
    gc.collect()
    gc.disable()
    a = gc.mem_alloc()
    try:
        r = f()
    finally:
        d = gc.mem_alloc() - a
        gc.enable()
    print("%-22s alloc %6d B" % (name, d))
    return r

box = {}
phase("boot(load)", lambda: box.__setitem__("k", Kernel(make_storage(), lambda s, p=False: None)))
k = box["k"]
print("live after load: %d" % (gc.mem_alloc() - 0), "nodes", k.vfs.count())
k.history.append("ls")
phase("save_history", lambda: k.save_history())
phase("release_spare", lambda: k.release_spare())
box["w"] = None
phase("writer()", lambda: box.__setitem__("w", k.storage.writer()))
w = box["w"]
def feedall():
    st = [0, 0]
    for fr in fs_stream(k.vfs, st):
        w.feed(fr)
phase("fs_stream+feed", feedall)
phase("finish", lambda: w.finish())
phase("verify(decode+cmp)", lambda: k.verify(w))
phase("commit", lambda: w.commit())
