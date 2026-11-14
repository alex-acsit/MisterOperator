import sys, time, os
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
K.VOLUME_PATH = T + "/Volume.dat"; open(K.VOLUME_PATH, "wb").write(bytes([3]))      # level 4
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("exit_grace_s", "0"), ("operator_hold_ms", "0"), ("nvram_dir", T + "/nvram"), ("nvram_save_s", "0.01")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1

cmds = []; core = {"name": "MENU", "stamp": 1}
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.core_name = lambda: core["name"]; K.core_stamp = lambda: core["stamp"]; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
def newcore(n): core["name"] = n; core["stamp"] += 1
fb_on = []
def fake_activate(self):
    fb_on.append(1)
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None,
                             "xres": 320, "yres": 240, "fmt": K.PixelFormat()})()
    self.make_canvases()
    return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
class Keys:
    def tap(s, c): cmds.append("TAP " + K.code_name(c))
    def close(s): pass
class FakeVirt:
    def __init__(s): s.out = []
    def emit(s, t, c, v, sync=False): s.out.append((t, c, v))
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s):
        s.path, s.name, s.vendor, s.product, s.phys = "/dev/input/event1", "Encoder", 0x16c0, 0x05e1, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}
        s.keys = [0x120, 0x121, 0x128, 0x129, 0x12a, K.KEY_NAMES["BTN_BASE3"]]
k = K.Kiosk(); k.keys_dev = Keys(); d = FakeDev(); k.devices = {d.path: d}
k.poll_core(time.monotonic())
check(k.mode == "launcher", "game list up")
def ev(*e): k.handle_events(d, list(e))
def press(code): ev((1, code, 1)); ev((1, code, 0))
def hold_op():                      # operator press + the main loop's hold check
    ev((1, 0x12a, 1)); k.op_fired = True
    if (not k.state["locked"] and k.mode in ("unlocked", "returning")):
        k.open_operator()
    else:
        k.set_locked(not k.state["locked"])
    ev((1, 0x12a, 0))
def stick(axis, val): ev((3, axis, val)); ev((3, axis, 127))
def down(n=1):
    for _ in range(n): stick(K.ABS_Y, 255)
def item(): return k.opview.items()[k.opview.sel][0]
def draws():
    c = K.Canvas(320, 240, K.PixelFormat()); k.opview.draw(c); return True

# ---- open from the game list, without reloading anything
del cmds[:]; fb_on.clear()
hold_op()
check(k.mode == "operator" and k.opview and not cmds and not fb_on, "OPERATOR on the list opens the operator menu in place")
check(not k.state["locked"] and draws(), "unlocked, and the menu draws")

# ---- settings
down(); check(item() == "VOLUME" and k.opview.volume_text() == "4", "volume read from the MiSTer (level 4)")
stick(K.ABS_X, 255); check(cmds[-1] == "volume 5", "right raises the volume")
for _ in range(6): stick(K.ABS_X, 0)
check(cmds[-1] == "volume mute" and k.opview.volume_text() == "MUTE", "left past 0 mutes")
stick(K.ABS_X, 255); check(cmds[-1] == "volume unmute", "right unmutes")
down(); stick(K.ABS_X, 255); stick(K.ABS_X, 255)
check(len(k.state["coins"]) == 2 and k.opview.credits == 2, "credits: right adds free credits")
press(0x120); check(len(k.state["coins"]) == 2 and k.opview.confirm == "CREDITS", "clearing credits asks for a second press")
press(0x120); check(k.state["coins"] == [], "second press clears them")
down(); stick(K.ABS_X, 255)
check(k.cfg["attract_idle_s"] == "180" and "attract_idle_s = 180" in open(K.CONFIG_PATH).read(),
      "demo time changed and saved to kiosk.ini")
stick(K.ABS_X, 0); stick(K.ABS_X, 0)
check(k.cfg["attract_idle_s"] == "60", "and back down")
down(4); check(item() == "SAVE NVRAM", "reached SAVE NVRAM"); stick(K.ABS_X, 255)
check(k.cfg["save_nvram"] == "off", "save NVRAM: always (default) -> off")
stick(K.ABS_X, 0); check(k.cfg["save_nvram"] == "always", "and back to always")
down(); stick(K.ABS_X, 255)
check(k.cfg["screen"] == "tate_cw" and k.lcanvas is not None and draws(), "screen: YOKO -> TATE, canvas follows")
stick(K.ABS_X, 0); check(k.cfg["screen"] == "yoko" and k.lcanvas is None, "and back")
down(); stick(K.ABS_X, 255); check(k.cfg["theme"] == "phosphor" and K.ACCENT == (0, 210, 90), "theme changes live")
stick(K.ABS_X, 0)

# ---- back locks; play a game, then OPERATOR from inside the game
press(0x121)
check(k.mode == "launcher" and k.state["locked"] and k.opview is None, "button 2 on the main page locks back to the list")
press(0x120); newcore("galaga"); k.poll_core(time.monotonic())
check(k.mode == "game" and k.state["plays"], "game running, play counted")
del cmds[:]
hold_op()
check(k.mode == "returning" and cmds[-1] == "load_core " + K.MENU_RBF, "OPERATOR in a game quits it")
newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "operator" and k.opview is not None, "... and the operator menu opens, not the stock menu")

# ---- game settings: run the last game unlocked, OPERATOR comes back
k.opview.sel = [i for i, it in enumerate(k.opview.items()) if it[0] == "GAME SETTINGS"][0]
last = k.last_game(); del cmds[:]
press(0x120)
check(k.mode == "unlocked" and cmds[-1] == "load_core " + last["path"], "game settings runs %s unlocked" % last["label"])
newcore("galaga"); k.poll_core(time.monotonic())
n = len(d.virtual.out); ev((1, 0x129, 1))
check(d.virtual.out[n:] == [(1, 0x129, 1)], "MENU reaches the MiSTer there (for DIP switches)")
ev((1, 0x129, 0))
hold_op(); newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "operator", "OPERATOR goes back to the operator menu")

# ---- stock MiSTer menu, and back
k.opview.sel = [i for i, it in enumerate(k.opview.items()) if it[0] == "MISTER MENU"][0]
del cmds[:]; press(0x120)
check(k.mode == "unlocked" and cmds == ["load_core " + K.MENU_RBF] and k.fb is None, "MiSTer menu item opens the stock menu")
newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "unlocked", "it stays there (no operator menu on top)")
hold_op(); newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "operator", "OPERATOR goes back to the operator menu")

# ---- pages
k.opview.open_page("plays")
played = k.last_game()["label"]
check(k.opview.lines and k.opview.lines[0][0].endswith(played) and k.opview.lines[0][0].strip().startswith("1 "),
      "play counts page shows %s played once" % played)
press(0x121); check(k.opview.page == "main", "button 2 goes back to the main page")
os.makedirs(T + "/nvram", exist_ok=True)
g = [x for x in k.all_games() if x["label"] == "NBA Jam TE"][0]
open(k.nvram_file(g), "wb").write(b"x"); k.state.setdefault("nvram_good", []).append(g["path"])
k.opview.open_page("nvram")
check(k.opview.lines[0][1] is g, "reset NVRAM lists games with a saved NVRAM")
press(0x120); check(os.path.exists(k.nvram_file(g)) and draws(), "first press asks to confirm")
press(0x120); check(not os.path.exists(k.nvram_file(g)) and g["path"] not in k.state["nvram_good"], "second press resets it")
k.opview.open_page("log"); check(k.opview.lines and draws(), "log page")
press(0x121)

# ---- timeout and control
k.op_activity = time.monotonic() - 1000
now = time.monotonic()
if now - k.op_activity >= float(k.cfg["operator_timeout_s"]): k.set_locked(True)
check(k.mode == "launcher" and k.state["locked"], "left alone, the operator menu locks itself")
open(K.CTL_PATH, "w").write("unlock"); k.check_control()
check(k.mode == "operator", "--unlock opens the operator menu")
open(K.CTL_PATH, "w").write("stock"); k.check_control()
check(k.mode == "unlocked" and cmds[-1] == "load_core " + K.MENU_RBF, "--stock goes to the stock MiSTer menu")
open(K.CTL_PATH, "w").write("lock"); k.check_control(); newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "launcher" and k.state["locked"], "--lock back to the list")

# ---- boot while unlocked opens the operator menu
k2 = K.Kiosk(); k2.keys_dev = Keys(); k2.devices = {}
k2.state["locked"] = False; k2.mode = "wait"; k2.poll_core(time.monotonic())
check(k2.mode == "operator", "kiosk restarted while unlocked: operator menu")
print("%d failure(s)" % fails)
