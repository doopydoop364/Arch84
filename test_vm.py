import os, random, sys, tempfile
sys.path.insert(0, ".")
from A84VM import Pager, MemBackend, FileBackend

def run(be, name):
    p = Pager(be, page=256, window=4)
    ids = [p.new_page() for _ in range(40)]
    ref = {}
    r = random.Random(1)
    for i in range(3000):
        pid = r.choice(ids); off = r.randrange(0, 200); d = bytes(r.randrange(256) for _ in range(r.randrange(1, 50)))
        if r.random() < .5:
            p.write(pid, off, d)
            m = ref.setdefault(pid, bytearray(256)); m[off:off+len(d)] = d
        else:
            assert p.read(pid, off, len(d)) == bytes(ref.get(pid, bytearray(256))[off:off+len(d)]), (name, i)
        assert len(p.res) <= 4
    p.flush()
    for pid in ids[:20]: p.free_page(pid)
    print(name, "ok faults", p.faults, "evicts", p.evicts, "reads", be.reads, "writes", be.writes)

run(MemBackend(), "mem")
d = tempfile.mkdtemp(); os.chdir(d)
fb = FileBackend(open, os.remove, page=256, seg=2048)
run(fb, "file")
fb.close()
print("segments left", sorted(os.listdir(".")), "live", fb.live)
assert sum(os.path.getsize(f) for f in os.listdir(".")) <= 40 * 256

