# micropython emu/mp/bench_lz.py  -- LZSS cost on typical frames
import gc, sys
from time import ticks_ms, ticks_diff
sys.path.insert(0, ".")
import A84CZ as Z

def sample(kind, n):
    if kind == "text":
        w = ["echo", "hello", "world", "cat", "/etc/profile", "ls -a", "the", "quick", "brown", "fox\n"]
        s = ""
        i = 7
        while len(s) < n:
            i = (i * 1103515245 + 12345) & 0x7fffffff
            s += w[(i >> 8) % len(w)] + " "
        return s[:n].encode()
    if kind == "rand":
        i = 1; b = bytearray()
        for _ in range(n):
            i = (i * 1103515245 + 12345) & 0x7fffffff
            b.append((i >> 16) & 255)
        return bytes(b)
    if kind == "zero":
        return bytes(n)
def main():
  pass
for kind in ("text", "rand", "zero") if __name__ == "__main__" else ():
    d = sample(kind, 1024)
    gc.collect()
    gc.disable()
    a = gc.mem_alloc()
    t = ticks_ms()
    for _ in range(10):
        c = Z.lz_compress(d)
    dt = ticks_diff(ticks_ms(), t)
    used = gc.mem_alloc() - a
    gc.enable()
    gc.collect()
    print(kind, "1024 ->", len(c), "alloc over 10 runs", used, "ms/run(host)", dt / 10)
    assert Z.lz_decompress(c, 1024) == d
