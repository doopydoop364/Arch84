# Arch84 0.0.6-dev launcher. The system is split over small modules so each
# one compiles within the calculator's Python heap:
#   A84FS (paths, VFS)  A84CZ (fs codec, LZSS)  A84ST (list storage)
#   A84PE (parser, editor)  A84KN (kernel)
#   A84UI (text terminals)  A84GX (color terminal)  A84CD (commands)
#   A84SH (shell)
# loaded on first use: A84C2 (phase 5 commands), A84TS (selftest)
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


def main():
    banner = "Arch84 " + VERSION + " booting\n"
    term = pick_term(TI, TD, banner)
    while True:
        kernel = Kernel(make_storage(), term.post)
        sh = Shell(kernel, term)
        sh.run()
        if not sh.reboot:
            break
        term.clear()
        term.post(banner)


main()
