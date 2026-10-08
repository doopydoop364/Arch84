# A84EV: `edit FILE` - drives the A84ED editor on the calculator terminal.
# Registers itself into COMMANDS (loaded on first use of `edit`).

from A84FS import VFSError, dchunks, dlen
from A84CD import COMMANDS
from A84ED import Editor

MAXCHARS = 20000        # larger files do not fit the heap as a list of lines


def paint(ed, term):
    tag = ""
    if term.mod == "2nd":
        tag = "2ND"
    elif term.mod == "alpha":
        tag = "ALPHA"
    elif term.mod == "lock":
        tag = "A-LOCK"
    if term.up:
        tag = (tag + " UP").strip()
    rows = ed.window()
    cr, cc = ed.cursor()
    gfx = hasattr(term, "td")
    out = []
    for i in range(len(rows)):
        t = rows[i]
        if gfx:
            if i == cr and ed.cmd is None:
                cur = t[cc:cc + 1] or " "
                out.append([(t[:cc], "w"), (cur, "c"), (t[cc + 1:], "w")])
            else:
                out.append([(t, "d" if t == "~" else "w")])
        elif i == cr and ed.cmd is None:
            out.append((t[:cc] + "|" + t[cc:])[:term.cols])
        else:
            out.append(t)
    st = ed.status(tag)
    bot = ed.bottom()
    if gfx:
        out.append([(st, "b")])
        if ed.cmd is not None:
            out.append([(bot, "y"), (" ", "c")])
        else:
            out.append([(bot, "y")])
    else:
        out.append(st)
        out.append(bot[:term.cols])
    while len(out) < term.rows:
        out.append([] if gfx else "")
    term.paint(out[:term.rows])


def load(sh, path):
    node = sh.vfs.get(path)
    if node is None:
        return [], False
    if node.is_dir:
        raise VFSError("Is a directory")
    if dlen(node.data) > MAXCHARS:
        raise VFSError("file too large to edit (limit " + str(MAXCHARS) + " chars)")
    lines = []
    for ln in sh.vfs.lines(path):
        lines.append(ln)
    return lines, True


def save(sh, ed, path):
    # the new data is built completely first and swapped in at the end, so a
    # failure (out of memory) leaves the old file untouched
    data = dchunks(ed.chunks())
    sh.vfs.put(path, data)


def cmd_edit(sh, args):
    if len(args) != 1:
        sh.err("usage: edit FILE")
        return 1
    term = sh.term
    if not (hasattr(term, "read_key") and hasattr(term, "translate")):
        sh.err("edit: needs the calculator terminal")
        return 1
    name = args[0]
    path = sh.resolve(name)
    try:
        lines, existed = load(sh, path)
    except VFSError as e:
        sh.err("edit: " + name + ": " + str(e))
        return 1
    except MemoryError:
        sh.err("edit: out of memory")
        return 1
    ed = Editor(name, lines, term.cols, term.rows - 2)
    if not existed:
        ed.msg = "new file"
    term.reset()
    status = 0
    while True:
        try:
            paint(ed, term)
            k = term.read_key()
            a = term.translate(k)
            if a is None:
                continue
            ed.key(a)
            act = ed.act
            if act is None:
                continue
            if act == "w" or act == "wq":
                target = path
                if ed.saveas:
                    target = sh.resolve(ed.saveas)
                save(sh, ed, target)
                if target == path:
                    ed.dirty = False
                ed.msg = "written " + str(len(ed.lines)) + " lines"
                if act == "wq":
                    break
            elif act == "q" or act == "q!":
                break
        except VFSError as e:
            ed.msg = str(e)[:30]
        except MemoryError:
            import gc
            gc.collect()
            ed.msg = "out of memory"
        except EOFError:
            status = 1
            break
    term.mod = ""
    term.up = False
    return status


COMMANDS["edit"] = cmd_edit
