"""MisterOperator: Wi-Fi setup from the operator menu.

Does what the MiSTer's own wifi script does, without a keyboard: scans,
saves the network in /media/fat/linux/wpa_supplicant.conf (keeping the
networks already there), has wpa_supplicant reload it and asks for an
address. Passwords are typed on an on-screen keyboard with the stick, and
only the WPA key derived from them is stored, never the password itself.
"""

import hashlib
import os
import re
import shutil
import subprocess
import threading
import time

WPA_CONF = "/media/fat/linux/wpa_supplicant.conf"
CONF_HEADER = "ctrl_interface=/run/wpa_supplicant\nupdate_config=1\n"


# ---------------------------------------------------------------------------
# System side
# ---------------------------------------------------------------------------
def run(cmd, timeout=20):
    """(returncode, stdout) of a command; (127, '') if it isn't there."""
    if not shutil.which(cmd[0]):
        return 127, ""
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode, r.stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def find_interface(sys_net="/sys/class/net"):
    """The Wi-Fi adapter (wlan0 on most MiSTers), or None if there isn't one."""
    try:
        names = sorted(os.listdir(sys_net))
    except OSError:
        return None
    for n in names:
        if os.path.isdir(os.path.join(sys_net, n, "wireless")) or os.path.isdir(os.path.join(sys_net, n, "phy80211")):
            return n
    return None


def wpa_psk(ssid, password):
    """The 256-bit WPA key for a passphrase (what wpa_passphrase prints)."""
    return hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), ssid.encode("utf-8"), 4096, 32).hex()


def _unescape_wpa(s):
    """wpa_cli prints non-ASCII SSID bytes as \\xNN."""
    try:
        return re.sub(rb"\\x([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]),
                      s.encode("latin-1", "backslashreplace")).decode("utf-8", "replace")
    except Exception:
        return s


def parse_wpa_scan(text):
    """wpa_cli scan_results -> [{ssid, signal (0-100), security}]"""
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or not re.match(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$", parts[0].lower()):
            continue
        try:
            dbm = int(parts[2])
        except ValueError:
            dbm = -90
        flags, ssid = parts[3], _unescape_wpa(parts[4])
        out.append({"ssid": ssid, "signal": max(0, min(100, 2 * (dbm + 100))),
                    "security": _security(flags)})
    return out


def _security(flags):
    f = flags.upper()
    if "EAP" in f and "PSK" not in f:
        return "enterprise"
    if "PSK" in f or "SAE" in f:
        return "wpa"
    if "WEP" in f:
        return "wep"
    return "open"


def parse_iwlist(text):
    """iwlist <if> scan -> [{ssid, signal, security}]"""
    out = []
    cell = None

    def done():
        if cell and cell.get("ssid"):
            if cell["security"] == "wpa" and cell["auth"] and not cell["psk"]:
                cell["security"] = "enterprise"
            out.append({k: cell[k] for k in ("ssid", "signal", "security")})

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Cell "):
            done()
            cell = {"ssid": "", "signal": 0, "security": "open", "auth": False, "psk": False}
            continue
        if cell is None:
            continue
        m = re.match(r'ESSID:"(.*)"$', s)
        if m:
            cell["ssid"] = _unescape_wpa(m.group(1))
        m = re.search(r"Quality[=:](\d+)/(\d+)", s)
        if m:
            cell["signal"] = int(m.group(1)) * 100 // max(1, int(m.group(2)))
        if s.startswith("Encryption key:on") and cell["security"] == "open":
            cell["security"] = "wep"
        if "WPA" in s and ("IE:" in s or "Version" in s):
            cell["security"] = "wpa"
        if s.startswith("Authentication Suites"):
            cell["auth"] = True
            if "PSK" in s or "SAE" in s:
                cell["psk"] = True
    done()
    return out


def merge_networks(found):
    """Strongest entry per SSID, strongest first."""
    best = {}
    for n in found:
        if not n["ssid"] or n["ssid"].startswith("\x00"):
            continue
        if n["ssid"] not in best or n["signal"] > best[n["ssid"]]["signal"]:
            best[n["ssid"]] = n
    return sorted(best.values(), key=lambda n: (-n["signal"], n["ssid"].lower()))


def scan(iface, wait=4):
    """Nearby networks. Uses wpa_supplicant's scan if it's running, else iwlist."""
    rc, out = run(["wpa_cli", "-i", iface, "ping"], 5)
    if rc == 0 and "PONG" in out:
        run(["wpa_cli", "-i", iface, "scan"], 5)
        time.sleep(wait)
        rc, out = run(["wpa_cli", "-i", iface, "scan_results"], 5)
        nets = parse_wpa_scan(out) if rc == 0 else []
        if nets:
            return merge_networks(nets)
    run(["ip", "link", "set", iface, "up"], 5)
    rc, out = run(["iwlist", iface, "scan"], 25)
    return merge_networks(parse_iwlist(out)) if rc == 0 else []


def current(iface):
    """{'ssid', 'ip'} of the current connection (either may be '')."""
    ssid = ""
    rc, out = run(["wpa_cli", "-i", iface, "status"], 5)
    if rc == 0:
        st = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
        if st.get("wpa_state") == "COMPLETED":
            ssid = _unescape_wpa(st.get("ssid", ""))
    if not ssid:
        rc, out = run(["iwgetid", "-r", iface], 5)
        ssid = out.strip() if rc == 0 else ""
    ip = ""
    rc, out = run(["ip", "-o", "-4", "addr", "show", "dev", iface, "scope", "global"], 5)
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out) if rc == 0 else None
    if m and not m.group(1).startswith("169.254."):
        ip = m.group(1)
    return {"ssid": ssid, "ip": ip}


# ---------------------------------------------------------------------------
# wpa_supplicant.conf
# ---------------------------------------------------------------------------
def _block_ssid(block):
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("ssid="):
            v = s[5:].strip()
            if v.startswith('"') and v.endswith('"') and len(v) >= 2:
                return v[1:-1]
            if re.match(r"^([0-9a-fA-F]{2})+$", v):
                try:
                    return bytes.fromhex(v).decode("utf-8", "replace")
                except ValueError:
                    return None
    return None


def split_conf(text):
    """(header lines, [network block texts], other blocks kept as they are)"""
    header, blocks, depth, cur = [], [], 0, []
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip() if not line.strip().startswith("#") else ""
        if depth == 0 and s.endswith("{"):
            depth, cur = 1, [line]
            continue
        if depth:
            cur.append(line)
            depth += s.count("{") - s.count("}")
            if depth <= 0:
                blocks.append("\n".join(cur))
                depth, cur = 0, []
            continue
        header.append(line)
    if cur:                                         # unterminated: keep it
        blocks.append("\n".join(cur))
    return header, blocks


def network_block(ssid, password, hidden=False):
    lines = ["network={", "    ssid=%s" % ssid.encode("utf-8").hex()]
    if hidden:
        lines.append("    scan_ssid=1")
    if password:
        lines.append("    psk=%s" % wpa_psk(ssid, password))
    else:
        lines.append("    key_mgmt=NONE")
    lines.append("    priority=5")
    lines.append("}")
    return "\n".join(lines)


def save_network(ssid, password, hidden=False, conf=WPA_CONF, country=""):
    """Add (or replace) a network, keeping everything else in the file.
    The new network gets a higher priority than the others."""
    try:
        with open(conf) as f:
            text = f.read()
    except OSError:
        text = CONF_HEADER
    header, blocks = split_conf(text)
    if not any(l.strip().startswith("ctrl_interface") for l in header):
        header.insert(0, "ctrl_interface=/run/wpa_supplicant")
    if not any(l.strip().startswith("update_config") for l in header):
        header.insert(1, "update_config=1")
    if country and not any(l.strip().startswith("country") for l in header):
        header.append("country=%s" % country.upper())
    kept = [b for b in blocks if not (b.lstrip().startswith("network") and _block_ssid(b) == ssid)]
    # earlier networks drop to the normal priority so the new one is preferred
    kept = [re.sub(r"(?m)^\s*priority=\d+\s*\n", "", b) if b.lstrip().startswith("network") else b
            for b in kept]
    while header and not header[-1].strip():
        header.pop()
    out = "\n".join(header) + "\n\n" + "".join(b + "\n\n" for b in kept) + network_block(ssid, password, hidden) + "\n"
    if os.path.exists(conf):
        shutil.copy2(conf, conf + ".bak")
    os.makedirs(os.path.dirname(conf), exist_ok=True)
    tmp = conf + ".tmp"
    with open(tmp, "w") as f:
        f.write(out)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, conf)
    return out


def apply(iface, conf=WPA_CONF):
    """Have wpa_supplicant use the file now, then ask for an address."""
    rc, out = run(["wpa_cli", "-i", iface, "ping"], 5)
    if rc == 0 and "PONG" in out:
        run(["wpa_cli", "-i", iface, "reconfigure"], 10)
        run(["wpa_cli", "-i", iface, "reassociate"], 10)
    else:
        run(["ip", "link", "set", iface, "up"], 5)
        run(["wpa_supplicant", "-B", "-i", iface, "-c", conf], 15)


def request_address(iface):
    for cmd in (["dhcpcd", "-n", iface], ["udhcpc", "-n", "-q", "-i", iface, "-T", "3", "-t", "5"],
                ["dhclient", iface]):
        rc, _ = run(cmd, 20)
        if rc != 127:
            return rc == 0
    return False


def connect(iface, ssid, wait=25, conf=WPA_CONF, sleep=time.sleep):
    """After save_network(): returns the IP address, or '' if it didn't connect."""
    apply(iface, conf)
    asked = False
    for i in range(wait):
        cur = current(iface)
        if cur["ssid"] == ssid:
            if cur["ip"]:
                return cur["ip"]
            if not asked and i >= 3:
                request_address(iface)
                asked = True
        sleep(1)
    return ""


# ---------------------------------------------------------------------------
# The operator-menu pages: network list and on-screen keyboard
# ---------------------------------------------------------------------------
KEY_ROWS = (
    "abcdefghijklm", "nopqrstuvwxyz",
    "ABCDEFGHIJKLM", "NOPQRSTUVWXYZ",
    "0123456789-_.",
    "!@#$%^&*()+=?",
    "[]{}<>/\\|:;'\"",
    ",`~",
)
SPECIAL_KEYS = ("SPACE", "DEL", "CLEAR", "SHOW", "DONE")
COLS = 13


class Keyboard:
    """Typing with a stick: move over the grid, button 1 types the key (or
    presses SPACE/DEL/CLEAR/SHOW/DONE), button 2 deletes, button 3 is DONE."""

    def __init__(self, title, prompt, max_len=63, min_len=0, masked=False):
        self.title, self.prompt = title, prompt
        self.text = ""
        self.max_len, self.min_len = max_len, min_len
        self.masked = masked
        self.row, self.col = 0, 0
        self.msg = None

    def rows(self):
        return len(KEY_ROWS) + 1

    def row_len(self, r):
        return len(SPECIAL_KEYS) if r == len(KEY_ROWS) else len(KEY_ROWS[r])

    def move(self, dx, dy):
        if dy:
            # keep roughly the same horizontal position between rows
            frac = (self.col + 0.5) / self.row_len(self.row)
            self.row = (self.row + dy) % self.rows()
            self.col = min(self.row_len(self.row) - 1, int(frac * self.row_len(self.row)))
        if dx:
            self.col = (self.col + dx) % self.row_len(self.row)
        self.msg = None

    def key(self):
        if self.row == len(KEY_ROWS):
            return SPECIAL_KEYS[self.col]
        return KEY_ROWS[self.row][self.col]

    def press(self):
        """Returns 'done' when the text is finished."""
        k = self.key()
        if k == "SPACE":
            self.type(" ")
        elif k == "DEL":
            self.text = self.text[:-1]
        elif k == "CLEAR":
            self.text = ""
        elif k == "SHOW":
            self.masked = not self.masked
        elif k == "DONE":
            return self.finish()
        else:
            self.type(k)
        return None

    def type(self, ch):
        if len(self.text) >= self.max_len:
            self.msg = "%d CHARACTERS AT MOST" % self.max_len
            return
        self.text += ch
        self.msg = None

    def backspace(self):
        self.text = self.text[:-1]

    def finish(self):
        if len(self.text) < self.min_len:
            self.msg = "AT LEAST %d CHARACTERS" % self.min_len
            return None
        return "done"

    def draw(self, c, th):
        BG, PANEL, LINE, ACCENT, TITLE, INFO, TEXT, DIM, SELECT = th
        c.fill(0, 0, c.w, c.h, BG)
        c.text(8, 5, self.title, TITLE, BG, scale=2)
        c.fill(0, 24, c.w, 2, ACCENT)
        chars = (c.w - 16) // 8
        c.text(8, 30, self.prompt[:chars], INFO, BG)
        # the text so far (the end of it if it's long)
        shown = ("*" * len(self.text)) if self.masked else self.text
        if self.masked and self.text:
            shown = shown[:-1] + self.text[-1]          # last character visible
        box_chars = chars - 1
        view = shown[-(box_chars - 1):] if len(shown) >= box_chars else shown
        c.frame(6, 41, c.w - 12, 13, LINE)
        c.text(9, 44, view + "_", TEXT, BG)
        c.text(c.w - 8 - 8 * len(str(len(self.text))) - 8, 30, "%d" % len(self.text), DIM, BG)
        # the grid
        cw = min(22, (c.w - 12) // COLS)
        ch = 15
        gx = (c.w - cw * COLS) // 2
        gy = 60
        for r, row in enumerate(KEY_ROWS):
            for i, k in enumerate(row):
                x, y = gx + i * cw, gy + r * ch
                sel = (r, i) == (self.row, self.col)
                if sel:
                    c.fill(x, y, cw - 1, ch - 1, ACCENT)
                c.text(x + (cw - 9) // 2 + 1, y + 3, k, SELECT if sel else TEXT, ACCENT if sel else BG)
        y = gy + len(KEY_ROWS) * ch + 2
        n = len(SPECIAL_KEYS)
        kw = (cw * COLS) // n
        for i, k in enumerate(SPECIAL_KEYS):
            label = ("HIDE" if not self.masked else "SHOW") if k == "SHOW" else k
            x = gx + i * kw
            sel = (len(KEY_ROWS), i) == (self.row, self.col)
            if sel:
                c.fill(x, y, kw - 2, ch, ACCENT)
            else:
                c.frame(x, y, kw - 2, ch, LINE)
            label = label[:max(1, (kw - 4) // 8)]
            c.text(x + (kw - 2 - 8 * len(label)) // 2, y + 4, label, SELECT if sel else TEXT, ACCENT if sel else BG)
        fy = c.h - 14
        c.fill(0, fy - 16, c.w, 1, LINE)
        if self.msg:
            c.text(8, fy - 12, self.msg[:chars], TITLE, BG)
        else:
            c.text(8, fy - 12, "1:TYPE  2:DELETE  3:DONE"[:chars], DIM, BG)
        c.text(8, fy, "MENU:CANCEL"[:chars], DIM, BG)


class WifiSetup:
    """WI-FI in the operator menu: the networks nearby (strongest first),
    then the keyboard for the password, then connect."""

    REPEAT_DELAY, REPEAT_EVERY = 0.4, 0.09

    def __init__(self, kiosk, opview, log, iface=None, conf=WPA_CONF, background=True, country=""):
        self.k, self.op, self.log = kiosk, opview, log
        self.iface = iface if iface is not None else find_interface()
        self.conf = conf
        self.country = country
        self.background = background
        self.networks = []
        self.sel = 0
        self.top = 0
        self.busy = None              # "SCANNING..." / "CONNECTING..." while working
        self.status = {"ssid": "", "ip": ""}
        self.keyboard = None          # Keyboard while typing
        self.kb_for = None            # ("password", ssid) or ("ssid", None)
        self.hidden_ssid = None
        self.result = None
        self.held = None              # (dx, dy, since, last repeat)
        if self.iface:
            self.rescan()

    # -- work done in the background -------------------------------------------
    def _bg(self, fn):
        if self.background:
            threading.Thread(target=fn, daemon=True).start()
        else:
            fn()

    def rescan(self):
        if self.busy:
            return
        self.busy = "SCANNING..."

        def work():
            try:
                self.status = current(self.iface)
                self.networks = scan(self.iface)
            except Exception as e:                 # never take the kiosk down
                self.log("wifi scan failed: %r" % e)
                self.networks = []
            self.sel = min(self.sel, max(0, len(self.rows()) - 1))
            self.busy = None
            self.k.need_redraw = True
        self._bg(work)

    def start_connect(self, ssid, password, hidden=False):
        self.busy = "CONNECTING TO\n" + ssid[:24]
        self.result = None

        def work():
            try:
                save_network(ssid, password, hidden, self.conf, self.country)
                self.log("wifi: saved %s (%s)" % (ssid, "WPA" if password else "open"))
                ip = connect(self.iface, ssid, conf=self.conf)
            except Exception as e:
                self.log("wifi connect failed: %r" % e)
                ip = ""
            self.status = current(self.iface)
            if ip:
                self.log("wifi: connected to %s, %s" % (ssid, ip))
                self.result = "CONNECTED\n" + ip
            else:
                self.log("wifi: no connection to %s" % ssid)
                self.result = "NOT CONNECTED\nCHECK THE PASSWORD"
            self.busy = None
            self.op.show_toast(self.result, 4)
            self.k.need_redraw = True
        self._bg(work)

    # -- the list -----------------------------------------------------------------
    def rows(self):
        out = [("SCAN AGAIN", None)]
        for n in self.networks:
            out.append((n["ssid"], n))
        out.append(("OTHER (HIDDEN) NETWORK", "hidden"))
        return out

    def choose(self):
        label, n = self.rows()[self.sel]
        if n is None:
            self.rescan()
        elif n == "hidden":
            self.keyboard = Keyboard("WI-FI", "NETWORK NAME (SSID)", max_len=32, min_len=1)
            self.kb_for = ("ssid", None)
        elif n["security"] in ("enterprise", "wep"):
            self.op.show_toast("%s NETWORKS\nAREN'T SUPPORTED" % ("WEP" if n["security"] == "wep" else "802.1X"), 3)
        elif n["security"] == "open":
            self.start_connect(n["ssid"], "")
        else:
            self.keyboard = Keyboard("WI-FI", "PASSWORD FOR " + n["ssid"], max_len=63, min_len=8)
            self.kb_for = ("password", n["ssid"])

    def keyboard_done(self):
        kind, ssid = self.kb_for
        text = self.keyboard.text
        if kind == "ssid":
            self.hidden_ssid = text
            self.keyboard = Keyboard("WI-FI", "PASSWORD (BLANK IF OPEN)", max_len=63, min_len=0)
            self.kb_for = ("hidden_password", text)
            return
        if kind == "hidden_password" and 0 < len(text) < 8:
            self.keyboard.msg = "AT LEAST 8 CHARACTERS"
            return
        self.keyboard = None
        self.start_connect(ssid, text, hidden=(kind == "hidden_password"))

    # -- input ----------------------------------------------------------------------
    def direction(self, axis, d, now):
        dx, dy = (d, 0) if axis == "x" else (0, d)
        if not d:
            self.held = None
            return
        self.held = (dx, dy, now, now)
        self.step(dx, dy)

    def step(self, dx, dy):
        if self.busy:
            return
        if self.keyboard:
            self.keyboard.move(dx, dy)
        elif dy:
            self.sel = (self.sel + dy) % len(self.rows())
        elif dx:
            self.sel = max(0, min(len(self.rows()) - 1, self.sel + dx * 8))
        self.k.need_redraw = True

    def button(self, role):
        """role: 'one', 'two', 'three', 'menu'. Returns 'leave' to go back."""
        if self.busy:
            return None
        if self.keyboard:
            if role == "menu":
                self.keyboard = None
            elif role == "one":
                if self.keyboard.press() == "done":
                    self.keyboard_done()
            elif role == "two":
                self.keyboard.backspace()
            elif role == "three":
                if self.keyboard.finish() == "done":
                    self.keyboard_done()
            self.k.need_redraw = True
            return None
        if role in ("menu", "two"):
            return "leave"
        if role == "one" and self.iface:
            self.choose()
        self.k.need_redraw = True
        return None

    def tick(self, now):
        if self.held:
            dx, dy, since, last = self.held
            if now - since >= self.REPEAT_DELAY and now - last >= self.REPEAT_EVERY:
                self.held = (dx, dy, since, now)
                self.step(dx, dy)

    # -- drawing -------------------------------------------------------------------------
    def draw(self, c, th):
        if self.keyboard and not self.busy:
            self.keyboard.draw(c, th)
            return
        BG, PANEL, LINE, ACCENT, TITLE, INFO, TEXT, DIM, SELECT = th
        c.fill(0, 0, c.w, c.h, BG)
        c.text(8, 5, "WI-FI", TITLE, BG, scale=2)
        c.fill(0, 24, c.w, 2, ACCENT)
        chars = (c.w - 16) // 8
        if not self.iface:
            c.text(8, 40, "NO WI-FI ADAPTER FOUND", TEXT, BG)
            c.text(8, 54, "PLUG IN A USB WI-FI ADAPTER", DIM, BG, max_chars=chars)
            c.text(8, 64, "AND OPEN THIS AGAIN.", DIM, BG, max_chars=chars)
        else:
            st = self.status
            if st.get("ssid"):
                line = "ON %s  %s" % (st["ssid"], st.get("ip") or "NO ADDRESS")
            else:
                line = "NOT CONNECTED (%s)" % self.iface
            c.text(8, 30, line[:chars], INFO, BG)
            if self.busy:
                for i, part in enumerate(self.busy.split("\n")):
                    c.text_center(c.w // 2, c.h // 2 - 10 + i * 12, part, TITLE, BG)
            else:
                rows = self.rows()
                per = (c.h - 44 - 34) // 11
                if self.sel < self.top:
                    self.top = self.sel
                if self.sel >= self.top + per:
                    self.top = self.sel - per + 1
                y = 44
                for i in range(self.top, min(len(rows), self.top + per)):
                    label, n = rows[i]
                    sel = i == self.sel
                    if sel:
                        c.fill(4, y - 2, c.w - 8, 11, ACCENT)
                    bg = ACCENT if sel else BG
                    fg = SELECT if sel else (TEXT if not isinstance(n, dict) or n["security"] in ("open", "wpa") else DIM)
                    right = ""
                    if isinstance(n, dict):
                        bars = 1 + min(3, n["signal"] // 25)
                        right = ("|" * bars).ljust(4) + {"wpa": " LOCK", "open": " OPEN",
                                                       "wep": " WEP", "enterprise": " 802.1X"}[n["security"]]
                        if n["ssid"] == st.get("ssid"):
                            label = "* " + label
                    room = chars - len(right) - 1
                    c.text(8, y, label[:room], fg, bg)
                    if right:
                        c.text(c.w - 8 - 8 * len(right), y, right, fg if sel else DIM, bg)
                    y += 11
                if not self.networks:
                    c.text(8, y + 4, "NO NETWORKS FOUND", DIM, BG)
        fy = c.h - 14
        c.fill(0, fy - 16, c.w, 1, LINE)
        c.text(8, fy - 12, "1:CHOOSE"[:chars], DIM, BG)
        c.text(8, fy, "2:BACK"[:chars], DIM, BG)
