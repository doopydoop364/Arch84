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
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900, **kw)
    ok = r.returncode == 0
    print("%-34s %s" % (name, "ok" if ok else "FAIL"), flush=True)
    if not ok:
        fails.append(name)
        print((r.stdout + r.stderr)[-600:])
    return r

for t in ("test_arch84", "test_storage", "test_campaign", "test_pipes", "test_editor", "test_pacman", "test_archive", "test_proc", "test_environ", "test_flashrepo", "test_cmds", "test_manpages") + (() if quick else ("test_bigfiles",)):
    sh(t, [sys.executable, t + ".py"])
n = 15 if quick else 60
bad = 0
for s in range(1, n + 1):
    a = subprocess.run([sys.executable, "fuzz_shell.py", str(s), "150"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
    b = subprocess.run([MP, "-X", "heapsize=3000000", "fuzz_shell.py", str(s), "150"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
    if a != b or "reload SAME bad 0" not in a:
        bad += 1
        print("  fuzz_shell seed", s, "differs / bad")
print("%-34s %s" % ("fuzz_shell CPython==MicroPython x%d" % n, "ok" if not bad else "FAIL"))
if bad:
    fails.append("fuzz_shell")
a = subprocess.run([sys.executable, "codec_fuzz.py", "1", "100"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
b = subprocess.run([MP, "-X", "heapsize=3000000", "codec_fuzz.py", "1", "100"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
pa = subprocess.run([sys.executable, "fuzz_pkg.py", "1", "60"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
pb = subprocess.run([MP, "-X", "heapsize=3000000", "fuzz_pkg.py", "1", "60"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
print("%-34s %s" % ("fuzz_pkg CPython==MicroPython", "ok" if pa == pb and "dirty 0" in pa else "FAIL"))
if not (pa == pb and "dirty 0" in pa):
    fails.append("fuzz_pkg")
fa = subprocess.run([sys.executable, "fuzz_archive.py", "1", "40"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
fb = subprocess.run([MP, "-X", "heapsize=3000000", "fuzz_archive.py", "1", "40"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
print("%-34s %s" % ("fuzz_archive CPython==MicroPython", "ok" if fa == fb and "bad 0" in fa else "FAIL"))
if not (fa == fb and "bad 0" in fa):
    fails.append("fuzz_archive")
print("%-34s %s" % ("codec_fuzz identical streams", "ok" if a == b and "bad 0" in a else "FAIL"))
if not (a == b and "bad 0" in a):
    fails.append("codec_fuzz")
sh("keyfuzz", [sys.executable, "emu/keyfuzz.py", "1", "5" if quick else "20", "1500"])
sh("keyfuzz low memory (103 KB heap)", [sys.executable, "emu/keyfuzz.py", "200", "4" if quick else "12", "2500", "--heap=103000"])
sh("cmdfuzz", [sys.executable, "emu/cmdfuzz.py", "1", "3" if quick else "8", "100"])
sh("flash repositories on device", [sys.executable, "emu/flashtest.py"])
sh("editor on emulated device", [sys.executable, "emu/edtest.py"])
sh("archive on emulated device", [sys.executable, "emu/archtest.py"])
sh("powercut (40 files)", [sys.executable, "emu/powercut.py", "40"])
if not quick:
    r = sh("leak check", [sys.executable, "emu/leak.py"])
print("FAILED: " + ", ".join(fails) if fails else "ALL OK")
sys.exit(1 if fails else 0)
