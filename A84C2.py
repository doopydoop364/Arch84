# A84C2: more commands, roadmap phase 5 (Arch84 module 8/10)
# Registers itself into COMMANDS when imported. File arguments only: the
# parser has no pipes yet. No `yes`: output is collected until a command
# returns, so an endless command would exhaust RAM (needs phase 8 jobs).
from A84FS import *
from A84KN import *
from A84CD import *


def pad(v, w):
    s = str(v)
    return " " * (w - len(s)) + s


def cmd_true(sh, args):
    return 0


def cmd_false(sh, args):
    return 1


def cmd_grep(sh, args):
    ci = False
    num = False
    inv = False
    cnt = False
    rest = []
    for a in args:
        if a[:1] == "-" and len(a) > 1 and not rest:
            for c in a[1:]:
                if c == "i":
                    ci = True
                elif c == "n":
                    num = True
                elif c == "v":
                    inv = True
                elif c == "c":
                    cnt = True
                else:
                    sh.err("grep: invalid option -- '" + c + "'")
                    return 2
        else:
            rest.append(a)
    if len(rest) < 2:
        sh.err("usage: grep [-ivnc] PATTERN FILE... (no pipes yet)")
        return 2
    pat = rest[0]
    if ci:
        pat = pat.lower()
    files = rest[1:]
    st = 1
    for f in files:
        try:
            it = sh.vfs.lines(sh.resolve(f))
        except VFSError as e:
            sh.err("grep: " + f + ": " + str(e))
            st = 2
            continue
        n = 0
        i = 0
        for line in it:
            i += 1
            hay = line
            if ci:
                hay = line.lower()
            if (pat in hay) != inv:
                n += 1
                if not cnt:
                    pre = ""
                    if len(files) > 1:
                        pre = f + ":"
                    if num:
                        pre += str(i) + ":"
                    sh.out(pre + line + "\n")
        if cnt:
            pre = ""
            if len(files) > 1:
                pre = f + ":"
            sh.out(pre + str(n) + "\n")
        if n and st != 2:
            st = 0
    return st


def glob_match(pat, s):
    # * and ? only; iterative
    p = 0
    i = 0
    star = -1
    mark = 0
    while i < len(s):
        if p < len(pat) and pat[p] == "*":
            star = p
            mark = i
            p += 1
        elif p < len(pat) and (pat[p] == "?" or pat[p] == s[i]):
            p += 1
            i += 1
        elif star >= 0:
            p = star + 1
            mark += 1
            i = mark
        else:
            return False
    while p < len(pat) and pat[p] == "*":
        p += 1
    return p == len(pat)


def join(a, b):
    if a.endswith("/"):
        return a + b
    return a + "/" + b


def cmd_find(sh, args):
    start = "."
    name = None
    typ = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-name" and i + 1 < len(args):
            name = args[i + 1]
            i += 2
        elif a == "-type" and i + 1 < len(args):
            typ = args[i + 1]
            i += 2
        elif a[:1] == "-":
            sh.err("find: unknown predicate '" + a + "'")
            return 1
        else:
            start = a
            i += 1
    root = sh.resolve(start)
    if not sh.vfs.exists(root):
        sh.err("find: '" + start + "': No such file or directory")
        return 1
    stack = [(start, root)]
    while stack:
        disp, ab = stack.pop()
        node = sh.vfs.get(ab)
        ok = name is None or glob_match(name, basename(ab))
        if typ == "d" and not node.is_dir:
            ok = False
        if typ == "f" and node.is_dir:
            ok = False
        if ok:
            sh.out(disp + "\n")
        if node.is_dir:
            names = sh.vfs.listdir(ab)
            for j in range(len(names) - 1, -1, -1):
                stack.append((join(disp, names[j]), join(ab, names[j])))


def numkey(s):
    s = s.strip()
    i = 0
    neg = False
    if s[:1] == "-":
        neg = True
        i = 1
    j = i
    while j < len(s) and "0" <= s[j] <= "9":
        j += 1
    if j == i:
        return 0
    v = int(s[i:j])
    if neg:
        return -v
    return v


def cmd_sort(sh, args):
    rev = False
    num = False
    uniq = False
    files = []
    for a in args:
        if a[:1] == "-" and len(a) > 1:
            for c in a[1:]:
                if c == "r":
                    rev = True
                elif c == "n":
                    num = True
                elif c == "u":
                    uniq = True
                else:
                    sh.err("sort: invalid option -- '" + c + "'")
                    return 2
        else:
            files.append(a)
    if not files:
        sh.err("usage: sort [-rnu] FILE... (no pipes yet)")
        return 2
    lines = []
    st = 0
    for f in files:
        try:
            for line in sh.vfs.lines(sh.resolve(f)):
                lines.append(line)
        except VFSError as e:
            sh.err("sort: " + f + ": " + str(e))
            st = 2
    if num:
        lines.sort(key=numkey)
    else:
        lines.sort()
    if rev:
        lines.reverse()
    out = []
    for l in lines:
        if not (uniq and out and out[-1] == l):
            out.append(l)
    if out:
        sh.out("\n".join(out) + "\n")
    return st


def cmd_wc(sh, args):
    flags = ""
    files = []
    for a in args:
        if a[:1] == "-" and len(a) > 1:
            for c in a[1:]:
                if c in "lwc":
                    flags += c
                else:
                    sh.err("wc: invalid option -- '" + c + "'")
                    return 2
        else:
            files.append(a)
    if not files:
        sh.err("usage: wc [-lwc] FILE... (no pipes yet)")
        return 2
    one = len(flags) == 1
    if flags == "":
        flags = "lwc"
    tot = [0, 0, 0]
    st = 0
    for f in files:
        try:
            it = sh.vfs.lines(sh.resolve(f))
            nchars = sh.vfs.size(sh.resolve(f))
        except VFSError as e:
            sh.err("wc: " + f + ": " + str(e))
            st = 1
            continue
        nl = 0
        nw = 0
        for line in it:
            nl += 1
            nw += len(line.split())
        v = [nl, nw, nchars]
        row = ""
        for k in range(3):
            tot[k] += v[k]
            if "lwc"[k] in flags:
                if one:
                    row += str(v[k])
                else:
                    row += pad(v[k], 7)
        sh.out(row + " " + f + "\n")
    if len(files) > 1:
        row = ""
        for k in range(3):
            if "lwc"[k] in flags:
                if one:
                    row += str(tot[k])
                else:
                    row += pad(tot[k], 7)
        sh.out(row + " total\n")
    return st


def cmd_basename(sh, args):
    if not args:
        sh.err("basename: missing operand")
        return 1
    p = args[0]
    q = p.rstrip("/")
    if q == "":
        if p == "":
            sh.out("\n")
        else:
            sh.out("/\n")
        return
    n = q[q.rfind("/") + 1:]
    if len(args) > 1 and n != args[1] and n.endswith(args[1]):
        n = n[:len(n) - len(args[1])]
    sh.out(n + "\n")


def cmd_dirname(sh, args):
    if not args:
        sh.err("dirname: missing operand")
        return 1
    p = args[0]
    q = p.rstrip("/")
    if p == "":
        sh.out(".\n")
    elif q == "":
        sh.out("/\n")
    else:
        i = q.rfind("/")
        if i < 0:
            sh.out(".\n")
        else:
            d = q[:i].rstrip("/")
            if d == "":
                d = "/"
            sh.out(d + "\n")


def show_path(arg, root, p):
    if root == "/":
        return p
    return arg.rstrip("/") + p[len(root):]


def cmd_du(sh, args):
    summary = False
    paths = []
    for a in args:
        if a == "-s":
            summary = True
        else:
            paths.append(a)
    if not paths:
        paths = ["."]
    st = 0
    for arg in paths:
        root = sh.resolve(arg)
        node = sh.vfs.get(root)
        if node is None:
            sh.err("du: cannot access '" + arg + "': No such file or directory")
            st = 1
            continue
        order = []
        stack = [root]
        while stack:
            p = stack.pop()
            order.append(p)
            if sh.vfs.isdir(p):
                for n in sh.vfs.listdir(p):
                    stack.append(join(p, n))
        sizes = {}
        for k in range(len(order) - 1, -1, -1):
            p = order[k]
            nd = sh.vfs.get(p)
            own = 0
            if not nd.is_dir:
                own = dlen(nd.data)
            sizes[p] = sizes.get(p, 0) + own
            if p != root:
                par = p[:p.rfind("/")]
                if par == "":
                    par = "/"
                sizes[par] = sizes.get(par, 0) + sizes[p]
        if summary or not node.is_dir:
            sh.out(pad(sizes[root], 6) + " " + arg + "\n")
        else:
            for k in range(len(order) - 1, -1, -1):
                p = order[k]
                if sh.vfs.isdir(p):
                    sh.out(pad(sizes[p], 6) + " " + show_path(arg, root, p) + "\n")
    return st


def cmd_df(sh, args):
    raw, stored = fs_measure(sh.vfs)
    per = DATA_ELEMS * ELEM_BYTES
    sh.out("Filesystem  " + pad("Raw", 6) + " " + pad("Stored", 6) + " "
           + pad("Blk", 3) + "\n")
    sh.out("rootfs      " + pad(raw, 6) + " " + pad(stored, 6) + " "
           + pad((stored + per - 1) // per, 3) + "\n")


def cmd_free(sh, args):
    try:
        import gc
        gc.collect()
        f = gc.mem_free()
        a = gc.mem_alloc()
    except (ImportError, AttributeError):
        sh.err("free: no memory information available")
        return 1
    sh.out("    " + pad("total", 8) + pad("used", 8) + pad("free", 8) + "\n")
    sh.out("Mem:" + pad(f + a, 8) + pad(a, 8) + pad(f, 8) + "\n")


def cmd_mount(sh, args):
    if args:
        sh.err("mount: only listing is supported")
        return 1
    sh.out("rootfs on / type vfs (rw)\n")
    if sh.k.storage.kind == "ti-lists":
        sh.out("storage: ti-lists (A84, S0/S1)\n")
    else:
        sh.out("storage: memory (not saved)\n")


def cmd_umount(sh, args):
    if not args:
        sh.err("umount: missing operand")
        return 1
    if args[0] == "/":
        sh.err("umount: /: target is busy")
    else:
        sh.err("umount: " + args[0] + ": not mounted")
    return 1


def hms(ms):
    s = ms // 1000
    return str(s // 3600) + ":" + ("0" + str(s // 60 % 60))[-2:] + ":" + ("0" + str(s % 60))[-2:]


def cmd_uptime(sh, args):
    up = ms_since(sh.k.t0)
    now = now_ms()
    if up is None or now is None:
        sh.err("uptime: no clock available")
        return 1
    sh.out("up " + hms(up) + "\n")
    sh.out("calculator ticks " + hms(now) + "\n")


def days_from_civil(y, m, d):
    if m <= 2:
        y -= 1
    era = y // 400
    yoe = y - era * 400
    if m > 2:
        mm = m - 3
    else:
        mm = m + 9
    doy = (153 * mm + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil_from_days(z):
    z += 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    if mp < 10:
        m = mp + 3
    else:
        m = mp - 9
    if m <= 2:
        y += 1
    return y, m, d


DAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
          "Oct", "Nov", "Dec")
CLOCK_FILE = "/etc/clock"


def clock_now(sh):
    # (days_since_1970, seconds_of_day, None) or (None, None, reason)
    try:
        parts = sh.vfs.read(CLOCK_FILE).split()
        days = int(parts[0])
        secs = int(parts[1])
        mono = int(parts[2])
    except (VFSError, ValueError, IndexError):
        return None, None, "clock not set (date -s 'YYYY-MM-DD HH:MM:SS')"
    now = mono_s()
    if now is None:
        return None, None, "no clock available"
    el = now - mono
    if el < 0:
        return None, None, "clock lost, calculator restarted (date -s ...)"
    t = secs + el
    return days + t // 86400, t % 86400, None


def parse_stamp(parts):
    # ["2026-10-07", "17:20[:30]"] -> (days, secs) or None
    if len(parts) != 2:
        return None
    try:
        d = parts[0].split("-")
        t = parts[1].split(":")
        if len(d) != 3 or len(t) < 2 or len(t) > 3:
            return None
        y = int(d[0])
        mo = int(d[1])
        da = int(d[2])
        h = int(t[0])
        mi = int(t[1])
        se = 0
        if len(t) == 3:
            se = int(t[2])
    except ValueError:
        return None
    if y < 1970 or y > 2099 or not 1 <= mo <= 12 or not 1 <= da <= 31:
        return None
    if not (0 <= h < 24 and 0 <= mi < 60 and 0 <= se < 60):
        return None
    days = days_from_civil(y, mo, da)
    if civil_from_days(days) != (y, mo, da):      # e.g. Feb 30
        return None
    return days, h * 3600 + mi * 60 + se


def cmd_date(sh, args):
    # No wall clock exists in this Python, so the time is set by hand and
    # kept as (moment, monotonic counter) in /etc/clock. It survives
    # relaunching Arch84 but not a calculator restart, and may drift if
    # the counter pauses while the calculator sleeps.
    if args and args[0] == "-s":
        parts = args[1:]
        if len(parts) == 1:
            parts = parts[0].split(" ")
        st = parse_stamp(parts)
        now = mono_s()
        if st is None:
            sh.err("date: invalid date, use -s 'YYYY-MM-DD HH:MM[:SS]'")
            return 1
        if now is None:
            sh.err("date: no clock available")
            return 1
        try:
            sh.vfs.write(CLOCK_FILE, str(st[0]) + " " + str(st[1]) + " " + str(now) + "\n")
        except VFSError as e:
            sh.err("date: cannot save clock: " + str(e))
            return 1
    elif args:
        sh.err("usage: date [-s 'YYYY-MM-DD HH:MM[:SS]']")
        return 1
    days, secs, why = clock_now(sh)
    if why:
        sh.err("date: " + why)
        return 1
    y, m, d = civil_from_days(days)
    sh.out(DAYS[(days + 4) % 7] + " " + MONTHS[m - 1] + " " + pad(d, 2) + " "
           + ("0" + str(secs // 3600))[-2:] + ":" + ("0" + str(secs // 60 % 60))[-2:]
           + ":" + ("0" + str(secs % 60))[-2:] + " " + str(y) + "\n")


def cmd_reboot(sh, args):
    if not sh.shutdown("reboot"):
        return 1


def cmd_poweroff(sh, args):
    sh.shutdown("poweroff")


COMMANDS.update({
    "true": cmd_true, "false": cmd_false, "grep": cmd_grep, "find": cmd_find,
    "sort": cmd_sort, "wc": cmd_wc, "basename": cmd_basename,
    "dirname": cmd_dirname, "du": cmd_du, "df": cmd_df, "free": cmd_free,
    "mount": cmd_mount, "umount": cmd_umount, "uptime": cmd_uptime,
    "date": cmd_date, "reboot": cmd_reboot, "poweroff": cmd_poweroff,
})
