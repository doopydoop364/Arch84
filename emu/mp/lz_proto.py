import gc, sys
from time import ticks_ms, ticks_diff
sys.path.insert(0, "."); sys.path.insert(0, "emu/mp")
import A84CZ as Z
from bench_lz import sample

HB = int(sys.argv[1]) if len(sys.argv) > 1 else 512

def lz2(d):
    n = len(d)
    out = bytearray(n + (n >> 3) + 2)
    tab = bytearray(HB * 2)   # pos+1 as 2 bytes; 0 = empty
    mask = HB - 1
    o = 0
    i = 0
    pos = 0
    ctl = 0
    nbit = 0
    while i < n:
        if nbit == 0:
            pos = o
            o += 1
            ctl = 0
        ln = 0
        if i + 2 < n:
            h = ((d[i] * 5 + d[i + 1] * 31 + d[i + 2] * 131) & mask) * 2
            j = (tab[h] | (tab[h + 1] << 8)) - 1
            if j >= 0 and i - j <= 4096 and d[j] == d[i] and d[j + 1] == d[i + 1] and d[j + 2] == d[i + 2]:
                ln = 3
                while ln < 18 and i + ln < n and d[j + ln] == d[i + ln]:
                    ln += 1
        if ln:
            v = i - j - 1
            out[o] = v & 255
            out[o + 1] = ((v >> 8) << 4) | (ln - 3)
            o += 2
            step = ln
        else:
            ctl |= 1 << nbit
            out[o] = d[i]
            o += 1
            step = 1
        p = i
        e = i + step
        if e > n - 2:
            e = n - 2
        while p < e:
            h = ((d[p] * 5 + d[p + 1] * 31 + d[p + 2] * 131) & mask) * 2
            tab[h] = (p + 1) & 255
            tab[h + 1] = (p + 1) >> 8
            p += 1
        i += step
        nbit += 1
        if nbit == 8:
            out[pos] = ctl
            nbit = 0
    if nbit:
        out[pos] = ctl
    return bytes(memoryview(out)[:o])

if __name__ == "__main__":
    for kind in ("text", "rand", "zero"):
        d = sample(kind, 1024)
        for name, f in (("old", Z.lz_compress), ("new", lz2)):
            gc.collect(); gc.disable()
            a = gc.mem_alloc(); t = ticks_ms()
            for _ in range(10):
                c = f(d)
            dt = ticks_diff(ticks_ms(), t)
            used = gc.mem_alloc() - a
            gc.enable(); gc.collect()
            assert Z.lz_decompress(c, 1024) == d
            print(kind, name, len(c), "alloc/10runs", used, "ms", dt / 10)
