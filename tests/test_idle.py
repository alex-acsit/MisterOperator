import sys, time
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
K.set_config_value("arcade_dir", T + "/_Arcade")
K.set_config_value("operator_menu", "0")   # these tests cover the direct-to-stock-menu unlock
for k, v in (("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"), ("exit_grace_s", "0")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1

# ---- themes
cfg = K.load_config()
check(cfg["theme"] == "green" and K.apply_theme(cfg)["accent"] == (40, 150, 85), "green is the default theme")
check(K.apply_theme({"theme": "classic"})["accent"] == (255, 60, 127), "classic theme available")
check(K.apply_theme({"theme": "phosphor"})["accent"] == (0, 210, 90), "phosphor theme available")
p = K.apply_theme({"theme": "green", "color_accent": "#123456", "color_text": "10, 20, 30", "color_dim": "nope"})
check(p["accent"] == (0x12, 0x34, 0x56) and p["text"] == (10, 20, 30) and p["dim"] == (135, 142, 138),
      "colour overrides (#RRGGBB and r,g,b); bad value ignored")
check(K.apply_theme({"theme": "purple"})["accent"] == (40, 150, 85), "unknown theme falls back to green")
K.apply_theme({})

# ---- idle exit
cmds = []; core = {"name": "MENU", "stamp": 1}
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.core_name = lambda: core["name"]; K.core_stamp = lambda: core["stamp"]; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
def newcore(n): core["name"] = n; core["stamp"] += 1
class FakeVirt:
    def __init__(s): s.out = []
    def emit(s, t, c, v, sync=False): s.out.append((t, c, v))
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s):
        s.path, s.name, s.vendor, s.product, s.phys = "/dev/input/event1", "Encoder", 0x16c0, 0x05e1, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0), 0x07: (0, 0, 255, 0, 0, 0)}
def fake_activate(self):
    self.canvas = K.Canvas(320, 240, K.PixelFormat())
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None})()
    return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
k = K.Kiosk(); d = FakeDev(); k.devices[d.path] = d
k.poll_core(time.monotonic())
check(k.mode == "launcher", "launcher up")
k.cfg["game_idle_exit_s"] = "0.4"
def idle_tick():
    now = time.monotonic()
    if (k.mode == "game" and float(k.cfg["game_idle_exit_s"]) > 0 and k.state["locked"]
            and now - k.game_last_input >= float(k.cfg["game_idle_exit_s"])):
        k.state["pending_toast"] = "GAME ENDED\nNO INPUT"; k.exit_game()
ev = lambda *e: k.handle_events(d, list(e))
ev((1, 0x120, 1)); ev((1, 0x120, 0))
newcore("galaga"); k.poll_core(time.monotonic())
check(k.mode == "game", "game running")
for _ in range(5):                         # stick jitter near centre: not activity
    time.sleep(0.12); ev((3, K.ABS_X, 140)); ev((3, K.ABS_X, 118)); idle_tick()
check(k.mode == "returning" and cmds[-1] == "load_core " + K.MENU_RBF, "stick jitter doesn't count; idle game quits")
newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "launcher" and k.view.toast == "GAME ENDED\nNO INPUT", "back on list with message")

ev((1, 0x120, 1)); ev((1, 0x120, 0)); newcore("galaga"); k.poll_core(time.monotonic())
for e in [(1, 0x121, 1), (3, K.ABS_Y, 255), (2, 0x00, 3), (3, 0x07, 200)]:   # button, stick, spinner, paddle
    time.sleep(0.25); ev(e); ev((1, 0x121, 0)) if e[0] == 1 else None
    if e[0] == 3 and e[1] == K.ABS_Y: ev((3, K.ABS_Y, 127))
    idle_tick()
check(k.mode == "game", "buttons, stick, spinner and paddle all keep the game alive")
time.sleep(0.45); idle_tick()
check(k.mode == "returning", "quits once they stop")
newcore("MENU"); k.poll_core(time.monotonic())

k.cfg["game_idle_exit_s"] = "0"
ev((1, 0x120, 1)); ev((1, 0x120, 0)); newcore("galaga"); k.poll_core(time.monotonic())
time.sleep(0.5); idle_tick()
check(k.mode == "game", "game_idle_exit_s = 0 never quits")
k.cfg["game_idle_exit_s"] = "0.2"; k.set_locked(False); time.sleep(0.3); idle_tick()
check(k.mode == "unlocked", "doesn't quit games while unlocked")
print("%d failure(s)" % fails)
