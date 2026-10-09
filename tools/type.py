#!/usr/bin/env python3
"""Type into a running Arch84 on the calculator by injecting key presses.

  python3 tools/type.py "ls -l" "echo hi > a.txt"      type each argument + Enter
  python3 tools/type.py --no-enter "ec{tab}"            {tab} {bs} {left} ... are keys
  python3 tools/type.py --dry-run "echo Hi"             show the key codes only

How it works (verified on a real TI-84 Evo, OS 7.0): evo_usb.py --key sends
standard TI-84 CE *scancodes* (Enter = 9, ) = 0x15, prgm = 0x1F, ...) and
get_key() reports the positional code we already know (Enter 105, ) 64,
prgm 43). CSC maps one to the other. The keystroke plan (alpha, 2nd, alpha
lock) comes from the key tables of A84UI, the same ones the terminal uses, so
what is typed is what the terminal decodes (tests check this round trip).

Keys that are NOT injectable: on/home (they are not scancodes).
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import A84UI

# scancode -> get_key code (positional; measured: all 49 keys round-tripped)
CSC = {0x01: 34, 0x02: 24, 0x03: 26, 0x04: 25, 0x09: 105, 0x0A: 95, 0x0B: 85, 0x0C: 75,
       0x0D: 65, 0x0E: 55, 0x0F: 45, 0x11: 104, 0x12: 94, 0x13: 84, 0x14: 74, 0x15: 64,
       0x16: 54, 0x17: 44, 0x19: 103, 0x1A: 93, 0x1B: 83, 0x1C: 73, 0x1D: 63, 0x1E: 53,
       0x1F: 43, 0x20: 33, 0x21: 102, 0x22: 92, 0x23: 82, 0x24: 72, 0x25: 62, 0x26: 52,
       0x27: 42, 0x28: 32, 0x2A: 91, 0x2B: 81, 0x2C: 71, 0x2D: 61, 0x2E: 51, 0x2F: 41,
       0x30: 31, 0x31: 15, 0x32: 14, 0x33: 13, 0x34: 12, 0x35: 11, 0x36: 21, 0x37: 22,
       0x38: 23}
GK2CSC = dict((v, k) for k, v in CSC.items())

K2ND = 21
KALPHA = 31
ACTIONS = {"enter": 105, "tab": 22, "bs": 23, "left": 24, "up": 25, "right": 26,
           "down": 34, "clear": 45}
ACTIONS2 = {"del": 23, "home": 24, "end": 26, "pgup": 25, "pgdn": 34}   # 2nd + key


def _inverse():
    letters = {}
    for code, ch in A84UI.ALPHA.items():
        if ch.isalpha():
            letters[ch] = code
    plain = {}
    for code, ch in sorted(A84UI.NORM.items(), reverse=True):    # lowest code wins ties
        plain[ch] = code
    plain[">"] = 14                                              # trace (math also types >)
    second = dict((ch, code) for code, ch in A84UI.SEC.items() if ch not in plain)
    alpha_only = dict((ch, code) for code, ch in A84UI.ALPHA.items() if not ch.isalpha()
                      and ch not in plain)
    return letters, plain, second, alpha_only


def tokens(text):
    """text -> list of ("c", char) / ("k", action) / ("k2", 2nd+action)."""
    out = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == "{" and text[i:i + 2] == "{{":
            out.append(("c", "{"))
            i += 2
        elif c == "{" and "}" in text[i:]:
            j = text.index("}", i)
            name = text[i + 1:j]
            if name in ACTIONS:
                out.append(("k", name))
            elif name in ACTIONS2:
                out.append(("k2", name))
            else:
                raise ValueError("unknown key {%s}" % name)
            i = j + 1
        else:
            out.append(("c", c))
            i += 1
    return out


def plan(text):
    """The get_key codes to press, in order, to type `text` into Arch84."""
    letters, plain, second, alpha_only = _inverse()
    toks = tokens(text)
    codes = []
    i = 0
    while i < len(toks):
        kind, v = toks[i]
        if kind == "k":
            codes.append(ACTIONS[v])
        elif kind == "k2":
            codes += [K2ND, ACTIONS2[v]]
        elif v.lower() in letters and v.isalpha():
            j = i
            while j < len(toks) and toks[j][0] == "c" and toks[j][1].isalpha() and toks[j][1].lower() in letters:
                j += 1
            run = [t[1] for t in toks[i:j]]
            if len(run) >= 2:
                codes += [K2ND, KALPHA]                           # alpha lock on
                for ch in run:
                    if ch.isupper():
                        codes.append(K2ND)                        # next letter upper-case
                    codes.append(letters[ch.lower()])
                codes.append(KALPHA)                              # lock off
            else:
                ch = run[0]
                codes.append(KALPHA)                              # one letter
                if ch.isupper():
                    codes.append(K2ND)
                codes.append(letters[ch.lower()])
            i = j
            continue
        elif v in plain:
            codes.append(plain[v])
        elif v in second:
            codes += [K2ND, second[v]]
        elif v in alpha_only:
            codes += [KALPHA, alpha_only[v]]
        else:
            raise ValueError("cannot type %r" % v)
        i += 1
    return codes


def to_scancodes(codes):
    return [GK2CSC[c] for c in codes]


def inject(codes, delay=0.12):
    import evo_usb
    evo_usb.send_scancodes(to_scancodes(codes), delay=delay)


def main(argv):
    delay = 0.12
    wait = 1.0
    enter = True
    dry = False
    cmds = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--delay":
            delay = float(argv[i + 1]); i += 1
        elif a == "--wait":
            wait = float(argv[i + 1]); i += 1
        elif a == "--no-enter":
            enter = False
        elif a == "--dry-run":
            dry = True
        else:
            cmds.append(a)
        i += 1
    for n, cmd in enumerate(cmds):
        codes = plan(cmd) + ([105] if enter else [])
        if dry:
            print(cmd, "->", codes)
            continue
        inject(codes, delay)
        if n + 1 < len(cmds):
            time.sleep(wait)


if __name__ == "__main__":
    main(sys.argv[1:])
