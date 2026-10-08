# Arch84 0.0.6-dev launcher. The system is split over small modules so each
# one compiles within the calculator's Python heap:
#   A84FS (paths, VFS)  A84CZ (fs codec, LZSS)  A84ST (list storage)
#   A84PE (parser, editor)  A84KN (kernel)
#   A84UI (text terminals)  A84GX (color terminal)  A84CD (commands)
#   A84SH (shell)
# loaded on first use: A84C2 (phase 5 commands), A84TS (selftest)
from A84FS import *
from A84CZ import *
from A84ST import *
from A84KN import *
import A84CD    # biggest compiles: load while little else is resident
import A84CE
from A84UI import *
from A84SH import *
from A84GX import *      # after the shell: its compile peak needs the room


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
