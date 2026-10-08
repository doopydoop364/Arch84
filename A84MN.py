# A84MN: `man` - the manual pages (Arch84 module, lazily loaded; unloads itself after use).
# GENERATED from docs/manpages.txt by tools/genman.py - edit that file, not this one.
# One line per page: name TAB usage TAB description.
from A84CD import COMMANDS, all_commands, unload

PAGES = (
    (
        '[\t[ EXPR ]\tsame as test; the last argument must be ]\n'
        'alias\talias [NAME[=VALUE]...]\tlist or define aliases (first word of a command)\n'
        'archive\tarchive create NAME PATH... | extract [-k] NAME | list | check [NAME] | delete NAME\tpack files into compressed calculator lists and take them out of RAM; extract brings them back (-k keeps the archive). Needs ~25 KB free heap.\n'
        'basename\tbasename PATH [SUFFIX]\tlast part of a path, minus SUFFIX\n'
        'cat\tcat [FILE...]\tprint files, or standard input (- also means standard input)\n'
        'cd\tcd [DIR]\tchange directory (default: home)\n'
        'clear\tclear\tclear the screen and the scrollback\n'
        'cp\tcp [-r] SRC... DEST\tcopy files; -r copies directories (files share their text, so copies are cheap)\n'
        'cut\tcut -d C -f LIST | -c LIST [FILE...]\tprint chosen fields (-f) or characters (-c); LIST is like 1,3-5,7-\n'
    ),
    (
        "date\tdate [-s 'YYYY-MM-DD HH:MM[:SS]']\tshow or set the date; the calculator has no clock, so it is kept from the moment you set it\n"
        'df\tdf\traw and stored size of the filesystem and how many lists it uses\n'
        'dirname\tdirname PATH\teverything but the last part of a path\n'
        'du\tdu [-s] [PATH...]\tcharacters used by files; -s only totals\n'
        'echo\techo [-n] [WORD...]\tprint the words; -n omits the newline\n'
        'edit\tedit FILE\tfull-screen editor. CLEAR = command line: w save, q quit, qq quit without saving, wq, N go to line, /text find, n next, d y p cut/copy/paste a line, u undo (again = redo), s/a/b/ and %s/a/b/ replace\n'
        'env\tenv\tlist the environment variables\n'
        'exit\texit\tsave and leave Arch84\n'
        'export\texport [NAME[=VALUE]...]\tset environment variables (no arguments: list them)\n'
    ),
    (
        'expr\texpr A OP B\tinteger arithmetic: + - * / %\n'
        'false\tfalse\tdo nothing, unsuccessfully\n'
        'find\tfind [PATH] [-name PATTERN] [-type f|d]\tlist files below PATH; PATTERN may use * and ?\n'
        'free\tfree\theap memory: total, used, free\n'
        'fsck\tfsck [-r]\tcheck the saved filesystem, archives, packages and system files; -r repairs what is safe\n'
        'grep\tgrep [-ivnc] PATTERN [FILE...]\tprint lines containing PATTERN (text, not a regular expression); -i ignore case, -v invert, -n numbers, -c count\n'
        'head\thead [-n N] [FILE...]\tfirst N lines (default 10)\n'
        'help\thelp [COMMAND]\tlist all commands, or show the page of one\n'
        'history\thistory [-c]\tnumbered command history; -c clears it\n'
        'hostname\thostname\tshow the host name (from /etc/hostname)\n'
        'keys\tkeys\thow to type symbols on the calculator keys\n'
    ),
    (
        'ls\tls [-a] [-l] [PATH...]\tlist a directory; -a shows dot files, -l shows sizes (directories end in /)\n'
        'makepkg\tmakepkg [-d DEP]... DIR NAME VERSION [DESCRIPTION]\tpack the tree in DIR (laid out like /) into /var/cache/pacman/pkg/NAME-VERSION.ar84\n'
        'man\tman [COMMAND | -k WORD]\tmanual page of a command; -k lists pages mentioning WORD\n'
        'mkdir\tmkdir [-p] DIR...\tmake directories; -p makes parents too and accepts existing ones\n'
        'mount\tmount\tshow the root filesystem and where it is stored\n'
        'mv\tmv SRC... DEST\tmove or rename\n'
        'nl\tnl [FILE...]\tnumber lines\n'
        'pacman\tpacman -U FILE | -S NAME | -R NAME | -Q[ilkop] [ARG] | -Sl\t.ar84 packages. -U install a file, -S install from /var/cache/pacman/pkg with its dependencies, -R remove, -Q list, -Qi info, -Ql files, -Qk verify files, -Qo owner of a path, -Qp inspect a package file, -Sl list the repository\n'
    ),
    (
        'poweroff\tpoweroff\tsave and leave Arch84\n'
        'pwd\tpwd\tprint the current directory\n'
        'reboot\treboot\tsave and restart Arch84\n'
        'rev\trev [FILE...]\treverse each line\n'
        'rm\trm [-rf] PATH...\tremove files; -r directories too, -f ignores missing names\n'
        'rmdir\trmdir DIR...\tremove empty directories\n'
        "sed\tsed [-n] 'COMMAND[;COMMAND...]' [FILE...]\tedit lines of standard input or files. Addresses: N, N,M, /text/. Commands: s/old/new/[g][p] (plain text, & = the match), d delete, p print; -n prints only what p says. Quote the script: ; also separates shell commands\n"
        'selftest\tselftest\trun the built-in tests in a sandbox (needs free memory; reboot first)\n'
        'seq\tseq [FIRST [STEP]] LAST\tprint numbers (at most 2000)\n'
        'sort\tsort [-rnu] [FILE...]\tsort lines; -r reverse, -n numeric, -u drop duplicates\n'
    ),
    (
        'sync\tsync [-f]\tsave the filesystem now; -f overwrites a save that failed to load\n'
        'tail\ttail [-n N] [FILE...]\tlast N lines (default 10)\n'
        'tee\ttee [-a] FILE...\tcopy standard input to the output and to the files; -a appends\n'
        'test\ttest EXPR   or   [ EXPR ]\tconditions for scripts: -e -f -d PATH, -z -n STRING, A = B, A != B, A -eq|-ne|-lt|-le|-gt|-ge B, ! EXPR. Status 0 = true\n'
        'touch\ttouch FILE...\tcreate empty files\n'
        'tr\ttr SET1 SET2   or   tr -d SET\ttranslate or delete characters read from standard input; sets may use ranges a-z and \\n\n'
        'true\ttrue\tdo nothing, successfully\n'
        'umount\tumount PATH\tonly reports that / is busy: nothing else can be mounted\n'
        'unalias\tunalias NAME...\tremove aliases\n'
        'uname\tuname [-a|-s|-n|-r]\tsystem name, host, version\n'
    ),
    (
        'uniq\tuniq [-cd] [FILE]\tcollapse repeated neighbouring lines; -c counts, -d only repeated ones\n'
        'uptime\tuptime\ttime since Arch84 started and the calculator tick counter\n'
        'wc\twc [-lwc] [FILE...]\tlines, words, characters\n'
        'which\twhich NAME...\twhat a command name refers to (alias, built-in, or a file on PATH)\n'
        'whoami\twhoami\tshow the user name\n'
    ),
)


def find(name):
    for chunk in PAGES:
        i = chunk.find(name + "\t")
        while i >= 0:
            if i == 0 or chunk[i - 1] == "\n":
                j = chunk.find("\n", i)
                return chunk[i:j].split("\t")
            i = chunk.find(name + "\t", i + 1)
    return None


def cmd_man(sh, args):
    try:
        return run(sh, args)
    finally:
        unload("man", "A84MN")


def run(sh, args):
    if not args or args[0][:1] == "-" and args[0] != "-k" or args[0] == "-k" and len(args) != 2:
        sh.err("usage: man COMMAND | man -k WORD")
        return 1
    if args[0] == "-k":
        word = args[1]
        hit = False
        for chunk in PAGES:
            for line in chunk.split("\n"):
                if line != "" and word in line:
                    f = line.split("\t")
                    sh.out(f[0] + " - " + f[2][:40] + "\n")
                    hit = True
        if not hit:
            sh.err("man: nothing appropriate: " + word)
            return 1
        return 0
    st = 0
    for name in args:
        page = find(name)
        if page is None:
            if name in all_commands():
                sh.err("man: no manual page for " + name)
            else:
                sh.err("man: no such command: " + name)
            st = 1
            continue
        sh.out(page[0] + " - " + page[2] + "\nusage: " + page[1] + "\n")
    return st


COMMANDS["man"] = cmd_man
