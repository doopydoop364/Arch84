"""ti_system shim for the MicroPython emulation harness (emu/).

Models what ARCH84_DEVLOG.md says was probed on the real calculator:
get_key(1) blocks and returns a key code, get_key(0) returns 0 when idle,
store_list is limited to 100 elements, plain ints >= 2**29 sometimes come
back exactly 1 low (deterministic ~0.1%), half values are exact.
The key queue is scripted; when it runs dry get_key(1) raises EOFError (the
shell treats that as `exit`). Not the real firmware.
"""
import os
KFILE = None        # file of key codes, one per line (streamed: costs no heap)
KPOS = 0
STORES = 0
RECALLS = 0
FLAKY = True
ON_IDLE = None      # called with no args each time the shell waits for a key


def get_key(mode=None):
    global KPOS
    if mode is None:
        raise TypeError("function takes 1 positional argument but 0 were given")
    if mode == 0:
        return 0
    if ON_IDLE is not None:
        ON_IDLE()
    ln = KFILE.readline()
    if ln == "":
        raise EOFError()
    KPOS += 1
    return int(ln)


getKey = get_key


FAIL = None         # store_list raises (calculator out of list memory) at this store count
CUT = None          # power cut: SystemExit when this many stores have happened
LISTDIR = None      # lists live in files, NOT on the MicroPython heap: on the
                    # device they are calculator (list) memory, not Python heap
import struct
_BUF = bytearray(1 + 100 + 800)   # n, n flag bytes (1 = int), n doubles
_MV = memoryview(_BUF)


def store_list(name, data):
    global STORES
    n = len(data)
    if n > 100:
        raise ValueError("List length > 100.")
    if CUT is not None and STORES >= CUT:
        raise SystemExit
    if FAIL is not None and STORES == FAIL:
        raise MemoryError("ERR:MEMORY")
    _BUF[0] = n
    i = 0
    for x in data:
        if isinstance(x, float) and x != int(x):
            _BUF[1 + i] = 0
            struct.pack_into("<d", _BUF, 101 + 8 * i, x)
        else:
            v = int(x)
            if v >= 2 ** 29 and FLAKY and (v * 2654435761) % 997 == 0:
                v -= 1
            _BUF[1 + i] = 1
            struct.pack_into("<d", _BUF, 101 + 8 * i, float(v))
        i += 1
    f = open(LISTDIR + "/" + name, "wb")
    f.write(_MV[:101 + 8 * n])
    f.close()
    STORES += 1


def recall_list(name):
    global RECALLS
    # os.stat first: a failed open() leaves an object whose finalizer closes fd 0
    # in the MicroPython 1.20 unix port, which breaks later opens
    try:
        os.stat(LISTDIR + "/" + name)
    except OSError:
        raise NameError(name)
    f = open(LISTDIR + "/" + name, "rb")
    f.readinto(_BUF)
    f.close()
    n = _BUF[0]
    out = []
    for i in range(n):
        x = struct.unpack_from("<d", _BUF, 101 + 8 * i)[0]
        out.append(int(x) if _BUF[1 + i] else x)
    RECALLS += 1
    return out


ROWS = {}


def disp_clr():
    ROWS.clear()


def disp_at(row, text, align):
    if not 1 <= row <= 11:
        raise ValueError("Invalid row")
    if align not in ("left", "center", "right"):
        raise ValueError("Invalid alignment")
    ROWS[row] = text[:31]


def disp_cursor(*a):
    pass


def disp_wait():
    pass


def escape():
    return False


def sleep(*a):
    pass


def wait(*a):
    pass


def wait_key():
    return get_key(1)


def recall_RegEQ(*a):
    return None
