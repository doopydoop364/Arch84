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


st = make_storage()
def rd():
    got = st.read()
    n = 0
    for b in got[1]:
        n += len(b)
    return n
print("stream bytes", phase("storage.read stream", rd))
from A84CZ import decode_stream
def dec():
    got = st.read()
    return decode_stream(got[1])
v = phase("read+decode_stream", dec)
phase("factory_vfs", lambda: __import__("A84CZ").factory_vfs(1))
phase("fix_system_files", lambda: Kernel.fix_system_files(type("K", (), {"vfs": v})()))
