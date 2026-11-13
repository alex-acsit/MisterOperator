#!/usr/bin/env python3
"""
Arcade Kiosk for MiSTer FPGA
============================

A locked-down arcade-only frontend for the MiSTer.

* LOCKED mode (normal operation)
    - The MiSTer shows a full-screen game list instead of the stock menu.
    - Players pick an arcade game (.mra or .mgl) and it starts.
    - One press of the PLAYER MENU button quits the game back to the list.
    - The stock OSD, settings, consoles and scripts are not reachable.

* UNLOCKED mode (service)
    - Hold the OPERATOR button to toggle. The stock MiSTer menu returns and
      every button (including the player menu button) behaves normally.
    - Hold the OPERATOR button again to lock and return to the game list.

How it works
------------
The daemon takes exclusive ownership of the physical controllers (EVIOCGRAB)
and re-creates each one as a virtual clone through /dev/uinput. The MiSTer
main program only ever sees the clones, so the daemon decides which presses
reach it: during a game everything is passed through except the menu and
operator buttons; on the game list nothing is passed through.

The game list is drawn on the Linux framebuffer of the MiSTer menu core
(the same screen the F9 terminal uses). Games are started and stopped by
writing "load_core" commands to /dev/MiSTer_cmd. /tmp/CORENAME tells the
daemon which core is running.

Only the Python 3 standard library is used.

Usage
-----
  arcadekiosk.py                 run the kiosk (started at boot by user-startup.sh)
  arcadekiosk.py --lock          ask the running kiosk to lock
  arcadekiosk.py --unlock        ask the running kiosk to unlock
  arcadekiosk.py --relearn       forget the menu/operator buttons and run setup again
  arcadekiosk.py --status        show what the kiosk is doing
  arcadekiosk.py --scan          list the games the launcher would show
  arcadekiosk.py --devices       list input devices and their capabilities
  arcadekiosk.py --preview F.ppm render the launcher to an image file (no hardware needed)
"""

import ctypes
import errno
import fcntl
import json
import mmap
import random
from array import array
import os
import re
import select
import shutil
import struct
import subprocess
import threading
import textwrap
import sys
import time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from font8x8 import FONT  # noqa: E402

VERSION = "2.1"

CONFIG_PATH = os.path.join(HERE, "kiosk.ini")
STATE_PATH = os.path.join(HERE, "state.json")
CACHE_PATH = os.path.join(HERE, "games_cache.json")
LOG_PATH = "/tmp/arcadekiosk.log"
PID_PATH = "/tmp/arcadekiosk.pid"
CTL_PATH = "/tmp/arcadekiosk.ctl"
STATUS_PATH = "/tmp/arcadekiosk.status"

MISTER_CMD = "/dev/MiSTer_cmd"
CORENAME_PATH = "/tmp/CORENAME"
FB_PARAM_PATH = "/sys/module/MiSTer_fb/parameters/mode"
MENU_RBF = "/media/fat/menu.rbf"
VOLUME_PATH = "/media/fat/config/Volume.dat"
# MisterOperator build of the MiSTer main program (github.com/alex-acsit/Main_MiSTer)
KIOSK_FLAG = "/tmp/kiosk_active"          # while it exists, that build shows no MiSTer menu
FEATURES_PATH = "/tmp/MiSTer_features"    # written by that build at start-up
# Kept on the SD card: in the first 2 minutes after power-on that build treats it
# like KIOSK_FLAG, so its menu doesn't open at boot before the kiosk has started.
KIOSK_BOOT_FLAG = "/media/fat/config/kiosk_boot"
MAIN_BIN = "/media/fat/MiSTer"
KIOSK_MAIN = os.path.join(HERE, "MiSTer_kiosk")
VIRTUAL_PHYS = "arcadekiosk/"

# ---------------------------------------------------------------------------
# Linux input constants
# ---------------------------------------------------------------------------

EV_SYN, EV_KEY, EV_REL, EV_ABS, EV_MSC = 0x00, 0x01, 0x02, 0x03, 0x04
SYN_REPORT = 0
ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y = 0x00, 0x01, 0x10, 0x11
REL_X = 0x00
KEY_MAX, ABS_MAX_ = 0x2FF, 0x3F
ABS_CNT = 64

KEY_NAMES = {
    "KEY_ESC": 1, "KEY_1": 2, "KEY_2": 3, "KEY_3": 4, "KEY_4": 5, "KEY_5": 6,
    "KEY_6": 7, "KEY_7": 8, "KEY_8": 9, "KEY_9": 10, "KEY_0": 11,
    "KEY_TAB": 15, "KEY_Q": 16, "KEY_W": 17, "KEY_E": 18, "KEY_R": 19,
    "KEY_T": 20, "KEY_Y": 21, "KEY_U": 22, "KEY_I": 23, "KEY_O": 24, "KEY_P": 25,
    "KEY_ENTER": 28, "KEY_LEFTCTRL": 29, "KEY_A": 30, "KEY_S": 31, "KEY_D": 32,
    "KEY_F": 33, "KEY_G": 34, "KEY_H": 35, "KEY_J": 36, "KEY_K": 37, "KEY_L": 38,
    "KEY_LEFTSHIFT": 42, "KEY_Z": 44, "KEY_X": 45, "KEY_C": 46, "KEY_V": 47,
    "KEY_B": 48, "KEY_N": 49, "KEY_M": 50, "KEY_RIGHTSHIFT": 54,
    "KEY_LEFTALT": 56, "KEY_SPACE": 57, "KEY_F1": 59, "KEY_F2": 60, "KEY_F3": 61,
    "KEY_F4": 62, "KEY_F5": 63, "KEY_F6": 64, "KEY_F7": 65, "KEY_F8": 66,
    "KEY_F9": 67, "KEY_F10": 68, "KEY_F11": 87, "KEY_F12": 88,
    "KEY_RIGHTCTRL": 97, "KEY_RIGHTALT": 100, "KEY_HOME": 102, "KEY_UP": 103,
    "KEY_PAGEUP": 104, "KEY_LEFT": 105, "KEY_RIGHT": 106, "KEY_END": 107,
    "KEY_DOWN": 108, "KEY_PAGEDOWN": 109, "KEY_MENU": 139,
    "BTN_TRIGGER": 0x120, "BTN_THUMB": 0x121, "BTN_THUMB2": 0x122,
    "BTN_TOP": 0x123, "BTN_TOP2": 0x124, "BTN_PINKIE": 0x125, "BTN_BASE": 0x126,
    "BTN_BASE2": 0x127, "BTN_BASE3": 0x128, "BTN_BASE4": 0x129,
    "BTN_BASE5": 0x12A, "BTN_BASE6": 0x12B, "BTN_DEAD": 0x12F,
    "BTN_SOUTH": 0x130, "BTN_EAST": 0x131, "BTN_C": 0x132, "BTN_NORTH": 0x133,
    "BTN_WEST": 0x134, "BTN_Z": 0x135, "BTN_TL": 0x136, "BTN_TR": 0x137,
    "BTN_TL2": 0x138, "BTN_TR2": 0x139, "BTN_SELECT": 0x13A, "BTN_START": 0x13B,
    "BTN_MODE": 0x13C, "BTN_THUMBL": 0x13D, "BTN_THUMBR": 0x13E,
    "BTN_DPAD_UP": 0x220, "BTN_DPAD_DOWN": 0x221, "BTN_DPAD_LEFT": 0x222,
    "BTN_DPAD_RIGHT": 0x223,
}
for _i in range(1, 41):
    KEY_NAMES["BTN_TRIGGER_HAPPY%d" % _i] = 0x2C0 + _i - 1
CODE_NAMES = {}
for _n, _c in KEY_NAMES.items():
    CODE_NAMES.setdefault(_c, _n)

KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT = 103, 108, 105, 106
KEY_PAGEUP, KEY_PAGEDOWN, KEY_F9 = 104, 109, 67
BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT = 0x220, 0x221, 0x222, 0x223


def code_name(code):
    return CODE_NAMES.get(code, "0x%03X" % code)


def parse_code(text):
    text = text.strip()
    if not text:
        return None
    up = text.upper()
    if up in KEY_NAMES:
        return KEY_NAMES[up]
    try:
        return int(text, 0)
    except ValueError:
        raise ValueError("unknown button name: %r" % text)


def parse_code_list(text):
    out = set()
    for part in text.split(","):
        c = parse_code(part)
        if c is not None:
            out.add(c)
    return out


# ioctl request numbers -----------------------------------------------------

def _IOC(d, t, nr, size):
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr


_PTR = ctypes.sizeof(ctypes.c_void_p)
EVIOCGID = _IOC(2, "E", 0x02, 8)
EVIOCGRAB = _IOC(1, "E", 0x90, 4)


def EVIOCGNAME(n): return _IOC(2, "E", 0x06, n)
def EVIOCGPHYS(n): return _IOC(2, "E", 0x07, n)
def EVIOCGBIT(ev, n): return _IOC(2, "E", 0x20 + ev, n)
def EVIOCGABS(a): return _IOC(2, "E", 0x40 + a, 24)


UI_DEV_CREATE = _IOC(0, "U", 1, 0)
UI_DEV_DESTROY = _IOC(0, "U", 2, 0)
UI_SET_EVBIT = _IOC(1, "U", 100, 4)
UI_SET_KEYBIT = _IOC(1, "U", 101, 4)
UI_SET_ABSBIT = _IOC(1, "U", 103, 4)
UI_SET_MSCBIT = _IOC(1, "U", 104, 4)
UI_SET_PHYS = _IOC(1, "U", 108, _PTR)


def UI_GET_SYSNAME(n): return _IOC(2, "U", 44, n)


_libc = None


def ioctl_ptr(fd, request, address):
    """ioctl() whose argument is a C pointer.

    fcntl.ioctl() only accepts a signed C int as an integer argument, and on the
    MiSTer's 32-bit ARM userspace addresses are above 2 GB, so it raises
    OverflowError. Call libc's ioctl directly with a real pointer type instead."""
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(None, use_errno=True)
        _libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
        _libc.ioctl.restype = ctypes.c_int
    if _libc.ioctl(fd, request, address) < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))

FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602
KDSETMODE, KD_TEXT, KD_GRAPHICS = 0x4B3A, 0, 1

EVENT_FMT = "llHHi"                 # struct input_event (timeval + type/code/value)
EVENT_SIZE = struct.calcsize(EVENT_FMT)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log(msg):
    line = "%s %s\n" % (time.strftime("%H:%M:%S"), msg)
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1024 * 1024:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        with open(LOG_PATH, "a") as f:
            f.write(line)
    except OSError:
        pass
    if sys.stderr.isatty():
        sys.stderr.write(line)


# ---------------------------------------------------------------------------
# Config and state
# ---------------------------------------------------------------------------

DEFAULTS = {
    "arcade_dir": "/media/fat/_Arcade",
    "include_subdirs": "0",
    "include_mgl": "1",
    "exclude_dirs": "_alternatives,cores,_Organized",
    "game_list": "",
    "orientation": "all",
    "genres": "",
    "exclude_genres": "",
    "hidden_genres": "",
    "hide_vertical": "0",
    "short_names": "1",
    "title": "ARCADE",
    "footer_play": "PRESS 1 TO PLAY",
    "art_dir": os.path.join(HERE, "art"),
    "menu_button": "",
    "menu_device": "",
    "operator_button": "",
    "operator_device": "",
    "operator_hold_ms": "1500",
    "operator_menu": "1",
    "operator_timeout_s": "300",
    "menu_hold_ms": "0",
    "exit_grace_s": "3",
    "lock_on_boot": "1",
    "menu_settle_s": "0",
    "attract_idle_s": "120",
    "attract_game_s": "60",
    "attract_list": "",
    "attract_vertical": "0",
    "attract_mute": "0",
    "launch_timeout_s": "12",
    "fb_width": "320",
    "fb_height": "240",
    "launch_buttons": "BTN_TRIGGER,BTN_SOUTH,BTN_START,KEY_ENTER,KEY_LEFTCTRL,KEY_1",
    "genre_buttons": "BTN_THUMB,BTN_EAST,KEY_LEFTALT,KEY_2",
    "genre_back_buttons": "BTN_THUMB2,BTN_NORTH,KEY_SPACE,KEY_3",
    "letter_buttons": "BTN_TOP,BTN_WEST,KEY_LEFTSHIFT,KEY_4",
    "coin_buttons": "KEY_5,KEY_6,BTN_SELECT,BTN_BASE3",
    "coin_delay_s": "30",
    "max_credits": "9",
    "ignore_devices": "",
    "log_inputs": "0",
    "remember_last": "1",
    "update_repo": "alex-acsit/MisterOperator",
    "update_token": "",
    "auto_update": "0",
    "game_idle_exit_s": "300",
    "save_nvram": "once",
    "nvram_save_s": "0.3",
    "nvram_dir": "/media/fat/config/nvram",
    "theme": "green",
    "standard_layout": "1",
    "panel_layout": "B,A,R,Y,X,L",
    "panel_start": "Start",
    "panel_coin": "Select",
    "drop_buttons": "pause,service,test,tilt,core credits,reset,freeze,slam",
    "layout_1": "1",
    "layout_2": "1,2",
    "layout_3": "1,2,3",
    "layout_4": "4,1,2,3",
    "layout_5": "1,2,3,4,5",
    "layout_6": "1,2,3,4,5,6",
    "inputs_dir": "/media/fat/config/inputs",
    "map_backup_dir": os.path.join(HERE, "map_backup"),
    "screen": "yoko",
}


def ini_line(raw):
    """A kiosk.ini line without its comment. ";" starts a comment anywhere; "#"
    only at the start of a line, so colours like #RRGGBB work as values."""
    line = raw.strip()
    if line.startswith("#"):
        return ""
    return line.split(";", 1)[0].strip()


def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULTS)
    try:
        with open(path) as f:
            for raw in f:
                line = ini_line(raw)
                if not line or line.startswith("[") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip().lower()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg


def set_config_value(key, value, path=CONFIG_PATH):
    """Change one key in kiosk.ini, keeping comments and layout."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = ["[kiosk]"]
    pat = re.compile(r"^(\s*%s\s*=\s*)([^;]*?)(\s*;.*)?$" % re.escape(key), re.I)
    for i, line in enumerate(lines):
        m = pat.match(line)
        if m:
            comment = m.group(3) or ""
            lines[i] = "%s%s%s" % (m.group(1), value, ("   " + comment.strip()) if comment else "")
            break
    else:
        lines.append("%s = %s" % (key, value))
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(lines) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, STATE_PATH)
    except OSError as e:
        log("could not save state: %s" % e)


def flag(cfg, key):
    return cfg.get(key, "0").strip().lower() in ("1", "yes", "true", "on")


# ---------------------------------------------------------------------------
# Game list (MRA scanning)
# ---------------------------------------------------------------------------

def _xml_text(root, tag):
    el = root.find(tag)
    return el.text.strip() if el is not None and el.text else ""


def _regex_text(text, tag):
    m = re.search(r"<%s>\s*(.*?)\s*</%s>" % (tag, tag), text, re.S | re.I)
    return m.group(1).strip() if m else ""


def parse_mra(path):
    """Read the game details from an .mra or .mgl file.

    .mgl (MiSTer Game Launcher) files normally hold only the core (<rbf>) and the
    file to load, but the MiSTer ignores tags it doesn't use, so <name>, <year>,
    <manufacturer>, <category> and <rotation> can be added to them by hand."""
    with open(path, "rb") as f:
        raw = f.read(65536).decode("utf-8", "replace")
    info = {}
    try:
        root = ET.fromstring(raw)
        for tag in ("name", "setname", "year", "manufacturer", "rotation", "rbf"):
            info[tag] = _xml_text(root, tag)
        cats = [c.text.strip() for c in root.findall("category") if c.text]
        info["category"] = cats[0] if cats else ""
        info["nvram"] = root.find("nvram") is not None
        b = root.find("buttons")
        info["buttons"] = (b.get("names") or "") if b is not None else ""
    except ET.ParseError:
        info["nvram"] = bool(re.search(r"<nvram\b", raw, re.I))
        m = re.search(r"<buttons\b[^>]*\bnames\s*=\s*\"([^\"]*)\"", raw, re.I)
        info["buttons"] = m.group(1) if m else ""
        for tag in ("name", "setname", "year", "manufacturer", "rotation", "category", "rbf"):
            info[tag] = _regex_text(raw, tag)
    return info


def is_vertical(rotation):
    """MRA <rotation> is usually "horizontal", "vertical (cw)" or "vertical (ccw)";
    a few files give an angle instead. A missing value means horizontal."""
    r = rotation.strip().lower()
    return "vertical" in r or r in ("90", "270", "-90", "cw", "ccw")


def orientation_filter(cfg):
    """Which games the list shows: "all", "horizontal" or "vertical"."""
    o = cfg.get("orientation", "all").strip().lower()
    if o in ("h", "hor", "horiz", "horizontal", "yoko"):
        return "horizontal"
    if o in ("v", "vert", "vertical", "tate"):
        return "vertical"
    if o not in ("", "all", "both", "any"):
        log("unknown orientation %r in kiosk.ini; showing all games" % o)
    # Older setting, kept so existing kiosk.ini files still work.
    return "horizontal" if flag(cfg, "hide_vertical") else "all"


def _genre_set(text):
    return {g.strip().lower() for g in text.split(",") if g.strip()}


def category_parts(category):
    """"Shooter / Vertical" -> ["Shooter", "Vertical"]."""
    return [p.strip().title() for p in re.split(r"[/|]", category) if p.strip()]


def genre_matches(parts, wanted):
    """True if any part of the game's category is in the wanted set.
    "Other" matches games with no category."""
    names = {p.lower() for p in parts} or {"other"}
    return bool(names & wanted)


def _clean(text):
    text = text.replace("&amp;", "&").replace("’", "'")
    return "".join(c if 32 <= ord(c) < 127 else "?" for c in text)


def scan_games(cfg, use_cache=True):
    root = cfg["arcade_dir"]
    exts = (".mra", ".mgl") if flag(cfg, "include_mgl") else (".mra",)
    excludes = {d.strip().lower() for d in cfg["exclude_dirs"].split(",") if d.strip()}
    files = []
    if flag(cfg, "include_subdirs"):
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d.lower() not in excludes]
            files += [os.path.join(dirpath, n) for n in filenames if n.lower().endswith(exts)]
    else:
        try:
            files = [os.path.join(root, n) for n in os.listdir(root) if n.lower().endswith(exts)]
        except FileNotFoundError:
            log("arcade folder not found: %s" % root)

    allowed = None
    if cfg["game_list"]:
        try:
            with open(cfg["game_list"]) as f:
                allowed = {line.strip().lower() for line in f if line.strip() and not line.startswith("#")}
        except OSError:
            log("game_list file not readable: %s" % cfg["game_list"])

    cache = {}
    if use_cache:
        try:
            with open(CACHE_PATH) as f:
                cache = json.load(f)
        except (OSError, ValueError):
            cache = {}
    new_cache = {}
    games = []
    orient = orientation_filter(cfg)
    skipped = 0
    want_genres = _genre_set(cfg.get("genres", ""))
    hidden_genres = _genre_set(cfg.get("hidden_genres", ""))
    drop_genres = _genre_set(cfg.get("exclude_genres", ""))
    genre_skipped = 0
    for path in files:
        base = os.path.basename(path)
        if allowed is not None and base.lower() not in allowed and base[:-4].lower() not in allowed:
            continue
        try:
            mtime = int(os.path.getmtime(path))
        except OSError:
            continue
        hit = cache.get(path)
        if hit and hit.get("mtime") == mtime and "buttons" in hit.get("info", {}):
            info = hit["info"]
        else:
            try:
                info = parse_mra(path)
            except OSError:
                continue
        new_cache[path] = {"mtime": mtime, "info": info}
        name = _clean(info.get("name") or base[:-4])
        vertical = is_vertical(info.get("rotation", ""))
        if (orient == "horizontal" and vertical) or (orient == "vertical" and not vertical):
            skipped += 1
            continue
        category = info.get("category", "")
        is_mgl = path.lower().endswith(".mgl")
        if is_mgl and not category and info.get("rbf"):
            # No category in a plain .mgl: group it by its core, e.g. "_Arcade/cores/NeoGeo" -> "Neogeo".
            category = os.path.basename(info["rbf"].replace("\\", "/")).split("_")[0]
        parts = category_parts(_clean(category))
        if want_genres and not genre_matches(parts, want_genres):
            genre_skipped += 1
            continue
        if drop_genres and genre_matches(parts, drop_genres):
            genre_skipped += 1
            continue
        genre = parts[0] if parts else "Other"
        if genre.lower() in hidden_genres:          # switched off in the operator menu
            genre_skipped += 1
            continue
        games.append({
            "path": path,
            "file": base[:-4],
            "name": name,
            "setname": info.get("setname", ""),
            "year": _clean(info.get("year", ""))[:4],
            "maker": _clean(info.get("manufacturer", "")),
            "genre": genre,
            "categories": parts,
            "mgl": is_mgl,
            "nvram": bool(info.get("nvram")),
            "buttons": info.get("buttons", ""),
            "vertical": vertical,
        })

    if want_genres or drop_genres or hidden_genres:
        log("genre filter: %d game%s hidden" % (genre_skipped, "" if genre_skipped == 1 else "s"))
    if orient != "all":
        log("orientation = %s: %d game%s hidden" % (orient, skipped, "" if skipped == 1 else "s"))

    if new_cache != cache:
        try:
            with open(CACHE_PATH + ".tmp", "w") as f:
                json.dump(new_cache, f)
            os.replace(CACHE_PATH + ".tmp", CACHE_PATH)
        except OSError:
            pass

    if flag(cfg, "short_names"):
        short = {}
        for g in games:
            s = re.sub(r"\s*[\(\[].*$", "", g["name"]).strip() or g["name"]
            short.setdefault(s.lower(), []).append(g)
            g["short"] = s
        for group in short.values():
            for g in group:
                g["label"] = g["short"] if len(group) == 1 else g["name"]
    else:
        for g in games:
            g["label"] = g["name"]

    games.sort(key=lambda g: (g["label"].lower(), g["name"].lower()))
    return games


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

class PixelFormat:
    """Packs RGB into the framebuffer's byte layout (from fb_var_screeninfo)."""

    def __init__(self, bpp=32, r=(16, 8), g=(8, 8), b=(0, 8), a=(24, 8)):
        self.bpp = bpp
        self.Bpp = bpp // 8
        self.r, self.g, self.b, self.a = r, g, b, a

    def pack(self, rgb):
        rr, gg, bb = rgb
        v = 0
        for (off, ln), c in ((self.r, rr), (self.g, gg), (self.b, bb)):
            if ln:
                v |= (c >> (8 - ln)) << off
        if self.a[1]:
            v |= ((1 << self.a[1]) - 1) << self.a[0]
        return v.to_bytes(self.Bpp, "little")


class Canvas:
    def __init__(self, w, h, fmt):
        self.w, self.h, self.fmt = w, h, fmt
        self.Bpp = fmt.Bpp
        self.stride = w * self.Bpp
        self.buf = bytearray(self.stride * h)
        self._colors = {}
        self._glyphs = {}

    def col(self, rgb):
        c = self._colors.get(rgb)
        if c is None:
            c = self._colors[rgb] = self.fmt.pack(rgb)
        return c

    def fill(self, x, y, w, h, rgb):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = self.col(rgb) * (x1 - x0)
        B, s = self.Bpp, self.stride
        for yy in range(y0, y1):
            o = yy * s + x0 * B
            self.buf[o:o + len(row)] = row

    def frame(self, x, y, w, h, rgb, t=1):
        self.fill(x, y, w, t, rgb)
        self.fill(x, y + h - t, w, t, rgb)
        self.fill(x, y, t, h, rgb)
        self.fill(x + w - t, y, t, h, rgb)

    def _glyph(self, ch, fg, bg, scale):
        key = (ch, fg, bg, scale)
        g = self._glyphs.get(key)
        if g is None:
            code = ord(ch)
            bits = FONT[code] if code < 128 else FONT[ord("?")]
            f, b = self.col(fg), self.col(bg)
            rows = []
            for byte in bits:
                row = b"".join((f if (byte >> i) & 1 else b) * scale for i in range(8))
                rows.extend([row] * scale)
            g = self._glyphs[key] = rows
        return g

    def text(self, x, y, s, fg, bg, scale=1, max_chars=None):
        if max_chars is not None and len(s) > max_chars:
            s = s[:max(0, max_chars - 1)] + "~" if max_chars > 1 else s[:max_chars]
        cw = 8 * scale
        B, st = self.Bpp, self.stride
        for i, ch in enumerate(s):
            cx = x + i * cw
            if cx < 0 or cx + cw > self.w:
                continue
            rows = self._glyph(ch, fg, bg, scale)
            for r, data in enumerate(rows):
                yy = y + r
                if 0 <= yy < self.h:
                    o = yy * st + cx * B
                    self.buf[o:o + len(data)] = data

    def text_center(self, cx, y, s, fg, bg, scale=1):
        self.text(cx - len(s) * 4 * scale, y, s, fg, bg, scale)

    def blit_rgb(self, x, y, w, h, data):
        """Draw raw RGB888 pixels (w*h*3 bytes)."""
        B, st = self.Bpp, self.stride
        col = self.col
        for yy in range(h):
            if not 0 <= y + yy < self.h:
                continue
            src = data[yy * w * 3:(yy + 1) * w * 3]
            row = b"".join(col((src[i], src[i + 1], src[i + 2])) for i in range(0, len(src) - 2, 3))
            o = (y + yy) * st + x * B
            self.buf[o:o + len(row)] = row

    def save_ppm(self, path):
        # Decode our own pixel bytes back to RGB for a preview image.
        f = self.fmt
        out = bytearray()
        B = self.Bpp
        for i in range(0, len(self.buf), B):
            v = int.from_bytes(self.buf[i:i + B], "little")
            px = []
            for off, ln in (f.r, f.g, f.b):
                c = (v >> off) & ((1 << ln) - 1)
                px.append((c << (8 - ln)) | (c >> (2 * ln - 8) if ln < 8 else 0))
            out += bytes(px)
        with open(path, "wb") as fh:
            fh.write(b"P6\n%d %d\n255\n" % (self.w, self.h))
            fh.write(out)


# Palette -------------------------------------------------------------------
# Each colour has a job:
#   bg      screen background          panel    box behind art / messages
#   line    dividers, frames           accent   selection bar, top rule, borders
#   title   title text, year           info     genre text, scroll thumb
#   text    game names                 dim      game count, hints
#   select  game name on the selection bar      white  message text
THEMES = {
    "green": {   # dark grey with green highlights and white text
        "bg": (26, 28, 27), "panel": (38, 42, 40), "line": (64, 70, 67),
        "accent": (40, 150, 85), "title": (245, 247, 246), "info": (95, 200, 130),
        "text": (222, 226, 224), "dim": (135, 142, 138), "select": (255, 255, 255),
        "white": (245, 247, 246),
    },
    "phosphor": {  # all-green terminal look
        "bg": (0, 12, 4), "panel": (0, 30, 12), "line": (0, 78, 34),
        "accent": (0, 210, 90), "title": (120, 255, 140), "info": (0, 235, 170),
        "text": (150, 225, 160), "dim": (70, 140, 90), "select": (0, 20, 6),
        "white": (220, 255, 225),
    },
    "classic": {  # the original pink / amber / cyan on navy
        "bg": (10, 12, 26), "panel": (18, 21, 44), "line": (42, 47, 86),
        "accent": (255, 60, 127), "title": (255, 179, 71), "info": (90, 209, 255),
        "text": (200, 203, 224), "dim": (120, 125, 160), "select": (255, 255, 255),
        "white": (255, 255, 255),
    },
}


def screen_rotation(cfg):
    """0 for a normal (YOKO) monitor, 90 or 270 for one turned on its side (TATE).
    The number is how far the picture is turned clockwise to stay upright."""
    v = cfg.get("screen", "yoko").strip().lower().replace("-", "_").replace(" ", "_")
    if v in ("", "yoko", "horizontal", "landscape", "0"):
        return 0
    if v in ("tate", "tate_cw", "vertical", "vertical_cw", "cw", "90", "portrait"):
        return 90
    if v in ("tate_ccw", "vertical_ccw", "ccw", "270", "-90"):
        return 270
    log("unknown screen %r in kiosk.ini; using yoko" % v)
    return 0


def rotate_canvas(src, dst, rotation):
    """Copy an upright portrait canvas onto the landscape framebuffer canvas,
    turned 90 degrees clockwise (90) or anticlockwise (270)."""
    w, h = src.w, src.h                      # dst must be h x w
    if src.Bpp == 4:
        a = array("I")
        a.frombytes(bytes(src.buf))
        out = array("I")
        if rotation == 90:                   # dst row r = src column r, bottom to top
            for r in range(w):
                col = a[r::w]
                col.reverse()
                out.extend(col)
        else:                                # dst row r = src column w-1-r, top to bottom
            for r in range(w):
                out.extend(a[w - 1 - r::w])
        dst.buf[:] = out.tobytes()
        return
    B = src.Bpp                               # any other pixel size (slow, rarely used)
    for r in range(w):
        for c in range(h):
            sy, sx = (h - 1 - c, r) if rotation == 90 else (c, w - 1 - r)
            so = (sy * w + sx) * B
            do = (r * h + c) * B
            dst.buf[do:do + B] = src.buf[so:so + B]


def parse_color(text):
    t = text.strip().lstrip("#")
    if re.fullmatch(r"[0-9A-Fa-f]{6}", t):
        return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))
    parts = [p.strip() for p in text.split(",")]
    if len(parts) == 3 and all(p.isdigit() and int(p) < 256 for p in parts):
        return tuple(int(p) for p in parts)
    raise ValueError(text)


def apply_theme(cfg):
    """Set the drawing colours from theme = and any color_<name> = overrides."""
    global BG, PANEL, LINE, ACCENT, AMBER, CYAN, TEXT, DIM, SELECT, WHITE
    name = cfg.get("theme", "green").strip().lower() or "green"
    if name not in THEMES:
        log("unknown theme %r; using green" % name)
        name = "green"
    pal = dict(THEMES[name])
    for key in pal:
        val = cfg.get("color_" + key, "").strip()
        if val:
            try:
                pal[key] = parse_color(val)
            except ValueError:
                log("bad colour color_%s = %s (use #RRGGBB)" % (key, val))
    BG, PANEL, LINE, ACCENT = pal["bg"], pal["panel"], pal["line"], pal["accent"]
    AMBER, CYAN, TEXT, DIM = pal["title"], pal["info"], pal["text"], pal["dim"]
    SELECT, WHITE = pal["select"], pal["white"]
    return pal


apply_theme({})


class LauncherView:
    """Lays out the game list: 320x240 for a normal (YOKO) monitor, or 240x320
    drawn upright for a monitor turned on its side (TATE)."""

    ROW_H = 11
    LIST_X, LIST_Y = 4, 42
    ROWS = 16
    ART_W, ART_H = 100, 75

    def __init__(self, cfg, games):
        self.cfg = cfg
        apply_theme(cfg)
        self.portrait = screen_rotation(cfg) != 0
        if self.portrait:
            # List across the full width, picture and details underneath.
            self.LIST_W, self.NAME_CHARS = 232, 27
            self.PANEL_X, self.PANEL_Y = 6, 226
            self.INFO_X, self.INFO_Y, self.INFO_CHARS, self.INFO_LINES = 114, 228, 15, 6
        else:
            # List on the left, picture and details on the right.
            self.LIST_W, self.NAME_CHARS = 204, 24
            self.PANEL_X, self.PANEL_Y = 214, 41
            self.INFO_X, self.INFO_Y, self.INFO_CHARS, self.INFO_LINES = 214, 124, 12, 7
        self.all_games = games
        genres = sorted({g["genre"] for g in games})
        # Locked to one genre (or the list only has one): show its name, no cycling.
        self.genres = genres if len(genres) == 1 else ["All Games"] + genres
        self.genre_idx = 0
        self.games = games
        self.sel = 0
        self.top = 0
        self.toast = None
        self.toast_until = 0
        self.overlay = None       # persistent message box (setup / loading)
        self.credits = 0          # coins banked on the list, shown in the header
        self.picker = None        # index into picker_letters while choosing a letter
        self.picker_until = 0
        self._art_cache = {}

    # selection ------------------------------------------------------------
    def set_genre(self, idx):
        cur = self.current()
        self.genre_idx = idx % len(self.genres)
        g = self.genres[self.genre_idx]
        self.games = (self.all_games if g == "All Games"
                      else [x for x in self.all_games if x["genre"] == g])
        self.sel = 0
        if cur in self.games:
            self.sel = self.games.index(cur)
        self._fix_top()

    def current(self):
        return self.games[self.sel] if self.games else None

    def move(self, d):
        if not self.games:
            return
        self.sel = max(0, min(len(self.games) - 1, self.sel + d))
        self._fix_top()

    def jump_letter(self, d):
        """Jump to the previous/next starting letter."""
        if not self.games:
            return
        first = lambda g: g["label"][:1].upper()
        cur = first(self.games[self.sel])
        i = self.sel
        if d > 0:
            while i < len(self.games) - 1 and first(self.games[i]) == cur:
                i += 1
        else:
            while i > 0 and first(self.games[i]) == cur:
                i -= 1
            target = first(self.games[i])
            while i > 0 and first(self.games[i - 1]) == target:
                i -= 1
        self.sel = i
        self._fix_top()

    @staticmethod
    def letter_of(g):
        ch = g["label"][:1].upper()
        return ch if "A" <= ch <= "Z" else "#"

    def picker_letters(self):
        """Letters that at least one game on the list starts with ("#" = digits etc.)."""
        return sorted({self.letter_of(g) for g in self.games}, key=lambda l: (l != "#", l))

    def open_picker(self):
        letters = self.picker_letters()
        if not letters:
            return
        cur = self.letter_of(self.current()) if self.current() else letters[0]
        self.picker = letters.index(cur) if cur in letters else 0
        self.picker_until = time.monotonic() + 6

    def close_picker(self):
        self.picker = None

    def picker_move(self, d):
        letters = self.picker_letters()
        if self.picker is None or not letters:
            return
        self.picker = (self.picker + d) % len(letters)
        self.picker_until = time.monotonic() + 6
        target = letters[self.picker]
        for i, g in enumerate(self.games):          # the list follows the letter
            if self.letter_of(g) == target:
                self.sel = i
                self.top = i                         # put that letter at the top
                self._fix_top()
                break

    def select_path(self, path):
        for i, g in enumerate(self.games):
            if g["path"] == path:
                self.sel = i
                self._fix_top()
                return

    def _fix_top(self):
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + self.ROWS:
            self.top = self.sel - self.ROWS + 1
        self.top = max(0, min(self.top, max(0, len(self.games) - self.ROWS)))

    def show_toast(self, text, seconds=2.0):
        self.toast = text
        self.toast_until = time.monotonic() + seconds

    # art --------------------------------------------------------------------
    def _art(self, game):
        key = game["path"]
        if key in self._art_cache:
            return self._art_cache[key]
        data = None
        size = self.ART_W * self.ART_H * 3
        for name in (game["file"], game["setname"]):
            if not name:
                continue
            p = os.path.join(self.cfg["art_dir"], name + ".rgb")
            try:
                with open(p, "rb") as f:
                    d = f.read()
                if len(d) == size:
                    data = d
                    break
            except OSError:
                pass
        if len(self._art_cache) > 24:
            self._art_cache.clear()
        self._art_cache[key] = data
        return data

    # drawing ----------------------------------------------------------------
    def draw(self, c, blink_on=True):
        c.fill(0, 0, c.w, c.h, BG)

        # header
        c.text(8, 5, self.cfg["title"][:12], AMBER, BG, scale=2)
        if self.credits:
            count = "CREDIT%s %d" % ("" if self.credits == 1 else "S", self.credits)
            c.text(c.w - 8 - len(count) * 8, 10, count, AMBER, BG)
        else:
            count = "%d GAME%s" % (len(self.games), "" if len(self.games) == 1 else "S")
            c.text(c.w - 8 - len(count) * 8, 10, count, DIM, BG)
        c.fill(0, 24, c.w, 2, ACCENT)

        # genre selector
        gname = self.genres[self.genre_idx].upper()
        label = "< %s >" % gname if len(self.genres) > 1 else gname
        c.text_center(self.LIST_X + self.LIST_W // 2, 30, label[:25], CYAN, BG)

        # list
        if not self.games:
            c.text(self.LIST_X + 8, self.LIST_Y + 20, "NO GAMES FOUND", AMBER, BG)
            c.text(self.LIST_X + 8, self.LIST_Y + 34, "CHECK ARCADE_DIR", DIM, BG)
        for row in range(self.ROWS):
            i = self.top + row
            if i >= len(self.games):
                break
            y = self.LIST_Y + row * self.ROW_H
            g = self.games[i]
            if i == self.sel:
                c.fill(self.LIST_X, y - 1, self.LIST_W - 6, self.ROW_H, ACCENT)
                c.text(self.LIST_X + 4, y + 1, g["label"], SELECT, ACCENT, max_chars=self.NAME_CHARS)
            else:
                c.text(self.LIST_X + 4, y + 1, g["label"], TEXT, BG, max_chars=self.NAME_CHARS)

        # scroll bar
        sb_x = self.LIST_X + self.LIST_W - 3
        sb_h = self.ROWS * self.ROW_H
        c.fill(sb_x, self.LIST_Y - 1, 2, sb_h, LINE)
        if len(self.games) > self.ROWS:
            th = max(8, sb_h * self.ROWS // len(self.games))
            ty = (sb_h - th) * self.top // (len(self.games) - self.ROWS)
            c.fill(sb_x, self.LIST_Y - 1 + ty, 2, th, CYAN)

        # picture and details: beside the list (YOKO) or under it (TATE)
        px = self.PANEL_X
        list_bottom = self.LIST_Y - 1 + self.ROWS * self.ROW_H
        if self.portrait:
            c.fill(0, list_bottom + 4, c.w, 1, LINE)
        else:
            c.fill(px - 3, 28, 1, 196, LINE)
        g = self.current()
        ay = self.PANEL_Y
        c.frame(px - 1, ay - 1, self.ART_W + 2, self.ART_H + 2, LINE)
        art = self._art(g) if g else None
        if art:
            c.blit_rgb(px, ay, self.ART_W, self.ART_H, art)
        else:
            c.fill(px, ay, self.ART_W, self.ART_H, PANEL)
            if g:
                initial = g["label"][:1].upper()
                c.text_center(px + self.ART_W // 2, ay + 22, initial, AMBER, PANEL, scale=4)
        if g:
            y = self.INFO_Y
            n = self.INFO_CHARS
            lines = []
            maker = g["maker"] or "Unknown"
            # Two lines at most, broken between words where possible.
            wrapped = textwrap.wrap(maker, n, break_long_words=True) or [maker[:n]]
            if len(wrapped) > 2:
                wrapped = wrapped[:2]
                wrapped[1] = (wrapped[1] + "~")[:n] if len(wrapped[1]) < n else wrapped[1][:n - 1] + "~"
            lines += [(w, TEXT) for w in wrapped]
            if g["year"]:
                lines.append((g["year"], AMBER))
            lines.append((g["genre"][:n].upper(), CYAN))
            if g["vertical"]:
                lines.append(("VERTICAL", DIM))
            for text, colr in lines[:self.INFO_LINES]:
                c.text(self.INFO_X, y, text, colr, BG)
                y += 11

        # footer: "press 1 to play", and the version on the right
        fy = c.h - 14
        c.fill(0, fy - 4, c.w, 1, LINE)
        ver = "V" + VERSION
        c.text(c.w - 8 - len(ver) * 8, fy, ver, DIM, BG)
        room = (c.w - 16 - len(ver) * 8 - 8) // 8
        if blink_on:
            c.text(8, fy, self.cfg["footer_play"][:room], AMBER, BG)

        # letter picker: big current letter with its neighbours either side
        if self.picker is not None:
            letters = self.picker_letters()
            if letters:
                self.picker %= len(letters)
                w, h = min(c.w - 16, 216), 74
                x, y = (c.w - w) // 2, (c.h - h) // 2
                c.fill(x, y, w, h, PANEL)
                c.frame(x, y, w, h, ACCENT, 2)
                c.text_center(c.w // 2, y + 7, "JUMP TO LETTER", DIM, PANEL)
                cx = c.w // 2
                c.fill(cx - 20, y + 20, 40, 40, ACCENT)
                c.text_center(cx, y + 24, letters[self.picker], SELECT, ACCENT, scale=4)
                n = len(letters)
                # Neighbours wrap round; only show as many as there are distinct letters.
                for off, dx in ((-1, -44), (1, 44), (-2, -78), (2, 78)):
                    if n >= 2 * abs(off) + 1 or (n == 2 and off == 1):
                        l = letters[(self.picker + off) % n]
                        c.text_center(cx + dx, y + 32, l, TEXT if abs(off) == 1 else DIM, PANEL, scale=2)
                c.text_center(c.w // 2, y + 63, "ANY BUTTON: DONE", DIM, PANEL)

        # overlays
        msg = self.overlay
        if not msg and self.toast and time.monotonic() < self.toast_until:
            msg = self.toast
        if msg:
            lines = msg.split("\n")
            w = min(c.w - 16, max(len(l) for l in lines) * 8 + 24)
            h = len(lines) * 12 + 16
            x, y = (c.w - w) // 2, (c.h - h) // 2
            c.fill(x, y, w, h, PANEL)
            c.frame(x, y, w, h, ACCENT, 2)
            for i, l in enumerate(lines):
                c.text_center(c.w // 2, y + 9 + i * 12, l[:(w - 16) // 8], WHITE, PANEL)


class OperatorView:
    """The operator menu, drawn in the kiosk's own theme.

    Opened by holding the OPERATOR button. Settings are written straight to
    kiosk.ini. The stock MiSTer menu is still reachable as one of the items,
    for the rare jobs only it can do (DIP switches, core options)."""

    ROW_H = 11
    LIST_Y = 34

    def __init__(self, kiosk):
        self.k = kiosk
        self.page = "main"
        self.sel = 0
        self.top = 0
        self.confirm = None          # item waiting for a second press
        self.toast = None
        self.toast_until = 0
        self.overlay = None
        self.credits = 0
        self.lines = []              # rows of the current sub-page
        self.volume = read_volume()
        self.release = None          # newer release found by UPDATE KIOSK

    # -- helpers ------------------------------------------------------------------
    @property
    def cfg(self):
        return self.k.cfg

    def portrait(self):
        return screen_rotation(self.cfg) != 0

    def rows(self, c_h):
        return (c_h - self.LIST_Y - 30) // self.ROW_H

    def show_toast(self, text, seconds=2.0):
        self.toast = text
        self.toast_until = time.monotonic() + seconds

    def set(self, key, value):
        value = str(value)
        self.cfg[key] = value
        try:
            set_config_value(key, value)
        except OSError as e:
            log("operator menu: could not save %s: %s" % (key, e))
            self.show_toast("COULD NOT SAVE")
        log("operator menu: %s = %s" % (key, value))

    def cycle(self, key, options, d, fmt=str):
        cur = self.cfg.get(key, "").strip().lower()
        keys = [str(o).lower() for o in options]
        i = keys.index(cur) if cur in keys else -1
        if i < 0:   # a value set by hand in kiosk.ini: step from the nearest one
            try:
                n = float(cur)
                i = min(range(len(options)), key=lambda j: abs(float(options[j]) - n))
            except (ValueError, TypeError):
                i = 0
        self.set(key, options[(i + d) % len(options)])

    # -- the main page ------------------------------------------------------------
    def items(self):
        k = self.k
        dur = lambda key, off="OFF": fmt_seconds(self.cfg.get(key, "0"), off)
        last = k.last_game()
        out = [
            ("BACK TO GAMES", lambda: "LOCK", None, k.operator_lock),
            ("VOLUME", self.volume_text, self.change_volume, None),
            ("CREDITS", lambda: str(self.credits), self.change_credits, self.clear_credits),
            ("DEMO AFTER", lambda: dur("attract_idle_s"),
             lambda d: self.cycle("attract_idle_s", [0, 30, 60, 120, 180, 300, 600], d), None),
            ("DEMO LENGTH", lambda: dur("attract_game_s"),
             lambda d: self.cycle("attract_game_s", [30, 45, 60, 90, 120, 180], d), None),
            ("IDLE GAME QUIT", lambda: dur("game_idle_exit_s", "NEVER"),
             lambda d: self.cycle("game_idle_exit_s", [0, 120, 180, 300, 600, 900], d), None),
            ("COIN DELAY", lambda: dur("coin_delay_s"),
             lambda d: self.cycle("coin_delay_s", [5, 10, 15, 20, 25, 30, 40, 45, 60], d), None),
            ("SAVE NVRAM", lambda: k.nvram_mode().upper(),
             lambda d: self.cycle("save_nvram", ["once", "always", "off"], d), None),
            ("SCREEN", self.screen_text, self.change_screen, None),
            ("THEME", lambda: (self.cfg.get("theme") or "green").upper(), self.change_theme, None),
            ("SHOW GAMES", self.orientation_text,
             lambda d: self.cycle("orientation", ["all", "horizontal", "vertical"], d), None),
            ("GENRES", self.genres_text, None, lambda: self.open_page("genres")),
            ("GAME SETTINGS", lambda: (last["label"] if last else "NONE"), None,
             (lambda: k.operator_game_settings(last)) if last else None),
            ("PLAY COUNTS", lambda: ">", None, lambda: self.open_page("plays")),
            ("RESET NVRAM", lambda: ">", None, lambda: self.open_page("nvram")),
            ("RESCAN GAMES", lambda: "", None, self.rescan),
            ("VIEW LOG", lambda: ">", None, lambda: self.open_page("log")),
            ("MISTER MENU", lambda: ">", None, k.operator_stock_menu),
            ("MISTER MAIN", self.main_text, None,
             k.install_kiosk_main if k.main_status() in ("STOCK", "OLD") and os.path.exists(KIOSK_MAIN) else None),
            ("UPDATE KIOSK", self.update_text, None, self.update_from_menu),
            ("REBOOT", lambda: "", None, k.operator_reboot),
        ]
        return out

    def volume_text(self):
        level, muted = self.volume
        if level is None:
            return "?"
        return "MUTE" if muted else "%d" % level

    def change_volume(self, d):
        level, muted = self.volume
        if level is None:
            level, muted = 7, False
        if muted:
            if d > 0:
                muted = False
                mister_cmd("volume unmute")
        elif d < 0 and level == 0:
            muted = True
            mister_cmd("volume mute")
        else:
            level = max(0, min(7, level + d))
            mister_cmd("volume %d" % level)
        self.volume = (level, muted)

    def change_credits(self, d):
        self.k.adjust_credits(d)
        self.credits = len(self.k.state.get("coins", []))

    def clear_credits(self):
        self.k.adjust_credits(-len(self.k.state.get("coins", [])))
        self.credits = 0
        self.show_toast("CREDITS CLEARED")

    def main_text(self):
        st = self.k.main_status()
        if st == "STOCK" and os.path.exists(KIOSK_MAIN):
            return "STOCK: 1 INSTALLS"
        if st == "OLD":
            return "OLD: 1 UPDATES"
        return st

    def update_text(self):
        if self.release:
            return "INSTALL V" + self.release["version"]
        return "V" + VERSION

    def busy(self, text):
        self.overlay = text
        self.k.need_redraw = True
        self.k.draw()

    def update_from_menu(self):
        """First press: check GitHub. If there's a newer version, the next press
        installs it and the kiosk restarts into it."""
        if self.release is None:
            self.busy("CHECKING FOR\nUPDATES...")
            try:
                rel = latest_release(self.cfg)
            except (UpdateError, OSError) as e:
                log("update check failed: %s" % e)
                self.overlay = None
                self.show_toast("UPDATE CHECK FAILED\n(SEE LOG)", 3)
                return
            self.overlay = None
            if version_tuple(rel["version"]) <= version_tuple(VERSION):
                self.show_toast("UP TO DATE\nV" + VERSION, 2.5)
                return
            self.release = rel
            self.show_toast("V%s AVAILABLE\nPRESS 1 TO INSTALL" % rel["version"], 3)
            return
        self.busy("INSTALLING\nV%s..." % self.release["version"])
        try:
            v = install_release(self.release, say=log)
        except (UpdateError, OSError) as e:
            log("update failed: %s" % e)
            self.overlay = None
            self.release = None
            self.show_toast("UPDATE FAILED\nNOTHING CHANGED", 3)
            return
        self.overlay = "UPDATED TO V%s\nRESTARTING..." % v
        self.k.draw()
        self.k.pending_restart = True

    def orientation_text(self):
        return {"all": "ALL", "horizontal": "YOKO ONLY", "vertical": "TATE ONLY"}[orientation_filter(self.cfg)]

    def hidden(self):
        return _genre_set(self.cfg.get("hidden_genres", ""))

    def genres_text(self):
        n = len(self.hidden())
        return "ALL >" if not n else "%d HIDDEN >" % n

    def toggle_genre(self, name):
        hidden = self.hidden()
        all_names = {g.lower(): g for g in self.k.genre_counts()}
        if name == "__on__":
            hidden = set()
        elif name == "__off__":
            hidden = set(all_names)
        elif name.lower() in hidden:
            hidden.discard(name.lower())
        else:
            hidden.add(name.lower())
        # keep the names as the games spell them
        self.set("hidden_genres", ", ".join(sorted(all_names.get(h, h) for h in hidden)))
        if hidden and hidden >= set(all_names):
            self.show_toast("ALL GENRES HIDDEN:\nNO GAMES WILL SHOW", 2.5)

    def screen_text(self):
        return {0: "YOKO", 90: "TATE CW", 270: "TATE CCW"}[screen_rotation(self.cfg)]

    def change_screen(self, d):
        self.cycle("screen", ["yoko", "tate_cw", "tate_ccw"], d)
        self.k.make_canvases()
        self.top = 0

    def change_theme(self, d):
        self.cycle("theme", list(THEMES), d)
        apply_theme(self.cfg)

    def rescan(self):
        n = self.k.rescan_games()
        self.show_toast("%d GAMES" % n)

    # -- sub-pages ----------------------------------------------------------------
    def open_page(self, page):
        self.page, self.sel, self.top, self.confirm = page, 0, 0, None
        k = self.k
        if page == "plays":
            plays = k.state.get("plays", {})
            names = {g["path"]: g["label"] for g in k.all_games()}
            rows = sorted(((n, names.get(p, os.path.basename(p)[:-4])) for p, n in plays.items()),
                          key=lambda r: (-r[0], r[1].lower()))
            self.lines = [("%4d  %s" % (n, name), None) for n, name in rows] or [("NO GAMES PLAYED YET", None)]
        elif page == "nvram":
            self.lines = []
            for g in k.all_games():
                if g.get("nvram") and os.path.exists(k.nvram_file(g)):
                    self.lines.append((g["label"], g))
            if not self.lines:
                self.lines = [("NO SAVED NVRAM", None)]
        elif page == "genres":
            counts = self.k.genre_counts()
            hidden = self.hidden()
            self.lines = [("SHOW ALL", "__on__"), ("HIDE ALL", "__off__")]
            for name in sorted(counts, key=str.lower):
                mark = "[ ]" if name.lower() in hidden else "[X]"
                self.lines.append(("%s %-18s %4d" % (mark, name.upper()[:18], counts[name]), name))
        elif page == "log":
            try:
                with open(LOG_PATH, errors="replace") as f:
                    tail = f.readlines()[-200:]
            except OSError:
                tail = []
            self.lines = [(l.rstrip("\n"), None) for l in tail] or [("LOG IS EMPTY", None)]
            self.sel = len(self.lines) - 1
        self.k.need_redraw = True

    def back(self):
        if self.confirm is not None:
            self.confirm = None
        elif self.page != "main":
            self.page, self.sel, self.top = "main", 0, 0
        else:
            self.k.operator_lock()
            return
        self.k.need_redraw = True

    # -- input --------------------------------------------------------------------
    def count(self):
        return len(self.items()) if self.page == "main" else len(self.lines)

    def move(self, axis, d):
        if axis == "x":
            if self.page == "main":
                label, value, change, action = self.items()[self.sel]
                if change:
                    change(d)
                    self.confirm = None
            else:                                   # page through long lists
                self.sel = max(0, min(self.count() - 1, self.sel + d * 10))
        else:
            self.sel = max(0, min(self.count() - 1, self.sel + d))
            self.confirm = None
        self.k.need_redraw = True

    def press(self):
        """Button 1."""
        if self.page == "main":
            label, value, change, action = self.items()[self.sel]
            if action is None and change:
                change(1)
            elif action:
                if label in ("REBOOT", "RESET NVRAM", "MISTER MAIN") or label == "CREDITS":
                    if label == "CREDITS" and self.credits == 0:
                        return
                    if self.confirm != label:
                        self.confirm = label
                        self.k.need_redraw = True
                        return
                self.confirm = None
                action()
        elif self.page == "genres":
            text, name = self.lines[self.sel]
            sel = self.sel
            self.toggle_genre(name)
            self.open_page("genres")
            self.sel = sel
        elif self.page == "nvram":
            text, g = self.lines[self.sel]
            if g is None:
                return
            if self.confirm != g["path"]:
                self.confirm = g["path"]
            else:
                self.confirm = None
                self.k.reset_nvram(g)
                self.open_page("nvram")
                self.show_toast("NVRAM RESET")
        self.k.need_redraw = True

    # -- drawing ------------------------------------------------------------------
    def draw(self, c, blink_on=True):
        c.fill(0, 0, c.w, c.h, BG)
        title = {"main": "OPERATOR", "plays": "PLAYS", "nvram": "NVRAM", "log": "LOG",
                 "genres": "GENRES"}[self.page]
        c.text(8, 5, title, AMBER, BG, scale=2)
        tag = "UNLOCKED"
        c.text(c.w - 8 - len(tag) * 8, 10, tag, ACCENT, BG)
        c.fill(0, 24, c.w, 2, ACCENT)

        rows = self.rows(c.h)
        n = self.count()
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + rows:
            self.top = self.sel - rows + 1
        self.top = max(0, min(self.top, max(0, n - rows)))
        chars = (c.w - 16) // 8

        if self.page == "main":
            items = self.items()
            for r in range(rows):
                i = self.top + r
                if i >= n:
                    break
                label, value, change, action = items[i]
                y = self.LIST_Y + r * self.ROW_H
                selected = i == self.sel
                fg, bg = (SELECT, ACCENT) if selected else (TEXT, BG)
                if selected:
                    c.fill(4, y - 1, c.w - 12, self.ROW_H, ACCENT)
                val = value() if value else ""
                if selected and self.confirm == label:
                    val = "PRESS 1 AGAIN"
                elif selected and change and val:
                    val = "< %s >" % val
                room = chars - len(label) - 1
                if len(val) > room:
                    val = val[:max(0, room - 1)] + "~"
                c.text(8, y + 1, label, fg, bg)
                vx = c.w - 10 - len(val) * 8
                c.text(vx, y + 1, val, fg if selected else AMBER, bg)
                if label == "VOLUME" and self.volume[0] is not None and not self.volume[1] \
                        and not (selected and self.confirm == label):
                    # seven steps, filled up to the current level
                    bx = vx - 6 - 7 * 5                 # just left of the number
                    for i in range(7):
                        on = i < self.volume[0]
                        colr = (fg if selected else CYAN) if on else (bg if selected else LINE)
                        c.fill(bx + i * 5, y + 1, 4, 7, colr)
                        if not on:
                            c.frame(bx + i * 5, y + 1, 4, 7, fg if selected else LINE)
        else:
            for r in range(rows):
                i = self.top + r
                if i >= n:
                    break
                text, ref = self.lines[i]
                y = self.LIST_Y + r * self.ROW_H
                selected = i == self.sel and self.page in ("nvram", "genres") and ref is not None
                if self.page == "nvram" and i == self.sel and ref is not None and self.confirm == ref["path"]:
                    text = "PRESS 1 AGAIN TO RESET"
                if selected:
                    c.fill(4, y - 1, c.w - 12, self.ROW_H, ACCENT)
                    c.text(8, y + 1, text, SELECT, ACCENT, max_chars=chars)
                else:
                    colr = DIM if self.page == "log" and i != self.sel else TEXT
                    c.text(8, y + 1, text, colr, BG, max_chars=chars)

        # scroll bar
        sb_h = rows * self.ROW_H
        if n > rows:
            c.fill(c.w - 5, self.LIST_Y - 1, 2, sb_h, LINE)
            th = max(8, sb_h * rows // n)
            ty = (sb_h - th) * self.top // (n - rows)
            c.fill(c.w - 5, self.LIST_Y - 1 + ty, 2, th, CYAN)

        # footer
        fy = c.h - 14
        c.fill(0, fy - 16, c.w, 1, LINE)
        if self.page == "main":
            hint1, hint2 = "1:SELECT  </>:CHANGE", "2:BACK  HOLD OP:LOCK"
        elif self.page == "nvram":
            hint1, hint2 = "1:RESET THIS GAME", "2:BACK"
        elif self.page == "genres":
            hint1, hint2 = "1:SHOW/HIDE", "2:BACK"
        else:
            hint1, hint2 = "UP/DOWN:SCROLL", "2:BACK"
        c.text(8, fy - 12, hint1[:chars], DIM, BG)
        c.text(8, fy, hint2[:chars], DIM, BG)

        msg = self.overlay
        if not msg and self.toast and time.monotonic() < self.toast_until:
            msg = self.toast
        if msg:
            lines = msg.split("\n")
            w = min(c.w - 16, max(len(l) for l in lines) * 8 + 24)
            h = len(lines) * 12 + 16
            x, y = (c.w - w) // 2, (c.h - h) // 2
            c.fill(x, y, w, h, PANEL)
            c.frame(x, y, w, h, ACCENT, 2)
            for i, l in enumerate(lines):
                c.text_center(c.w // 2, y + 9 + i * 12, l[:(w - 16) // 8], WHITE, PANEL)


def fmt_seconds(value, off="OFF"):
    try:
        s = int(float(value))
    except (TypeError, ValueError):
        return str(value)
    if s <= 0:
        return off
    if s % 60 == 0:
        return "%d MIN" % (s // 60)
    return "%d S" % s


def read_volume():
    """(level 0-7, muted) from the MiSTer's saved volume, or (None, False)."""
    try:
        with open(VOLUME_PATH, "rb") as f:
            b = f.read(1)
        v = b[0]
        return 7 - (v & 7), bool(v & 0x10)
    except (OSError, IndexError):
        return None, False


# ---------------------------------------------------------------------------
# Framebuffer
# ---------------------------------------------------------------------------

class Framebuffer:
    def __init__(self, path="/dev/fb0"):
        self.fd = os.open(path, os.O_RDWR)
        vbuf = bytearray(160)
        fcntl.ioctl(self.fd, FBIOGET_VSCREENINFO, vbuf)
        v = struct.unpack_from("20I", vbuf)
        self.xres, self.yres, self.bpp = v[0], v[1], v[6]
        fmt = PixelFormat(self.bpp, (v[8], v[9]), (v[11], v[12]), (v[14], v[15]), (v[17], v[18]))
        fbuf = bytearray(128)
        fcntl.ioctl(self.fd, FBIOGET_FSCREENINFO, fbuf)
        fixfmt = "16sLIIIIHHHI"
        fx = struct.unpack_from(fixfmt, fbuf)
        self.smem_len, self.line_length = fx[2], fx[9]
        if self.line_length == 0:
            self.line_length = self.xres * self.bpp // 8
        size = min(self.smem_len or self.line_length * self.yres, self.line_length * self.yres)
        self.mem = mmap.mmap(self.fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        self.fmt = fmt
        log("framebuffer %dx%d %dbpp stride=%d rgb=%s/%s/%s" %
            (self.xres, self.yres, self.bpp, self.line_length, fmt.r, fmt.g, fmt.b))

    def present(self, canvas):
        ox = max(0, (self.xres - canvas.w) // 2)
        oy = max(0, (self.yres - canvas.h) // 2)
        w = min(canvas.w, self.xres) * canvas.Bpp
        if ox == 0 and oy == 0 and self.line_length == canvas.stride and canvas.h <= self.yres:
            self.mem[0:len(canvas.buf)] = canvas.buf
            return
        for y in range(min(canvas.h, self.yres - oy)):
            s = y * canvas.stride
            d = (y + oy) * self.line_length + ox * canvas.Bpp
            self.mem[d:d + w] = canvas.buf[s:s + w]

    def clear(self):
        try:
            self.mem[:] = bytes(len(self.mem))
        except Exception:
            pass

    def close(self):
        try:
            self.mem.close()
        finally:
            os.close(self.fd)


# ---------------------------------------------------------------------------
# Input devices
# ---------------------------------------------------------------------------

def _bits(fd, ev, nbits):
    buf = bytearray((nbits + 7) // 8)
    try:
        fcntl.ioctl(fd, EVIOCGBIT(ev, len(buf)), buf)
    except OSError:
        return []
    return [i for i in range(nbits) if buf[i // 8] & (1 << (i % 8))]


def _ioctl_str(fd, req_fn, n=256):
    buf = bytearray(n)
    try:
        fcntl.ioctl(fd, req_fn(n), buf)
    except OSError:
        return ""
    return buf.split(b"\0", 1)[0].decode("utf-8", "replace")


class PhysicalDevice:
    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self.name = _ioctl_str(self.fd, EVIOCGNAME)
        self.phys = _ioctl_str(self.fd, EVIOCGPHYS)
        idbuf = bytearray(8)
        fcntl.ioctl(self.fd, EVIOCGID, idbuf)
        self.bustype, self.vendor, self.product, self.version = struct.unpack("4H", idbuf)
        self.ev = _bits(self.fd, 0, 32)
        self.keys = _bits(self.fd, EV_KEY, KEY_MAX + 1) if EV_KEY in self.ev else []
        self.abs = _bits(self.fd, EV_ABS, ABS_MAX_ + 1) if EV_ABS in self.ev else []
        self.msc = _bits(self.fd, EV_MSC, 8) if EV_MSC in self.ev else []
        self.rel = _bits(self.fd, EV_REL, 16) if EV_REL in self.ev else []
        self.absinfo = {}
        for a in self.abs:
            buf = bytearray(24)
            try:
                fcntl.ioctl(self.fd, EVIOCGABS(a), buf)
                self.absinfo[a] = struct.unpack("6i", buf)  # value,min,max,fuzz,flat,res
            except OSError:
                self.absinfo[a] = (0, -1, 1, 0, 0, 0)
        self.grabbed = False
        self.virtual = None
        self.pressed = set()
        self.abs_state = {}
        self._partial = b""

    @property
    def vidpid(self):
        return "%04x:%04x" % (self.vendor, self.product)

    def matches(self, spec):
        """spec is '' (any), a vid:pid, or part of the device name."""
        spec = spec.strip().lower()
        if not spec:
            return True
        return spec == self.vidpid or spec in self.name.lower()

    def is_input_we_want(self):
        if self.phys.startswith(VIRTUAL_PHYS):
            return False
        if EV_KEY not in self.ev:
            return False
        if EV_REL in self.ev and REL_X in self.rel and EV_ABS not in self.ev:
            return False                      # plain mouse
        has_joy = any(0x120 <= k <= 0x13F or 0x2C0 <= k <= 0x2E7 for k in self.keys)
        has_kbd = any(1 <= k <= 0x77 for k in self.keys)
        return has_joy or has_kbd

    def try_grab(self):
        if self.grabbed:
            return True
        try:
            fcntl.ioctl(self.fd, EVIOCGRAB, 1)
            self.grabbed = True
            log("grabbed %s (%s %s)" % (self.path, self.vidpid, self.name))
        except OSError as e:
            if e.errno != errno.EBUSY:
                log("grab %s failed: %s" % (self.path, e))
        return self.grabbed

    def read_events(self):
        try:
            data = os.read(self.fd, EVENT_SIZE * 64)
        except BlockingIOError:
            return []
        data = self._partial + data
        n = len(data) // EVENT_SIZE
        self._partial = data[n * EVENT_SIZE:]
        out = []
        for i in range(n):
            _, _, t, c, v = struct.unpack_from(EVENT_FMT, data, i * EVENT_SIZE)
            out.append((t, c, v))
        return out

    def close(self):
        if self.virtual:
            self.virtual.close()
        try:
            if self.grabbed:
                fcntl.ioctl(self.fd, EVIOCGRAB, 0)
        except OSError:
            pass
        os.close(self.fd)


class VirtualDevice:
    """A /dev/uinput device. Clones a physical device so the MiSTer's
    existing button mapping (stored by vid:pid) still applies."""

    _UINPUT_USER_DEV = "80sHHHHI%di%di%di%di" % (ABS_CNT, ABS_CNT, ABS_CNT, ABS_CNT)

    def __init__(self, name, ids, keys, absinfo=None, msc=(), phys_suffix="pad"):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        absinfo = absinfo or {}
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        for k in keys:
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, k)
        if absinfo:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_ABS)
            for a in absinfo:
                fcntl.ioctl(self.fd, UI_SET_ABSBIT, a)
        if msc:
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_MSC)
            for m in msc:
                fcntl.ioctl(self.fd, UI_SET_MSCBIT, m)
        self._phys = ctypes.create_string_buffer((VIRTUAL_PHYS + phys_suffix).encode())
        try:
            ioctl_ptr(self.fd, UI_SET_PHYS, ctypes.addressof(self._phys))
        except (OSError, AttributeError) as e:
            log("UI_SET_PHYS failed (%s); virtual devices identified by sysfs instead" % e)
        absmax, absmin, absfuzz, absflat = ([0] * ABS_CNT for _ in range(4))
        for a, info in absinfo.items():
            absmin[a], absmax[a], absfuzz[a], absflat[a] = info[1], info[2], info[3], info[4]
        bustype, vendor, product, version = ids
        data = struct.pack(self._UINPUT_USER_DEV, name.encode()[:79], bustype, vendor, product,
                           version, 0, *absmax, *absmin, *absfuzz, *absflat)
        os.write(self.fd, data)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        self.name = name
        self.event_nodes = set()
        try:
            buf = bytearray(64)
            fcntl.ioctl(self.fd, UI_GET_SYSNAME(len(buf)), buf)
            sysname = buf.split(b"\0", 1)[0].decode()
            for n in os.listdir("/sys/class/input/" + sysname):
                if n.startswith("event"):
                    self.event_nodes.add("/dev/input/" + n)
        except OSError as e:
            log("UI_GET_SYSNAME failed: %s" % e)

    def emit(self, t, c, v, sync=False):
        try:
            os.write(self.fd, struct.pack(EVENT_FMT, 0, 0, t, c, v))
            if sync:
                os.write(self.fd, struct.pack(EVENT_FMT, 0, 0, EV_SYN, SYN_REPORT, 0))
        except OSError as e:
            log("uinput write failed: %s" % e)

    def tap(self, code):
        self.emit(EV_KEY, code, 1, sync=True)
        time.sleep(0.04)
        self.emit(EV_KEY, code, 0, sync=True)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        except OSError:
            pass
        os.close(self.fd)


# ---------------------------------------------------------------------------
# MiSTer helpers
# ---------------------------------------------------------------------------

def mister_cmd(text, quiet=False):
    if not quiet:
        log("MiSTer_cmd: %s" % text)
    try:
        fd = os.open(MISTER_CMD, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, (text + "\n").encode())
        finally:
            os.close(fd)
        return True
    except OSError as e:
        log("MiSTer_cmd write failed: %s" % e)
        return False


def mister_ready():
    """True when a MiSTer main program is running and reading /dev/MiSTer_cmd.
    (Opening a FIFO for writing without blocking fails while nobody reads it.)"""
    try:
        fd = os.open(MISTER_CMD, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return False
    os.close(fd)
    return True


def core_stamp():
    """Changes every time a freshly started MiSTer main program writes /tmp/CORENAME."""
    try:
        return os.stat(CORENAME_PATH).st_mtime_ns
    except OSError:
        return None


def main_features():
    """Extra features of the running MiSTer main program (empty for stock MiSTer)."""
    try:
        with open(FEATURES_PATH) as f:
            return {w.strip() for w in f if w.strip()}
    except OSError:
        return set()


def set_kiosk_flag(on):
    try:
        if on:
            with open(KIOSK_FLAG, "w") as f:
                f.write("%d\n" % os.getpid())
        elif os.path.exists(KIOSK_FLAG):
            os.remove(KIOSK_FLAG)
    except OSError as e:
        log("kiosk flag: %s" % e)


def same_file(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                x, y = fa.read(1 << 16), fb.read(1 << 16)
                if x != y:
                    return False
                if not x:
                    return True
    except OSError:
        return False


def set_boot_flag(on):
    try:
        if on and not os.path.exists(KIOSK_BOOT_FLAG):
            os.makedirs(os.path.dirname(KIOSK_BOOT_FLAG), exist_ok=True)
            with open(KIOSK_BOOT_FLAG, "w") as f:
                f.write("MisterOperator kiosk: skip the MiSTer menu at boot\n")
        elif not on and os.path.exists(KIOSK_BOOT_FLAG):
            os.remove(KIOSK_BOOT_FLAG)
    except OSError as e:
        log("boot flag: %s" % e)


def core_name():
    try:
        with open(CORENAME_PATH, errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def read_fb_param():
    try:
        with open(FB_PARAM_PATH) as f:
            return f.read().split()
    except OSError:
        return None


def write_fb_param(values):
    try:
        with open(FB_PARAM_PATH, "w") as f:
            f.write(" ".join(str(v) for v in values) + "\n")
        return True
    except OSError:
        return False


def set_tty_mode(mode):
    try:
        fd = os.open("/dev/tty1", os.O_RDWR | os.O_NOCTTY)
        try:
            fcntl.ioctl(fd, KDSETMODE, mode)
        finally:
            os.close(fd)
    except OSError as e:
        log("KDSETMODE failed: %s" % e)


# ---------------------------------------------------------------------------
# The kiosk
# ---------------------------------------------------------------------------

S_WAIT, S_LAUNCHER, S_GAME, S_RETURNING, S_UNLOCKED = "wait", "launcher", "game", "returning", "unlocked"
S_ATTRACT = "attract"
S_OPERATOR = "operator"


# ---------------------------------------------------------------------------
# Standard button layout
#
# The MiSTer keeps each arcade game's controls in
#   /media/fat/config/inputs/<setname>_input_<vid>_<pid>_v4.map
# (older builds: _v3.map): 38 little-endian uint32 slots. Slots 0-3 are
# right/left/down/up and slot 4+i is the i-th name in the .mra's
# <buttons names="...">. The controller's own mapping from the MiSTer menu is
# input_<vid>_<pid>_v4.map, in "virtual pad" slots (A=4, B=5, X=6, Y=7, L=8,
# R=9, Select=10, Start=11, axes 28/29). Before each game starts, the kiosk
# writes that game's file so panel buttons 1-6 always land on the game's
# buttons in the same order, Start and Coin are kept, and Pause/Service/etc.
# are left unmapped.
# ---------------------------------------------------------------------------

MAP_SLOTS = 38
PAD_SLOTS = {"RIGHT": 0, "LEFT": 1, "DOWN": 2, "UP": 3, "A": 4, "B": 5, "X": 6, "Y": 7,
             "L": 8, "R": 9, "SELECT": 10, "START": 11, "L2": 32, "R2": 33, "L3": 34, "R3": 35}
SYS_AXIS_X, SYS_AXIS_Y = 28, 29
MAP_AXIS_MASK, MAP_FLAG_INVERT = 0xFFFF, 0x10000
KEY_EMU = 0x2FF + 1        # KEY_MAX + 1 in the MiSTer source


def read_map(path):
    try:
        with open(path, "rb") as f:
            raw = f.read(MAP_SLOTS * 4)
    except OSError:
        return None
    if len(raw) < 16:
        return None
    raw += b"\0" * (MAP_SLOTS * 4 - len(raw))
    return list(struct.unpack("<%dI" % MAP_SLOTS, raw))


def find_map(inputs_dir, stem):
    """Newest-format file for this map name, e.g. stem 'input_16c0_05e1'."""
    for ver in (4, 3):
        p = os.path.join(inputs_dir, "%s_v%d.map" % (stem, ver))
        if os.path.exists(p):
            return p, read_map(p)
    return None, None


def device_ids(inputs_dir, vid, pid):
    """The id strings the MiSTer uses for this controller in map file names:
    vid_pid, plus any vid_pid_<suffix> it has saved menu maps under."""
    base = "%04x_%04x" % (vid, pid)
    ids = {base}
    try:
        for n in os.listdir(inputs_dir):
            m = re.match(r"^input_(%s(?:_[0-9a-zA-Z]+)?)(_m)?_v\d\.map$" % re.escape(base), n)
            if m:
                ids.add(m.group(1))
    except OSError:
        pass
    return sorted(ids)


def dirs_from_pad_map(mmap):
    """Same as the MiSTer's own default: d-pad codes, plus the stick axes."""
    d = [mmap[i] & 0xFFFF for i in range(4)]
    for axis_slot, (lo_i, hi_i) in ((SYS_AXIS_X, (1, 0)), (SYS_AXIS_Y, (3, 2))):
        a = mmap[axis_slot]
        if a and a != 0xFFFFFFFF:
            mn = KEY_EMU + ((a & MAP_AXIS_MASK) << 1)
            mx = mn + 1
            lo, hi = (mx, mn) if a & MAP_FLAG_INVERT else (mn, mx)
            d[lo_i] |= lo << 16
            d[hi_i] |= hi << 16
    return d


def _num_list(text):
    out = []
    for p in text.split(","):
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
    return out


def plan_layout(cfg, names_text):
    """Work out where each of a game's buttons goes.
    Returns a list of (index, name, role) with role one of
    ("panel", n) / ("start",) / ("coin",) / ("off", why)."""
    names = [n.strip() for n in names_text.split(",")]
    while names and not names[-1]:
        names.pop()
    drop = [w.strip().lower() for w in cfg.get("drop_buttons", "").split(",") if w.strip()]
    kinds = []
    for n in names:
        low = n.lower()
        if not low or low == "-":
            kinds.append("unused")
        elif any(w in low for w in drop):
            kinds.append("drop")
        elif "start" in low:
            kinds.append("start")
        elif "coin" in low or low.startswith("credit") or low == "insert":
            kinds.append("coin")
        else:
            kinds.append("action")
    actions = [i for i, k in enumerate(kinds) if k == "action"]
    count = len(actions)
    layout = _num_list(cfg.get("layout_%d" % min(count, 6), "")) if count else []
    if count > 6:
        layout = layout[:6]
    plan, seen = [], set()
    for i, (n, k) in enumerate(zip(names, kinds)):
        if k == "action":
            pos = actions.index(i)
            if pos < len(layout) and 1 <= layout[pos] <= 6:
                plan.append((i, n, ("panel", layout[pos])))
            else:
                plan.append((i, n, ("off", "more than 6 buttons" if pos >= 6 else "not in layout_%d" % count)))
        elif k in ("start", "coin"):
            if k in seen:
                plan.append((i, n, ("off", "second %s" % k)))
            else:
                seen.add(k)
                plan.append((i, n, (k,)))
        elif k == "drop":
            plan.append((i, n, ("off", "removed")))
        else:
            plan.append((i, n, ("off", "unused")))
    return plan


def describe_plan(plan):
    parts = []
    for _, n, role in plan:
        if role[0] == "panel":
            parts.append("%s=%d" % (n, role[1]))
        elif role[0] in ("start", "coin"):
            parts.append("%s=%s" % (n, role[0].upper()))
        elif role[1] != "unused":
            parts.append("%s=off" % n)
    return ", ".join(parts)


def panel_codes(cfg, mmap):
    """Map values for panel buttons 1-6, Start and Coin, from the controller's
    MiSTer menu mapping (names like B,A,R,Y,X,L) or from key names
    (e.g. BTN_TRIGGER)."""
    def one(name):
        name = name.strip()
        if not name:
            return 0
        if name.upper() in PAD_SLOTS:
            return mmap[PAD_SLOTS[name.upper()]] if mmap else 0
        try:
            return parse_code(name) or 0
        except ValueError:
            return 0
    panel = [one(n) for n in cfg.get("panel_layout", "").split(",")][:6]
    panel += [0] * (6 - len(panel))
    return panel, one(cfg.get("panel_start", "")), one(cfg.get("panel_coin", ""))


def build_game_map(cfg, plan, mmap, old):
    """The 38-slot map for one game on one controller, or None if it can't
    be built (no menu mapping and no earlier map to take directions from)."""
    if old and any(old[:4]):
        dirs = old[:4]
    elif mmap:
        dirs = dirs_from_pad_map(mmap)
    else:
        return None
    panel, start, coin = panel_codes(cfg, mmap)
    if not any(panel):
        return None
    out = [0] * MAP_SLOTS
    out[:4] = dirs
    for i, _, role in plan:
        slot = 4 + i
        if slot >= MAP_SLOTS:
            continue
        if role[0] == "panel":
            out[slot] = panel[role[1] - 1]
        elif role[0] == "start":
            out[slot] = start
        elif role[0] == "coin":
            out[slot] = coin
    return out


def map_core_name(game):
    # The MiSTer names an arcade game's map after its <setname>, cut to 31 chars.
    return (game.get("setname") or "")[:31]


def write_game_maps(cfg, game, vidpids, log_fn=None):
    """Write the standard layout for one game for each controller.
    Returns the number of files written."""
    log_fn = log_fn or log
    if not flag(cfg, "standard_layout") or game.get("mgl"):
        return 0
    core = map_core_name(game)
    if not core or not game.get("buttons"):
        log_fn("layout: %s has no setname or button list, left as is" % game.get("file"))
        return 0
    plan = plan_layout(cfg, game["buttons"])
    inputs = cfg["inputs_dir"]
    backup = cfg["map_backup_dir"]
    written = 0
    for vid, pid in sorted(set(vidpids)):
        for dev_id in device_ids(inputs, vid, pid):
            _, mmap = find_map(inputs, "input_" + dev_id)
            old_path, old = find_map(inputs, "%s_input_%s" % (core, dev_id))
            new = build_game_map(cfg, plan, mmap, old)
            if new is None:
                log_fn("layout: no MiSTer menu mapping for %s; map the controller once in the "
                       "MiSTer menu (input_%s_v4.map)" % (dev_id, dev_id))
                continue
            data = struct.pack("<%dI" % MAP_SLOTS, *new)
            for ver in (4, 3):
                path = os.path.join(inputs, "%s_input_%s_v%d.map" % (core, dev_id, ver))
                try:
                    with open(path, "rb") as f:
                        if f.read() == data:
                            continue
                    _backup_map(path, backup)
                except OSError:
                    _note_created(path, backup)
                try:
                    os.makedirs(inputs, exist_ok=True)
                    with open(path + ".tmp", "wb") as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(path + ".tmp", path)
                    written += 1
                except OSError as e:
                    log_fn("layout: could not write %s: %s" % (path, e))
    if written:
        log_fn("layout: %s (%s): %s" % (game.get("file"), core, describe_plan(plan)))
    return written


def _backup_map(path, backup_dir):
    dst = os.path.join(backup_dir, os.path.basename(path))
    if os.path.exists(dst) or os.path.basename(path) in _created_list(backup_dir):
        return
    try:
        os.makedirs(backup_dir, exist_ok=True)
        with open(path, "rb") as f, open(dst, "wb") as g:
            g.write(f.read())
    except OSError as e:
        log("layout: could not back up %s: %s" % (path, e))


def _created_list(backup_dir):
    try:
        with open(os.path.join(backup_dir, "created.txt")) as f:
            return {l.strip() for l in f if l.strip()}
    except OSError:
        return set()


def _note_created(path, backup_dir):
    name = os.path.basename(path)
    if name in _created_list(backup_dir):
        return
    try:
        os.makedirs(backup_dir, exist_ok=True)
        with open(os.path.join(backup_dir, "created.txt"), "a") as f:
            f.write(name + "\n")
    except OSError:
        pass


def restore_maps(cfg):
    """Put back every map the kiosk changed, and delete the ones it created."""
    inputs, backup = cfg["inputs_dir"], cfg["map_backup_dir"]
    restored = removed = 0
    for name in sorted(_created_list(backup)):
        try:
            os.unlink(os.path.join(inputs, name))
            removed += 1
        except OSError:
            pass
    try:
        names = [n for n in os.listdir(backup) if n.endswith(".map")]
    except OSError:
        names = []
    for name in names:
        with open(os.path.join(backup, name), "rb") as f, open(os.path.join(inputs, name), "wb") as g:
            g.write(f.read())
        restored += 1
    for name in names + ["created.txt"]:
        try:
            os.unlink(os.path.join(backup, name))
        except OSError:
            pass
    return restored, removed


class Kiosk:
    def __init__(self):
        self.cfg = load_config()
        self.state = load_state()
        if flag(self.cfg, "lock_on_boot"):
            self.state["locked"] = True
        self.state.setdefault("locked", True)
        self.mode = S_WAIT
        self.devices = {}               # path -> PhysicalDevice
        self.ungrabbed = {}             # path -> (first seen, carries menu/operator button)
        self.current_game = None
        self.opview = None              # operator menu, while it's open
        self.flag_on = None             # is KIOSK_FLAG present
        self.pending_restart = False    # restart (after an update) once nobody's playing
        self.restarting = False
        self.op_activity = 0
        self.coin_queue = []            # coins waiting to go into the game just started
        self.coin_next = 0
        self.coin_down = None           # coin being "pressed" right now
        self.own_nodes = set()          # event nodes of our own virtual devices
        self.keys_dev = None            # virtual keyboard used to send F9
        self.fb = None
        self.canvas = None
        self.view = None
        self.need_redraw = True
        self.last_blink = 0
        self.blink_on = True
        self.menu_since = None
        self.last_core = None
        self.game_started = 0
        self.game_seen_core = False
        self.suppress = set()           # (dev, code) releases to swallow after launch
        self.op_down_at = None
        self.op_fired = False
        self.menu_down_at = None
        self.setup_step = None          # None, "menu", "operator"
        self.repeat = {}                # direction -> next repeat time
        self.repeat_count = {}
        self.dir_state = {}             # (dev, axis) -> -1/0/1
        self.last_scan = 0
        self.last_poll = 0
        self.last_fb_check = 0
        self.return_at = -1e9
        self.await_stamp = None         # CORENAME stamp to wait past after reloading the menu
        self.last_activity = time.monotonic()
        self.game_last_input = 0
        self.attract_started = 0
        self.attract_seen_core = False
        self.attract_stamp = None
        self.attract_recent = []

        self.launch_buttons = parse_code_list(self.cfg["launch_buttons"])
        self.genre_buttons = parse_code_list(self.cfg["genre_buttons"])
        self.genre_back_buttons = parse_code_list(self.cfg["genre_back_buttons"])
        self.letter_buttons = parse_code_list(self.cfg["letter_buttons"])
        self.coin_buttons = parse_code_list(self.cfg["coin_buttons"])
        self.reload_buttons()

    # -- config -------------------------------------------------------------
    def reload_buttons(self):
        try:
            self.menu_button = parse_code(self.cfg["menu_button"])
            self.operator_button = parse_code(self.cfg["operator_button"])
        except ValueError as e:
            log("config error: %s" % e)
            self.menu_button = self.operator_button = None
        if self.menu_button is None or self.operator_button is None:
            self.setup_step = "menu" if self.menu_button is None else "operator"

    def is_menu_btn(self, dev, code):
        return code == self.menu_button and dev.matches(self.cfg["menu_device"])

    def is_operator_btn(self, dev, code):
        return code == self.operator_button and dev.matches(self.cfg["operator_device"])

    # -- devices --------------------------------------------------------------
    def scan_devices(self):
        ignore = [s.strip().lower() for s in self.cfg["ignore_devices"].split(",") if s.strip()]
        try:
            nodes = sorted(n for n in os.listdir("/dev/input") if n.startswith("event"))
        except OSError:
            nodes = []
        present = {"/dev/input/" + n for n in nodes}
        for path in list(self.devices):
            if path not in present:
                log("device removed: %s" % path)
                try:
                    self.devices.pop(path).close()
                except OSError:
                    pass
        for path in list(self.ungrabbed):
            if path not in present:
                self.ungrabbed.pop(path, None)
        for path in present - set(self.devices) - self.own_nodes:
            try:
                dev = PhysicalDevice(path)
            except OSError:
                continue
            if dev.name.startswith("ArcadeKiosk") or any(
                    v.virtual and v.virtual.name == dev.name and v.vidpid == dev.vidpid
                    and not dev.phys for v in self.devices.values()):
                os.close(dev.fd)            # one of ours
                self.own_nodes.add(path)
                continue
            if not dev.is_input_we_want() or any(dev.matches(s) for s in ignore):
                os.close(dev.fd)
                continue
            if not dev.try_grab():
                # The MiSTer has hold of it (it grabs every controller while a core is
                # running). Cloning it now would give the core the same controller
                # twice and we'd see none of its presses, so wait until the game list
                # is up, when the MiSTer lets go.
                if path not in self.ungrabbed:
                    log("can't take %s %s '%s' yet (in use by the MiSTer); will retry" %
                        (path, dev.vidpid, dev.name))
                    self.ungrabbed[path] = (time.monotonic(), self.is_control_device(dev))
                os.close(dev.fd)
                continue
            if self.ungrabbed.pop(path, None):
                log("took %s after waiting" % path)
            try:
                dev.virtual = VirtualDevice(dev.name, (dev.bustype, dev.vendor, dev.product, dev.version),
                                            dev.keys, dev.absinfo, dev.msc,
                                            phys_suffix=os.path.basename(path))
            except Exception as e:      # never let one controller stop the kiosk
                log("cannot create virtual clone for %s: %s" % (path, e))
                dev.close()
                continue
            self.own_nodes |= dev.virtual.event_nodes
            for a, info in dev.absinfo.items():
                dev.abs_state[a] = info[0]
            log("device added: %s %s '%s' keys=%d abs=%s" %
                (path, dev.vidpid, dev.name, len(dev.keys), [hex(a) for a in dev.abs]))
            self.devices[path] = dev

    def is_control_device(self, dev):
        """Does this controller carry the MENU or OPERATOR button?"""
        for code, spec in ((self.menu_button, self.cfg["menu_device"]),
                           (self.operator_button, self.cfg["operator_device"])):
            if code is not None and code in dev.keys and dev.matches(spec):
                return True
        return False

    def ensure_keys_dev(self):
        if self.keys_dev is None:
            self.keys_dev = VirtualDevice("ArcadeKiosk Keys", (0x03, 0x1209, 0xAC01, 1),
                                          [KEY_F9, KEY_NAMES["KEY_F12"]], phys_suffix="keys")
            self.own_nodes |= self.keys_dev.event_nodes
            time.sleep(1.0)  # let the MiSTer notice the new keyboard

    # -- framebuffer ----------------------------------------------------------
    def activate_framebuffer(self, timeout=15.0):
        """Switch the menu core to the Linux framebuffer at our resolution.

        The stock MiSTer menu is on screen from the moment the menu core starts
        until this succeeds, so it runs as fast as the MiSTer allows: it starts
        the instant the new main program is reading commands, and checks the
        result through the framebuffer driver's mode parameter."""
        w, h = int(self.cfg["fb_width"]), int(self.cfg["fb_height"])
        target = ["8888", "1", str(w), str(h)]
        fb_cmd = "fb_cmd1 8888 1 %d %d" % (w, h)
        self.ensure_keys_dev()
        extra = float(self.cfg["menu_settle_s"])
        if extra > 0:
            time.sleep(extra)
        t0 = time.monotonic()
        deadline = t0 + timeout
        set_tty_mode(KD_GRAPHICS)   # keep the login prompt off screen when F9 lands

        def accepted(wait):
            end = time.monotonic() + wait
            while True:
                cur = read_fb_param()
                if cur and cur[:4] == target:
                    return True
                if time.monotonic() >= end:
                    return False
                time.sleep(0.02)

        ok = False
        presses = 0
        if read_fb_param() is None:
            # No way to confirm on this system: fixed sequence.
            while not mister_ready() and time.monotonic() < deadline:
                time.sleep(0.05)
            time.sleep(1.0)
            self.keys_dev.tap(KEY_F9)
            presses = 1
            time.sleep(0.5)
            mister_cmd(fb_cmd, quiet=True)
            time.sleep(0.3)
            ok = True
        else:
            def settle_offload():
                # F9 also schedules a background write of the console's mode;
                # make sure that didn't land after ours.
                time.sleep(0.25)
                if not accepted(0):
                    mister_cmd(fb_cmd, quiet=True)
                    accepted(0.4)

            reloaded = False
            while time.monotonic() < deadline and not ok:
                if not mister_ready():
                    time.sleep(0.03)
                    continue
                if (not reloaded and time.monotonic() - t0 > 3
                        and "kiosk_active" in main_features() and os.path.exists(KIOSK_FLAG)):
                    # Kiosk build of the MiSTer main program, but its menu is still
                    # up (an early build that started before the kiosk and blocks
                    # F9). A fresh start of the menu core skips the menu.
                    log("MiSTer menu still showing; reloading the menu core")
                    reloaded = True
                    stamp = core_stamp()
                    mister_cmd("load_core %s" % MENU_RBF)
                    wait_until = time.monotonic() + 10
                    while time.monotonic() < wait_until and core_stamp() == stamp:
                        time.sleep(0.1)
                    continue
                cur = read_fb_param()
                if cur and cur[:4] == target:
                    # Stale value from an earlier session: change it so we can tell
                    # whether the MiSTer accepts the next request.
                    write_fb_param([8888, 1, w, h - 8, w * 4])
                # Already on (e.g. the kiosk restarted over its own screen)?
                mister_cmd(fb_cmd, quiet=True)
                if accepted(0.15):
                    ok = True
                    break
                # Framebuffer is off: F9 turns on the menu core's terminal screen.
                self.keys_dev.tap(KEY_F9)
                presses += 1
                # Resend the (harmless while off) mode command until it takes, so
                # F9 is never pressed twice while the first press is in flight.
                until = time.monotonic() + 0.7
                while time.monotonic() < until:
                    time.sleep(0.04)
                    mister_cmd(fb_cmd, quiet=True)
                    if accepted(0.04):
                        settle_offload()
                        ok = True
                        break
        log("framebuffer %s in %.2fs (%d F9 press%s)" % (
            "ready" if ok else "NOT confirmed", time.monotonic() - t0, presses,
            "" if presses == 1 else "es"))
        set_tty_mode(KD_GRAPHICS)
        try:
            self.fb = Framebuffer()
        except OSError as e:
            log("cannot open framebuffer: %s" % e)
            self.fb = None
            return False
        self.make_canvases()
        return True

    def make_canvases(self):
        w, h = int(self.cfg["fb_width"]), int(self.cfg["fb_height"])
        self.canvas = Canvas(min(w, self.fb.xres), min(h, self.fb.yres), self.fb.fmt)
        self.rotation = screen_rotation(self.cfg)
        # TATE: draw upright on a portrait canvas, then turn it onto the screen.
        self.lcanvas = (Canvas(self.canvas.h, self.canvas.w, self.fb.fmt)
                        if self.rotation else None)

    def check_fb_mode(self):
        """Put our screen mode back if something else changed it."""
        if not self.fb:
            return
        w, h = int(self.cfg["fb_width"]), int(self.cfg["fb_height"])
        cur = read_fb_param()
        if cur is None or cur[:4] == ["8888", "1", str(w), str(h)]:
            return
        log("screen mode changed to %s; restoring" % " ".join(cur))
        mister_cmd("fb_cmd1 8888 1 %d %d" % (w, h), quiet=True)
        time.sleep(0.1)
        try:
            self.fb.close()
            self.fb = Framebuffer()
            self.make_canvases()
        except OSError as e:
            log("cannot reopen framebuffer: %s" % e)
            self.fb = None
        self.need_redraw = True

    def release_framebuffer(self, text_mode=True, clear=True):
        if self.fb:
            if clear:
                self.fb.clear()
            self.fb.close()
            self.fb = None
        if text_mode:
            set_tty_mode(KD_TEXT)

    # -- modes ----------------------------------------------------------------
    def enter_launcher(self):
        log("entering launcher")
        if not self.fb and not self.activate_framebuffer():
            return
        self.opview = None
        self.scan_devices()          # grabs succeed now the MiSTer has let go
        games = scan_games(self.cfg)
        log("%d games" % len(games))
        keep = self.view
        self.view = LauncherView(self.cfg, games)
        if keep:
            self.view.set_genre(keep.genre_idx)
            self.view.select_path(keep.current()["path"] if keep.current() else "")
        elif flag(self.cfg, "remember_last") and self.state.get("last"):
            self.view.select_path(self.state["last"])
        if self.setup_step:
            self.update_setup_overlay()
        if self.state.get("pending_toast"):
            self.view.show_toast(self.state.pop("pending_toast"), 3)
        self.return_coins()
        self.view.credits = len(self.state.get("coins", []))
        self.release_virtual_keys()
        self.dir_state.clear()
        self.repeat.clear()
        self.last_activity = time.monotonic()
        self.mode = S_LAUNCHER
        self.need_redraw = True
        self.write_status()

    # -- coins ------------------------------------------------------------------
    # Coins put in on the game list (or during a demo) are held, shown on screen,
    # and inserted into the next game once it has had time to load. They are kept
    # in state.json so a reboot or kiosk restart doesn't lose them.
    def bank_coin(self, dev, code):
        bank = self.state.setdefault("coins", [])
        if len(bank) >= int(self.cfg["max_credits"]):
            log("coin: bank full (%d)" % len(bank))
        else:
            bank.append([dev.vidpid, code])
            save_state(self.state)
            log("coin: banked (%s on %s), %d credit%s" % (code_name(code), dev.vidpid, len(bank),
                                                        "" if len(bank) == 1 else "s"))
        if self.view:
            self.view.credits = len(bank)
            self.view.show_toast("CREDIT%s %d" % ("" if len(bank) == 1 else "S", len(bank)), 1.5)
            self.need_redraw = True

    def return_coins(self):
        """Put coins that never reached the game back in the bank."""
        left = list(self.coin_queue)
        if self.coin_down:
            self.release_coin()
        if left:
            log("coin: %d not delivered, kept for the next game" % len(left))
            self.state["coins"] = [list(c) for c in left] + self.state.get("coins", [])
            save_state(self.state)
        self.coin_queue = []

    def coin_device(self, vidpid, code):
        """The virtual copy of the controller the coin came from, or any that has that button."""
        devs = list(self.devices.values())
        for d in devs:
            if d.virtual and d.vidpid == vidpid and code in d.keys:
                return d
        for d in devs:
            if d.virtual and code in d.keys:
                return d
        return None

    def release_coin(self):
        dev, code = self.coin_down
        if dev.virtual:
            dev.virtual.emit(EV_KEY, code, 0, sync=True)
        self.coin_down = None

    def tick_coins(self, now):
        if self.mode != S_GAME or not (self.coin_queue or self.coin_down):
            return
        if now < self.coin_next:
            return
        if self.coin_down:                          # finish the press
            self.release_coin()
            self.coin_next = now + 0.35
            return
        vidpid, code = self.coin_queue[0]
        dev = self.coin_device(vidpid, code)
        self.coin_queue.pop(0)
        if not dev:
            log("coin: no controller with %s to insert it; dropped" % code_name(code))
            return
        log("coin: inserting (%s), %d more to go" % (code_name(code), len(self.coin_queue)))
        dev.virtual.emit(EV_KEY, code, 1, sync=True)
        self.coin_down = (dev, code)
        self.coin_next = now + 0.15                 # hold it like a real coin switch

    def launch(self, game):
        log("launching %s" % game["path"])
        self.view.overlay = "LOADING\n" + game["label"][:30]
        self.draw()
        self.state["last"] = game["path"]
        plays = self.state.setdefault("plays", {})
        plays[game["path"]] = plays.get(game["path"], 0) + 1
        save_state(self.state)
        self.suppress = {(d.path, k) for d in self.devices.values() for k in d.pressed}
        # Keep the LOADING screen up (no console flash) until the core takes over.
        self.release_framebuffer(text_mode=False, clear=False)
        self.view.overlay = None
        self.mode = S_GAME
        self.current_game = game
        self.game_started = time.monotonic()
        # Banked coins go in once the game has had time to load.
        self.coin_queue = [tuple(c) for c in self.state.get("coins", [])]
        if self.coin_queue:
            self.state["coins"] = []
            save_state(self.state)
            self.coin_next = self.game_started + float(self.cfg["coin_delay_s"])
            log("coin: %d credit%s will go in after %s s" % (
                len(self.coin_queue), "" if len(self.coin_queue) == 1 else "s", self.cfg["coin_delay_s"]))
        self.game_last_input = self.game_started
        self.game_seen_core = False
        self.menu_since = None
        try:
            write_game_maps(self.cfg, game, [(d.vendor, d.product) for d in self.devices.values() if d.virtual])
        except Exception as e:      # never stop a game starting over this
            log("layout: failed for %s: %s" % (game.get("file"), e))
        mister_cmd("load_core %s" % game["path"])
        self.write_status()

    def nvram_mode(self):
        m = self.cfg.get("save_nvram", "once").strip().lower()
        if m in ("0", "off", "no", "never", "false"):
            return "off"
        if m in ("always", "every", "2"):
            return "always"
        return "once"            # "1" from v1.6 kiosk.ini files also means once

    def nvram_file(self, g):
        base = os.path.basename(g["path"])
        if base.lower().endswith(".mra"):
            base = base[:-4]
        return os.path.join(self.cfg["nvram_dir"], base + ".nvm")

    def save_nvram(self):
        """Let the MiSTer save the running game's NVRAM (settings, high scores, CMOS).

        The MiSTer only writes arcade NVRAM to the SD card when its on-screen menu
        opens, and there is no command to do it otherwise. Players never open that
        menu here, so without this a game such as NBA Jam loses its settings and
        shows a CMOS error every time it starts.

        The kiosk opens the menu (F12), waits a moment and closes it again, so it
        appears for a fraction of a second. With save_nvram = once (default) that
        only happens until the game has a good saved NVRAM file; = always saves on
        every exit (keeps high scores, shows the flash each time)."""
        g = self.current_game
        mode = self.nvram_mode()
        if not (g and g.get("nvram")) or mode == "off":
            return
        if core_name().upper() in ("", "MENU"):
            return
        if "save_nvram" in main_features():
            # Kiosk build of the MiSTer main program: save directly, nothing on
            # screen, so it can happen on every quit.
            log("nvram: saving for %s (command)" % g["label"])
            mister_cmd("save_nvram", quiet=True)
            time.sleep(0.2)
            return
        played = time.monotonic() - self.game_started
        good = self.state.setdefault("nvram_good", [])
        if mode == "once" and g["path"] in good and os.path.exists(self.nvram_file(g)):
            return
        try:
            self.ensure_keys_dev()
        except OSError as e:
            log("nvram: no virtual keyboard (%s)" % e)
            return
        log("nvram: saving for %s (played %d s)" % (g["label"], played))
        self.release_virtual_keys()
        f12 = KEY_NAMES["KEY_F12"]
        self.keys_dev.tap(f12)             # open the MiSTer menu: it saves straight away
        time.sleep(float(self.cfg["nvram_save_s"]))
        self.keys_dev.tap(f12)             # and close it again
        time.sleep(0.05)
        # A save made in the first minute may have caught the game mid-way through a
        # CMOS reset, so keep saving until one comes after a longer session.
        if played >= 60 and g["path"] not in good:
            good.append(g["path"])
            save_state(self.state)

    def exit_game(self, reason="menu button"):
        log("%s: returning to launcher" % reason)
        self.release_virtual_keys()
        self.save_nvram()
        self.current_game = None
        self.go_menu()
        self.write_status()

    def go_menu(self):
        """Reload the menu core; the launcher appears once it has settled."""
        self.mode = S_RETURNING
        self.menu_since = None
        self.return_at = time.monotonic()
        self.await_stamp = core_stamp()
        mister_cmd("load_core %s" % MENU_RBF)

    def back_to_launcher_now(self):
        """The menu core is already running (a game ended or failed): take over at once."""
        self.mode = S_RETURNING
        self.await_stamp = None

    # -- attract mode -------------------------------------------------------------
    def attract_pool(self):
        games = self.view.all_games if self.view else scan_games(self.cfg)
        if self.cfg["attract_list"]:
            try:
                with open(self.cfg["attract_list"]) as f:
                    names = {l.strip().lower() for l in f if l.strip() and not l.startswith("#")}
                games = [g for g in games if os.path.basename(g["path"]).lower() in names
                         or g["file"].lower() in names]
            except OSError:
                log("attract_list not readable: %s" % self.cfg["attract_list"])
        elif orientation_filter(self.cfg) == "all" and not flag(self.cfg, "attract_vertical"):
            # The list already holds only one orientation when orientation is set,
            # so this extra filter only applies to a mixed list.
            games = [g for g in games if not g["vertical"]]
        return games

    def start_attract(self):
        """Start (or move on to) a random demo game."""
        now = time.monotonic()
        pool = self.attract_pool()
        if not pool:
            log("attract: no games to show")
            self.last_activity = now
            return
        fresh = [g for g in pool if g["path"] not in self.attract_recent] or pool
        g = random.choice(fresh)
        self.attract_recent = (self.attract_recent + [g["path"]])[-max(1, min(10, len(pool) // 2)):]
        log("attract: %s" % g["label"])
        if self.mode == S_LAUNCHER:
            self.release_framebuffer(text_mode=False, clear=True)
        if flag(self.cfg, "attract_mute") and not self.state.get("attract_muted"):
            mister_cmd("volume mute")
            self.state["attract_muted"] = True
            save_state(self.state)
        self.mode = S_ATTRACT
        self.attract_started = now
        self.attract_seen_core = False
        self.attract_stamp = core_stamp()
        mister_cmd("load_core %s" % g["path"])
        self.write_status()

    def unmute_attract(self):
        if self.state.pop("attract_muted", False):
            mister_cmd("volume unmute")
            save_state(self.state)

    def stop_attract(self):
        log("attract: player input, back to the game list")
        self.unmute_attract()
        self.go_menu()
        self.write_status()

    # -- operator menu ----------------------------------------------------------
    def open_operator(self):
        """Show the operator menu, from wherever the kiosk is."""
        if self.mode in (S_LAUNCHER, S_OPERATOR) and self.fb:
            self.enter_operator()
            return
        if self.mode == S_GAME:
            self.save_nvram()
        self.unmute_attract()
        self.current_game = None
        self.go_menu()                          # poll_core opens it once the menu core is up

    def enter_operator(self):
        log("entering operator menu")
        if not self.fb and not self.activate_framebuffer():
            return
        self.scan_devices()
        if self.view is None:
            self.rescan_games()
        self.opview = OperatorView(self)
        self.opview.credits = len(self.state.get("coins", []))
        self.release_virtual_keys()
        self.dir_state.clear()
        self.repeat.clear()
        self.op_activity = time.monotonic()
        self.mode = S_OPERATOR
        self.need_redraw = True
        self.write_status()

    def all_games(self):
        return self.view.all_games if self.view else scan_games(self.cfg)

    def last_game(self):
        last = self.state.get("last")
        for g in self.all_games():
            if g["path"] == last:
                return g
        return None

    def genre_counts(self):
        """Main genre -> number of games, before the operator menu's genre switches."""
        cfg = dict(self.cfg, hidden_genres="")
        counts = {}
        for g in scan_games(cfg):
            counts[g["genre"]] = counts.get(g["genre"], 0) + 1
        return counts

    def rescan_games(self):
        games = scan_games(self.cfg, use_cache=False)
        keep = self.view
        self.view = LauncherView(self.cfg, games)
        if keep and keep.current():
            self.view.select_path(keep.current()["path"])
        log("rescan: %d games" % len(games))
        return len(games)

    def adjust_credits(self, d):
        bank = self.state.setdefault("coins", [])
        if d > 0:
            codes = sorted(self.coin_buttons)
            have = [c for c in codes if any(c in x.keys for x in self.devices.values())]
            code = (have or codes or [KEY_NAMES["KEY_5"]])[0]
            for _ in range(d):
                if len(bank) < int(self.cfg["max_credits"]):
                    bank.append(["", code])       # free credit: any controller with that button
        else:
            del bank[max(0, len(bank) + d):]
        save_state(self.state)
        log("operator menu: credits now %d" % len(bank))

    def reset_nvram(self, g):
        try:
            os.remove(self.nvram_file(g))
        except OSError as e:
            log("nvram reset failed for %s: %s" % (g["label"], e))
        good = self.state.get("nvram_good", [])
        if g["path"] in good:
            good.remove(g["path"])
        save_state(self.state)
        log("nvram reset: %s" % g["label"])

    def operator_lock(self):
        self.set_locked(True)

    def sync_flag(self):
        """The kiosk build of the MiSTer main program hides its menu while the flag
        exists, so it's there whenever the kiosk owns the screen and gone while
        the operator is using the stock MiSTer menu."""
        want = self.mode != S_UNLOCKED
        if want != self.flag_on:
            set_kiosk_flag(want)
            self.flag_on = want

    def main_status(self):
        """KIOSK, STOCK, or OLD when a kiosk build is installed but MiSTer_kiosk
        in the kiosk folder is a different (newer) one."""
        if "kiosk_active" not in main_features():
            return "STOCK"
        if os.path.exists(KIOSK_MAIN) and not same_file(MAIN_BIN, KIOSK_MAIN):
            return "OLD"
        return "KIOSK"

    def install_kiosk_main(self):
        """Copy the kiosk build of the MiSTer main program over /media/fat/MiSTer
        (keeping the original as MiSTer.stock) and reboot."""
        if not os.path.exists(KIOSK_MAIN):
            self.opview.show_toast("NO MiSTer_kiosk FILE\nIN THE KIOSK FOLDER", 3)
            return
        try:
            if os.path.exists(MAIN_BIN) and not os.path.exists(MAIN_BIN + ".stock"):
                shutil.copy2(MAIN_BIN, MAIN_BIN + ".stock")
            tmp = MAIN_BIN + ".new"
            shutil.copy2(KIOSK_MAIN, tmp)
            os.chmod(tmp, 0o755)
            os.replace(tmp, MAIN_BIN)
        except OSError as e:
            log("install kiosk main failed: %s" % e)
            self.opview.show_toast("INSTALL FAILED", 3)
            return
        # On the next boot, check_new_main() puts the stock one back if this one
        # never starts.
        self.state["main_install_check"] = True
        save_state(self.state)
        log("installed the kiosk MiSTer main program; rebooting")
        self.operator_reboot()

    def auto_update_loop(self, first_wait=60, every=24 * 3600):
        """auto_update = 1: check for a new release after boot and once a day.
        A new version is installed in the background and takes over the next
        time nobody's playing."""
        time.sleep(first_wait)                   # let the network come up
        while True:
            try:
                rel = latest_release(self.cfg)
                if version_tuple(rel["version"]) > version_tuple(VERSION):
                    log("auto update: %s available" % rel["version"])
                    install_release(rel, say=log)
                    self.pending_restart = True
                    return
            except (UpdateError, OSError) as e:
                log("auto update: %s" % e)
            time.sleep(every)

    def check_new_main(self, wait=90):
        """Safety net after installing the kiosk build: if the MiSTer main program
        never starts taking commands, restore MiSTer.stock and reboot."""
        if not self.state.get("main_install_check"):
            return True
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if mister_ready():
                log("new MiSTer main program is running")
                self.state.pop("main_install_check", None)
                save_state(self.state)
                return True
            time.sleep(0.5)
        log("new MiSTer main program didn't start in %d s; restoring MiSTer.stock" % wait)
        self.state.pop("main_install_check", None)
        save_state(self.state)
        try:
            if os.path.exists(MAIN_BIN + ".stock"):
                shutil.copy2(MAIN_BIN + ".stock", MAIN_BIN + ".new")
                os.replace(MAIN_BIN + ".new", MAIN_BIN)
                os.system("sync; reboot")
        except OSError as e:
            log("restore failed: %s" % e)
        return False

    def operator_game_settings(self, g):
        """Run a game unlocked, so MENU opens the MiSTer menu for its DIP switches
        and options. Holding OPERATOR comes back to the operator menu."""
        log("operator menu: game settings for %s" % g["label"])
        self.mode = S_UNLOCKED
        self.sync_flag()                        # before the new main program starts
        self.release_framebuffer()
        self.opview = None
        self.current_game = g
        self.mode = S_UNLOCKED
        mister_cmd("load_core %s" % g["path"])
        self.write_status()

    def operator_stock_menu(self):
        log("operator menu: stock MiSTer menu")
        if self.mode == S_GAME:
            self.save_nvram()
        self.mode = S_UNLOCKED
        self.sync_flag()                        # before the new main program starts
        self.state["locked"] = False
        save_state(self.state)
        self.release_framebuffer()
        self.opview = None
        self.current_game = None
        self.mode = S_UNLOCKED
        mister_cmd("load_core %s" % MENU_RBF)
        self.write_status()

    def operator_reboot(self):
        log("operator menu: reboot")
        if self.opview:
            self.opview.overlay = "REBOOTING"
            self.draw()
        os.system("sync; reboot")

    def operator_input(self, dev, t, c, v, now):
        dirn = self._direction_from(dev, t, c, v)
        if (t == EV_KEY and v == 1) or (dirn and dirn[1]):
            self.op_activity = now
        if dirn:
            axis, d = dirn
            key = (dev.path, axis)
            if self.dir_state.get(key, 0) != d:
                self.dir_state[key] = d
                if d:
                    self.step(axis, d)
                    self.repeat[key] = now + 0.35
                    self.repeat_count[key] = 0
                else:
                    self.repeat.pop(key, None)
            return
        if t != EV_KEY or v != 1 or not self.opview:
            return
        if c in self.launch_buttons:
            self.opview.press()
        elif (c in self.genre_buttons or c in self.genre_back_buttons
              or self.is_menu_btn(dev, c)):
            self.opview.back()
        self.need_redraw = True

    def set_locked(self, locked):
        if locked == self.state["locked"]:
            return
        self.state["locked"] = locked
        save_state(self.state)
        log("operator: %s" % ("LOCKED" if locked else "UNLOCKED"))
        self.release_virtual_keys()
        self.unmute_attract()
        self.return_coins()
        if locked:
            self.state["pending_toast"] = "LOCKED"
            self.current_game = None
            if self.mode == S_OPERATOR and self.fb:
                self.enter_launcher()            # already on the kiosk screen
            else:
                self.go_menu()
        elif flag(self.cfg, "operator_menu"):
            self.open_operator()
        else:
            # Old behaviour: straight to the stock MiSTer menu.
            if self.mode == S_LAUNCHER:
                self.release_framebuffer()
            elif self.mode == S_GAME:
                self.save_nvram()
            self.current_game = None
            set_tty_mode(KD_TEXT)
            self.mode = S_UNLOCKED
            self.sync_flag()
            mister_cmd("load_core %s" % MENU_RBF)
        self.write_status()

    def release_virtual_keys(self):
        for dev in self.devices.values():
            if not dev.virtual:
                continue
            for k in list(dev.pressed):
                dev.virtual.emit(EV_KEY, k, 0)
            for a, info in dev.absinfo.items():
                if a in (ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y):
                    centre = 0 if a in (ABS_HAT0X, ABS_HAT0Y) else (info[1] + info[2]) // 2
                    dev.virtual.emit(EV_ABS, a, centre)
            dev.virtual.emit(EV_SYN, SYN_REPORT, 0)

    # -- setup wizard ---------------------------------------------------------
    def update_setup_overlay(self):
        if not self.view:
            return
        if self.setup_step == "menu":
            self.view.overlay = "BUTTON SETUP\n\nPRESS THE PLAYER\nMENU BUTTON"
        elif self.setup_step == "operator":
            self.view.overlay = "BUTTON SETUP\n\nPRESS THE OPERATOR\nBUTTON"
        else:
            self.view.overlay = None
        self.need_redraw = True

    def setup_capture(self, dev, code):
        if self.setup_step == "menu":
            set_config_value("menu_button", code_name(code))
            set_config_value("menu_device", dev.vidpid)
            log("setup: menu button = %s on %s" % (code_name(code), dev.vidpid))
            self.cfg = load_config()
            self.setup_step = "operator" if parse_code(self.cfg["operator_button"]) is None else None
        elif self.setup_step == "operator":
            if code == self.menu_button and dev.matches(self.cfg["menu_device"]):
                self.view.show_toast("USE A DIFFERENT\nBUTTON", 2)
                return
            set_config_value("operator_button", code_name(code))
            set_config_value("operator_device", dev.vidpid)
            log("setup: operator button = %s on %s" % (code_name(code), dev.vidpid))
            self.cfg = load_config()
            self.setup_step = None
        self.reload_buttons()
        self.update_setup_overlay()
        if not self.setup_step:
            self.view.show_toast("SETUP COMPLETE", 2)

    # -- input handling -------------------------------------------------------
    def handle_events(self, dev, events):
        now = time.monotonic()
        for t, c, v in events:
            if t == EV_KEY:
                if v:
                    dev.pressed.add(c)
                else:
                    dev.pressed.discard(c)
                if flag(self.cfg, "log_inputs") and v in (0, 1):
                    log("key %s %s on %s '%s'" % (code_name(c), "down" if v else "up",
                                                  dev.vidpid, dev.name))
            elif t == EV_ABS:
                dev.abs_state[c] = v

            # Setup wizard takes the first new button press.
            if self.setup_step and self.mode == S_LAUNCHER and t == EV_KEY and v == 1:
                if c not in (KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
                             BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT):
                    self.setup_capture(dev, c)
                    continue

            # Operator button: always ours, never forwarded.
            if t == EV_KEY and self.is_operator_btn(dev, c):
                if v == 1:
                    self.op_down_at = now
                    self.op_fired = False
                    log("operator button down (%s, mode %s); hold %d ms to %s" % (
                        dev.vidpid, self.mode, int(self.cfg["operator_hold_ms"]),
                        "unlock" if self.state["locked"] else "lock"))
                    if self.mode == S_OPERATOR and self.opview and int(self.cfg["operator_hold_ms"]) > 0:
                        self.opview.show_toast("KEEP HOLDING\nTO LOCK", 5)
                        self.need_redraw = True
                    if self.mode == S_LAUNCHER and self.view and int(self.cfg["operator_hold_ms"]) > 0:
                        self.view.show_toast("KEEP HOLDING\nTO UNLOCK", 5)
                        self.need_redraw = True
                elif v == 0:
                    if self.op_down_at and not self.op_fired:
                        log("operator button released after %d ms (too short)" %
                            ((now - self.op_down_at) * 1000))
                        if self.mode == S_LAUNCHER and self.view:
                            self.view.show_toast("HOLD THE OPERATOR\nBUTTON TO UNLOCK", 2)
                            self.need_redraw = True
                    self.op_down_at = None
                continue

            if self.mode == S_ATTRACT:
                # Any button or stick movement ends the demo. Nothing reaches the game.
                # A coin put in during the demo is banked for the player's game.
                if t == EV_KEY and v == 1 and c in self.coin_buttons:
                    self.bank_coin(dev, c)
                dirn = self._direction_from(dev, t, c, v)
                if (t == EV_KEY and v == 1) or (dirn and dirn[1]):
                    self.stop_attract()
                continue

            if self.mode == S_LAUNCHER:
                self.launcher_input(dev, t, c, v, now)
                continue

            if self.mode == S_OPERATOR:
                self.operator_input(dev, t, c, v, now)
                continue

            if self.mode == S_GAME and t == EV_KEY and self.is_menu_btn(dev, c) and self.state["locked"]:
                hold = int(self.cfg["menu_hold_ms"]) / 1000.0
                if v == 1:
                    self.menu_down_at = now
                    if hold <= 0 and now - self.game_started >= float(self.cfg["exit_grace_s"]):
                        self.exit_game()
                elif v == 0:
                    self.menu_down_at = None
                continue

            if self.mode == S_GAME and self.is_activity(dev, t, c, v):
                self.game_last_input = now

            if self.mode in (S_GAME, S_UNLOCKED):
                if t == EV_KEY and v == 0 and (dev.path, c) in self.suppress:
                    self.suppress.discard((dev.path, c))
                    continue
                if t == EV_KEY and v and (dev.path, c) in self.suppress:
                    continue
                if dev.virtual:
                    dev.virtual.emit(t, c, v)
            # S_WAIT / S_RETURNING: drop everything

    def is_activity(self, dev, t, c, v):
        """A real player action: a button press, the stick/d-pad moving off centre,
        or a spinner/trackball turning. Analogue jitter around centre doesn't count."""
        if t == EV_KEY:
            return v == 1
        if t == EV_REL:
            return v != 0
        if t == EV_ABS:
            d = self._direction_from(dev, t, c, v)
            if d:
                key = (dev.path, "idle", d[0])
                moved = d[1] != 0 and self.dir_state.get(key, 0) != d[1]
                self.dir_state[key] = d[1]
                return moved
            # Other axes (paddles, wheels, pedals): count a big enough change.
            info = dev.absinfo.get(c)
            if info:
                span = max(1, info[2] - info[1])
                key = (dev.path, "idle_abs", c)
                last = self.dir_state.get(key)
                self.dir_state[key] = v
                return last is not None and abs(v - last) * 20 >= span
        return False

    def _direction_from(self, dev, t, c, v):
        """Return ('y'|'x', -1/0/1) if this event is a direction change."""
        if t == EV_KEY:
            mapping = {KEY_UP: ("y", -1), KEY_DOWN: ("y", 1), KEY_LEFT: ("x", -1), KEY_RIGHT: ("x", 1),
                       BTN_DPAD_UP: ("y", -1), BTN_DPAD_DOWN: ("y", 1),
                       BTN_DPAD_LEFT: ("x", -1), BTN_DPAD_RIGHT: ("x", 1)}
            if c in mapping:
                axis, d = mapping[c]
                return axis, (d if v else 0)
        elif t == EV_ABS and c in (ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y):
            axis = "x" if c in (ABS_X, ABS_HAT0X) else "y"
            if c in (ABS_HAT0X, ABS_HAT0Y):
                d = (v > 0) - (v < 0)
            else:
                info = dev.absinfo.get(c, (0, -1, 1, 0, 0, 0))
                lo, hi = info[1], info[2]
                mid, span = (lo + hi) / 2.0, max(1, (hi - lo) / 2.0)
                n = (v - mid) / span
                d = 1 if n > 0.5 else -1 if n < -0.5 else 0
            return axis, d
        return None

    def launcher_input(self, dev, t, c, v, now):
        if not self.view:
            return
        dirn = self._direction_from(dev, t, c, v)
        if (t == EV_KEY and v == 1) or (dirn and dirn[1]):
            self.last_activity = now
        if dirn:
            axis, d = dirn
            key = (dev.path, axis)
            if self.dir_state.get(key, 0) != d:
                self.dir_state[key] = d
                if d:
                    self.step(axis, d)
                    self.repeat[key] = now + 0.35
                    self.repeat_count[key] = 0
                else:
                    self.repeat.pop(key, None)
            return
        if t != EV_KEY or v != 1 or self.setup_step:
            return
        if c in self.coin_buttons:
            self.bank_coin(dev, c)
            return
        if self.view.picker is not None:
            # Any button closes the letter picker, leaving the list on that letter.
            self.view.close_picker()
            self.need_redraw = True
            return
        if c in self.launch_buttons:
            g = self.view.current()
            if g:
                self.launch(g)
        elif c in self.genre_buttons:
            self.view.set_genre(self.view.genre_idx + 1)
            self.need_redraw = True
        elif c in self.genre_back_buttons:
            self.view.set_genre(self.view.genre_idx - 1)
            self.need_redraw = True
        elif c in self.letter_buttons:
            self.view.open_picker()
            self.need_redraw = True

    def step(self, axis, d):
        if self.mode == S_OPERATOR:
            if self.opview:
                self.opview.move(axis, d)
            self.need_redraw = True
            return
        if self.view.picker is not None:
            self.view.picker_move(d)          # any direction moves through the letters
        elif axis == "y":
            self.view.move(d)
        else:
            self.view.jump_letter(d)
        self.need_redraw = True

    def tick_repeat(self, now):
        for key, when in list(self.repeat.items()):
            if now >= when:
                d = self.dir_state.get(key, 0)
                if not d:
                    self.repeat.pop(key, None)
                    continue
                self.step(key[1], d)
                n = self.repeat_count.get(key, 0) + 1
                self.repeat_count[key] = n
                self.repeat[key] = now + (0.09 if n < 10 else 0.04)

    # -- drawing --------------------------------------------------------------
    def draw(self):
        view = self.opview if getattr(self, "mode", None) == S_OPERATOR else self.view
        if not (self.fb and self.canvas and view):
            return
        if getattr(self, "lcanvas", None):
            view.draw(self.lcanvas, self.blink_on)
            rotate_canvas(self.lcanvas, self.canvas, self.rotation)
        else:
            view.draw(self.canvas, self.blink_on)
        self.fb.present(self.canvas)
        self.need_redraw = False

    # -- status / control -----------------------------------------------------
    def write_status(self):
        try:
            with open(STATUS_PATH, "w") as f:
                json.dump({"mode": self.mode, "locked": self.state["locked"], "core": core_name(),
                           "menu_button": self.cfg["menu_button"],
                           "operator_button": self.cfg["operator_button"],
                           "devices": [{"path": d.path, "id": d.vidpid, "name": d.name,
                                        "grabbed": d.grabbed} for d in self.devices.values()],
                           "waiting_for": sorted(self.ungrabbed)},
                          f, indent=1)
        except OSError:
            pass

    def check_control(self):
        try:
            with open(CTL_PATH) as f:
                cmd = f.read().strip()
            os.unlink(CTL_PATH)
        except OSError:
            return
        log("control: %s" % cmd)
        if cmd == "lock":
            self.set_locked(True)
        elif cmd == "unlock":
            self.set_locked(False)
        elif cmd == "stock":
            self.release_virtual_keys()
            self.return_coins()
            self.operator_stock_menu()
        elif cmd == "relearn":
            self.cfg = load_config()
            self.reload_buttons()
            self.update_setup_overlay()
        elif cmd == "restart":
            self.pending_restart = True
        elif cmd == "rescan" and self.mode == S_LAUNCHER:
            self.enter_launcher()

    # -- main loop ------------------------------------------------------------
    def poll_core(self, now):
        name = core_name()
        is_menu = name.upper() == "MENU"
        if name != self.last_core:
            log("core: %s" % (name or "?"))
            self.last_core = name
            self.menu_since = now if is_menu else None
            self.write_status()
        if is_menu and self.menu_since is None:
            self.menu_since = now

        locked = self.state["locked"]
        settle = float(self.cfg["menu_settle_s"])

        if not locked:
            if not flag(self.cfg, "operator_menu"):
                if self.mode != S_UNLOCKED:
                    if self.mode == S_LAUNCHER:
                        self.release_framebuffer()
                    self.mode = S_UNLOCKED
            elif self.mode in (S_WAIT, S_RETURNING):
                # Unlocked: once the menu core is back, show the operator menu.
                if is_menu and (self.await_stamp is None or core_stamp() != self.await_stamp
                                or now - self.return_at > 10):
                    self.await_stamp = None
                    self.enter_operator()
                elif name and not is_menu and self.mode == S_WAIT:
                    self.go_menu()
            return

        if self.mode == S_GAME:
            if not is_menu and name:
                self.game_seen_core = True
            elif is_menu and self.game_seen_core:
                log("game ended without the menu button; back to launcher")
                self.back_to_launcher_now()
            elif now - self.game_started > float(self.cfg["launch_timeout_s"]):
                log("game did not start")
                self.state["pending_toast"] = "COULD NOT START\nTHAT GAME"
                self.back_to_launcher_now()
            return

        if self.mode == S_ATTRACT:
            fresh_main = core_stamp() != self.attract_stamp
            if not is_menu and name and fresh_main:
                self.attract_seen_core = True
            if is_menu and (self.attract_seen_core or fresh_main):
                # The demo game dropped back to the menu, or never loaded.
                log("attract: game did not run; trying another")
                self.start_attract()
            elif not self.attract_seen_core and now - self.attract_started > float(self.cfg["launch_timeout_s"]):
                log("attract: game did not start; trying another")
                self.start_attract()
            elif self.attract_seen_core and now - self.attract_started >= float(self.cfg["attract_game_s"]):
                self.start_attract()      # straight to the next demo, no menu in between
            return

        if self.mode in (S_WAIT, S_RETURNING):
            if is_menu:
                # After a reload, wait for the new main program (it rewrites CORENAME);
                # fall back after 10 s in case the stamp never changes.
                if (self.await_stamp is None or core_stamp() != self.await_stamp
                        or now - self.return_at > 10):
                    self.await_stamp = None
                    self.enter_launcher()
            elif name and self.mode == S_WAIT:
                # Locked but a game is running (e.g. booted with bootcore): go back.
                self.go_menu()

    def run(self):
        log("Arcade Kiosk %s starting (locked=%s)" % (VERSION, self.state["locked"]))
        kiosk_boot = flag(self.cfg, "lock_on_boot") or self.state["locked"] or flag(self.cfg, "operator_menu")
        set_boot_flag(kiosk_boot)
        if kiosk_boot:
            set_kiosk_flag(True)
            self.flag_on = True
        self.check_new_main()
        if flag(self.cfg, "auto_update"):
            threading.Thread(target=self.auto_update_loop, daemon=True).start()
        while not os.path.exists(MISTER_CMD):
            time.sleep(1)
        if not os.path.exists("/dev/uinput"):
            os.system("modprobe uinput >/dev/null 2>&1")
        # Create the virtual keyboard now so it is already known when the menu starts.
        try:
            self.ensure_keys_dev()
        except OSError as e:
            log("cannot create virtual keyboard: %s" % e)
        if self.state.get("attract_muted"):
            while not mister_ready():
                time.sleep(0.2)
            self.unmute_attract()
        self.scan_devices()
        if not self.state["locked"] and flag(self.cfg, "operator_menu"):
            pass                                    # poll_core opens the operator menu
        elif not self.state["locked"]:
            self.mode = S_UNLOCKED
            # Grab the controllers once (they are free while the terminal screen is up),
            # so the operator button keeps working, then put the stock menu back.
            if self.ungrabbed or not self.devices:
                while core_name().upper() != "MENU":
                    time.sleep(0.2)
                if self.activate_framebuffer():
                    self.scan_devices()
                    self.release_framebuffer()
                mister_cmd("load_core %s" % MENU_RBF)
        self.write_status()

        while True:
            now = time.monotonic()
            fds = {d.fd: d for d in self.devices.values()}
            try:
                r, _, _ = select.select(list(fds), [], [], 0.05)
            except (OSError, ValueError):
                r = []
            for fd in r:
                dev = fds.get(fd)
                if not dev:
                    continue
                try:
                    events = dev.read_events()
                except OSError:
                    log("read failed on %s; dropping" % dev.path)
                    try:
                        self.devices.pop(dev.path).close()
                    except (KeyError, OSError):
                        pass
                    continue
                self.handle_events(dev, events)

            now = time.monotonic()
            # Operator hold
            if self.op_down_at and not self.op_fired:
                if now - self.op_down_at >= int(self.cfg["operator_hold_ms"]) / 1000.0:
                    self.op_fired = True
                    if (not self.state["locked"] and self.mode in (S_UNLOCKED, S_RETURNING)
                            and flag(self.cfg, "operator_menu")):
                        self.open_operator()
                    else:
                        self.set_locked(not self.state["locked"])
            # Menu hold (if configured)
            hold = int(self.cfg["menu_hold_ms"]) / 1000.0
            if (self.mode == S_GAME and hold > 0 and self.menu_down_at
                    and now - self.menu_down_at >= hold
                    and now - self.game_started >= float(self.cfg["exit_grace_s"])):
                self.menu_down_at = None
                self.exit_game()

            # The controller with the MENU/OPERATOR button is held by the MiSTer
            # (e.g. it was unplugged and replugged mid-game), so neither button can
            # work. Return to the list, where the MiSTer lets go of it.
            if self.mode in (S_GAME, S_ATTRACT) and self.state["locked"]:
                lost = [p for p, (t0, ctl) in self.ungrabbed.items() if ctl and now - t0 > 3]
                if lost:
                    log("lost the menu/operator controller (%s); back to the list" % ", ".join(lost))
                    for p in lost:
                        self.ungrabbed[p] = (now + 30, True)   # don't loop if it persists
                    self.unmute_attract()
                    self.current_game = None
                    self.go_menu()

            self.tick_coins(now)
            self.sync_flag()
            if self.pending_restart and self.mode in (S_LAUNCHER, S_OPERATOR, S_WAIT,
                                                      S_RETURNING, S_ATTRACT):
                log("restarting the kiosk (new version)")
                self.restarting = True
                raise SystemExit(0)              # run.sh starts the new version

            # Nobody playing: quit the game back to the list.
            idle_exit = float(self.cfg["game_idle_exit_s"])
            if (self.mode == S_GAME and idle_exit > 0 and self.state["locked"]
                    and now - self.game_last_input >= idle_exit):
                self.state["pending_toast"] = "GAME ENDED\nNO INPUT"
                self.exit_game("no input for %d s" % idle_exit)

            if self.mode == S_OPERATOR:
                self.tick_repeat(now)
                if self.opview and self.opview.toast and now > self.opview.toast_until:
                    self.opview.toast = None
                    self.need_redraw = True
                timeout = float(self.cfg["operator_timeout_s"])
                if timeout > 0 and now - self.op_activity >= timeout:
                    log("operator menu left alone for %d s; locking" % timeout)
                    self.set_locked(True)
                if now - self.last_fb_check > 1.0:
                    self.last_fb_check = now
                    self.check_fb_mode()
                if self.need_redraw:
                    self.draw()

            if self.mode == S_LAUNCHER:
                self.tick_repeat(now)
                if now - self.last_blink > 0.5:
                    self.last_blink = now
                    self.blink_on = not self.blink_on
                    self.need_redraw = True
                if self.view and self.view.toast and now > self.view.toast_until:
                    self.view.toast = None
                    self.need_redraw = True
                if self.view and self.view.picker is not None and now > self.view.picker_until:
                    self.view.close_picker()           # left alone: keep the letter
                    self.need_redraw = True
                if now - self.last_fb_check > 1.0:
                    self.last_fb_check = now
                    self.check_fb_mode()
                idle = float(self.cfg["attract_idle_s"])
                if (idle > 0 and not self.setup_step and self.state["locked"]
                        and not self.state.get("coins")
                        and now - self.last_activity >= idle):
                    self.start_attract()
                if self.need_redraw:
                    self.draw()

            if now - self.last_poll > 0.1:
                self.last_poll = now
                self.poll_core(now)
                self.check_control()
            if now - self.last_scan > 3:
                self.last_scan = now
                self.scan_devices()


# ---------------------------------------------------------------------------
# Updating from GitHub
# ---------------------------------------------------------------------------
# Releases are published by the repo's GitHub Actions: each tagged version gets
# a release with the SD-card zip (arcade_kiosk/ + Scripts/) attached. The kiosk
# downloads the latest one, keeps the operator's settings and data, backs up the
# version it replaces, and restarts itself.

UPDATE_TMP = "/tmp/arcadekiosk_update"
BACKUP_DIR = os.path.join(HERE, "backup")
SCRIPTS_DIR = "/media/fat/Scripts"
# kept from the installed copy, never overwritten by an update
KEEP_FILES = {"kiosk.ini", "state.json", "games_cache.json", "games_cache.json.tmp", "state.json.tmp"}
KEEP_DIRS = {"art", "backup", "map_backup"}
# settings that no longer exist; dropped when kiosk.ini is merged
RETIRED_KEYS = {"footer_genre", "footer_letter", "hide_vertical"}
CA_FILES = ("/etc/ssl/certs/cacert.pem", "/etc/ssl/certs/ca-certificates.crt",
            "/etc/ssl/cert.pem", "/etc/pki/tls/certs/ca-bundle.crt")


class UpdateError(Exception):
    pass


def version_tuple(v):
    nums = re.findall(r"\d+", str(v))
    return tuple(int(n) for n in nums[:4]) or (0,)


def http_get(url, headers=None, timeout=60):
    """Fetch a URL. Uses curl (as MiSTer's own updaters do) and falls back to
    Python's urllib."""
    headers = dict(headers or {})
    headers.setdefault("User-Agent", "MisterOperator-updater")
    curl = shutil.which("curl")
    if curl:
        cmd = [curl, "-fsSL", "--max-time", str(timeout), "--retry", "2"]
        for ca in CA_FILES:
            if os.path.exists(ca):
                cmd += ["--cacert", ca]
                break
        for k, v in headers.items():
            cmd += ["-H", "%s: %s" % (k, v)]
        r = subprocess.run(cmd + [url], capture_output=True)
        if r.returncode == 0:
            return r.stdout
        err = r.stderr.decode("utf-8", "replace").strip()
        if "(22)" in err:                                    # HTTP error from the server
            raise UpdateError(err.splitlines()[-1] if err else "HTTP error")
    import ssl
    import urllib.request
    ctx = None
    for ca in CA_FILES:
        if os.path.exists(ca):
            ctx = ssl.create_default_context(cafile=ca)
            break
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read()
    except Exception as e:
        raise UpdateError(str(e))


def latest_release(cfg):
    """{'version', 'tag', 'url', 'headers'} for the newest release's SD zip."""
    repo = cfg.get("update_repo", "").strip()
    if not repo:
        raise UpdateError("update_repo is empty in kiosk.ini")
    headers = {"Accept": "application/vnd.github+json"}
    token = cfg.get("update_token", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    data = http_get("https://api.github.com/repos/%s/releases/latest" % repo, headers, timeout=30)
    try:
        rel = json.loads(data.decode("utf-8"))
    except ValueError:
        raise UpdateError("unexpected answer from GitHub")
    if "tag_name" not in rel:
        raise UpdateError(rel.get("message", "no releases found"))
    for a in rel.get("assets", []):
        name = a.get("name", "")
        if name.lower().endswith(".zip") and name.lower().startswith("misteroperator"):
            if token:      # private repo: the API URL with the token
                url, hdr = a["url"], dict(headers, Accept="application/octet-stream")
            else:
                url, hdr = a["browser_download_url"], {}
            return {"version": rel["tag_name"].lstrip("vV"), "tag": rel["tag_name"],
                    "url": url, "headers": hdr, "notes": rel.get("body") or ""}
    raise UpdateError("release %s has no MisterOperator zip" % rel["tag_name"])


def merge_ini(new_text, old_text):
    """New kiosk.ini (with its comments and any new settings), carrying over every
    value the operator had set."""
    old = {}
    order = []
    for raw in old_text.splitlines():
        line = ini_line(raw)
        if "=" in line and not line.startswith("["):
            k, v = line.split("=", 1)
            k = k.strip().lower()
            if k not in old:
                order.append(k)
            old[k] = v.strip()
    lines = new_text.splitlines()
    seen = set()
    for i, raw in enumerate(lines):
        m = re.match(r"^(\s*)([A-Za-z0-9_]+)(\s*=\s*)([^;]*?)(\s*;.*)?$", raw)
        if not m or m.group(2).lower() not in old:
            continue
        k = m.group(2).lower()
        seen.add(k)
        comment = m.group(5) or ""
        lines[i] = "%s%s%s%s%s" % (m.group(1), m.group(2), m.group(3), old[k],
                                   ("   " + comment.strip()) if comment else "")
    extra = [k for k in order if k not in seen and k not in RETIRED_KEYS]
    if extra:
        lines += ["", "; ---- kept from your previous kiosk.ini ----"]
        lines += ["%s = %s" % (k, old[k]) for k in extra]
    return "\n".join(lines) + "\n"


def copy_tree_files(src, dst, skip_files=(), skip_dirs=()):
    """Copy files from src into dst, replacing each one atomically."""
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        if rel == ".":
            dirs[:] = [d for d in dirs if d not in skip_dirs and d != "__pycache__"]
        else:
            dirs[:] = [d for d in dirs if d != "__pycache__"]
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            if rel == "." and f in skip_files:
                continue
            s_, d_ = os.path.join(root, f), os.path.join(dst, rel, f)
            tmp = d_ + ".new"
            shutil.copy2(s_, tmp)
            if f.endswith(".sh") or f in ("arcadekiosk.py", "MiSTer_kiosk") or f.endswith(".py"):
                os.chmod(tmp, 0o755)
            os.replace(tmp, d_)


def backup_current(dest_root=None):
    """Copy the running version's program files to backup/<version>/."""
    dest_root = dest_root or BACKUP_DIR
    dest = os.path.join(dest_root, VERSION)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    for name in os.listdir(HERE):
        p = os.path.join(HERE, name)
        if name in KEEP_FILES or name in KEEP_DIRS or name == "__pycache__":
            continue
        if os.path.isdir(p):
            shutil.copytree(p, os.path.join(dest, name), ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(p, os.path.join(dest, name))
    if os.path.exists(os.path.join(HERE, "kiosk.ini")):      # settings as they were
        shutil.copy2(os.path.join(HERE, "kiosk.ini"), os.path.join(dest, "kiosk.ini"))
    # keep the three most recent backups
    olds = sorted(os.listdir(dest_root), key=version_tuple)
    for v in olds[:-3]:
        shutil.rmtree(os.path.join(dest_root, v), ignore_errors=True)
    return dest


def install_release(rel, say=print):
    """Download and install a release. Returns the new version string."""
    import zipfile
    if os.path.exists(UPDATE_TMP):
        shutil.rmtree(UPDATE_TMP)
    os.makedirs(UPDATE_TMP)
    say("Downloading %s..." % rel["tag"])
    data = http_get(rel["url"], rel["headers"], timeout=300)
    pkg = os.path.join(UPDATE_TMP, "update.zip")
    with open(pkg, "wb") as f:
        f.write(data)
    try:
        z = zipfile.ZipFile(pkg)
        bad = z.testzip()
    except zipfile.BadZipFile:
        raise UpdateError("download is not a zip file")
    if bad:
        raise UpdateError("download is damaged (%s)" % bad)
    names = z.namelist()
    prefix = ""
    if "arcade_kiosk/arcadekiosk.py" not in names:   # zip with a top folder
        hit = [n for n in names if n.endswith("/arcade_kiosk/arcadekiosk.py")]
        if not hit:
            raise UpdateError("zip doesn't contain arcade_kiosk/arcadekiosk.py")
        prefix = hit[0][:-len("arcade_kiosk/arcadekiosk.py")]
    new = os.path.join(UPDATE_TMP, "new")
    for n in names:
        if not n.startswith(prefix) or ".." in n.split("/") or n.startswith("/"):
            continue
        rel_name = n[len(prefix):]
        if not rel_name or n.endswith("/"):
            continue
        target = os.path.join(new, rel_name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with z.open(n) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
    new_kiosk = os.path.join(new, "arcade_kiosk")
    main_py = os.path.join(new_kiosk, "arcadekiosk.py")
    # sanity checks before touching the installed copy
    import py_compile
    try:
        py_compile.compile(main_py, doraise=True, cfile=os.path.join(UPDATE_TMP, "check.pyc"))
    except py_compile.PyCompileError as e:
        raise UpdateError("new version doesn't compile: %s" % e)
    with open(main_py) as f:
        m = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M)
    new_version = m.group(1) if m else rel["version"]

    say("Backing up %s..." % VERSION)
    backup_current()
    say("Installing %s..." % new_version)
    copy_tree_files(new_kiosk, HERE, skip_files=KEEP_FILES, skip_dirs=KEEP_DIRS)
    # merge settings
    new_ini = os.path.join(new_kiosk, "kiosk.ini")
    cur_ini = os.path.join(HERE, "kiosk.ini")
    if os.path.exists(new_ini):
        with open(new_ini) as f:
            template = f.read()
        old_text = open(cur_ini).read() if os.path.exists(cur_ini) else ""
        merged = merge_ini(template, old_text)
        with open(cur_ini + ".tmp", "w") as f:
            f.write(merged)
            f.flush()
            os.fsync(f.fileno())
        os.replace(cur_ini + ".tmp", cur_ini)
    # new box art the operator doesn't have yet
    new_art = os.path.join(new_kiosk, "art")
    if os.path.isdir(new_art):
        os.makedirs(os.path.join(HERE, "art"), exist_ok=True)
        for f in os.listdir(new_art):
            if not os.path.exists(os.path.join(HERE, "art", f)):
                shutil.copy2(os.path.join(new_art, f), os.path.join(HERE, "art", f))
    # our scripts in the MiSTer Scripts menu
    new_scripts = os.path.join(new, "Scripts")
    if os.path.isdir(new_scripts) and os.path.isdir(SCRIPTS_DIR):
        for f in os.listdir(new_scripts):
            if f.endswith(".sh"):
                shutil.copy2(os.path.join(new_scripts, f), os.path.join(SCRIPTS_DIR, f))
    os.system("sync")
    shutil.rmtree(UPDATE_TMP, ignore_errors=True)
    log("updated %s -> %s" % (VERSION, new_version))
    return new_version


def rollback(say=print):
    if not os.path.isdir(BACKUP_DIR) or not os.listdir(BACKUP_DIR):
        raise UpdateError("no backups in %s" % BACKUP_DIR)
    versions = sorted(os.listdir(BACKUP_DIR), key=version_tuple)
    older = [v for v in versions if version_tuple(v) < version_tuple(VERSION)] or versions
    v = older[-1]
    src = os.path.join(BACKUP_DIR, v)
    say("Restoring %s..." % v)
    copy_tree_files(src, HERE, skip_files=KEEP_FILES, skip_dirs=KEEP_DIRS)
    if os.path.exists(os.path.join(src, "kiosk.ini")):
        shutil.copy2(os.path.join(src, "kiosk.ini"), os.path.join(HERE, "kiosk.ini"))
    os.system("sync")
    log("rolled back %s -> %s" % (VERSION, v))
    return v


def update_command(argv):
    """--update / --check / --rollback from the command line or the Scripts menu."""
    cfg = load_config()
    if "--rollback" in argv:
        v = rollback()
        print("Restored %s. Restarting the kiosk..." % v)
        send_control("restart")
        return 0
    try:
        rel = latest_release(cfg)
    except UpdateError as e:
        print("Couldn't check for updates: %s" % e)
        return 1
    print("Installed: %s   Latest: %s" % (VERSION, rel["version"]))
    if "--check" in argv:
        return 0
    if version_tuple(rel["version"]) <= version_tuple(VERSION) and "--force" not in argv:
        print("Already up to date.")
        return 0
    try:
        v = install_release(rel)
    except (UpdateError, OSError) as e:
        print("Update failed, nothing changed: %s" % e)
        log("update failed: %s" % e)
        return 1
    print("Updated to %s. Restarting the kiosk..." % v)
    if os.path.exists(os.path.join(HERE, "MiSTer_kiosk")):
        print("If the operator menu shows 'MiSTer main: OLD', install the new main program there.")
    send_control("restart")
    return 0


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def send_control(cmd):
    with open(CTL_PATH, "w") as f:
        f.write(cmd)
    print("sent '%s' to the kiosk" % cmd)


def demo_games():
    names = [
        ("1942 (Revision B)", "Capcom", "1984", "Shooter / Vertical", True),
        ("Bomb Jack", "Tehkan", "1984", "Platform", False),
        ("Bubble Bobble", "Taito", "1986", "Platform", False),
        ("Centipede (Revision 4)", "Atari", "1980", "Shooter", True),
        ("Donkey Kong (US Set 1)", "Nintendo", "1981", "Platform", True),
        ("Galaga (Namco rev. B)", "Namco", "1981", "Shooter / Vertical", True),
        ("Gauntlet (Rev 14)", "Atari Games", "1985", "Maze", False),
        ("Ghosts'n Goblins (World? set 1)", "Capcom", "1985", "Platform", False),
        ("Gyruss", "Konami (Centuri license)", "1983", "Shooter", True),
        ("Joust (Green label)", "Williams", "1982", "Action", False),
        ("Mr. Do!", "Universal", "1982", "Maze", True),
        ("Ms. Pac-Man", "Midway / General Computer", "1981", "Maze", True),
        ("Pac-Man (Midway)", "Namco (Midway license)", "1980", "Maze", True),
        ("Robotron: 2084", "Williams", "1982", "Shooter", False),
        ("Rygar (US set 1)", "Tecmo", "1986", "Platform", False),
        ("Scramble", "Konami", "1981", "Shooter / Horizontal", False),
        ("Street Fighter II: The World Warrior", "Capcom", "1991", "Fighter", False),
        ("Strider (US set 1)", "Capcom", "1989", "Platform", False),
        ("Super Pang (World 900914)", "Mitchell", "1990", "Puzzle", False),
        ("Tetris (set 1)", "Atari Games", "1988", "Puzzle", False),
        ("Time Pilot", "Konami", "1982", "Shooter", True),
        ("Xevious (Namco)", "Namco", "1982", "Shooter / Vertical", True),
    ]
    games = []
    for n, m, y, cat, vert in names:
        games.append({"path": "/media/fat/_Arcade/%s.mra" % n, "file": n, "name": n, "setname": "",
                      "year": y, "maker": m, "genre": cat.split("/")[0].strip().title(),
                      "categories": category_parts(cat),
                      "vertical": vert})
    for g in games:
        g["label"] = re.sub(r"\s*[\(\[].*$", "", g["name"])
    games.sort(key=lambda g: g["label"].lower())
    return games


def main(argv):
    if any(a in argv for a in ("--update", "--check", "--rollback")):
        sys.exit(update_command(argv))
    if "--lock" in argv:
        return send_control("lock")
    if "--unlock" in argv:
        return send_control("unlock")
    if "--stock" in argv:
        return send_control("stock")
    if "--rescan" in argv:
        return send_control("rescan")
    if "--relearn" in argv:
        for k in ("menu_button", "menu_device", "operator_button", "operator_device"):
            set_config_value(k, "")
        send_control("relearn")
        print("Buttons cleared. Lock the kiosk and press the buttons it asks for.")
        return
    if "--layout" in argv:
        cfg = load_config()
        for g in scan_games(cfg, use_cache=False):
            if g.get("mgl"):
                print("%-40s (MGL: uses the core's own mapping)" % g["label"][:40])
            elif not g.get("buttons") or not g.get("setname"):
                print("%-40s (no button list in the .mra, left as is)" % g["label"][:40])
            else:
                print("%-40s %s" % (g["label"][:40], describe_plan(plan_layout(cfg, g["buttons"]))))
        if not flag(cfg, "standard_layout"):
            print("standard_layout = 0: none of this is applied")
        return
    if "--restore-maps" in argv:
        r, d = restore_maps(load_config())
        print("restored %d map file%s, removed %d the kiosk created" % (r, "" if r == 1 else "s", d))
        print("Set standard_layout = 0 in kiosk.ini or the kiosk writes them again at the next game.")
        return
    if "--status" in argv:
        try:
            with open(STATUS_PATH) as f:
                print(f.read())
        except OSError:
            print("kiosk is not running (no %s)" % STATUS_PATH)
        return
    if "--scan" in argv:
        cfg = load_config()
        games = scan_games(cfg, use_cache=False)
        for g in games:
            print("%-40s %-6s %-12s %-2s %-4s %s" % (g["label"][:40], g["year"], g["genre"][:12],
                                                    "V" if g["vertical"] else "H",
                                                    "MGL" if g.get("mgl") else "MRA", g["path"]))
        print("%d games" % len(games))
        return
    if "--genres" in argv:
        cfg = load_config()
        cfg["genres"] = cfg["exclude_genres"] = ""
        counts = {}
        for g in scan_games(cfg, use_cache=False):
            for part in g["categories"] or ["Other"]:
                counts[part] = counts.get(part, 0) + 1
        print("Genres found (use these names in genres = / exclude_genres =):")
        for name in sorted(counts):
            print("  %-24s %d game%s" % (name, counts[name], "" if counts[name] == 1 else "s"))
        return
    if "--devices" in argv:
        for n in sorted(os.listdir("/dev/input")):
            if not n.startswith("event"):
                continue
            try:
                d = PhysicalDevice("/dev/input/" + n)
            except OSError as e:
                print("%s: %s" % (n, e))
                continue
            print("%s  %s  '%s'  phys=%s  keys=%d abs=%s  %s" % (
                n, d.vidpid, d.name, d.phys, len(d.keys), [hex(a) for a in d.abs],
                "USED" if d.is_input_we_want() else "ignored"))
            os.close(d.fd)
        return
    if "--preview" in argv:
        out = argv[argv.index("--preview") + 1]
        cfg = load_config()
        games = demo_games() if "--demo" in argv else scan_games(cfg, use_cache=False)
        view = LauncherView(cfg, games)
        if "--select" in argv:
            view.move(int(argv[argv.index("--select") + 1]))
        if "--genre" in argv:
            view.set_genre(int(argv[argv.index("--genre") + 1]))
        if "--overlay" in argv:
            view.overlay = argv[argv.index("--overlay") + 1].replace("|", "\n")
        fw, fh = int(cfg["fb_width"]), int(cfg["fb_height"])
        rot = screen_rotation(cfg)
        canvas = Canvas(fh, fw, PixelFormat()) if rot else Canvas(fw, fh, PixelFormat())
        t0 = time.perf_counter()
        view.draw(canvas)
        if rot and "--raw" in argv:            # what the monitor receives, before turning it
            raw = Canvas(fw, fh, PixelFormat())
            rotate_canvas(canvas, raw, rot)
            canvas = raw
        ms = (time.perf_counter() - t0) * 1000
        canvas.save_ppm(out)
        print("wrote %s (draw %.1f ms)" % (out, ms))
        return

    # Daemon
    try:
        with open(PID_PATH) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        print("already running (pid %d)" % pid)
        return
    except (OSError, ValueError):
        pass
    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))
    kiosk = Kiosk()
    try:
        kiosk.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:  # keep a record of crashes for the operator
        import traceback
        log("CRASH: %s\n%s" % (e, traceback.format_exc()))
        raise
    finally:
        for d in list(kiosk.devices.values()):
            try:
                d.close()
            except OSError:
                pass
        if kiosk.keys_dev:
            kiosk.keys_dev.close()
        if kiosk.restarting:
            # Planned restart after an update: keep the screen and the flag, the
            # new version takes over in a couple of seconds.
            if kiosk.fb:
                kiosk.fb.close()
        else:
            kiosk.release_framebuffer()
            set_kiosk_flag(False)               # never leave the MiSTer menu blocked
        try:
            os.unlink(PID_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    main(sys.argv[1:])
