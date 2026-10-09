"""Read the Arch84 network frames off a calculator screenshot.

Arch84 draws a request as rows of characters (A84NT.ALPHA, 5 bits each) in the calculator's
10x18 pixel text cells. Glyphs are crisp (no anti-aliasing), so each cell is matched exactly
against templates learned once from a screenshot of the alphabet (tools/glyphs.json):

    python3 tools/a84screen.py --learn alphabet.rgb       (raw 320x240 RGB565, see learn())

Layout: the canvas starts 30 px below the top (status bar); text row r is at y = 30 + 18 r.
Row 0 of a frame is a banner, rows 1..10 carry the frame symbols in text columns 1..30.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import A84NT

CELL_W, CELL_H = 10, 18
CANVAS_Y = 30
W, H = 320, 240
GLYPHS = os.path.join(HERE, "glyphs.json")
_templates = {}


def white(rgb, x, y):
    o = (y * W + x) * 2
    v = rgb[o] | (rgb[o + 1] << 8)
    return (((v >> 11) & 31) << 3) + (((v >> 5) & 63) << 2) + ((v & 31) << 3) > 300


def cell_bits(rgb, row, col):
    """The 10x17 pixels of a text cell as bytes of 0/1 (the y = CANVAS_Y line is skipped)."""
    x0 = col * CELL_W
    y0 = CANVAS_Y + row * CELL_H + 1
    out = bytearray()
    for y in range(y0, y0 + CELL_H - 1):
        for x in range(x0, x0 + CELL_W):
            out.append(1 if white(rgb, x, y) else 0)
    return bytes(out)


def pack(bits):
    return bytes(bits).hex()


def learn(rgb, path=GLYPHS):
    """Learn the glyphs from a screenshot: text row 0 = " " + ALPHA[:30], row 1 = " " + ALPHA[2:]
    (every symbol once in an interior cell)."""
    t = {}
    for i in range(30):
        t[pack(cell_bits(rgb, 0, i + 1))] = i
    for j in range(30):
        sym = j + 2
        if sym >= 30:
            t[pack(cell_bits(rgb, 1, j + 1))] = sym
    # row 1 must agree with row 0 on the symbols they share
    for j in range(28):
        if t.get(pack(cell_bits(rgb, 1, j + 1))) != j + 2:
            raise SystemExit("rows 0 and 1 disagree at symbol %d: is the screenshot right?" % (j + 2))
    if sorted(set(t.values())) != list(range(32)):
        raise SystemExit("the alphabet cells are not all different: is the screenshot right?")
    with open(path, "w") as f:
        json.dump({"alphabet": A84NT.ALPHA, "cells": t}, f)
    _templates.clear()
    return t


def templates():
    if not _templates:
        d = json.load(open(GLYPHS))
        if d["alphabet"] != A84NT.ALPHA:
            raise SystemExit("tools/glyphs.json does not match A84NT.ALPHA: run --learn again")
        _templates.update(d["cells"])
    return _templates


BLANK = pack(bytes(CELL_W * (CELL_H - 1)))


def read_symbols(rgb, rows=range(1, A84NT.ROWS + 1), quick=False):
    """Symbols of the frame cells (-1 for a cell that is blank/unknown)."""
    t = templates()
    out = []
    for r in rows:
        for c in range(1, A84NT.COLS + 1):          # column 0 stays blank
            if quick and len(out) >= 2:
                return out
            out.append(t.get(pack(cell_bits(rgb, r, c)), -1))
    return out


def read_frame(rgb):
    """The frame on the screen -> (type, seq, payload), or None when there is none (or it is damaged)."""
    first = read_symbols(rgb, rows=[1], quick=True)
    if len(first) < 2 or first[0] != 21 or first[1] < 0:      # 0xA8 = symbols 21, 2..: the frame magic
        return None
    syms = read_symbols(rgb)
    if -1 in syms[:12]:
        return None
    data = A84NT.from_symbols(syms[:12])
    n = (data[5] << 8) | data[6]
    need = ((11 + n) * 8 + 4) // 5
    if need > len(syms) or -1 in syms[:need]:
        return None
    return A84NT.parse(A84NT.from_symbols(syms[:need]))


def grab():
    """Screenshot of the calculator as raw RGB565 bytes."""
    import evo_usb
    from usblock import usb_lock
    with usb_lock(timeout=60):
        raw = evo_usb._get_request(evo_usb._screen_url(0))
    return evo_usb.screen_rgb565_from_payload(raw)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--learn":
        print(len(learn(open(sys.argv[2], "rb").read())), "glyphs learned")
    elif len(sys.argv) == 2 and sys.argv[1] == "--read":
        print(read_frame(grab()))
    else:
        print(__doc__)
