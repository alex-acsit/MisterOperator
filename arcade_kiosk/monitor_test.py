"""MisterOperator: monitor test patterns and a live input tester for the
operator menu, plus finding the 240p Test Suite on the SD card.

The patterns follow the ones in Artemio Urbina's 240p Test Suite (grid,
colour bars, black and white level, grey ramps, purity, overscan,
linearity, sharpness). They are drawn by the kiosk at the menu core's
resolution and refresh (320x240, 15 kHz with the [menu] video_mode in
MiSTer.ini), straight onto the raster, so a TATE monitor sees them exactly
as a YOKO one does. For tests at a console's own 240p timing, launch the
real suite (TEST SUITE in the operator menu).
"""

import os
import re
import time

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREY = (128, 128, 128)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------
def _scale(rgb, pct):
    return tuple(v * pct // 100 for v in rgb)


def _hline(c, x, y, w, rgb, t=1):
    c.fill(x, y, w, t, rgb)


def _vline(c, x, y, h, rgb, t=1):
    c.fill(x, y, t, h, rgb)


def _circle(c, cx, cy, r, rgb, t=2):
    """A circle outline, t pixels thick (midpoint algorithm, one run per row)."""
    for k in range(t):
        rr = r - k
        x, y, err = rr, 0, 1 - rr
        pts = set()
        while x >= y:
            for px, py in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
                pts.add((cx + px, cy + py))
            y += 1
            if err < 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1
        for px, py in pts:
            c.fill(px, py, 1, 1, rgb)


def _rows(c, row_a, row_b, y0, y1, period=1):
    """Fill rows y0..y1 alternating two prebuilt rows every `period` lines."""
    s = c.stride
    for y in range(max(0, y0), min(c.h, y1)):
        row = row_a if (y // period) % 2 == 0 else row_b
        c.buf[y * s:y * s + len(row)] = row


def _paste(src, dst, x, y):
    """Copy a small canvas onto a bigger one at (x, y)."""
    B = src.Bpp
    for r in range(src.h):
        yy = y + r
        if not 0 <= yy < dst.h:
            continue
        x0 = max(0, x)
        x1 = min(dst.w, x + src.w)
        if x1 <= x0:
            continue
        so = r * src.stride + (x0 - x) * B
        do = yy * dst.stride + x0 * B
        dst.buf[do:do + (x1 - x0) * B] = src.buf[so:so + (x1 - x0) * B]


# ---------------------------------------------------------------------------
# The patterns. Each draws on the whole canvas; `v` is the variant index.
# ---------------------------------------------------------------------------
def draw_grid(c, v):
    cell = (16, 20, 8, 32)[v]
    c.fill(0, 0, c.w, c.h, BLACK)
    # centre the grid so the middle lines land on the centre of the screen
    ox = (c.w // 2) % cell
    oy = (c.h // 2) % cell
    for x in range(ox, c.w, cell):
        _vline(c, x, 0, c.h, WHITE)
    for y in range(oy, c.h, cell):
        _hline(c, 0, y, c.w, WHITE)
    # edge of the picture in red, centre cross in red
    c.frame(0, 0, c.w, c.h, RED)
    _vline(c, c.w // 2, 0, c.h, RED)
    _hline(c, 0, c.h // 2, c.w, RED)
    return "GRID %d PX" % cell


def draw_convergence(c, v):
    c.fill(0, 0, c.w, c.h, BLACK)
    step = 16
    ox, oy = (c.w // 2) % step, (c.h // 2) % step
    if v == 0:                                   # dots
        for y in range(oy, c.h, step):
            for x in range(ox, c.w, step):
                c.fill(x, y, 1, 1, WHITE)
        return "CONVERGENCE: DOTS"
    if v == 1:                                   # crosses
        for y in range(oy, c.h, step):
            for x in range(ox, c.w, step):
                c.fill(x - 2, y, 5, 1, WHITE)
                c.fill(x, y - 2, 1, 5, WHITE)
        return "CONVERGENCE: CROSSES"
    # single-colour grids: a misconverged gun shows as a shifted grid
    col = (RED, GREEN, BLUE)[v - 2]
    for x in range(ox, c.w, step):
        _vline(c, x, 0, c.h, col)
    for y in range(oy, c.h, step):
        _hline(c, 0, y, c.w, col)
    return "CONVERGENCE: %s" % ("RED", "GREEN", "BLUE")[v - 2]


BAR_COLOURS = (WHITE, YELLOW, CYAN, GREEN, MAGENTA, RED, BLUE, BLACK)


def draw_colour_bars(c, v):
    pct = (75, 100)[v]
    n = len(BAR_COLOURS)
    top = c.h * 2 // 3
    for i, col in enumerate(BAR_COLOURS):
        x0, x1 = c.w * i // n, c.w * (i + 1) // n
        c.fill(x0, 0, x1 - x0, top, _scale(col, pct))
    # reversed strip (blue, black, magenta, black, cyan, black, white)
    mid = top + c.h // 12
    rev = (BLUE, BLACK, MAGENTA, BLACK, CYAN, BLACK, WHITE, BLACK)
    for i, col in enumerate(rev):
        x0, x1 = c.w * i // n, c.w * (i + 1) // n
        c.fill(x0, top, x1 - x0, mid - top, _scale(col, pct))
    # grey steps underneath, black to white
    steps = 8
    for i in range(steps):
        x0, x1 = c.w * i // steps, c.w * (i + 1) // steps
        g = 255 * i // (steps - 1)
        c.fill(x0, mid, x1 - x0, c.h - mid, (g, g, g))
    return "COLOUR BARS %d%%" % pct


def draw_level(c, v):
    if v == 0:
        # Black level: set BRIGHTNESS so the 0 bar matches the background and
        # the lowest bars are just visible.
        c.fill(0, 0, c.w, c.h, BLACK)
        levels = (0, 4, 8, 12, 16, 24, 32, 48)
        name = "BLACK LEVEL (BRIGHTNESS)"
    else:
        # White level: set CONTRAST so the top bars stay apart from the
        # background without blooming.
        c.fill(0, 0, c.w, c.h, WHITE)
        levels = (255, 251, 247, 243, 239, 231, 223, 207)
        name = "WHITE LEVEL (CONTRAST)"
    n = len(levels)
    bw = c.w // (n * 2)
    y0, y1 = c.h // 4, c.h * 3 // 4
    for i, lv in enumerate(levels):
        x = bw // 2 + i * bw * 2
        c.fill(x, y0, bw, y1 - y0, (lv, lv, lv))
    return name


def draw_ramps(c, v):
    steps = (32, 16, c.w)[v]
    bands = (RED, GREEN, BLUE, WHITE)
    bh = c.h // len(bands)
    for b, col in enumerate(bands):
        y0 = b * bh
        h = bh if b < len(bands) - 1 else c.h - y0
        for i in range(steps):
            x0, x1 = c.w * i // steps, c.w * (i + 1) // steps
            k = 255 * i // max(1, steps - 1)
            c.fill(x0, y0, max(1, x1 - x0), h, tuple(cc * k // 255 for cc in col))
    return "GREY RAMPS: %s" % ("32 STEPS", "16 STEPS", "SMOOTH")[v]


PURITY = ((WHITE, "WHITE"), (RED, "RED"), (GREEN, "GREEN"), (BLUE, "BLUE"),
          (GREY, "50% GREY"), (BLACK, "BLACK"))


def draw_purity(c, v):
    col, name = PURITY[v]
    c.fill(0, 0, c.w, c.h, col)
    return "PURITY: " + name


def draw_overscan(c, v):
    c.fill(0, 0, c.w, c.h, BLACK)
    marks = ((10, (90, 90, 90)), (7.5, BLUE), (5, GREEN), (2.5, YELLOW), (0, WHITE))
    for pct, col in marks:
        dx, dy = int(c.w * pct / 200), int(c.h * pct / 200)   # pct of the whole width
        c.frame(dx, dy, c.w - 2 * dx, c.h - 2 * dy, col)
    return "OVERSCAN 2.5/5/7.5/10%"


def draw_linearity(c, v):
    c.fill(0, 0, c.w, c.h, BLACK)
    step = 16
    ox, oy = (c.w // 2) % step, (c.h // 2) % step
    if v == 0:
        dim = (40, 40, 40)
        for x in range(ox, c.w, step):
            _vline(c, x, 0, c.h, dim)
        for y in range(oy, c.h, step):
            _hline(c, 0, y, c.w, dim)
    r = c.h // 2 - 2
    _circle(c, c.w // 2, c.h // 2, r, WHITE)
    small = c.h // 8
    for cx, cy in ((small + 2, small + 2), (c.w - small - 3, small + 2),
                   (small + 2, c.h - small - 3), (c.w - small - 3, c.h - small - 3)):
        _circle(c, cx, cy, small, WHITE)
    _vline(c, c.w // 2, c.h // 2 - 4, 9, WHITE)
    _hline(c, c.w // 2 - 4, c.h // 2, 9, WHITE)
    return "LINEARITY%s" % ("" if v == 0 else " (NO GRID)")


def draw_sharpness(c, v):
    c.fill(0, 0, c.w, c.h, BLACK)
    w, b = c.col(WHITE), c.col(BLACK)
    third = c.w // 3
    half = c.h // 2
    # top: vertical stripes 1 px | 2 px | checkerboard
    r1 = (w + b) * (third // 2) + b * (third % 2)
    r2 = (w * 2 + b * 2) * (third // 4) + b * (third % 4)
    rest = c.w - 2 * third
    ca = (w + b) * (rest // 2) + w * (rest % 2)
    cb = (b + w) * (rest // 2) + b * (rest % 2)
    _rows(c, r1 + r2 + ca, r1 + r2 + cb, 0, half)
    # bottom: horizontal stripes 1 px | 2 px | 4 px
    s = c.stride
    for y in range(half, c.h):
        row = bytearray(b * c.w)
        for i, period in enumerate((1, 2, 4)):
            if ((y - half) // period) % 2 == 0:
                x0 = c.w * i // 3
                x1 = c.w * (i + 1) // 3
                row[x0 * c.Bpp:x1 * c.Bpp] = w * (x1 - x0)
        c.buf[y * s:y * s + len(row)] = row
    return "SHARPNESS"


# (name, draw function, number of variants)
PATTERNS = (
    ("GRID", draw_grid, 4),
    ("CONVERGENCE", draw_convergence, 5),
    ("COLOUR BARS", draw_colour_bars, 2),
    ("BLACK/WHITE LEVEL", draw_level, 2),
    ("GREY RAMPS", draw_ramps, 3),
    ("PURITY", draw_purity, len(PURITY)),
    ("OVERSCAN", draw_overscan, 1),
    ("LINEARITY", draw_linearity, 2),
    ("SHARPNESS", draw_sharpness, 1),
)


class Patterns:
    """Full-screen test patterns. Left/right or button 1 changes the pattern,
    up/down changes its variant; the name shows for a few seconds."""

    LABEL_S = 3.0

    def __init__(self, canvas_type, rotation=0):
        self.idx = 0
        self.variant = 0
        self.rotation = rotation
        self.canvas_type = canvas_type          # Canvas class, for the label
        self.label_until = time.monotonic() + self.LABEL_S
        self.cache = None                       # (idx, variant, w, h, bytes)

    def step(self, d):
        self.idx = (self.idx + d) % len(PATTERNS)
        self.variant = 0
        self.show_label()

    def vary(self, d):
        n = PATTERNS[self.idx][2]
        self.variant = (self.variant + d) % n
        self.show_label()

    def show_label(self):
        self.label_until = time.monotonic() + self.LABEL_S

    def label_visible(self, now=None):
        return (now or time.monotonic()) < self.label_until

    def draw(self, c, rotate_fn=None):
        name, fn, n = PATTERNS[self.idx]
        key = (self.idx, self.variant, c.w, c.h)
        if self.cache and self.cache[0] == key:
            c.buf[:] = self.cache[2]
            title = self.cache[1]
        else:
            title = fn(c, self.variant)
            self.cache = (key, title, bytes(c.buf))
        if self.label_visible():
            self.draw_label(c, "%d/%d %s" % (self.idx + 1, len(PATTERNS), title),
                            "</>:NEXT  UP/DN:VARY  2:BACK" if n > 1 else "</>:NEXT  2:BACK",
                            rotate_fn)

    def draw_label(self, c, line1, line2, rotate_fn):
        # Drawn upright for the monitor: on a TATE screen the label is turned
        # like the menu is, while the pattern itself stays on the raster.
        portrait = self.rotation in (90, 270)
        cw = c.h if portrait else c.w
        chars = max(len(line1), len(line2))
        w = min(cw - 8, chars * 8 + 12)
        line1, line2 = line1[:(w - 12) // 8], line2[:(w - 12) // 8]
        lab = self.canvas_type(w, 28, c.fmt)
        lab.fill(0, 0, w, 28, (20, 20, 20))
        lab.frame(0, 0, w, 28, (40, 150, 85))
        lab.text(6, 5, line1, WHITE, (20, 20, 20))
        lab.text(6, 16, line2, (150, 150, 150), (20, 20, 20))
        if portrait and rotate_fn:
            rot = self.canvas_type(lab.h, lab.w, c.fmt)
            rotate_fn(lab, rot, self.rotation)
            # bottom of the upright picture = one side of the raster
            x = 6 if self.rotation == 90 else c.w - rot.w - 6
            _paste(rot, c, x, (c.h - rot.h) // 2)
        else:
            _paste(lab, c, (c.w - w) // 2, c.h - 28 - 8)


# ---------------------------------------------------------------------------
# Input test
# ---------------------------------------------------------------------------
class InputTest:
    """Shows every controller the kiosk holds: its stick, its buttons as they
    are pressed (named by their job in the kiosk), analogue values and
    spinner counts. Hold any one button for 3 s, or tap OPERATOR, to leave."""

    HOLD_EXIT_S = 3.0

    def __init__(self, kiosk):
        self.k = kiosk
        self.seen = {}          # dev.path -> [codes in the order first pressed]
        self.counts = {}        # (path, code) -> presses
        self.rel = {}           # dev.path -> [x, y, wheel]
        self.held = {}          # (path, code) -> time pressed
        self.last = ""

    def event(self, dev, t, c, v, now, code_name):
        if t == 1:              # EV_KEY
            if v == 1:
                lst = self.seen.setdefault(dev.path, [])
                if c not in lst:
                    lst.append(c)
                self.counts[(dev.path, c)] = self.counts.get((dev.path, c), 0) + 1
                self.held[(dev.path, c)] = now
                self.last = "%s %s" % (self.role(dev, c) or "", short_name(code_name(c)))
            elif v == 0:
                self.held.pop((dev.path, c), None)
        elif t == 2:            # EV_REL
            r = self.rel.setdefault(dev.path, [0, 0, 0])
            if c in (0, 1):
                r[c] += v
            else:
                r[2] += v

    def hold_progress(self, now):
        """Seconds the longest-held button has been down (0 if none)."""
        if not self.held:
            return 0.0
        return now - min(self.held.values())

    def should_exit(self, now):
        return self.hold_progress(now) >= self.HOLD_EXIT_S

    def role(self, dev, c):
        k = self.k
        if k.is_operator_btn(dev, c):
            return "OPERATOR"
        if k.is_menu_btn(dev, c):
            return "MENU"
        if c in k.coin_buttons:
            return "COIN"
        if c in k.launch_buttons:
            return "PLAY"
        if c in k.genre_buttons:
            return "GENRE+"
        if c in k.genre_back_buttons:
            return "GENRE-"
        if c in k.letter_buttons:
            return "LETTER"
        return ""

    def draw(self, c, theme, now, code_name, devices):
        BG, PANEL, LINE, ACCENT, TITLE, INFO, TEXT, DIM, SELECT = theme
        c.fill(0, 0, c.w, c.h, BG)
        c.text(8, 5, "INPUT TEST", TITLE, BG, scale=2)
        c.fill(0, 24, c.w, 2, ACCENT)
        chars = (c.w - 16) // 8
        y = 30
        devs = [d for d in devices if not getattr(d, "is_keys", False)]
        if not devs:
            c.text(8, y + 4, "NO CONTROLLERS FOUND", TEXT, BG)
        bottom = c.h - 30
        for dev in devs:
            if y > bottom - 22:
                c.text(8, y, "(MORE NOT SHOWN)", DIM, BG)
                break
            name = "%s %s" % (dev.vidpid, dev.name)
            c.text(8, y, name, INFO if dev.grabbed else DIM, BG, max_chars=chars)
            y += 10
            # stick: 3x3 boxes
            dx, dy = stick_direction(dev)
            sx, sy = 8, y
            for gy in range(3):
                for gx in range(3):
                    on = (gx - 1, gy - 1) == (dx, dy) and (dx or dy)
                    cx, cy = sx + gx * 7, sy + gy * 7
                    if on:
                        c.fill(cx, cy, 6, 6, ACCENT)
                    elif gx == 1 and gy == 1:
                        c.fill(cx + 2, cy + 2, 2, 2, LINE)
                    else:
                        c.frame(cx, cy, 6, 6, LINE)
            # buttons, in the order they were first pressed
            bx, by = 34, y
            for code in self.seen.get(dev.path, []):
                label = self.role(dev, code) or short_name(code_name(code))
                label = label[:9]
                w = len(label) * 8 + 6
                if bx + w > c.w - 6:
                    bx, by = 34, by + 11
                    if by > bottom - 10:
                        break
                down = code in dev.pressed
                if down:
                    c.fill(bx, by, w, 10, ACCENT)
                    c.text(bx + 3, by + 1, label, SELECT, ACCENT)
                else:
                    c.frame(bx, by, w, 10, LINE)
                    c.text(bx + 3, by + 1, label, TEXT, BG)
                bx += w + 3
            if not self.seen.get(dev.path):
                c.text(34, by + 1, "PRESS ITS BUTTONS", DIM, BG)
            y = max(y + 22, by + 12)
            # analogue / spinner values
            extra = analog_text(dev, self.rel.get(dev.path))
            if extra:
                c.text(34, y - 2, extra, DIM, BG, max_chars=chars - 4)
                y += 9
            c.fill(4, y, c.w - 8, 1, LINE)
            y += 4
        # footer
        fy = c.h - 14
        c.fill(0, fy - 16, c.w, 1, LINE)
        c.text(8, fy - 12, ("LAST: " + self.last.strip())[:chars] if self.last else "PRESS ANY CONTROL", TEXT, BG)
        p = self.hold_progress(now)
        if p >= 1.0:
            left = max(0, int(self.HOLD_EXIT_S - p + 0.99))
            c.text(8, fy, ("LEAVING IN %d..." % left)[:chars], TITLE, BG)
        else:
            c.text(8, fy, "HOLD A BUTTON 3S OR TAP OP: BACK"[:chars], DIM, BG)


def short_name(name):
    for pre in ("BTN_", "KEY_"):
        if name.startswith(pre):
            return name[len(pre):]
    return name


DPAD_KEYS = {103: (0, -1), 108: (0, 1), 105: (-1, 0), 106: (1, 0),       # KEY_UP/DOWN/LEFT/RIGHT
             0x220: (0, -1), 0x221: (0, 1), 0x222: (-1, 0), 0x223: (1, 0)}  # BTN_DPAD_*


def _axis_dir(dev, a):
    v = dev.abs_state.get(a)
    if v is None:
        return 0
    if a in (0x10, 0x11):                          # hat
        return (v > 0) - (v < 0)
    info = dev.absinfo.get(a, (0, -1, 1, 0, 0, 0))
    lo, hi = info[1], info[2]
    mid, span = (lo + hi) / 2.0, max(1, (hi - lo) / 2.0)
    n = (v - mid) / span
    return 1 if n > 0.5 else -1 if n < -0.5 else 0


def stick_direction(dev):
    dx = _axis_dir(dev, 0) or _axis_dir(dev, 0x10)
    dy = _axis_dir(dev, 1) or _axis_dir(dev, 0x11)
    for code, (kx, ky) in DPAD_KEYS.items():
        if code in dev.pressed:
            dx = dx or kx
            dy = dy or ky
    return dx, dy


AXIS_NAMES = {0: "X", 1: "Y", 2: "Z", 3: "RX", 4: "RY", 5: "RZ", 6: "THR", 7: "RUD",
              8: "WHL", 9: "GAS", 10: "BRK"}


def analog_text(dev, rel):
    parts = []
    for a in sorted(dev.absinfo):
        if a in AXIS_NAMES and a in dev.abs_state:
            parts.append("%s%d" % (AXIS_NAMES[a], dev.abs_state[a]))
    if rel and any(rel):
        parts.append("SPIN X%+d Y%+d" % (rel[0], rel[1]))
    return " ".join(parts[:6])


# ---------------------------------------------------------------------------
# The 240p Test Suite (a console ROM, run on its MiSTer core)
# ---------------------------------------------------------------------------
# (system, rbf names, rom extensions, games folders, file slot for each rbf)
# The slot is the number after "FS" in the core's CONF_STR: MegaDrive and SNES
# load cartridges into slot 1, the older Genesis core and NES into slot 0.
SUITE_SYSTEMS = (
    ("MEGA DRIVE", (("MegaDrive", 1), ("Genesis", 0)), (".bin", ".md", ".gen"),
     ("MegaDrive", "Genesis")),
    ("SNES", (("SNES", 1),), (".sfc", ".smc"), ("SNES",)),
    ("NES", (("NES", 0),), (".nes",), ("NES",)),
)
FAT = "/media/fat"
SUITE_DIR_NAME = "testsuite"          # arcade_kiosk/testsuite/ for dropping ROMs in


def find_rbf(name, fat=FAT):
    """'_Console/MegaDrive' if a MegaDrive_YYYYMMDD.rbf (or MegaDrive.rbf) is there."""
    for folder in ("_Console", "_console"):
        d = os.path.join(fat, folder)
        try:
            files = os.listdir(d)
        except OSError:
            continue
        pat = re.compile(r"^%s(_\d{8})?\.rbf$" % re.escape(name), re.I)
        if any(pat.match(f) for f in files):
            return "%s/%s" % (folder, name)
    return None


def _find_roms(dirs, exts, depth=3):
    found = []
    for top in dirs:
        top_depth = top.rstrip("/").count("/")
        for root, sub, files in os.walk(top):
            if root.count("/") - top_depth >= depth:
                sub[:] = []
            for f in files:
                if "240p" in f.lower() and f.lower().endswith(exts):
                    found.append(os.path.join(root, f))
    return sorted(found)


def find_test_suite(setting="", kiosk_dir=None, fat=FAT):
    """Work out what TEST SUITE launches.

    setting is kiosk.ini's test_suite: blank to search the SD card, a path to an
    .mgl to launch as it is, or a path to the suite's ROM.
    Returns {"system", "rbf", "rom", "index", "mgl"} or None. "mgl" is set when an
    existing .mgl file is used; otherwise rbf/rom/index say what to write."""
    setting = (setting or "").strip()
    if setting:
        path = setting if setting.startswith("/") else os.path.join(fat, setting)
        if path.lower().endswith(".mgl"):
            return {"system": "MGL", "mgl": path} if os.path.exists(path) else None
        if not os.path.exists(path):
            return None
        for system, rbfs, exts, folders in SUITE_SYSTEMS:
            if path.lower().endswith(exts):
                for name, index in rbfs:
                    rbf = find_rbf(name, fat)
                    if rbf:
                        return {"system": system, "rbf": rbf, "rom": path, "index": index, "mgl": None}
        return None
    for system, rbfs, exts, folders in SUITE_SYSTEMS:
        core = None
        for name, index in rbfs:
            rbf = find_rbf(name, fat)
            if rbf:
                core = (rbf, index)
                break
        if not core:
            continue
        dirs = [os.path.join(fat, "games", f) for f in folders]
        dirs += [os.path.join("/media/usb0/games", f) for f in folders]
        if kiosk_dir:
            dirs.insert(0, os.path.join(kiosk_dir, SUITE_DIR_NAME))
        roms = _find_roms([d for d in dirs if os.path.isdir(d)], exts)
        if roms:
            return {"system": system, "rbf": core[0], "rom": roms[-1], "index": core[1], "mgl": None}
    return None


def suite_mgl(info):
    """The MGL text that loads the suite's ROM on its core."""
    from xml.sax.saxutils import quoteattr
    return ('<mistergamedescription>\n'
            '  <rbf>%s</rbf>\n'
            '  <file delay="2" type="f" index="%d" path=%s/>\n'
            '</mistergamedescription>\n') % (info["rbf"], info["index"], quoteattr(info["rom"]))
