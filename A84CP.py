# A84CP: tab completion for the shell (Arch84 module, split from A84SH to keep
# each module's compile-time memory peak low). Mixed into Shell.

from A84FS import VFSError
from A84CD import all_commands


ARGKIND = {
    "cd": "d", "rmdir": "d", "ls": "p", "cat": "p", "rm": "p", "cp": "p",
    "mv": "p", "head": "p", "tail": "p", "touch": "p", "mkdir": "p",
    "which": "c", "help": "c", "export": "v", "unalias": "a", "uname": "o",
}


class Completer:
    def complete(self, text):
        start = 0
        q = ""
        words = []
        i = 0
        wstart = -1
        while i < len(text):
            c = text[i]
            if q != "":
                if c == q:
                    q = ""
            elif c == "'" or c == '"':
                q = c
                if wstart < 0:
                    wstart = i
            elif c == "\\":
                if wstart < 0:
                    wstart = i
                i += 1
            elif c == " " or c == "\t":
                if wstart >= 0:
                    words.append(text[wstart:i])
                    wstart = -1
            elif wstart < 0:
                wstart = i
            i += 1
        if wstart < 0:
            start = len(text)
            word = ""
        else:
            start = wstart
            word = text[wstart:]
        quote = ""
        if word[:1] == "'" or word[:1] == '"':
            quote = word[:1]
            word = word[1:]
            start += 1
        word = word.replace("\\ ", " ")
        prev = ""
        if words:
            prev = words[-1]
        cands = []
        if len(words) == 0 and prev == "":
            cands = self.match_names(self.command_names(), word)
        elif word[:1] == "$":
            cands = ["$" + n for n in self.match_names(list(self.k.env.keys()), word[1:])]
        else:
            kind = ARGKIND.get(words[0], "")
            if prev == ">" or prev == ">>":
                kind = "p"
            if kind == "d" or kind == "p":
                cands = self.path_cands(word, kind == "d")
            elif kind == "c":
                cands = self.match_names(self.command_names(), word)
            elif kind == "v":
                cands = self.match_names(list(self.k.env.keys()), word)
            elif kind == "a":
                cands = self.match_names(list(self.k.aliases.keys()), word)
            elif kind == "o":
                cands = self.match_names(["-a", "-n", "-r", "-s"], word)
        out = []
        for c in cands:
            if quote == "":
                c = c.replace(" ", "\\ ")
            out.append(quote + c)
        return start, out

    def command_names(self):
        names = all_commands()
        for a in self.k.aliases:
            if a not in names:
                names.append(a)
        return names

    def match_names(self, names, prefix):
        out = [n for n in names if n.startswith(prefix)]
        out.sort()
        return out

    def path_cands(self, word, dirs_only):
        if word == "~":
            return ["~/"]
        i = word.rfind("/")
        dirpart = word[:i + 1]
        base = word[i + 1:]
        if dirpart == "":
            d = self.cwd
        else:
            d = self.resolve(dirpart)
        try:
            names = self.vfs.listdir(d)
        except VFSError:
            return []
        out = []
        for n in names:
            if not n.startswith(base):
                continue
            if n.startswith(".") and not base.startswith("."):
                continue
            isd = self.vfs.isdir(d.rstrip("/") + "/" + n)
            if dirs_only and not isd:
                continue
            if isd:
                out.append(dirpart + n + "/")
            else:
                out.append(dirpart + n)
        return out
