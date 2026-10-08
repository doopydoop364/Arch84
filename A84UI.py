# A84UI: terminals (Arch84 module 5/10)
# Verified on a TI-84 Evo (OS 7.0): get_key(1) blocks and returns the
# positional key code, get_key(0) returns 0 when no key is down,
# disp_at(row, text, align) with rows 1..10 and 31 columns.
from A84FS import ERR, ms_since, now_ms

ROWS = 10
COLS = 31


def wrap(s, cols):
    if s == "":
        return [""]
    out = []
    i = 0
    while i < len(s):
        out.append(s[i:i + cols])
        i += cols
    return out


class PlainTerm:
    # print()/input() fallback: works anywhere, no editing features
    def write(self, text):
        text = text.replace(ERR, "")
        if text != "" and not text.endswith("\n"):
            text += "\n"
        print(text, end="")

    def echo(self, text):
        pass

    def post(self, text, pending=False):
        if not pending:
            self.write(text)

    def busy(self):
        pass

    def safe_key(self, tick=None):
        return False

    def readline(self, prompt, ed):
        return input(prompt)

    def clear(self):
        print("\n" * 12)

    def close(self):
        pass


# key code -> char. Letters live on the green alpha layer.
LET_CODES = (41, 42, 43, 51, 52, 53, 54, 55, 61, 62, 63, 64, 65, 71, 72,
             73, 74, 75, 81, 82, 83, 84, 85, 91, 92, 93)
ALPHA = {95: '"', 102: " ", 103: ":", 104: "?"}
for _i in range(26):
    ALPHA[LET_CODES[_i]] = "abcdefghijklmnopqrstuvwxyz"[_i]
NORM = {
    11: '"', 12: "'", 13: "$", 14: ">", 15: "=", 33: "~", 41: ">", 51: "^",
    55: "/", 62: ",", 63: "(", 64: ")", 65: "*", 72: "7", 73: "8",
    74: "9", 75: "-", 82: "4", 83: "5", 84: "6", 85: "+", 92: "1",
    53: "<", 52: "|", 61: "\\",
    93: "2", 94: "3", 95: " ", 102: "0", 103: ".", 104: "_",
}
ACT = {22: "tab", 23: "bs", 24: "left", 25: "up", 26: "right", 34: "down",
       45: "clear", 105: "enter"}
ACT2 = {23: "del", 24: "home", 26: "end", 25: "pgup", 34: "pgdn"}
SEC = {41: ">", 63: "{", 64: "}", 75: "[", 85: "]"}


class TiTerm:
    # text-console terminal (disp_at); GfxTerm in A84GX draws in color
    def __init__(self, ti):
        self.ti = ti
        self.rows = ROWS
        self.cols = COLS
        self.lines = []
        self.off = 0
        self.mod = ""
        self.up = False
        self.prev = []

    def write(self, text):
        mark = ""
        if text.startswith(ERR):
            mark = ERR
            text = text[1:]
        for line in text.split("\n"):
            for part in wrap(line, self.cols):
                self.lines.append(mark + part)
        if text.endswith("\n"):
            self.lines.pop()
        self.lines = self.lines[-self.rows * 8:]
        self.off = 0

    def echo(self, text):
        self.write(text + "\n")

    def clear(self):
        self.lines = []
        self.off = 0

    def reset(self):
        self.ti.disp_clr()
        self.prev = []

    def close(self):
        self.reset()
        for line in self.lines[-(self.rows - 1):]:
            print(line.replace(ERR, ""))

    def translate(self, k):
        # raw key code -> char / action name, or None (modifier or unknown)
        m = self.mod
        if k == 21:
            if m == "alpha" or m == "lock":
                self.up = True
            elif m == "2nd":
                self.mod = ""
            else:
                self.mod = "2nd"
            return None
        if k == 31:
            if m == "2nd":
                self.mod = "lock"
            elif m == "":
                self.mod = "alpha"
            else:
                self.mod = ""
            return None
        if m == "2nd":
            self.mod = ""
            m = ""
            if k in ACT2:
                return ACT2[k]
            if k in SEC:
                return SEC[k]
        if k in ACT:
            if m == "alpha":
                self.mod = ""
            return ACT[k]
        if (m == "alpha" or m == "lock") and k in ALPHA:
            c = ALPHA[k]
            if self.up:
                c = c.upper()
                self.up = False
            if m == "alpha":
                self.mod = ""
            return c
        if m == "alpha":
            self.mod = ""
        return NORM.get(k)

    def read_key(self):
        k = self.ti.get_key(1)
        while self.ti.get_key(0):
            pass
        return k

    def scroll_by(self, ed):
        self.off += ed.scroll
        if self.off > len(self.lines) - 1:
            self.off = len(self.lines) - 1
        if self.off < 0:
            self.off = 0
        ed.scroll = 0

    def shown(self, space):
        end = len(self.lines) - self.off
        if end < 0:
            end = 0
        return self.lines[max(0, end - space):end]

    def draw(self, prompt, ed):
        # rows 1..rows-1: scrollback then the input line; last row: hint
        text = prompt + ed.buf[:ed.pos] + "|" + ed.buf[ed.pos:]
        inrows = wrap(text, self.cols)
        area = self.rows - 1
        maxin = area - 1
        if len(inrows) > maxin:
            crow = (len(prompt) + ed.pos) // self.cols
            end = max(crow + 1, maxin)
            inrows = inrows[end - maxin:end]
        out = [l.replace(ERR, "") for l in self.shown(area - len(inrows))]
        out.extend(inrows)
        while len(out) < area:
            out.append("")
        flag = ""
        if self.up:
            flag = "^ "
        out.append((flag + ed.hint)[:self.cols])
        self.paint(out)

    def paint(self, out):
        # draw only the rows that changed since the last frame
        for i in range(self.rows):
            s = out[i] + " " * (self.cols - len(out[i]))
            if i >= len(self.prev) or self.prev[i] != s:
                self.ti.disp_at(i + 1, s, "left")
            out[i] = s
        self.prev = out

    def post(self, text, pending=False):
        # boot/progress output: show it right now. A pending line is only
        # drawn (not kept) and gets replaced by the next real line.
        if pending:
            out = self.lines[-(self.rows - 1):] + [text.rstrip("\n")[:self.cols]]
        else:
            self.write(text)
            out = self.lines[-self.rows:]
        out = [l.replace(ERR, "") for l in out]
        while len(out) < self.rows:
            out.append("")
        self.paint(out)

    def safe_key(self, tick=None):
        # hold CLEAR while Arch84 starts to skip the startup files
        t0 = now_ms()
        while True:
            if self.ti.get_key(0) == 45:
                return True
            if tick is not None:
                tick()
            d = ms_since(t0)        # ticks_diff: correct across a counter wrap
            if d is None or d > 500:
                return False

    def busy(self):
        # a command is running: show the submitted line and a cursor on a
        # fresh line below it
        out = [l.replace(ERR, "") for l in self.lines[-(self.rows - 1):]]
        out.append("|")
        while len(out) < self.rows:
            out.append("")
        self.paint(out)

    def readline(self, prompt, ed):
        self.reset()
        while not ed.done:
            self.draw(prompt, ed)
            k = self.read_key()
            a = self.translate(k)
            if a is not None:
                ed.feed(a)
                if ed.scroll != 0:
                    self.scroll_by(ed)
            elif k != 21 and k != 31:
                ed.hint = "key " + str(k)
        self.mod = ""
        self.up = False
        return ed.buf
