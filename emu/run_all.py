#!/usr/bin/env python3
"""One-shot validation: desktop unit tests, CPython-vs-MicroPython differential
fuzz, codec fuzz, key fuzz, power-cut sweep, leak check. Exit 1 on any failure.
   python3 emu/run_all.py [--quick]"""
import os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MP = os.environ.get("A84_MICROPYTHON") or "/tmp/a84-micropython"
quick = "--quick" in sys.argv
fails = []

def sh(name, cmd, **kw):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, **kw)
    ok = r.returncode == 0
    print("%-34s %s" % (name, "ok" if ok else "FAIL"), flush=True)
    if not ok:
        fails.append(name)
        print((r.stdout + r.stderr)[-600:])
    return r

for t in ("test_arch84", "test_storage", "test_campaign", "test_pipes") + (() if quick else ("test_bigfiles",)):
    sh(t, [sys.executable, t + ".py"])
n = 15 if quick else 60
bad = 0
for s in range(1, n + 1):
    a = subprocess.run([sys.executable, "fuzz_shell.py", str(s), "150"], cwd=ROOT, capture_output=True, text=True).stdout
    b = subprocess.run([MP, "-X", "heapsize=3000000", "fuzz_shell.py", str(s), "150"], cwd=ROOT, capture_output=True, text=True).stdout
    if a != b or "reload SAME bad 0" not in a:
        bad += 1
        print("  fuzz_shell seed", s, "differs / bad")
print("%-34s %s" % ("fuzz_shell CPython==MicroPython x%d" % n, "ok" if not bad else "FAIL"))
if bad:
    fails.append("fuzz_shell")
a = subprocess.run([sys.executable, "codec_fuzz.py", "1", "100"], cwd=ROOT, capture_output=True, text=True).stdout
b = subprocess.run([MP, "-X", "heapsize=3000000", "codec_fuzz.py", "1", "100"], cwd=ROOT, capture_output=True, text=True).stdout
print("%-34s %s" % ("codec_fuzz identical streams", "ok" if a == b and "bad 0" in a else "FAIL"))
if not (a == b and "bad 0" in a):
    fails.append("codec_fuzz")
sh("keyfuzz", [sys.executable, "emu/keyfuzz.py", "1", "5" if quick else "20", "1500"])
sh("powercut (40 files)", [sys.executable, "emu/powercut.py", "40"])
if not quick:
    r = sh("leak check", [sys.executable, "emu/leak.py"])
print("FAILED: " + ", ".join(fails) if fails else "ALL OK")
sys.exit(1 if fails else 0)
