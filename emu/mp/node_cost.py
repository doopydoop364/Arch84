import sys, gc
sys.path.insert(0, ".")
from A84FS import VFS, Node
v = VFS(); v.reset_default()
gc.collect(); a = gc.mem_alloc()
for i in range(100):
    v.write("/home/evo/f%d" % i, "%d\n" % i)
gc.collect()
print("100 small files:", gc.mem_alloc() - a, "B ->", (gc.mem_alloc() - a) // 100, "per file")
a = gc.mem_alloc()
for i in range(100):
    v.mkdir("/tmp/d%d" % i)
gc.collect()
print("100 dirs:", (gc.mem_alloc() - a) // 100, "per dir")
n = Node(False, "x")
print(type(n.__dict__) if hasattr(n, "__dict__") else "no __dict__")
