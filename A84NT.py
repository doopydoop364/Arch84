# A84NT: the network library (Arch84 module, lazily loaded). The calculator has no network; a
# program on the computer (tools/a84bridge.py) does the work. See docs/NETWORK.md.
#
# Why not lists: any variable transfer over USB closes the running Python app (measured), so the
# channels are the two that do not interrupt it:
#   calculator -> PC   the request is DRAWN on screen as rows of characters (ALPHA, 5 bits each);
#                      the bridge reads them from screenshots.
#   PC -> calculator   the answer is TYPED: the bridge injects key presses; 32 harmless keys
#                      carry 5 bits each (measured: 300 of 300 keys, in order, 40-70 keys/s).
# Both directions carry the same frame: A8 type seq(3) len(2) payload checksum(4), as symbols.
# A DATA frame holds one chunk of the answer (LZSS-compressed when that is smaller) and a
# FIN frame (total chunks, round number) ends the answer; the calculator draws a STATUS frame
# (chunks it has, done flag, the same round number) and the bridge resends from the first missing one.
from A84FS import ms_since, now_ms
from A84ST import adler

ALPHA = "0123456789ABCDEFGHJKLMNPQRSTUVWX"
# positional get_key code of each symbol: no Enter, CLEAR (cancel), 2nd, alpha, mode, del, and not
# key 32 (scancode 0x28), the one key nothing in Arch84 reacts to: the bridge's keepalive press
KEYS = (34, 24, 26, 25, 95, 85, 75, 65, 55, 104, 94, 84, 74, 64, 54, 44,
        103, 93, 83, 73, 63, 53, 43, 33, 102, 92, 82, 72, 62, 52, 42, 91)
CANCEL = 45
MAGIC = 0xA8
T_REQ = 1
T_STATUS = 2
T_DATA = 3
T_FIN = 4
SYNC = (31, 0, 31, 0, 31, 0, 31, 0)
ROWS = 10               # frame rows on screen (row 0 is a banner)
COLS = 30               # symbols per row: columns 1..30 (the edge cells of the screen draw differently)
MAXFRAME = ROWS * COLS * 5 // 8      # bytes that fit
MAXPAYLOAD = MAXFRAME - 11
MAXCHUNK = 600          # longest payload the calculator accepts in a frame from the bridge
MAXSYM = ((MAXCHUNK + 11) * 8 + 4) // 5 + 8      # symbols of the longest frame we accept
OP_PING = 1
OP_TIME = 2
OP_GET = 3
OP_ECHO = 4
OP_STAT = 5
STATUS = ("ok", "bad request", "denied", "fetch failed", "http error", "too big", "unknown operation")


class NetError(Exception):
    pass


class NoNet(NetError):
    pass                    # this terminal cannot show frames: there is no network here


def to_symbols(data):
    out = []
    acc = 0
    nb = 0
    for b in data:
        acc = (acc << 8) | b
        nb += 8
        while nb >= 5:
            nb -= 5
            out.append((acc >> nb) & 31)
        acc &= (1 << nb) - 1
    if nb:
        out.append((acc << (5 - nb)) & 31)
    return out


def from_symbols(syms):
    out = bytearray()
    acc = 0
    nb = 0
    for s in syms:
        acc = (acc << 5) | s
        nb += 5
        if nb >= 8:
            nb -= 8
            out.append((acc >> nb) & 255)
            acc &= (1 << nb) - 1
    return bytes(out)


def checksum(data):
    a, b = adler(1, 0, data)
    return bytes((b >> 8, b & 255, a >> 8, a & 255))


def build(ftype, seq, payload):
    n = len(payload)
    head = bytes((MAGIC, ftype, (seq >> 16) & 255, (seq >> 8) & 255, seq & 255, n >> 8, n & 255))
    body = head + payload
    return body + checksum(body)


def parse(data):
    # -> (type, seq, payload) or None when the frame is damaged
    if len(data) < 11 or data[0] != MAGIC:
        return None
    n = (data[5] << 8) | data[6]
    if len(data) < 11 + n:
        return None
    body = data[:7 + n]
    if checksum(body) != data[7 + n:11 + n]:
        return None
    return data[1], (data[2] << 16) | (data[3] << 8) | data[4], data[7:7 + n]


def frame_symbols(ftype, seq, payload):
    return to_symbols(build(ftype, seq, payload))


def frame_rows(frame):
    # the frame as ROWS rows of COLS characters ("." pads the end)
    s = to_symbols(frame)
    txt = "".join([ALPHA[v] for v in s])
    txt = txt + "." * (ROWS * COLS - len(txt))
    return [" " + txt[i * COLS:(i + 1) * COLS] for i in range(ROWS)]


def new_seq(salt=0):
    t = now_ms()
    if t is None:
        t = 0
    return (t // 3 + salt * 7919) % 16000000 + 1


_n = [0]


def utf8_split(data):
    # (complete, rest): rest is the start of a character that is not all here yet
    n = len(data)
    i = n - 1
    k = 0
    while i >= 0 and k < 4:
        b = data[i]
        if b & 0xC0 != 0x80:
            need = 1
            if b >= 0xF0:
                need = 4
            elif b >= 0xE0:
                need = 3
            elif b >= 0xC0:
                need = 2
            if n - i < need:
                return data[:i], data[i:]
            break
        i -= 1
        k += 1
    return data, b""


def show(sh, ftype, seq, payload, banner):
    term = sh.term
    if not hasattr(term, "show_rows"):
        raise NoNet("the network needs the color terminal")
    term.show_rows([banner] + frame_rows(build(ftype, seq, payload)))


def resync(buf, n):
    # a damaged frame: look inside the n symbols it swallowed for the start of the next one
    # -> index of the first symbol after a SYNC, or -1
    for i in range(n - 7):
        j = 0
        while j < 8 and buf[i + j] == SYNC[j]:
            j += 1
        if j == 8:
            return i + 8
    return -1


def wait_for_answer(sh, seq, sink, banner, wait, idle):
    # Reads the key presses of the answer; calls sink(chunk bytes) for each chunk in order. Returns
    # when the FIN frame arrives and every chunk is in. The request frame is on screen.
    # The loop below allocates nothing per key (a garbage collection pause would miss presses).
    import gc
    term = sh.term
    getkey = term.ti.get_key
    sym = {}
    for i in range(32):
        sym[KEYS[i]] = i
    fb = bytearray(MAXSYM)      # symbols of the frame being received
    n = -1                      # symbols in fb, -1: not inside a frame
    pos = 0                     # SYNC symbols matched so far
    need = 0
    expect = 0
    last = 0
    gc.collect()
    t_key = now_ms()            # the last symbol key: silence for `idle` (or `wait` before the first key) is an error
    heard = False
    spin = 0
    while True:
        k = getkey(0)
        if k == 0:
            last = 0
            spin += 1
            if spin >= 40:
                spin = 0
                d = ms_since(t_key)
                if d is not None and d > (idle if heard else wait) * 1000:
                    raise NetError("the answer stalled" if heard else
                                   "no answer from the bridge: is arch84-bridge running on the computer?")
                if n >= 0 and ms_since(t_key) > 1500:
                    n = -1                  # a frame that stopped half way: wait for the next one
                    pos = 0
            continue
        if k == last:
            continue
        last = k
        if k == CANCEL:
            raise NetError("cancelled")
        s = sym.get(k)
        if s is None:
            continue
        t_key = now_ms()
        heard = True
        if n < 0:
            if s == SYNC[pos]:
                pos += 1
                if pos == 8:
                    n = 0
                    need = 0
                    pos = 0
            else:
                pos = 1 if s == 31 else 0
            continue
        fb[n] = s
        n += 1
        while n >= 0:
            if need == 0:
                if n < 12:
                    break
                hdr = from_symbols(fb[:12])
                ln = (hdr[5] << 8) | hdr[6]
                if hdr[0] != MAGIC or ln > MAXCHUNK:
                    n, need = reframe(fb, n)
                    continue
                need = ((11 + ln) * 8 + 4) // 5
            if n < need:
                break
            fr = parse(from_symbols(fb[:need]))
            if fr is None:
                n, need = reframe(fb, n)
                continue
            left = n - need                 # symbols of the next frame that arrived behind this one
            if left > 0:
                tail = bytes(fb[need:n])
                fb[0:left] = tail
            n = -1
            pos = 0
            need = 0
            if fr[1] == seq:
                ft = fr[0]
                p = fr[2]
                if ft == T_DATA and len(p) >= 5 and ((p[0] << 8) | p[1]) == expect:
                    raw = None
                    if p[2] == 1:
                        from A84CZ import lz_decompress
                        try:
                            raw = lz_decompress(p, (p[3] << 8) | p[4], 5)
                        except ValueError:
                            raw = None
                    else:
                        raw = p[5:]
                    if raw is not None:
                        sink(raw)
                        expect += 1
                elif ft == T_FIN and len(p) >= 3:
                    total = (p[0] << 8) | p[1]
                    done = expect >= total
                    show(sh, T_STATUS, seq, bytes((expect >> 8, expect & 255, 1 if done else 0, p[2])), banner)
                    if done:
                        term.end_frame()
                        return
            if left > 0:                    # the next frame may already have started behind this one
                j = resync(fb, left)
                if j >= 0:
                    rest = left - j
                    fb[0:rest] = bytes(fb[j:left])
                    n = rest
                    need = 0


def reframe(fb, n):
    # a damaged frame: continue with whatever the next SYNC inside it starts -> (n, need)
    j = resync(fb, n)
    if j < 0:
        return -1, 0
    rest = n - j
    fb[0:rest] = bytes(fb[j:n])
    return rest, 0


def receive(sh, seq, sink, banner, wait=40.0, idle=20.0):
    try:
        wait_for_answer(sh, seq, sink, banner, wait, idle)
    except BaseException:
        sh.term.end_frame()         # whatever went wrong (timeout, CLEAR, memory), give the screen back:
        raise                       # the bridge sees it and stops typing


def request(sh, op, args, sink, wait=40.0, idle=20.0, label="network"):
    # sends one request and streams the answer through sink(bytes)
    if len(args) + 1 > MAXPAYLOAD:
        raise NetError("request too long")
    _n[0] += 1
    seq = new_seq(_n[0])
    banner = "NET " + label[:18] + " CLEAR=quit"
    show(sh, T_REQ, seq, bytes((op,)) + args, banner)
    receive(sh, seq, sink, banner, wait, idle)


def call(sh, op, args=b"", wait=40.0):
    # small answers: -> (status, data bytes)
    out = bytearray()
    request(sh, op, args, out.extend, wait, label="request")
    if len(out) == 0:
        raise NetError("empty answer")
    return out[0], bytes(out[1:])


def explain(status, data):
    s = STATUS[status] if status < len(STATUS) else "error " + str(status)
    try:
        d = data.decode()
    except (ValueError, UnicodeError):
        d = ""
    if d != "":
        s += ": " + d
    return s


def fetch_text(sh, url, sink, limit=300000, label="download", wait=40.0):
    # downloads url, calling sink(text) for each piece; -> characters received
    state = [None, b"", 0]      # status, carry, total

    def on_chunk(raw):
        if state[0] is None:
            state[0] = raw[0]
            raw = raw[1:]
            if state[0] != 0:
                state[1] = bytes(raw)
                return
        elif state[0] != 0:
            state[1] = state[1] + bytes(raw)
            return
        data = state[1] + bytes(raw)
        state[2] += len(raw)
        if state[2] > limit:
            raise NetError("too big (limit " + str(limit) + " bytes)")
        done, rest = utf8_split(data)
        state[1] = rest
        if len(done):
            try:
                sink(done.decode())
            except (ValueError, UnicodeError):
                raise NetError("not text (binary data)")
    request(sh, OP_GET, url.encode(), on_chunk, wait, label=label)
    if state[0] is None:
        raise NetError("empty answer")
    if state[0] != 0:
        raise NetError(explain(state[0], state[1]))
    if state[1]:
        raise NetError("not text (cut-off character)")
    return state[2]


def fetch_file(sh, url, path, limit=300000, label="download", wait=40.0):
    # downloads url into the file `path` (replaced); -> bytes
    from A84FS import VFSError
    sh.vfs.write(path, "")

    def sink(text):
        sh.vfs.append(path, text)
    try:
        return fetch_text(sh, url, sink, limit, label, wait)
    except (NetError, VFSError, MemoryError):
        try:
            sh.vfs.remove(path)
        except VFSError:
            pass
        raise
