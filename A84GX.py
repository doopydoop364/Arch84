# A84GX: color terminal on ti_draw (Arch84 module 6/10)
# Measured on a TI-84 Evo (OS 7.0): canvas 320x210 below the status bar,
# monospace font 10 px wide, rows 18 px apart -> 32 columns; 11 rows used.
# draw_text's y is NOT the baseline: the glyph spans about y-18 .. y-7, so a
# glyph sits 2 px below its row top Y when y = Y + 20; descenders end ~Y+17.
# fill_rect(x, y, w, h), draw_text(x, y_baseline, text), set_color(r, g, b);
# draw calls show immediately (paint_buffer/show_draw are not usable).
from A84FS import ERR
from A84UI import PlainTerm, TiTerm

try:
    import ti_system as TI
except ImportError:
    TI = None
try:
    import ti_draw as TD
except ImportError:
    TD = None

GX_COLS = 32
GX_ROWS = 11      # 9 log/input rows + hint row + mode indicator row
TEXT_DY = 20
CW = 10
CH = 18     # row pitch; descenders (p y g j q) reach ~Y+17, so rows clear 18 px
CURH = 16   # cursor block height (glyph box without the descender)
# w white, g green, r red, y yellow, b blue, d dim gray, c = cursor cell
COL = {"w": (225, 225, 225), "g": (0, 200, 0), "r": (235, 60, 60),
       "y": (230, 200, 0), "b": (90, 150, 255), "d": (125, 125, 125)}
TAGS = {"[  OK  ]": "g", "[FAILED]": "r", "[ WARN ]": "y",
        "[ FIX  ]": "y"}


def mode_segs(mod, up):
    # our own 2nd/alpha indicator (the OS one is hidden by the drawn screen)
    out = []
    if mod == "2nd":
        out.append(("2ND", "b"))
    elif mod == "alpha":
        out.append(("ALPHA", "y"))
    elif mod == "lock":
        out.append(("A-LOCK", "g"))
    if up:
        if out:
            out.append((" ", "w"))
        out.append(("UPPER", "y"))
    return out


def line_segs(line):
    # one scrollback/prompt line -> [(text, color)]
    if line[:1] == ERR:
        return [(line[1:], "r")]
    inner = line[1:7]
    if line[:1] == "[" and line[7:8] == "]" and "*" in inner and inner.strip(" *") == "":
        return [("[", "w"), (inner, "r"), ("]", "w"), (line[8:], "w")]
    for tag in TAGS:
        if line.startswith(tag):
            return [("[", "w"), (tag[1:-1], TAGS[tag]), ("]", "w"),
                    (line[len(tag):], "w")]
    if line[:1] == "[" and "@" in line:
        i = line.find("]$")
        j = line.find(" ")
        if 0 < j < i:
            return [("[", "w"), (line[1:j], "g"), (line[j:i], "b"),
                    (line[i:], "w")]
    return [(line, "w")]


def wrap_segs(segs, cols):
    rows = [[]]
    n = 0
    for text, c in segs:
        while text != "":
            part = text[:cols - n]
            rows[-1].append((part, c))
            n += len(part)
            text = text[len(part):]
            if n >= cols:
                rows.append([])
                n = 0
    if len(rows) > 1 and rows[-1] == []:
        rows.pop()
    return rows


class GfxTerm(TiTerm):
    def __init__(self, ti, td):
        TiTerm.__init__(self, ti)
        self.td = td
        self.rows = GX_ROWS
        self.cols = GX_COLS

    def reset(self):
        self.td.set_color(0, 0, 0)
        self.td.fill_rect(0, 0, 320, 240)
        self.prev = []

    def close(self):
        self.ti.disp_clr()
        for line in self.lines[-(self.rows - 1):]:
            print(line.replace(ERR, ""))

    def paint(self, rows):
        td = self.td
        for i in range(self.rows):
            r = rows[i]
            if i < len(self.prev) and self.prev[i] == r:
                continue
            y = i * CH
            td.set_color(0, 0, 0)
            td.fill_rect(0, y, 320, CH)
            x = 0
            for text, c in r:
                if text == "":
                    continue
                if c == "c":
                    td.set_color(225, 225, 225)
                    td.fill_rect(x, y, CW * len(text), CURH)
                    td.set_color(0, 0, 0)
                else:
                    rgb = COL[c]
                    td.set_color(rgb[0], rgb[1], rgb[2])
                td.draw_text(x, y + TEXT_DY, text)
                x += CW * len(text)
        self.prev = rows

    def draw(self, prompt, ed):
        buf = ed.buf
        pos = ed.pos
        cur = " "
        if pos < len(buf):
            cur = buf[pos]
        segs = line_segs(prompt)
        segs.append((buf[:pos], "w"))
        segs.append((cur, "c"))
        segs.append((buf[pos + 1:], "w"))
        hint = ed.hint
        if pos == len(buf):
            s = ed.suggest()
            if s is not None:
                segs.append((s[len(buf):], "d"))
                hint = ""
        inrows = wrap_segs(segs, self.cols)
        area = self.rows - 2          # last two rows: hint, mode indicator
        maxin = area - 1
        if len(inrows) > maxin:
            crow = (len(prompt) + pos) // self.cols
            end = max(crow + 1, maxin)
            inrows = inrows[end - maxin:end]
        out = [line_segs(l) for l in self.shown(area - len(inrows))]
        out.extend(inrows)
        while len(out) < area:
            out.append([])
        out.append([(hint[:self.cols - 1], "d")])
        out.append(mode_segs(self.mod, self.up))
        self.paint(out)

    def busy(self):
        # a command is running: submitted line stays, cursor on a new line
        ls = self.lines[-(self.rows - 2):]
        out = [line_segs(l) for l in ls]
        out.append([(" ", "c")])
        while len(out) < self.rows:
            out.append([])
        self.paint(out)

    def post(self, text, pending=False):
        if pending:
            ls = self.lines[-(self.rows - 1):] + [text.rstrip("\n")[:self.cols]]
        else:
            self.write(text)
            ls = self.lines[-self.rows:]
        out = [line_segs(l) for l in ls]
        while len(out) < self.rows:
            out.append([])
        self.paint(out)


def pick_term(ti, td, banner):
    # best terminal that survives its first draw: color, text console, plain
    tries = []
    if ti is not None and td is not None and hasattr(td, "draw_text") \
            and hasattr(td, "fill_rect") and hasattr(td, "set_color") \
            and hasattr(ti, "get_key"):
        tries.append(lambda: GfxTerm(ti, td))
    if ti is not None and hasattr(ti, "get_key") and hasattr(ti, "disp_at") \
            and hasattr(ti, "disp_clr"):
        tries.append(lambda: TiTerm(ti))
    for mk in tries:
        try:
            t = mk()
            t.reset()
            t.post(banner)
            return t
        except Exception as e:
            print("terminal failed:", repr(e))
    t = PlainTerm()
    t.post(banner)
    return t
