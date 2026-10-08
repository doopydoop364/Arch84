# Arch84 0.0.7 launcher. The system is split over small modules so each
# one compiles within the calculator's Python heap:
#   A84FS (paths, VFS)  A84CZ (fs codec, LZSS)  A84ST (list storage)
#   A84PE (parser, editor)  A84KN (kernel)
#   A84UI (text terminals)  A84GX (color terminal)  A84CD (commands)
#   A84SH (shell)
# loaded on first use: A84C2 (phase 5 commands), A84TS (selftest)
import gc
import A84FS
import A84CZ
import A84ST
from A84KN import Kernel
import A84CD    # biggest compiles: load while little else is resident
import A84CE
import A84UI
from A84SH import Shell
from A84GX import pick_term
from A84FS import VERSION
from A84ST import make_storage
from A84GX import TI, TD


def boot_once(term):
    # everything the session holds (kernel, filesystem tree, shell) is local
    # to this call, so a reboot really releases it before the next load
    sh = Shell(Kernel(make_storage(), term.post), term)
    sh.run()
    return sh.reboot


def scrub(n=6):
    # The GC is conservative: a stale pointer left in a register or a dead stack
    # slot keeps the finished session (kernel + whole filesystem tree) alive.
    # Running some calls with fresh locals overwrites those slots first.
    a = b = c = d = e = f = g = h = 0
    if n:
        scrub(n - 1)
    return a + b + c + d + e + f + g + h


def main():
    banner = "Arch84 " + VERSION + " booting\n"
    term = pick_term(TI, TD, banner)
    while boot_once(term):
        scrub()
        term.clear()
        gc.collect()
        term.post(banner)


main()
