"""ti_draw shim: counts draw calls and filled pixels (a display-cost proxy)."""
CALLS = 0
PIXELS = 0
TEXTS = 0
CHARS = 0
LAST = {}


def set_color(r, g, b):
    if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
        raise ValueError("color")


def fill_rect(x, y, w, h):
    global CALLS, PIXELS
    CALLS += 1
    PIXELS += max(w, 0) * max(h, 0)


def draw_text(x, y, text):
    global CALLS, TEXTS, CHARS
    CALLS += 1
    TEXTS += 1
    CHARS += len(text)
    LAST[y] = (x, text)


def draw_rect(*a):
    pass


def draw_line(*a):
    pass


def show_draw():
    raise RuntimeError("show_draw blocks on the device")
