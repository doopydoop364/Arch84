# Arch84 0.0.7 launcher. The system is split over small modules so each
# one compiles within the calculator's Python heap:
#   A84FS (paths, VFS)  A84CZ (fs codec, LZSS)  A84ST (list storage)
#   A84PE (parser, editor)  A84KN (kernel)
#   A84UI (text terminals)  A84GX (color terminal)  A84CD (commands)
#   A84SH (shell)
# loaded on first use: A84C2 (phase 5 commands), A84TS (selftest)
#
# Compiling ~a dozen modules takes a while, so the launcher draws first: a few
# raw ti_draw calls (same look as A84GX: 18 px rows, 10 px characters, text at
# row top + 20) show "Arch84 booting" at once and a progress line for every
# module while it loads ("Filesystem (A84FS)": what it is, then its module
# name); the real terminal then replays those lines.
import gc

try:
    import ti_draw as _d
except ImportError:
    _d = None
try:
    from time import ticks_ms as _ms, ticks_diff as _tdiff
except ImportError:
    _ms = None

_SPIN = ("*     ", "**    ", "***   ", " ***  ", "  *** ", "   ***", "    **", "     *")
_lines = []     # finished boot lines (replayed into the real terminal)
_pend = [""]    # the running step, drawn after them
_frame = [0]
_t0 = [0]
_last = [0]    # time of the last frame change
_cur = [""]     # module being loaded


_sh = [[]]       # what each screen row shows now: only rows that changed are redrawn
_col = [None]    # the colour last set (skip redundant set_color calls)


def _setc(c):
    if _col[0] != c:
        _d.set_color(c[0], c[1], c[2])
        _col[0] = c


def _paint():
    if _d is None:
        return
    try:
        # 11 rows: "Arch84 booting", one line per module and the summary fit
        # exactly, so nothing scrolls and a step redraws just 2 rows
        rows = _lines[-11:]
        if _pend[0] != "":
            rows = _lines[-10:] + ["[" + _SPIN[_frame[0]] + "] " + _pend[0]]
        old = _sh[0]
        for i in range(len(rows)):
            t = rows[i]
            if i < len(old) and old[i] == t:
                continue
            y = i * 18
            _setc((0, 0, 0))
            _d.fill_rect(0, y, 320, 18)
            x = 0
            if t[:1] == "[" and t[7:8] == "]":
                inner = t[1:7]
                if "*" in inner or "FAIL" in inner:
                    c = (235, 60, 60)
                elif "OK" in inner:
                    c = (0, 200, 0)
                else:
                    c = (230, 200, 0)
                parts = (("[", (225, 225, 225)), (inner, c), ("]", (225, 225, 225)),
                         (t[8:], (225, 225, 225)))
            else:
                parts = ((t, (225, 225, 225)),)
            for p in parts:
                if p[0] != "":
                    _setc(p[1])
                    _d.draw_text(x, y + 20, p[0])
                    x += 10 * len(p[0])
        for i in range(len(rows), len(old)):
            _setc((0, 0, 0))
            _d.fill_rect(0, i * 18, 320, 18)
        _sh[0] = rows
    except Exception:
        pass        # never let the splash stop the boot


def _step(name):
    # Finish the previous module's line and start "[***   ] Loading name".
    # An import blocks (nothing can redraw while it compiles), so the frame
    # advances by the time that passed since the last one (one per 90 ms, the
    # same speed as the animation in the other boot steps), at least one.
    if _cur[0] != "":
        _lines.append("[  OK  ] " + _cur[0])
    _cur[0] = name
    _pend[0] = name
    n = 1
    if _ms is not None:
        t = _ms()
        n = _tdiff(t, _last[0]) // 90
        if n < 1:
            n = 1
        _last[0] = t
    _frame[0] = (_frame[0] + n) % 8
    _paint()


def _done(line):
    _pend[0] = ""
    _lines.append(line)
    _paint()


if _d is not None:
    try:
        _d.set_color(0, 0, 0)
        _d.fill_rect(0, 0, 320, 240)
        _col[0] = (0, 0, 0)
    except Exception:
        _d = None
_lines.append("Arch84 booting")
_paint()
if _ms is not None:
    _t0[0] = _ms()
    _last[0] = _t0[0]

try:
    _step("Filesystem (A84FS)")
    import A84FS
    _lines[0] = "Arch84 " + A84FS.VERSION + " booting"
    _step("FS compression (A84CZ)")
    import A84CZ
    _step("List storage (A84ST)")
    import A84ST
    _step("Kernel, parser (A84KN)")
    from A84KN import Kernel
    _step("Core commands (A84CD)")
    import A84CD    # biggest compiles: load while little else is resident
    _step("Env commands (A84CE)")
    import A84CE
    _step("Text terminal (A84UI)")
    import A84UI
    _step("Shell, startup (A84SH)")
    from A84SH import Shell
    _step("Color display (A84GX)")
    from A84GX import pick_term
    from A84FS import VERSION
    from A84ST import make_storage
    from A84GX import TI, TD
except Exception as _e:
    _pend[0] = ""
    _done("[FAILED] " + _cur[0])
    _done(str(_e)[:32])
    raise

_note = ""
if _ms is not None:
    _n = _tdiff(_ms(), _t0[0])
    _note = " (" + str(_n // 1000) + "." + str(_n // 100 % 10) + "s)"
if _cur[0] != "":
    _lines.append("[  OK  ] " + _cur[0])
_cur[0] = ""
_done("[  OK  ] Loaded modules" + _note)


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
    first = banner
    if _d is not None:
        # the splash lines are already on screen: carry them into the terminal
        banner = "".join([l + "\n" for l in _lines])
    term = pick_term(TI, TD, banner)
    while boot_once(term):
        scrub()
        term.clear()
        gc.collect()
        term.post(first)


main()
