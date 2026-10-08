import sys, gc
sys.path.insert(0, "."); sys.path.insert(0, "emu/mp")
import A84CZ as Z
import lz_proto as P
files = ["A84FS.py", "A84SH.py", "README.md", "ARCH84_DEVLOG.md"]
for hb in (128, 256, 512, 1024):
    P.HB = hb
    tot = [0, 0, 0]
    for fn in files:
        f = open(fn, "rb"); data = f.read(8192); f.close()
        for i in range(0, len(data), 1024):
            d = data[i:i+1024]
            tot[0] += len(d); tot[1] += len(Z.lz_compress(d)); tot[2] += len(P.lz2(d))
    print("HB", hb, "raw", tot[0], "old", tot[1], "new", tot[2])
