# A84GX: color terminal on ti_draw (Arch84 module 6/10)
# Measured on a TI-84 Evo (OS 7.0): canvas 320x210 below the status bar,
# monospace font 10 px wide, rows 18 px apart -> 32 columns; 11 rows used.
# draw_text's y is NOT the baseline: the glyph spans about y-18 .. y-7, so a
# glyph sits 2 px below its row top Y when y = Y + 20; descenders end ~Y+17.
# fill_rect(x, y, w, h), draw_text(x, y_baseline, text), set_color(r, g, b);
# draw calls show immediately (paint_buffer/show_draw are not usable).
from A84FS import BLK, CLR, ERR
from A84UI import PlainTerm, TiTerm, strip

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
       "y": (230, 200, 0), "b": (90, 150, 255), "d": (125, 125, 125),
       "m": (200, 80, 220), "n": (0, 190, 200)}      # m magenta, n cyan
# the palette neofetch shows (the colours this terminal really draws with, in this order)
PALETTE = "rgybmnw"
# a segment whose colour is "#x" is a solid block of colour x (text: spaces)
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


def block_runs(text, c):
    # text with BLK cells -> [(text, colour)]: each run of BLK cells becomes a solid block
    # ("#c" colour, spaces), the rest keeps colour c
    out = []
    i = 0
    while i < len(text):
        j = i
        blk = text[i] == BLK
        while j < len(text) and (text[j] == BLK) == blk:
            j += 1
        if blk:
            out.append((" " * (j - i), "#" + c))
        else:
            out.append((text[i:j], c))
        i = j
    return out


def line_segs(line):
    # one scrollback/prompt line -> [(text, color)]
    if line[:1] == ERR:
        return [(line[1:], "r")]
    if CLR in line:
        parts = line.split(CLR)
        segs = []
        if parts[0] != "":
            segs.append((parts[0], "w"))
        for p in parts[1:]:
            c = p[:1]
            if c not in COL:
                c = "w"
            if BLK in p:
                segs.extend(block_runs(p[1:], c))
            elif p[1:] != "":
                segs.append((p[1:], c))
        return segs
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


POST_STEP = 5   # boot view: when full, scroll this many lines at once (not one by one)


def rlen(r):
    n = 0
    for t, c in r:
        n += len(t)
    return n


class GfxTerm(TiTerm):
    # Every ti_draw call costs real time on the calculator, so painting is
    # frugal: unchanged rows are skipped; a row that only changed a few cells
    # (the spinner, "[***   ]" -> "[  OK  ]") redraws just those cells, so
    # nothing flickers; a full row costs one erase plus ONE draw_text per
    # colour (the font is monospace, other colours' cells are spaces); a row
    # that was blank (or never drawn after reset) is not erased at all.
    def __init__(self, ti, td):
        TiTerm.__init__(self, ti)
        self.td = td
        self.rows = GX_ROWS
        self.cols = GX_COLS
        self.col = None     # colour last set
        self.vis = None     # boot view: how many of the newest lines are on screen
        self.stale = False  # the display refused something: next paint starts from a clean screen

    def reset(self):
        self.td.set_color(0, 0, 0)
        self.td.fill_rect(0, 0, 320, 240)
        self.col = (0, 0, 0)
        self.prev = []
        self.vis = None
        self.stale = False

    def clear(self):
        TiTerm.clear(self)
        self.vis = None

    def close(self):
        self.ti.disp_clr()
        for line in self.lines[-(self.rows - 1):]:
            print(strip(line))

    def show_rows(self, rows):
        # a full-screen text frame (the network request, see A84NT): row 0 is a banner in green,
        # the others are white text the PC reads from a screenshot. Call end_frame() when done.
        td = self.td
        self.reset()
        self.setc(COL["g"])
        td.draw_text(0, TEXT_DY, rows[0])
        self.setc(COL["w"])
        for i in range(1, len(rows)):
            td.draw_text(0, i * CH + TEXT_DY, rows[i])
        self.stale = True

    def end_frame(self):
        # give the screen back to the terminal: the next paint starts from a clean screen
        self.stale = True
        self.prev = []

    def palette(self):
        # the colours this terminal can really draw (neofetch shows them as blocks)
        return PALETTE

    def setc(self, c):
        if self.col != c:
            self.td.set_color(c[0], c[1], c[2])
            self.col = c

    def fill(self, x, y, w, h):
        # ti_draw raises "Width cannot be negative" for an empty rectangle (a blank
        # row has nothing to erase), so never ask for one
        if w <= 0 or h <= 0:
            return
        self.setc((0, 0, 0))
        self.td.fill_rect(x, y, w, h)

    def draw_row(self, y, r):
        td = self.td
        groups = {}
        order = []
        k = 0
        for text, c in r:
            n = len(text)
            if n == 0:
                continue
            key = c
            if c[0] == "#":
                self.setc(COL[c[1]])
                td.fill_rect(k * CW, y, CW * n, CURH)
                k += n
                continue
            if c == "c":
                self.setc((225, 225, 225))
                td.fill_rect(k * CW, y, CW * n, CURH)
                key = "k"           # black text on the cursor block
            g = groups.get(key)
            if g is None:
                g = [k, ""]
                groups[key] = g
                order.append(key)
            g[1] = g[1] + " " * (k - g[0] - len(g[1])) + text
            k += n
        for key in order:
            g = groups[key]
            if key == "k":
                self.setc((0, 0, 0))
            else:
                self.setc(COL[key])
            td.draw_text(g[0] * CW, y + TEXT_DY, g[1])

    def cells(self, y, old, r):
        # same layout, some cells differ: redraw only those cells. False if the
        # layout changed (different segments/lengths) or a cursor is involved.
        if len(old) != len(r):
            return False
        for j in range(len(r)):
            if len(old[j][0]) != len(r[j][0]) or old[j][1] == "c" or r[j][1] == "c" \
                    or old[j][1][0] == "#" or r[j][1][0] == "#":
                return False
        px = 0
        for j in range(len(r)):
            ot = old[j][0]
            oc = old[j][1]
            nt = r[j][0]
            nc = r[j][1]
            n = len(nt)
            if oc != nc:
                self.fill(px, y, n * CW, CH)
                if nt.strip() != "":
                    self.setc(COL[nc])
                    self.td.draw_text(px, y + TEXT_DY, nt)
            elif ot != nt:
                i = 0
                while i < n:
                    if ot[i] == nt[i]:
                        i += 1
                        continue
                    e = i
                    while e < n and ot[e] != nt[e]:
                        e += 1
                    self.fill(px + i * CW, y, (e - i) * CW, CH)
                    if nt[i:e].strip() != "":
                        self.setc(COL[nc])
                        self.td.draw_text(px + i * CW, y + TEXT_DY, nt[i:e])
                    i = e
            px += n * CW
        return True

    def paint(self, rows):
        # A drawing error must not take the system down: recover by clearing the
        # screen and painting everything once more; if the display keeps refusing,
        # give up quietly (each later paint tries again from a clean screen).
        for attempt in (0, 1):
            try:
                if self.stale:
                    self.td.set_color(0, 0, 0)
                    self.td.fill_rect(0, 0, 320, 240)
                    self.col = (0, 0, 0)
                    self.prev = []
                    self.stale = False
                self.paint_rows(rows)
                return
            except Exception:
                self.stale = True

    def paint_rows(self, rows):
        prev = self.prev
        for i in range(self.rows):
            r = rows[i]
            old = None
            if i < len(prev):
                old = prev[i]
            if old == r:
                continue
            y = i * CH
            if old and self.cells(y, old, r):
                continue
            if old:
                self.fill(0, y, CW * rlen(old), CH)     # blank/new rows need no erase
            if r:
                self.draw_row(y, r)
        self.prev = rows

    def draw(self, prompt, ed):
        self.vis = None
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
        self.vis = None
        ls = self.lines[-(self.rows - 2):]
        out = [line_segs(l) for l in ls]
        out.append([(" ", "c")])
        while len(out) < self.rows:
            out.append([])
        self.paint(out)

    def post(self, text, pending=False):
        # Boot/progress view: lines fill the screen from the top. When it is
        # full it scrolls by POST_STEP lines at once, so most new lines only
        # draw their own row instead of repainting the whole screen.
        if not pending:
            self.write(text)
            if self.vis is None:
                self.vis = len(self.lines)
                if self.vis > self.rows:
                    self.vis = self.rows
            else:
                self.vis += self.nw
                if self.vis > self.rows:
                    keep = self.rows - POST_STEP
                    if self.nw > keep:
                        keep = self.nw
                        if keep > self.rows:
                            keep = self.rows
                    self.vis = keep
            if self.vis > len(self.lines):
                self.vis = len(self.lines)
        vis = self.vis
        if vis is None:
            vis = len(self.lines)
            if vis > self.rows:
                vis = self.rows
        if pending:
            if vis > self.rows - 1:
                vis = self.rows - 1
        ls = []
        if vis > 0:
            ls = self.lines[len(self.lines) - vis:]
        if pending:
            ls = ls + [text.rstrip("\n")[:self.cols]]
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
