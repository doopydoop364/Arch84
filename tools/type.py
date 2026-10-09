#!/usr/bin/env python3
"""Type into a running Arch84 on the calculator by injecting key presses.

  python3 tools/type.py "ls -l" "echo hi > a.txt"      type each argument + Enter
  python3 tools/type.py --no-enter "ec{tab}"            {tab} {bs} {left} ... are keys
  python3 tools/type.py --dry-run "echo Hi"             show the key codes only
  python3 tools/type.py --idle --sc 0x1F,0x01,0x09,0x09   press keys by scancode (starts ARCH84 from the home screen)
  python3 tools/type.py --idle --shot out.png "selftest 2"   wait for the screen to settle, then screenshot

Busy refusals (CALCULATOR_BUSY) are retried; other transport errors stop and say how many keys went out.

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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from usblock import usb_lock

from csc import CSC, GK2CSC      # scancode <-> positional get_key code (all 49 keys verified)

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


def _transient(err):
    text = str(err)
    return "BZ" in text or "CALCULATOR_BUSY" in text


def _inject(codes, delay=0.12, patience=120):
    """Press the keys in order. A key refused because the calculator is busy
    (BZ / CALCULATOR_BUSY: it was NOT delivered) is retried until `patience`
    seconds have passed; any other transport error stops with the number of
    keys already delivered (the caller decides, a retry could double a key)."""
    import evo_usb
    scs = to_scancodes(codes)
    done = 0
    t0 = time.time()
    wait = 0.5
    while done < len(scs):
        dev = None
        try:
            dev = evo_usb.connect()
            session = evo_usb.KermitSession()
            seq = 0
            pkt = evo_usb.make_packet(seq, "S", evo_usb.S_INIT, session=session)
            dev.write(pkt, timeout=evo_usb.TIMEOUT)
            _, rtype, rdata = evo_usb.parse_packet(bytes(dev.read(timeout=evo_usb.TIMEOUT)), session=session)
            if rtype == "E":
                raise RuntimeError("init: " + evo_usb.transfer_error_text(rdata))
            if rtype == "Y":
                session.update_from_send_init(rdata)
            seq += 1
            while done < len(scs):
                seq = evo_usb.send_scancode_packet(dev, session, seq, scs[done])
                done += 1
                if delay:
                    time.sleep(delay)
            pkt = evo_usb.make_packet(seq, "B", b"", session=session)
            dev.write(pkt, timeout=evo_usb.TIMEOUT)
            dev.read(timeout=evo_usb.TIMEOUT)
        except RuntimeError as e:
            if not _transient(e) or time.time() - t0 > patience:
                raise RuntimeError("%s (delivered %d of %d keys)" % (e, done, len(scs)))
            time.sleep(wait)
            wait = min(wait * 2, 8.0)
        except Exception as e:
            raise RuntimeError("%s: %s (delivered %d of %d keys)" % (type(e).__name__, str(e)[:80], done, len(scs)))
        finally:
            if dev is not None:
                try:
                    evo_usb.release(dev)
                except Exception:
                    pass


def inject(codes, delay=0.12, patience=120):
    # one USB conversation at a time (the network bridge polls the same link)
    with usb_lock(timeout=max(patience, 60)):
        _inject(codes, delay, patience)


def screen_bytes():
    import evo_usb
    with usb_lock(timeout=60):
        return evo_usb._get_request(evo_usb._screen_url(0))


def _changed(a, b, limit=500):
    """True when two screens differ by more than a blinking cursor or a spinner
    (limit bytes of the raw frame; a cursor block is ~360, new text is thousands)."""
    if a is None or b is None or len(a) != len(b):
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            n += 1
            if n > limit:
                return True
    return False


def wait_idle(quiet=4.0, timeout=240, poll=1.5):
    """Block until the screen has not really changed for `quiet` seconds (a command
    that is still printing or computing keeps changing it; a blinking cursor does
    not count). Returns True when idle."""
    t0 = time.time()
    last = None
    since = time.time()
    while time.time() - t0 < timeout:
        try:
            cur = screen_bytes()
        except Exception:
            time.sleep(poll)
            continue
        if _changed(last, cur):
            since = time.time()
        elif time.time() - since >= quiet:
            return True
        last = cur
        time.sleep(poll)
    return False


def shot(path):
    import evo_usb
    with usb_lock(timeout=60):
        evo_usb.take_screenshot(path)


def main(argv):
    delay = 0.12
    wait = 1.0
    enter = True
    dry = False
    idle = False
    out = None
    cmds = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--delay":
            delay = float(argv[i + 1]); i += 1
        elif a == "--wait":
            wait = float(argv[i + 1]); i += 1
        elif a == "--idle":
            idle = True             # wait for the screen to settle after each command
        elif a == "--shot":
            out = argv[i + 1]; i += 1   # screenshot after the last command
        elif a == "--sc":
            raw = [int(x, 0) for x in argv[i + 1].split(",")]    # raw scancodes (e.g. launch: 0x1F,0x01,0x09,0x09)
            inject([CSC[x] for x in raw], delay)
            i += 1
            if idle:
                wait_idle()
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
        if idle:
            if not wait_idle():
                print("warning: screen still changing after the timeout", file=sys.stderr)
        elif n + 1 < len(cmds):
            time.sleep(wait)
    if out and not dry:
        if idle:
            wait_idle(quiet=1.5)
        shot(out)


if __name__ == "__main__":
    main(sys.argv[1:])
