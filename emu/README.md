# emu/ - MicroPython emulation harness (NOT the calculator)

Runs the real Arch84 sources under a **32-bit MicroPython 1.20 unix port** with a
device-sized heap (`-X heapsize=127800`) and shims for `ti_system` / `ti_draw`
(scripted keys, 100-element lists, flaky big ints, draw-call counters).

Fidelity: same bytecode VM, GC, 32-bit object sizes and compile-time memory
behaviour as MicroPython; calibrated so free heap after boot (~49 KB) matches
the device figure in ARCH84_DEVLOG.md (~48.5-50 KB). NOT modelled: the eZ80/ARM
CPU, real clock speed (host timings are relative only), firmware heap
fragmentation, real `ti_system`. Timings from this harness are host timings.

Build (needs gcc-multilib): fetch micropython-1.20.0, then in ports/unix:
`make CWARN="-Wall -Wno-error" MICROPY_FORCE_32BIT=1 MICROPY_NLR_SETJMP=1 MICROPY_PY_FFI=0 MICROPY_PY_BTREE=0 MICROPY_SSL_AXTLS=0 MICROPY_SSL_MBEDTLS=0 MICROPY_PY_USSL=0`
then `export A84_MICROPYTHON=<path>/build-standard/micropython`.
