# A84CE: shell-environment commands (Arch84 module, split from A84CD to keep
# each module's compile-time memory peak low). Registers into A84CD.COMMANDS.

from A84FS import StorageError
from A84PE import isname
from A84CD import COMMANDS, need


def cmd_history(sh, args):
    if args and args[0] == "-c":
        while sh.k.history:
            sh.k.history.pop()
        return
    h = sh.k.history
    for i in range(len(h)):
        sh.out(str(i + 1) + "  " + h[i] + "\n")


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


def cmd_exit(sh, args):
    sh.shutdown("exit")


COMMANDS.update({
    "history": cmd_history, "env": cmd_env, "export": cmd_export,
    "alias": cmd_alias, "unalias": cmd_unalias, "sync": cmd_sync, "exit": cmd_exit,
})
