# Driver executed BY MICROPYTHON:
#   micropython -X heapsize=N emu/run.py KEYSFILE LISTSFILE REPORTFILE
# KEYSFILE: key codes, one per line. LISTSFILE: json of stored lists
# (read at start if present, written at exit). REPORTFILE: json report.
import sys
import gc
import json
import micropython
from time import ticks_ms, ticks_diff

sys.path.insert(0, ".")
sys.path.insert(0, "emu")
import ti_system
import ti_draw

kf, lf, rf = sys.argv[1], sys.argv[2], sys.argv[3]
ti_system.KFILE = open(kf)
ti_system.LISTDIR = lf
try:
    import os
    c = os.getenv("A84_CUT")
    if c:
        ti_system.CUT = int(c)
except AttributeError:
    pass
rep = {"imports": []}
gc.collect()
rep["heap_total"] = gc.mem_free() + gc.mem_alloc()
rep["free_start"] = gc.mem_free()
mn = [rep["free_start"], rep["free_start"]]   # [min free before gc, min after gc]
stack = [0]
samples = [0]


def idle():
    samples[0] += 1
    a = gc.mem_free()
    if a < mn[0]:
        mn[0] = a
    gc.collect()
    b = gc.mem_free()
    if b < mn[1]:
        mn[1] = b
    s = micropython.stack_use()
    if s > stack[0]:
        stack[0] = s
    if "boot_free" not in rep:
        rep["boot_free"] = b
        rep["boot_ms"] = ticks_diff(ticks_ms(), t_start)
        rep["boot_stores"] = ti_system.STORES
        rep["boot_recalls"] = ti_system.RECALLS
    rep["last_free"] = b
    if SHOT:
        rep.setdefault("free_log", []).append(b)
    if SHOT:
        rep.setdefault("screens", []).append(screen())
    rep["keys_used"] = ti_system.KPOS


SHOT = len(sys.argv) > 4 and sys.argv[4] == "shots"


def screen():
    ys = sorted(ti_draw.LAST)
    return [ti_draw.LAST[y][1] for y in ys]


ti_system.ON_IDLE = idle
t_start = ticks_ms()
# same order as ARCH84.py, with a heap reading after each
for name in ("A84FS", "A84CZ", "A84ST", "A84KN", "A84CD", "A84CE", "A84UI",
             "A84SH", "A84GX"):
    __import__(name)
    gc.collect()
    rep["imports"].append((name, gc.mem_free()))
rep["free_loaded"] = gc.mem_free()
import A84SH
_orig_run = A84SH.Shell.run
rep["run_entries"] = []


def _run(self):
    gc.collect()
    rep["run_entries"].append(gc.mem_free())
    return _orig_run(self)


A84SH.Shell.run = _run
err = None
try:
    import ARCH84
except BaseException as e:
    err = repr(e)
rep["error"] = err
rep["total_ms"] = ticks_diff(ticks_ms(), t_start)
gc.collect()
rep["end_free"] = gc.mem_free()
if len(sys.argv) > 4 and sys.argv[4] == "meminfo":
    micropython.mem_info()
rep["min_free_nogc"] = mn[0]
rep["min_free_gc"] = mn[1]
rep["stack_peak"] = stack[0]
rep["samples"] = samples[0]
rep["draw_calls"] = ti_draw.CALLS
rep["draw_pixels"] = ti_draw.PIXELS
rep["draw_chars"] = ti_draw.CHARS
rep["screen"] = screen()
rep["stores"] = ti_system.STORES
rep["recalls"] = ti_system.RECALLS
rep["keys_used"] = ti_system.KPOS
f = open(rf, "w")
json.dump(rep, f)
f.close()
