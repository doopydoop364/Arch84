# A84ED: text editor state machine (Arch84 module, loaded by `edit` only).
# Pure logic - no drawing, no filesystem. A84EV drives it with keys and paints it.
#
# Keys (A84UI names): characters insert; left/right/up/down move; 2nd+left/right
# = home/end, 2nd+up/down = page up/down; del = backspace, 2nd+del = delete.
# CLEAR opens the command line; Enter runs it, CLEAR again cancels:
#   w [file]   save           q  quit        qq (or q!)  quit, discard   wq / x  save+quit
#   N          go to line N   /text  find    n   find next
#   d          delete line (kept)   y  copy line   p  paste below
#   s/old/new/ replace in this line     %s/old/new/  replace in every line
MAXLINES = 1500
HELP = "CLEAR=cmd  w save  q quit"


class Editor:
    def __init__(self, name, lines, cols=32, rows=9):
        self.name = name
        self.lines = lines if lines else [""]
        self.row = 0
        self.col = 0
        self.top = 0
        self.left = 0
        self.W = cols
        self.H = rows
        self.dirty = False
        self.yank = None
        self.find = ""
        self.msg = HELP
        self.cmd = None         # None, or the command line being typed
        self.act = None         # for the driver: "w" "q" "wq" "q!"
        self.saveas = None

    # ---- movement
    def fix(self):
        n = len(self.lines)
        if self.row >= n:
            self.row = n - 1
        if self.row < 0:
            self.row = 0
        ln = len(self.lines[self.row])
        if self.col > ln:
            self.col = ln
        if self.col < 0:
            self.col = 0
        if self.row < self.top:
            self.top = self.row
        if self.row >= self.top + self.H:
            self.top = self.row - self.H + 1
        if self.col < self.left:
            self.left = self.col
        if self.col >= self.left + self.W:
            self.left = self.col - self.W + 1

    def goto(self, n):
        self.row = n - 1
        self.col = 0
        self.fix()

    # ---- editing
    def insert(self, s):
        ln = self.lines[self.row]
        self.lines[self.row] = ln[:self.col] + s + ln[self.col:]
        self.col += len(s)
        self.dirty = True

    def split(self):
        if len(self.lines) >= MAXLINES:
            self.msg = "too many lines"
            return
        ln = self.lines[self.row]
        self.lines[self.row] = ln[:self.col]
        self.lines.insert(self.row + 1, ln[self.col:])
        self.row += 1
        self.col = 0
        self.dirty = True

    def backspace(self):
        if self.col > 0:
            ln = self.lines[self.row]
            self.lines[self.row] = ln[:self.col - 1] + ln[self.col:]
            self.col -= 1
            self.dirty = True
        elif self.row > 0:
            prev = self.lines[self.row - 1]
            self.lines[self.row - 1] = prev + self.lines[self.row]
            self.lines.pop(self.row)
            self.row -= 1
            self.col = len(prev)
            self.dirty = True

    def delete(self):
        ln = self.lines[self.row]
        if self.col < len(ln):
            self.lines[self.row] = ln[:self.col] + ln[self.col + 1:]
            self.dirty = True
        elif self.row + 1 < len(self.lines):
            self.lines[self.row] = ln + self.lines[self.row + 1]
            self.lines.pop(self.row + 1)
            self.dirty = True

    # ---- keys
    def key(self, a):
        self.msg = ""
        self.act = None
        if self.cmd is not None:
            self.cmd_key(a)
            return
        if len(a) == 1:
            self.insert(a)
        elif a == "left":
            if self.col > 0:
                self.col -= 1
            elif self.row > 0:
                self.row -= 1
                self.col = len(self.lines[self.row])
        elif a == "right":
            if self.col < len(self.lines[self.row]):
                self.col += 1
            elif self.row + 1 < len(self.lines):
                self.row += 1
                self.col = 0
        elif a == "up":
            self.row -= 1
        elif a == "down":
            self.row += 1
        elif a == "home":
            self.col = 0
        elif a == "end":
            self.col = len(self.lines[self.row])
        elif a == "pgup":
            self.row -= self.H - 1
        elif a == "pgdn":
            self.row += self.H - 1
        elif a == "enter":
            self.split()
        elif a == "bs":
            self.backspace()
        elif a == "del":
            self.delete()
        elif a == "tab":
            self.insert("  ")
        elif a == "clear":
            self.cmd = ""
        self.fix()

    def cmd_key(self, a):
        if len(a) == 1:
            self.cmd += a
        elif a == "bs":
            if self.cmd == "":
                self.cmd = None
            else:
                self.cmd = self.cmd[:-1]
        elif a == "clear":
            self.cmd = None
        elif a == "enter":
            text = self.cmd
            self.cmd = None
            self.run(text.strip())
            self.fix()

    # ---- command line
    def run(self, c):
        if c == "":
            return
        if c == "w" or c[:2] == "w ":
            self.act = "w"
            self.saveas = c[2:].strip() or None
        elif c == "q":
            if self.dirty:
                self.msg = "unsaved: w, or qq to discard"
            else:
                self.act = "q"
        elif c == "q!" or c == "qq":        # "!" is not a calculator key: qq discards too
            self.act = "q!"
        elif c == "wq" or c == "x":
            self.act = "wq"
            self.saveas = None
        elif c.strip("0123456789") == "":
            self.goto(int(c))
        elif c[0] == "/":
            if len(c) > 1:
                self.find = c[1:]
            self.search()
        elif c == "n":
            self.search()
        elif c == "d":
            self.yank = self.lines[self.row]
            if len(self.lines) > 1:
                self.lines.pop(self.row)
            else:
                self.lines[0] = ""
            self.dirty = True
        elif c == "y":
            self.yank = self.lines[self.row]
            self.msg = "line copied"
        elif c == "p":
            if self.yank is None:
                self.msg = "nothing to paste"
            elif len(self.lines) >= MAXLINES:
                self.msg = "too many lines"
            else:
                self.lines.insert(self.row + 1, self.yank)
                self.row += 1
                self.dirty = True
        elif c[:2] == "s/" or c[:3] == "%s/":
            self.subst(c)
        else:
            self.msg = "? " + c[:20]

    def search(self):
        if self.find == "":
            self.msg = "no pattern"
            return
        n = len(self.lines)
        for k in range(n + 1):
            r = (self.row + k) % n
            start = 0
            if k == 0:
                start = self.col + 1
            i = self.lines[r].find(self.find, start)
            if i >= 0:
                self.row = r
                self.col = i
                return
        self.msg = "not found"

    def subst(self, c):
        whole = c[0] == "%"
        parts = c[c.find("/") + 1:].split("/")
        if len(parts) < 2 or parts[0] == "":
            self.msg = "use s/old/new/"
            return
        old = parts[0]
        new = parts[1]
        rows = [self.row]
        if whole:
            rows = range(len(self.lines))
        hits = 0
        for r in rows:
            ln = self.lines[r]
            if old in ln:
                hits += ln.count(old)
                self.lines[r] = ln.replace(old, new)
        if hits:
            self.dirty = True
            self.msg = str(hits) + " replaced"
        else:
            self.msg = "not found"

    # ---- output
    def window(self):
        # the visible text rows, each cut to the screen width
        out = []
        for r in range(self.top, self.top + self.H):
            if r < len(self.lines):
                out.append(self.lines[r][self.left:self.left + self.W])
            else:
                out.append("~")
        return out

    def status(self, tag=""):
        s = self.name[-14:] + " " + str(self.row + 1) + ":" + str(self.col + 1)
        if self.dirty:
            s += " *"
        if tag:
            s = s + " " * (self.W - len(s) - len(tag)) + tag
        return s[:self.W]

    def bottom(self):
        if self.cmd is not None:
            return ":" + self.cmd
        return self.msg

    def cursor(self):
        # (screen row, screen col) of the text cursor
        return self.row - self.top, self.col - self.left

    def chunks(self):
        # the file text in pieces of <= 512 chars (a trailing newline unless empty)
        buf = ""
        last = len(self.lines) - 1
        for i in range(len(self.lines)):
            ln = self.lines[i]
            if i == last and ln == "":
                break                       # no extra empty line after the final newline
            buf += ln + "\n"
            if len(buf) >= 512:
                yield buf
                buf = ""
        if buf != "":
            yield buf
