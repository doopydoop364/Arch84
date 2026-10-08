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


from A84CZ import fs_stream, factory_vfs
st2 = [0, 0]
frames = []
def gen():
    for fr in fs_stream(k.vfs, st2):
        frames.append(fr)
box = {}
k = Kernel(make_storage(), lambda s, p=False: None)
k.release_spare()
phase("fs_stream only", gen)
print("frames", len(frames), [len(f) for f in frames], "raw/stored", st2)
phase("factory_vfs", lambda: factory_vfs(1))
w = k.storage.writer()
phase("writer.feed frames", lambda: [w.feed(f) for f in frames])
phase("writer.finish", lambda: w.finish())
from A84CZ import make_frame, lz_compress
raw = bytes(range(97, 123)) * 30
phase("lz_compress 780B", lambda: lz_compress(raw))
