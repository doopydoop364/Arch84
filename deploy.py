#!/usr/bin/env python3
"""Send Arch84 to the calculator.

  python3 deploy.py             RAM copies (these run) + Archive backups (<name>BAK)
  python3 deploy.py --no-bak    RAM copies only
  python3 deploy.py --bak-only  Archive backups only
  python3 deploy.py --dry-run   show what would be sent

Backups live in the calculator's Archive, so they survive a RAM clear. Each
backup is a complete second system: its imports are renamed (A84FS ->
A84FSBAK, ...) so ARC84BAK runs on its own once the *BAK programs are
unarchived to RAM. (ARCH84BAK would be 9 characters; names allow 8.)

Backups are only rewritten when their content changed, to spare flash.
evo_usb.py is used as a library and is not modified.
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MODULES = ["A84FS", "A84V1", "A84CZ", "A84ST", "A84PE", "A84KN", "A84UI", "A84GX", "A84CD", "A84CE", "A84CP", "A84C2", "A84C3", "A84C4", "A84C5", "A84C6", "A84C7", "A84C8", "A84C9", "A84CA", "A84CB", "A84MN", "A84PF", "A84ED", "A84EV", "A84PM", "A84PS", "A84PQ", "A84PD", "A84PI", "A84PB", "A84PL", "A84PX", "A84AI", "A84AR", "A84AE", "A84AX", "A84FK", "A84SC", "A84SD",
           "A84SH", "A84TD", "A84TX", "A84TS"]
LAUNCHER = "ARCH84"
BAK_LAUNCHER = "ARC84BAK"
STATE = os.path.join(HERE, ".deploy_state.json")
HEADER = "# BACKUP COPY made by deploy.py; imports point at the *BAK modules\n"


def bak_name(name):
    if name == LAUNCHER:
        return BAK_LAUNCHER
    return name + "BAK"


def bak_source(text):
    pat = re.compile(r"\b(" + "|".join(MODULES) + r")\b")
    return HEADER + pat.sub(lambda m: m.group(1) + "BAK", text)


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main(argv):
    no_bak = "--no-bak" in argv
    bak_only = "--bak-only" in argv
    dry = "--dry-run" in argv
    names = MODULES + [LAUNCHER]
    for n in names:
        if not os.path.isfile(os.path.join(HERE, n + ".py")):
            sys.exit("missing source: " + n + ".py")
    if dry:
        for n in names:
            print(("RAM  " if not bak_only else "-    ") + n + "  ->  "
                  + ("-" if no_bak else "ARC  " + bak_name(n)))
        return
    import evo_usb as e
    for n in names:
        if not e.is_valid_evo_python_name(bak_name(n)):
            sys.exit("invalid backup name: " + bak_name(n))
    listing = {}
    if not no_bak:
        for f in e.list_files():
            listing[f["name"]] = f
    state = load_state()
    for n in names:
        path = os.path.join(HERE, n + ".py")
        if not bak_only:
            e.send_file(path, n)
        if no_bak:
            continue
        with open(path) as f:
            text = bak_source(f.read())
        bn = bak_name(n)
        h = hashlib.sha256(text.encode()).hexdigest()
        have = listing.get(bn)
        if have is not None and have.get("mem") and state.get(bn) == h:
            print("backup " + bn + " up to date")
            continue
        payload = e.build_payload(bn, text)
        data = payload + e.evo_checksum(payload).to_bytes(2, "big")
        e._put_var_file_to_target(bn, data, archive=True)
        state[bn] = h
        with open(STATE, "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main(sys.argv[1:])
