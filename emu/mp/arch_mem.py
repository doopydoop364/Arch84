import sys, gc, os
sys.path.insert(0, "."); sys.path.insert(0, "emu")
import ti_system
ti_system.LISTDIR = "/tmp/ld6"
try: os.mkdir("/tmp/ld6")
except OSError: pass
for f in os.listdir("/tmp/ld6"): os.remove("/tmp/ld6/" + f)
from A84ST import make_storage
from A84KN import Kernel
import A84CD, A84CE, A84UI, A84SH
class T:
    def write(self, s): pass
    def post(self, s, p=False): pass
    def busy(self): pass
    def clear(self): pass
k = Kernel(make_storage(), lambda s, p=False: None)
sh = A84SH.Shell(k, T())
def used():
    gc.collect(); return gc.mem_alloc()
u0 = used()
for i in range(6):
    sh.execute("echo " + "x" * 90 + " > f%d" % i)
    sh.execute("cat f%d f%d > t" % (i, i)); sh.execute("cat t t > f%d" % i); sh.execute("cat f%d f%d > t" % (i, i)); sh.execute("cat t t > f%d" % i)
sh.execute("rm t")
u1 = used()
print("3 files:", u1 - u0)
sh.execute("archive create big f0 f1 f2 f3 f4 f5")
u2 = used()
print("after archive create (modules unloaded):", u2 - u1, "vs files", u1 - u0, "mods:", [m for m in sys.modules if m in ("A84AX", "A84AR")])
import micropython
for i in range(3):
    gc.collect()
print("again:", used() - u1)

def scrub(n=6):
    a = b = c = d = e = f = g = h = 0
    if n:
        scrub(n - 1)
    return a + b + c + d
scrub()
print("after scrub:", used() - u1)
print("files left:", sh.vfs.listdir("/home/evo"))
