"""ti_system shim for the MicroPython emulation harness (emu/).

Models what ARCH84_DEVLOG.md says was probed on the real calculator:
get_key(1) blocks and returns a key code, get_key(0) returns 0 when idle,
store_list is limited to 100 elements, plain ints >= 2**29 sometimes come
back exactly 1 low (deterministic ~0.1%), half values are exact.
The key queue is scripted; when it runs dry get_key(1) raises EOFError (the
shell treats that as `exit`). Not the real firmware.
"""
KFILE = None        # file of key codes, one per line (streamed: costs no heap)
KPOS = 0
LISTS = {}
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


def store_list(name, data):
    global STORES
    if len(data) > 100:
        raise ValueError("List length > 100.")
    out = []
    for x in data:
        if isinstance(x, float) and x != int(x):
            out.append(x)
        else:
            v = int(x)
            if v >= 2 ** 29 and FLAKY and (v * 2654435761) % 997 == 0:
                v -= 1
            out.append(v)
    STORES += 1
    LISTS[name] = out


def recall_list(name):
    global RECALLS
    if name not in LISTS:
        raise NameError(name)
    RECALLS += 1
    return list(LISTS[name])


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
