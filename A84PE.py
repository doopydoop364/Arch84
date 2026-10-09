# A84PE: shell parser and line editor (Arch84 module, split from A84KN to
# keep each module's compile-time memory peak low)




# --------------------------------------------------------------- parser

class ParseError(Exception):
    pass


MAX_LINE = 4096             # a shell line must fit the calculator's small heap
MAX_COMMANDS = 32
MAX_WORDS = 128
MAX_STAGES = 16


def isname(c):
    return c == "_" or ("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9")


def expand(line, i, env):
    # line[i] == "$"; returns (text, next_index)
    n = len(line)
    j = i + 1
    if j < n and line[j] == "{":
        k = line.find("}", j)
        if k < 0:
            raise ParseError("unterminated ${")
        return env.get(line[j + 1:k], ""), k + 1
    if j < n and (line[j] == "?" or line[j] == "#"):
        return env.get(line[j], "0"), j + 1
    if j < n and "0" <= line[j] <= "9":
        return env.get(line[j], ""), j + 1     # $0..$9: one digit (script arguments)
    k = j
    while k < n and isname(line[k]):
        k += 1
    if k == j:
        return "$", j
    return env.get(line[j:k], ""), k


def split_commands(line):
    # [(text, connector)] cut at unquoted ";", "&&" and "||"; connector is None for
    # the first piece, else what precedes it. Quotes/escapes/comments are respected.
    if len(line) > MAX_LINE:
        raise ParseError("command line too long")
    out = []
    seg = 0
    conn = None
    q = ""
    start = True            # at the start of a word (a "#" there begins a comment)
    i = 0
    n = len(line)
    while i < n:
        c = line[i]
        if q != "":
            if c == q:
                q = ""
            elif c == "\\" and q == '"' and i + 1 < n:
                i += 1
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            start = False
            continue
        if c == "'" or c == '"':
            q = c
            start = False
        elif c == "#" and start:
            break
        elif c == ";" or (c == "&" and line[i + 1:i + 2] == "&") or (c == "|" and line[i + 1:i + 2] == "|"):
            op = c
            end = i
            if c != ";":
                op = c + c
                i += 1
            part = line[seg:end]
            if part.strip() == "":
                raise ParseError("syntax error near " + op)
            if len(out) >= MAX_COMMANDS:
                raise ParseError("too many commands")
            out.append((part, conn))
            conn = op
            start = True
            seg = i + 1
        else:
            start = c == " " or c == "\t"
        i += 1
    if q != "":
        raise ParseError("unterminated quote")
    part = line[seg:]
    if part.strip() == "":
        if conn is not None and conn != ";":
            raise ParseError("syntax error near " + conn)
        if not out:
            out.append((part, None))
    else:
        if len(out) >= MAX_COMMANDS:
            raise ParseError("too many commands")
        out.append((part, conn))
    return out


def parse(line, env, home, pipes=False):
    # pipes False -> (words, redir); redir is None or (">" | ">>", target); "|" and "<" are errors.
    # pipes True  -> [(words, redir, infile), ...] one entry per pipeline stage.
    if len(line) > MAX_LINE:
        raise ParseError("command line too long")
    stages = []
    words = []
    redir = None
    infile = None
    pending = None   # redirection operator waiting for its target
    cur = []
    started = False
    i = 0
    n = len(line)
    while i <= n:
        c = ""
        if i < n:
            c = line[i]
        if c == "" or c == " " or c == "\t" or (pipes and c == "|"):
            if started:
                w = "".join(cur)
                if pending == "<":
                    if infile is not None:
                        raise ParseError("only one input redirection allowed")
                    infile = w
                    pending = None
                elif pending is not None:
                    if redir is not None:
                        raise ParseError("only one redirection allowed")
                    redir = (pending, w)
                    pending = None
                else:
                    if len(words) >= MAX_WORDS:
                        raise ParseError("too many arguments")
                    words.append(w)
                cur = []
                started = False
            if c == "|":
                if pending is not None or (not words and redir is None and infile is None):
                    raise ParseError("syntax error near |")
                stages.append((words, redir, infile))
                if len(stages) >= MAX_STAGES:
                    raise ParseError("too many pipeline stages")
                words = []
                redir = None
                infile = None
            i += 1
        elif c == "'":
            k = line.find("'", i + 1)
            if k < 0:
                raise ParseError("unterminated quote")
            cur.append(line[i + 1:k])
            started = True
            i = k + 1
        elif c == '"':
            i += 1
            while True:
                if i >= n:
                    raise ParseError("unterminated quote")
                d = line[i]
                if d == '"':
                    i += 1
                    break
                if d == "\\" and i + 1 < n and line[i + 1] in '"\\$':
                    cur.append(line[i + 1])
                    i += 2
                elif d == "$":
                    t, i = expand(line, i, env)
                    cur.append(t)
                else:
                    j = i + 1
                    while j < n and line[j] not in '"\\$':
                        j += 1
                    cur.append(line[i:j])
                    i = j
            started = True
        elif c == "\\":
            if i + 1 < n:
                cur.append(line[i + 1])
                i += 2
            else:
                cur.append("\\")
                i += 1
            started = True
        elif c == "$":
            t, i = expand(line, i, env)
            cur.append(t)
            started = True
        elif c == ">" or (pipes and c == "<"):
            if started:
                raise ParseError("put a space before " + c)
            if pending is not None:
                raise ParseError("syntax error near " + c)
            if c == ">" and i + 1 < n and line[i + 1] == ">":
                pending = ">>"
                i += 2
            else:
                pending = c
                i += 1
        elif c == "~" and not started and (i + 1 == n or line[i + 1] in " \t/>"):
            cur.append(home)
            started = True
            i += 1
        elif c == "#" and not started:
            i = n   # comment
        elif c in "|;&<":
            raise ParseError("unsupported syntax: " + c)
        else:
            j = i + 1
            while j < n and line[j] not in " \t'\"\\$><~#|;&":
                j += 1
            cur.append(line[i:j])
            started = True
            i = j
    if pending is not None:
        raise ParseError("missing file after " + pending)
    if not pipes:
        return words, redir
    if stages and not words and redir is None and infile is None:
        raise ParseError("syntax error near |")
    stages.append((words, redir, infile))
    return stages


# ---------------------------------------------------------- line editor

class LineEditor:
    # Pure state machine: feed() takes a char or action name; no drawing.
    def __init__(self, history, completer):
        self.hist = history
        self.completer = completer
        self.buf = ""
        self.pos = 0
        self.done = False
        self.hi = -1
        self.hprefix = ""
        self.cyc = None
        self.hint = ""
        self.scroll = 0     # requested scrollback delta (consumed by terminal)

    def set_buf(self, s):
        self.buf = s
        self.pos = len(s)

    def insert(self, s):
        self.buf = self.buf[:self.pos] + s + self.buf[self.pos:]
        self.pos += len(s)

    def feed(self, act):
        # act: one printable char to insert, or an action name
        if len(act) == 1:
            self.cyc = None
            self.hi = -1
            self.hint = ""
            self.insert(act)
            self.update_hint()
            return
        if act != "tab":
            self.cyc = None
        if act != "up" and act != "down":
            self.hi = -1
        self.hint = ""
        if act == "left":
            if self.pos > 0:
                self.pos -= 1
        elif act == "right":
            if self.pos < len(self.buf):
                self.pos += 1
            else:
                s = self.suggest()
                if s is not None:
                    self.set_buf(s)
        elif act == "home":
            self.pos = 0
        elif act == "end":
            self.pos = len(self.buf)
        elif act == "bs":
            if self.pos > 0:
                self.buf = self.buf[:self.pos - 1] + self.buf[self.pos:]
                self.pos -= 1
        elif act == "del":
            self.buf = self.buf[:self.pos] + self.buf[self.pos + 1:]
        elif act == "clear":
            self.set_buf("")
        elif act == "enter":
            self.done = True
            return
        elif act == "up":
            self.hist_move(-1)
        elif act == "down":
            self.hist_move(1)
        elif act == "tab":
            self.do_tab()
        elif act == "pgup":
            self.scroll = 5
        elif act == "pgdn":
            self.scroll = -5
        if not self.hint:
            self.update_hint()

    def suggest(self):
        # newest history entry that extends the current line
        if self.buf == "" or self.pos != len(self.buf):
            return None
        i = len(self.hist) - 1
        while i >= 0:
            h = self.hist[i]
            if len(h) > len(self.buf) and h.startswith(self.buf):
                return h
            i -= 1
        return None

    def update_hint(self):
        if self.cyc is not None:
            return
        s = self.suggest()
        if s is not None:
            self.hint = ">" + s[len(self.buf):]

    def hist_move(self, d):
        if self.hi == -1:
            if d > 0:
                return
            self.hprefix = self.buf
            i = len(self.hist)
        else:
            i = self.hi
        i += d
        while 0 <= i < len(self.hist):
            if self.hist[i].startswith(self.hprefix):
                self.hi = i
                self.set_buf(self.hist[i])
                return
            i += d
        if d > 0:
            self.hi = -1
            self.set_buf(self.hprefix)

    def do_tab(self):
        if self.cyc is not None:
            start, end, cands, idx = self.cyc
            idx = (idx + 1) % len(cands)
            self.replace(start, end, cands, idx)
            return
        start, cands = self.completer(self.buf[:self.pos])
        if len(cands) == 0:
            self.hint = "no matches"
            return
        word = self.buf[start:self.pos]
        if len(cands) == 1:
            self.buf = self.buf[:start] + cands[0] + self.buf[self.pos:]
            self.pos = start + len(cands[0])
            return
        cp = cands[0]
        for c in cands:
            j = 0
            while j < len(cp) and j < len(c) and cp[j] == c[j]:
                j += 1
            cp = cp[:j]
        if len(cp) > len(word):
            self.buf = self.buf[:start] + cp + self.buf[self.pos:]
            self.pos = start + len(cp)
            self.hint = self.cand_hint(cands, -1)
        else:
            self.cyc = [start, self.pos, cands, -1]
            self.replace(start, self.pos, cands, 0)

    def replace(self, start, end, cands, idx):
        c = cands[idx]
        self.buf = self.buf[:start] + c + self.buf[end:]
        self.pos = start + len(c)
        self.cyc = [start, self.pos, cands, idx]
        self.hint = self.cand_hint(cands, idx)

    def cand_hint(self, cands, idx):
        # current candidate first (in brackets) so it never scrolls off
        out = []
        n = len(cands)
        start = idx
        if start < 0:
            start = 0
        for k in range(n):
            i = (start + k) % n
            c = cands[i]
            c = c[c.rfind("/", 0, len(c) - 1) + 1:][:26]
            if i == idx:
                c = "[" + c + "]"
            out.append(c)
        return " ".join(out)
