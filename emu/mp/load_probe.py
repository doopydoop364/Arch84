# micropython -X heapsize=N emu/mp/load_probe.py  (after sync_probe left lists in /tmp/ld2)
import sys, gc
sys.path.insert(0, "."); sys.path.insert(0, "emu")
import ti_system
ti_system.LISTDIR = "/tmp/ld2"
from A84ST import make_storage
from A84CZ import _decode as decode_stream
import A84KN, A84CD, A84CE, A84UI, A84SH
gc.collect()
print("free", gc.mem_free())
st = make_storage()
spare = bytearray(3072)
try:
    got = st.read()
    vfs = decode_stream(got[1])
    a=gc.mem_free(); gc.collect(); print("loaded", vfs.count(), "free", a, "after gc", gc.mem_free(), "live delta", 65072-gc.mem_free())
except Exception as e:
    sys.print_exception(e)
