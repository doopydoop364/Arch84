# A84SH: shell (Arch84 module 9/10)

from A84FS import ERR, HOME, VFSError, dappend, dlen, iter_lines, normalize
from A84PE import LineEditor, ParseError, parse, split_commands
from A84UI import PlainTerm
from A84CD import COMMANDS, LAZY, evict, load_command
from A84CP import Completer
from A84SD import Lifecycle
import A84CE    # registers its commands into COMMANDS


# ----------------------------------------------------- shell + commands

class Shell(Completer, Lifecycle):
    def __init__(self, kernel, term):
        self.k = kernel
        if kernel.log is None:
            kernel.log = term.post       # progress/pending lines go to this terminal
        self.vfs = kernel.vfs
        self.term = term
        self.cwd = HOME
        self.running = True
        self.reboot = False
        self.status = 0
        self._out = []
        self._outn = 0
        self._rpath = None
        self._rname = ""
        self._rfail = False
        self.stdin = None       # canonical file data of the pipe/`<` feeding this command
        self._cap = None        # canonical data collecting the output of a non-final stage
        self._tee = None        # canonical data collecting terminal output while a script runs
        self._depth = 0         # nesting of scripts

    # -- helpers used by commands
    def lines(self, arg):
        # lines of FILE, or of standard input for "-"
        if arg == "-":
            if self.stdin is None:
                return iter_lines("")
            return iter_lines(self.stdin)
        return self.vfs.lines(self.resolve(arg))

    def fsize(self, arg):
        if arg == "-":
            if self.stdin is None:
                return 0
            return dlen(self.stdin)
        return self.vfs.size(self.resolve(arg))

    def out(self, text):
        # output is flushed in ~512 B batches (on a line boundary), so a command
        # that prints a big file never builds one big string
        self._out.append(text)
        self._outn += len(text)
        if self._outn >= 512 and text.endswith("\n"):
            self.flush_out()

    def flush_out(self):
        text = "".join(self._out)
        self._out = []
        self._outn = 0
        if self._rpath is None and self._cap is not None:
            self._cap = dappend(self._cap, text)       # a pipe: kept in pieces, never one big string
        elif self._rpath is not None:
            try:
                self.vfs.append(self._rpath, text)
            except VFSError as e:
                self.err("ash: " + self._rname + ": " + str(e))
                self._rfail = True
                self._rpath = None
        elif text != "":
            if self._tee is not None:
                self._tee = dappend(self._tee, text)
            else:
                self.term.write(text)

    def err(self, text):
        self.term.write(ERR + text + "\n")

    def resolve(self, path):
        return normalize(path, self.cwd, self.k.env.get("HOME", HOME))

    def prompt(self):
        home = self.k.env.get("HOME", HOME)
        p = self.cwd
        if p == home:
            p = "~"
        elif p.startswith(home + "/"):
            p = "~" + p[len(home):]
        return "[" + self.k.env.get("USER", "evo") + "@" + self.k.hostname() + " " + p + "]$ "

    def new_editor(self):
        return LineEditor(self.k.history, self.complete)

    # -- execution
    def expand_alias(self, line):
        seen = []
        while True:
            s = line.lstrip()
            i = 0
            while i < len(s) and s[i] != " " and s[i] != "\t":
                i += 1
            first = s[:i]
            if first in self.k.aliases and first not in seen:
                seen.append(first)
                line = self.k.aliases[first] + s[i:]
            else:
                return line

    def execute(self, line):
        # a line is commands joined by ; && || ; each one is a pipeline
        try:
            segs = split_commands(line)
        except ParseError as e:
            self.err("ash: " + str(e))
            self.status = 2
            return
        if len(segs) == 1:
            self.execute_one(segs[0][0])
            return
        for text, conn in segs:
            if conn == "&&" and self.status != 0:
                continue
            if conn == "||" and self.status == 0:
                continue
            self.execute_one(text)

    def execute_one(self, line):
        env = dict(self.k.env)
        env["?"] = str(self.status)
        try:
            stages = parse(self.expand_alias(line), env,
                           self.k.env.get("HOME", HOME), True)
        except ParseError as e:
            self.err("ash: " + str(e))
            self.status = 2
            return
        n = len(stages)
        stdin = None
        try:
            for i in range(n):
                words, redir, infile = stages[i]
                if infile is not None:
                    try:
                        stdin = self.vfs._file(self.resolve(infile)).data   # shared, not copied
                    except VFSError as e:
                        self.err("ash: " + infile + ": " + str(e))
                        self.status = 1
                        return
                self.stdin = stdin
                self._cap = None
                if i < n - 1:
                    self._cap = ""
                self.run_stage(words, redir)
                stdin = self._cap       # "" (empty pipe) is still an input
        finally:
            self.stdin = None
            self._cap = None

    def script(self, name):
        # a file on PATH (or named with a "/") runs as a script: A84SC, loaded on demand
        try:
            try:
                import A84SC
            except MemoryError:
                evict()
                import A84SC
        except (ImportError, MemoryError):
            return None
        sp = A84SC.script_path(self, name)
        if sp is None:
            return None
        return lambda sh, a: A84SC.run_script(sh, sp, [name] + a)

    def run_stage(self, words, redir):
        if not words:
            if redir is not None:
                self.redirect(redir, "")
            return
        fn = COMMANDS.get(words[0])
        if fn is None and words[0] in LAZY:
            try:
                fn = load_command(words[0])
            except MemoryError:
                self.err("ash: " + words[0] + ": out of memory loading " + LAZY[words[0]])
                self.status = 1
                return
            except ImportError:
                self.err("ash: " + words[0] + ": module " + LAZY[words[0]] + " is not installed")
                self.status = 127
                return
        if fn is None:
            fn = self.script(words[0])
        if fn is None:
            self.err("ash: command not found: " + words[0])
            self.status = 127
            return
        self._out = []
        self._outn = 0
        self._rpath = None
        self._rfail = False
        if redir is not None:
            # like a real shell: the target is opened (and a '>' target
            # truncated) before the command runs, and a bad target stops it
            mode, target = redir
            path = self.resolve(target)
            try:
                if mode == ">>":
                    self.vfs.append(path, "")
                else:
                    self.vfs.write(path, "")
            except VFSError as e:
                self.err("ash: " + target + ": " + str(e))
                self.status = 1
                return
            self._rpath = path
            self._rname = target
        st = fn(self, words[1:])
        self.flush_out()
        self.status = 0
        if st:
            self.status = st
        if self._rfail:
            self.status = 1
        self._rpath = None

    def redirect(self, redir, text):
        mode, target = redir
        path = self.resolve(target)
        try:
            if mode == ">>":
                self.vfs.append(path, text)
            else:
                self.vfs.write(path, text)
        except VFSError as e:
            self.err("ash: " + target + ": " + str(e))
            self.status = 1

    def run(self):
        t = self.term
        self.k.spin("Startup (hold CLEAR to skip)")
        if t.safe_key(self.k.tick):
            t.post("[ WARN ] Startup files skipped\n")
        else:
            self.startup()
        self.k.spin("Starting shell")
        if self.vfs.isdir(self.cwd) and len(COMMANDS) > 0:
            t.post("[  OK  ] Reached target Shell\n")
        else:
            self.cwd = "/"
            t.post("[FAILED] Shell: bad cwd, using /\n")
        t.post(self.k.hostname() + " login: " + self.k.env["USER"]
               + " (auto)\n")
        memerr = 0
        while self.running:
            self.vfs = self.k.vfs
            prompt = self.prompt()
            try:
                line = t.readline(prompt, self.new_editor())
            except EOFError:
                line = "exit"
            except MemoryError:
                # a transient shortage while typing/drawing is not an API
                # mismatch: free garbage and retry before giving up the terminal
                import gc
                gc.collect()
                memerr += 1
                if memerr < 4:
                    continue
                memerr = 0
                self.term.write(ERR + "ash: low memory\n")
                continue
            except Exception as e:
                # key/display API mismatch: degrade to input() instead of dying
                print("terminal error:", repr(e))
                if isinstance(t, PlainTerm):
                    self.running = False   # nothing left to fall back to
                    continue
                print("falling back to plain input() shell")
                self.term = t = PlainTerm()
                self.k.log = t.post
                continue
            memerr = 0
            try:
                t.echo(prompt + line)
                t.busy()
                self.k.add_history(line)
            except MemoryError:
                # cosmetic steps only: carry on and run the command
                import gc
                gc.collect()
            try:
                self.execute(line)
            except MemoryError:
                import gc
                gc.collect()
                t.write(ERR + "ash: out of memory\n")
                self.status = 1
            except Exception as e:
                t.write("ash: internal error: " + repr(e) + "\n")
        if not self.reboot:
            t.close()


