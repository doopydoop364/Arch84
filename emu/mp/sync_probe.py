# micropython -X heapsize=N emu/mp/sync_probe.py NFILES
# Reproduces "reload then sync" memory behaviour with a traceback for MemoryError.
import sys, gc
sys.path.insert(0, ".")
sys.path.insert(0, "emu")
import ti_system
ti_system.LISTDIR = "/tmp/ld2"
from A84FS import StorageError
from A84ST import make_storage
from A84KN import Kernel
import A84CD, A84CE, A84UI, A84SH
n = int(sys.argv[1])
gc.collect()
print("free at start", gc.mem_free())
k = Kernel(make_storage(), lambda s, p=False: None)
for i in range(n):
    k.vfs.write("/home/evo/f%d" % i, "%d\n" % i)
print('before sync', gc.mem_free())
k.sync()
print('after sync', gc.mem_free())
if len(sys.argv) > 2:
    raise SystemExit
k = None
gc.collect()
print('after free', gc.mem_free())
k = Kernel(make_storage(), lambda s, p=False: None)
print("booted; free", gc.mem_free(), "nodes", k.vfs.count(), k.sync_ok, k.boot_msgs[:2])
k.history.append("ls")
k.save_history()
stats = [0, 0]
k.release_spare()
try:
    w = k.storage.writer()
    from A84CZ import fs_stream
    for fr in fs_stream(k.vfs, stats):
        w.feed(fr)
    print("fed; free", gc.mem_free())
    w.finish()
    print("finished; free", gc.mem_free())
    warns = k.verify(w)
    print("verified; free", gc.mem_free(), warns)
    print(w.commit())
except MemoryError as e:
    sys.print_exception(e)
print("end free", gc.mem_free())
