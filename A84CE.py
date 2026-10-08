# A84CE: shell-environment commands (Arch84 module, split from A84CD to keep
# each module's compile-time memory peak low). Registers into A84CD.COMMANDS.

from A84FS import StorageError, VERSION
from A84PE import isname
from A84CD import COMMANDS, LAZY, need


def cmd_history(sh, args):
    if args and args[0] == "-c":
        while sh.k.history:
            sh.k.history.pop()
        return
    h = sh.k.history
    for i in range(len(h)):
        sh.out(str(i + 1) + "  " + h[i] + "\n")


def cmd_uname(sh, args):
    host = sh.k.hostname()
    if not args:
        sh.out("Arch84\n")
        return
    parts = []
    for a in args:
        if a == "-a":
            parts = ["Arch84", host, VERSION, "evo", "Python"]
            break
        elif a == "-s":
            parts.append("Arch84")
        elif a == "-n":
            parts.append(host)
        elif a == "-r":
            parts.append(VERSION)
        else:
            sh.err("uname: invalid option '" + a + "'")
            return 1
    sh.out(" ".join(parts) + "\n")


def cmd_whoami(sh, args):
    sh.out(sh.k.env.get("USER", "evo") + "\n")


def cmd_hostname(sh, args):
    sh.out(sh.k.hostname() + "\n")


def cmd_env(sh, args):
    names = list(sh.k.env.keys())
    names.sort()
    for n in names:
        sh.out(n + "=" + sh.k.env[n] + "\n")


def cmd_export(sh, args):
    if not args:
        return cmd_env(sh, args)
    st = 0
    for a in args:
        i = a.find("=")
        name = a
        if i >= 0:
            name = a[:i]
        ok = name != "" and not ("0" <= name[0] <= "9")
        for c in name:
            if not isname(c):
                ok = False
        if not ok:
            sh.err("export: '" + a + "': not a valid identifier")
            st = 1
        elif i >= 0:
            sh.k.env[name] = a[i + 1:]
        elif name not in sh.k.env:
            sh.k.env[name] = ""
    return st


def cmd_alias(sh, args):
    if not args:
        names = list(sh.k.aliases.keys())
        names.sort()
        for n in names:
            sh.out("alias " + n + "='" + sh.k.aliases[n] + "'\n")
        return
    for a in args:
        i = a.find("=")
        if i <= 0:
            if a in sh.k.aliases:
                sh.out("alias " + a + "='" + sh.k.aliases[a] + "'\n")
            else:
                sh.err("alias: " + a + ": not found")
                return 1
        else:
            sh.k.aliases[a[:i]] = a[i + 1:]


def cmd_unalias(sh, args):
    if not need(sh, "unalias", args):
        return 1
    st = 0
    for a in args:
        if a in sh.k.aliases:
            del sh.k.aliases[a]
        else:
            sh.err("unalias: " + a + ": not found")
            st = 1
    return st


def cmd_which(sh, args):
    if not need(sh, "which", args):
        return 1
    st = 0
    for a in args:
        if a in sh.k.aliases:
            sh.out(a + ": aliased to " + sh.k.aliases[a] + "\n")
        elif a in COMMANDS or a in LAZY:
            sh.out(a + ": shell built-in command\n")
        else:
            found = False
            for d in sh.k.env.get("PATH", "").split(":"):
                if d != "" and sh.vfs.isfile(d.rstrip("/") + "/" + a):
                    sh.out(d.rstrip("/") + "/" + a + "\n")
                    found = True
                    break
            if not found:
                sh.err(a + " not found in " + sh.k.env.get("PATH", ""))
                st = 1
    return st


def cmd_sync(sh, args):
    sh.k.spin("Syncing filesystem")
    try:
        raw, stored, blocks, warns = sh.k.sync("-f" in args)
    except StorageError as e:
        sh.k.stop_spin()
        sh.err("sync: " + str(e))
        return 1
    sh.k.stop_spin()
    sh.out("synced " + str(raw) + " -> " + str(stored) + " bytes, "
           + str(blocks) + " blocks\n")
    for w in warns:
        sh.err("sync: warning: " + w)


def cmd_keys(sh, args):
    sh.out("alpha=1 letter  2nd+alpha=lock\n"
           "2nd then letter = UPPER\n"
           "mode=Tab del=bksp clear=clr\n"
           "2nd+: <=home >=end del=del\n"
           "mem=space (-)=_ stat=~\n"
           "Y=\" window' zoom$ trace> graph=\n"
           "math or trace = >  2nd+()-+={}[]\n"
           "x^=^ /*-+ . , ( )\n"
           "sin=<  x^-1=|  x^2=\\\n"
           "2nd+up/down = scroll\n")


def unload_selftest():
    # the test modules (~15 KB resident) are only needed while testing: drop
    # them on the calculator so a later sync/command has the memory back
    import sys
    if getattr(sys.implementation, "name", "") != "micropython":
        return                  # desktop tests patch and re-run the module
    try:
        for m in ("A84TS", "A84TD", "A84TX"):
            if m in sys.modules:
                del sys.modules[m]
    except Exception:
        pass
    import gc
    gc.collect()


def cmd_selftest(sh, args):
    # runs in a sandbox shell; never touches the real filesystem
    try:
        from A84TS import selftest
    except ImportError:
        sh.err("selftest: module A84TS is not installed")
        return 1
    except MemoryError:
        sh.err("selftest: out of memory loading the test modules (try reboot first)")
        return 1
    try:
        return selftest(sh, args)
    finally:
        selftest = None         # drop the last reference, then unload
        unload_selftest()


def cmd_exit(sh, args):
    sh.shutdown("exit")


COMMANDS.update({
    "history": cmd_history, "uname": cmd_uname, "whoami": cmd_whoami,
    "hostname": cmd_hostname, "env": cmd_env, "export": cmd_export,
    "alias": cmd_alias, "unalias": cmd_unalias, "which": cmd_which,
    "sync": cmd_sync, "keys": cmd_keys, "selftest": cmd_selftest,
    "exit": cmd_exit,
})
