import sys, time, os
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"; K.VOLUME_PATH = T + "/vol"
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("exit_grace_s", "0"), ("operator_hold_ms", "0")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
cmds = []; core = {"name": "MENU", "stamp": 1}
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.core_name = lambda: core["name"]; K.core_stamp = lambda: core["stamp"]; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
def newcore(n): core["name"] = n; core["stamp"] += 1
def fake_activate(self):
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None,
                             "xres": 320, "yres": 240, "fmt": K.PixelFormat()})()
    self.make_canvases(); return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
class FakeVirt:
    def __init__(s): s.out = []
    def emit(s, t, c, v, sync=False): s.out.append((t, c, v))
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s):
        s.path, s.name, s.vendor, s.product, s.phys = "/dev/input/event1", "Encoder", 1, 2, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}; s.keys = [0x120, 0x121, 0x129, 0x12a]
k = K.Kiosk(); d = FakeDev(); k.devices = {d.path: d}
def press(c): k.handle_events(d, [(1, c, 1)]); k.handle_events(d, [(1, c, 0)])
def goto(label):
    k.opview.sel = [i for i, it in enumerate(k.opview.items()) if it[0] == label][0]
def stick_x(v): k.handle_events(d, [(3, K.ABS_X, v)]); k.handle_events(d, [(3, K.ABS_X, 127)])
k.poll_core(time.monotonic())
labels = lambda: sorted(g["label"] for g in k.view.all_games)
everything = labels()
print(" games:", everything)
k.set_locked(False); check(k.mode == "operator", "operator menu open")

# ---- SHOW GAMES
goto("SHOW GAMES"); check(k.opview.orientation_text() == "ALL", "shows ALL by default")
stick_x(255); check(k.cfg["orientation"] == "horizontal" and k.opview.orientation_text() == "YOKO ONLY", "right: YOKO only")
k.set_locked(True)
check(labels() == ["Bomb Jack", "Ghosts'n Goblins"], "list now horizontal games only")
k.set_locked(False); goto("SHOW GAMES"); stick_x(255)
check(k.cfg["orientation"] == "vertical", "right again: TATE only")
k.set_locked(True); check(labels() == ["Galaga"], "list now vertical games only")
k.set_locked(False); goto("SHOW GAMES"); stick_x(255)
check(k.cfg["orientation"] == "all", "and back to ALL")

# ---- GENRES page
goto("GENRES"); check(k.opview.genres_text() == "ALL >", "no genres hidden yet")
press(0x120); check(k.opview.page == "genres", "button 1 opens the genre page")
names = [ref for _, ref in k.opview.lines]
check(names[:2] == ["__on__", "__off__"] and set(names[2:]) == {"Platform", "Shooter"}, "lists every main genre: %s" % names[2:])
check(any("[X] PLATFORM" in t and t.rstrip().endswith("2") for t, _ in k.opview.lines), "with tick boxes and game counts")
k.opview.sel = names.index("Platform"); press(0x120)
check(k.cfg["hidden_genres"] == "Platform" and k.opview.sel == names.index("Platform"), "button 1 hides Platform (cursor stays)")
check(any("[ ] PLATFORM" in t for t, _ in k.opview.lines), "shown unticked")
press(0x121); check(k.opview.page == "main" and k.opview.genres_text() == "1 HIDDEN >", "button 2 back; summary says 1 hidden")
k.set_locked(True)
check(labels() == ["Galaga"] and "Platform" not in k.view.genres, "game list without Platform games")
k.set_locked(False); goto("GENRES"); press(0x120)
k.opview.sel = 1; press(0x120)
check(set(K._genre_set(k.cfg["hidden_genres"])) == {"platform", "shooter"} and "NO GAMES" in (k.opview.toast or ""),
      "HIDE ALL hides everything and warns")
k.opview.sel = 0; press(0x120); check(k.cfg["hidden_genres"] == "", "SHOW ALL brings them all back")
press(0x121); k.set_locked(True); check(labels() == everything, "full list again")
check(K.load_config()["hidden_genres"] == "" and "hidden_genres" in open(K.CONFIG_PATH).read(), "saved in kiosk.ini")

# ---- UPDATE KIOSK
k.set_locked(False)
rel = {"version": "9.9", "tag": "v9.9", "url": "u", "headers": {}}
K.latest_release = lambda cfg: rel
installed = []
K.install_release = lambda r, say=None: installed.append(r) or r["version"]
goto("UPDATE KIOSK"); check(k.opview.update_text() == "V" + K.VERSION, "shows the installed version")
press(0x120); check(k.opview.release is rel and "AVAILABLE" in k.opview.toast and not installed, "first press: finds 9.9")
check(k.opview.update_text() == "INSTALL V9.9", "row now offers the install")
press(0x120); check(installed == [rel] and k.pending_restart, "second press installs and asks for a restart")
k.pending_restart = False; k.opview.release = None
K.latest_release = lambda cfg: dict(rel, version=K.VERSION)
press(0x120); check("UP TO DATE" in k.opview.toast and not k.opview.release, "already current: says so")
def boom(cfg): raise K.UpdateError("offline")
K.latest_release = boom
press(0x120); check("FAILED" in k.opview.toast, "no connection: says the check failed")

# ---- restart waits until nobody's playing
k.set_locked(True)
press(0x120); newcore("galaga"); k.poll_core(time.monotonic())
open(K.CTL_PATH, "w").write("restart"); k.check_control()
safe = (K.S_LAUNCHER, K.S_OPERATOR, K.S_WAIT, K.S_RETURNING, K.S_ATTRACT)
check(k.pending_restart and k.mode == "game" and k.mode not in safe, "restart requested mid-game is held back")
press(0x129); check(k.mode in safe, "after the player quits, it's allowed")
print("%d failure(s)" % fails)
