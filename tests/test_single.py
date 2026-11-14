import sys, time, os
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
SHOTS = os.environ.get("SHOTS")
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"; K.VOLUME_PATH = T + "/vol"
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("exit_grace_s", "0"), ("operator_hold_ms", "0"), ("game_idle_exit_s", "60"),
             ("inputs_dir", T + "/inputs"), ("save_nvram", "off")):
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
K.Kiosk.release_framebuffer = lambda self, text_mode=True, clear=True: setattr(self, "fb", None)
K.Kiosk.scan_devices = lambda self: None
class FakeVirt:
    def __init__(s): s.out = []
    def emit(s, t, c, v, sync=False): s.out.append((t, c, v))
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s):
        s.path, s.name, s.vendor, s.product, s.phys = "/dev/input/event1", "Encoder", 1, 2, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}; s.keys = []
k = K.Kiosk(); d = FakeDev(); k.devices = {d.path: d}
def press(c): k.handle_events(d, [(1, c, 1)]); k.handle_events(d, [(1, c, 0)])
def poll(n=3):
    for _ in range(n):
        k.poll_core(time.monotonic())
MENU, OP = K.parse_code("BTN_BASE4"), K.parse_code("BTN_BASE5")
def hold_op():
    k.handle_events(d, [(1, OP, 1)])
    k.op_fired = True
    if not k.state["locked"] and k.mode in (K.S_UNLOCKED, K.S_RETURNING) and K.flag(k.cfg, "operator_menu"):
        k.open_operator()
    else:
        k.set_locked(not k.state["locked"])
    k.handle_events(d, [(1, OP, 0)])

poll(); check(k.mode == "launcher", "no single game: the game list as usual")
k.set_locked(False); check(k.mode == "operator", "operator menu")
items = [it[0] for it in k.opview.items()]
check("SINGLE GAME" in items and k.opview.single_text() == "OFF >", "SINGLE GAME item, OFF")
k.opview.sel = items.index("SINGLE GAME"); press(0x120)
check(k.opview.page == "single" and k.opview.lines[0][1] == "" and k.opview.lines[0][0].startswith("*"),
      "page lists OFF (current) then the games")
galaga = [i for i, (t, p) in enumerate(k.opview.lines) if "GALAGA" in t][0]
gpath = k.opview.lines[galaga][1]
if SHOTS:
    k.opview.sel = galaga; k.need_redraw = True; k.draw(); k.canvas.save_ppm(SHOTS + "/single.ppm")
k.opview.sel = galaga; press(0x120)
check(K.load_config()["single_game"] == gpath and k.opview.lines[galaga][0].startswith("*"), "Galaga chosen and saved")
press(0x121); check(k.opview.single_text().startswith("GALAGA"), "menu shows the game")

cmds.clear(); k.set_locked(True)
check(k.mode == "game" and cmds[-1] == "load_core " + gpath, "locking goes straight into the game")
newcore("galaga"); poll()
cmds.clear(); press(MENU)
check(k.mode == "game" and not cmds, "MENU does nothing")
check(all(c != MENU for _, c, _ in d.virtual.out), "and isn't passed to the game")
k.game_last_input = time.monotonic() - 1000
k.cfg["game_idle_exit_s"] = "60"
idle = float(k.cfg["game_idle_exit_s"])
would_exit = (k.mode == K.S_GAME and idle > 0 and k.state["locked"] and not k.cfg.get("single_game", "").strip())
check(not would_exit, "no idle quit")

# the game drops out: started again
newcore("MENU"); poll(); check(k.mode == "game" and cmds[-1] == "load_core " + gpath, "game ended: started again")
newcore("galaga"); poll()

# operator: hold opens the operator menu, locking again restarts the game
hold_op(); check(k.mode == K.S_RETURNING and not k.state["locked"], "OPERATOR: unlocked, leaving the game")
newcore("MENU"); poll(); check(k.mode == "operator", "operator menu")
cmds.clear(); k.opview.back()
check(k.mode == "game" and cmds[-1] == "load_core " + gpath, "BACK TO GAMES: into Galaga again")

# a power cut: boots locked into the game
newcore("galaga"); poll()
k2 = K.Kiosk(); k2.devices = {d.path: d}
cmds.clear(); newcore("MENU")
for _ in range(3):
    k2.poll_core(time.monotonic())
check(k2.mode == "game" and cmds[-1] == "load_core " + gpath, "after a reboot: straight into the game")

# never starts: falls back to the list after 3 tries
k2.cfg["launch_timeout_s"] = "0"
for i in range(3):
    k2.game_started = time.monotonic() - 10; k2.game_seen_core = False
    k2.poll_core(time.monotonic()); k2.poll_core(time.monotonic())
check(k2.mode == "launcher" and "COULD NOT START" in (k2.view.toast or ""), "game won't start: list with a message after 3 tries")

# off again
k2.set_locked(False); poll()
k2.opview.open_page("single"); k2.opview.sel = 0; k2.opview.press()
check(K.load_config()["single_game"] == "" and k2.opview.single_text() == "OFF >", "OFF: back to the game list")
k2.opview.back(); k2.opview.back(); check(k2.mode == "launcher", "locking shows the list again")
# 2.4: an older install on save_nvram = once is moved to always, one time only
st = K.load_state(); st.pop("nvram_always_set", None); K.save_state(st)
K.set_config_value("save_nvram", "once")
k3 = K.Kiosk(); check(K.load_config()["save_nvram"] == "always" and k3.cfg["save_nvram"] == "always",
                     "old default once becomes always")
K.set_config_value("save_nvram", "once")
k4 = K.Kiosk(); check(K.load_config()["save_nvram"] == "once", "only once: an operator's later choice stays")
print("%d failure(s)" % fails)
