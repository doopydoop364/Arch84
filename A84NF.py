# A84NF: neofetch (Arch84 module, lazily loaded): the login greeting. The small Arch logo on
# the left (the bite holds an "84"), system facts on the right, in color, and a row of
# solid color blocks that are the colors the terminal really draws with (it asks the
# terminal for its palette; a text-only terminal has none, so the row is left out).
# The shell runs it once after login unless ~/.hushlogin exists; `neofetch` runs it by hand.
from A84FS import BLK, CLR, VERSION, ms_since
from A84CD import COMMANDS

LOGO = ("      /\\      ",
        "     /  \\     ",
        "    /    \\    ",
        "   /      \\   ",
        "  /   ,,   \\  ",
        " /   |84|   \\ ",
        "/_-''    ''-_\\")
W = 14                  # logo width (the rows above are padded to it)
PAD = " " * W
ART = "n"               # logo / label color (cyan, like Arch)


def logo_row(i):
    if i >= len(LOGO):
        return PAD + " "
    r = LOGO[i][:W]
    j = r.find("84")
    if j < 0:
        return CLR + ART + r + " "
    return CLR + ART + r[:j] + CLR + "y" + "84" + CLR + ART + r[j + 2:] + " "


def kv(key, val):
    return CLR + ART + key + " " + CLR + "w" + val


def facts(sh):
    k = sh.k
    out = [CLR + "g" + (k.env.get("USER", "evo") + CLR + "w@" + CLR + "g" + k.hostname())[:15]]
    out.append(kv("OS", "Arch84 " + VERSION))
    out.append(kv("Host", "TI-84 Evo"))
    t = sh.term
    kind = "gfx" if hasattr(t, "palette") else "text"
    out.append(kv("Term", kind + " " + str(getattr(t, "cols", 31)) + "x" + str(getattr(t, "rows", 10))))
    try:
        import gc
        gc.collect()
        out.append(kv("Mem", str(gc.mem_free() // 1000) + "K free"))
    except (ImportError, AttributeError):
        pass
    disk = "unsaved"
    try:
        m = k.storage._meta()       # the saved copy: stored (compressed) bytes and lists used
        if m is not None:
            disk = str(m[4]) + "B " + str(m[3]) + "blk"
    except Exception:
        pass
    out.append(kv("Disk", disk))
    pk = 0
    try:
        pk = len(sh.vfs.listdir("/var/lib/pacman/local"))
    except Exception:
        pass
    line = kv("Pkgs", str(pk))
    up = ms_since(k.t0)
    if up is not None:
        s = up // 1000
        line += " " + kv("Up", str(s // 60) + "m" if s >= 60 else str(s) + "s")
    out.append(line)
    return out


def palette(sh):
    # solid blocks (2 cells each) of the colors the terminal reports; "" if it has none
    pal = ""
    if hasattr(sh.term, "palette"):
        pal = sh.term.palette()
    out = ""
    for c in pal[:7]:
        out += CLR + c + BLK + BLK
    return out


def cmd_neofetch(sh, args):
    info = facts(sh)
    for i in range(max(len(info), len(LOGO))):
        sh.out(logo_row(i) + (info[i] if i < len(info) else "") + "\n")
    p = palette(sh)
    if p != "":
        sh.out(PAD + " " + p + "\n")


COMMANDS["neofetch"] = cmd_neofetch
