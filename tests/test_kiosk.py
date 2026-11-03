import os, sys, time, json
sys.path.insert(0, sys.argv[1])
import arcadekiosk as K
T = sys.argv[2]
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
K.set_config_value("arcade_dir", T + "/_Arcade")
K.set_config_value("menu_settle_s", "0.1")
K.set_config_value("exit_grace_s", "0.3")
K.set_config_value("operator_hold_ms", "200")
fails = 0
def check(cond, msg):
    global fails
    print(("PASS " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1

# --- config writer keeps comments
txt = open(K.CONFIG_PATH).read()
check("; How long the operator button" in txt and "arcade_dir = %s/_Arcade" % T in txt, "config writer keeps comments")

# --- scanning
cfg = K.load_config()
games = K.scan_games(cfg)
labels = [g["label"] for g in games]
check(labels == ["Bomb Jack", "Galaga", "Ghosts'n Goblins"], "scan + short names + broken XML fallback: %s" % labels)
check(any(g["vertical"] for g in games if g["label"] == "Galaga"), "rotation parsed")
check(next(g for g in games if g["label"].startswith("Ghost"))["maker"] == "Capcom & Co", "regex fallback decodes &amp;")
cfg["hide_vertical"] = "1"
check([g["label"] for g in K.scan_games(cfg)] == ["Bomb Jack", "Ghosts'n Goblins"], "hide_vertical")
open(T + "/list.txt", "w").write("Bomb Jack.mra\n")
cfg = K.load_config(); cfg["game_list"] = T + "/list.txt"
check([g["label"] for g in K.scan_games(cfg)] == ["Bomb Jack"], "game_list whitelist")
cfg = K.load_config(); cfg["include_subdirs"] = "1"
check(len(K.scan_games(cfg)) == 3, "subdir scan excludes _alternatives")

# --- state machine with fakes
cmds = []; core = {"name": "MENU"}
K.mister_cmd = lambda t: cmds.append(t) or True
core["stamp"] = 1
K.core_name = lambda: core["name"]
K.core_stamp = lambda: core["stamp"]
K.mister_ready = lambda: True
def newcore(n):
    core["name"] = n; core["stamp"] += 1
K.set_tty_mode = lambda m: None
class FakeVirt:
    def __init__(s): s.out = []
    def emit(s, t, c, v, sync=False): s.out.append((t, c, v))
    def tap(s, c): pass
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s, path, name, vid, pid):
        s.path, s.name, s.vendor, s.product, s.phys = path, name, vid, pid, "usb-1"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}
def fake_activate(self):
    self.canvas = K.Canvas(320, 240, K.PixelFormat()); self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None})()
    return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
kio = K.Kiosk()
p1 = FakeDev("/dev/input/event1", "Xin-Mo Dual Arcade", 0x16c0, 0x05e1)
kio.devices[p1.path] = p1
check(kio.setup_step == "menu", "setup required on first run")
def ev(*e): kio.handle_events(p1, list(e))
def step(dt=0.0):
    time.sleep(dt); now = time.monotonic(); kio.poll_core(now)
    if kio.op_down_at and not kio.op_fired and now - kio.op_down_at >= 0.2:
        kio.op_fired = True; kio.set_locked(not kio.state["locked"])
step(0.0); step(0.15); p1.virtual.out.clear()
check(kio.mode == "launcher", "launcher shown when menu core settles (mode=%s)" % kio.mode)
ev((1, K.KEY_NAMES["BTN_BASE4"], 1)); ev((1, K.KEY_NAMES["BTN_BASE4"], 0))
check(kio.setup_step == "operator", "menu button captured")
ev((1, K.KEY_NAMES["BTN_BASE4"], 1)); ev((1, K.KEY_NAMES["BTN_BASE4"], 0))
check(kio.setup_step == "operator", "same button refused as operator")
ev((1, K.KEY_NAMES["BTN_BASE5"], 1)); ev((1, K.KEY_NAMES["BTN_BASE5"], 0))
c2 = K.load_config()
check(kio.setup_step is None and c2["menu_button"] == "BTN_BASE4" and c2["operator_button"] == "BTN_BASE5"
      and c2["menu_device"] == "16c0:05e1", "buttons saved to kiosk.ini")

# navigate: down twice on ABS_Y -> Ghosts'n Goblins
ev((3, K.ABS_Y, 255)); ev((3, K.ABS_Y, 127)); ev((3, K.ABS_Y, 255)); ev((3, K.ABS_Y, 127))
check(kio.view.current()["label"] == "Ghosts'n Goblins", "stick moves selection")
ev((3, K.ABS_Y, 0)); ev((3, K.ABS_Y, 127))
check(kio.view.current()["label"] == "Galaga", "stick up")
print("virt out on list:", p1.virtual.out); check(not p1.virtual.out, "nothing forwarded on the game list")
ev((1, K.KEY_NAMES["BTN_TRIGGER"], 1))
check(kio.mode == "game" and cmds[-1].endswith("Galaga (Namco rev. B).mra"), "button 1 launches: %s" % cmds[-1])
ev((1, K.KEY_NAMES["BTN_TRIGGER"], 0))
check(not p1.virtual.out, "launch button release swallowed")
newcore("galaga"); step(0.05)
ev((1, K.KEY_NAMES["BTN_TRIGGER"], 1), (0, 0, 0))
check(p1.virtual.out[-2:] == [(1, 0x120, 1), (0, 0, 0)], "game input forwarded")
ev((1, K.KEY_NAMES["BTN_BASE4"], 1)); ev((1, K.KEY_NAMES["BTN_BASE4"], 0))
check(kio.mode == "game" and (1, 0x129, 1) not in p1.virtual.out, "menu press ignored in grace period, not forwarded")
time.sleep(0.35)
ev((1, K.KEY_NAMES["BTN_BASE4"], 1))
check(kio.mode == "returning" and cmds[-1] == "load_core " + K.MENU_RBF, "menu button quits game")
check((1, 0x120, 0) in p1.virtual.out, "held keys released on exit")
ev((1, K.KEY_NAMES["BTN_BASE4"], 0))
newcore("MENU"); step(0.05); step(1.2)
check(kio.mode == "launcher" and kio.view.current()["label"] == "Galaga", "back on list, last game selected")

# operator unlock / lock
ev((1, K.KEY_NAMES["BTN_BASE5"], 1)); step(0.25)
check(kio.mode == "unlocked" and not kio.state["locked"] and cmds[-1] == "load_core " + K.MENU_RBF, "operator hold unlocks to stock menu")
ev((1, K.KEY_NAMES["BTN_BASE5"], 0))
n = len(p1.virtual.out)
ev((1, K.KEY_NAMES["BTN_BASE4"], 1))
check(p1.virtual.out[n:] == [(1, 0x129, 1)], "unlocked: menu button passes to MiSTer")
ev((1, K.KEY_NAMES["BTN_BASE4"], 0))
check((1, 0x12a, 1) not in p1.virtual.out, "operator button never forwarded")
ev((1, K.KEY_NAMES["BTN_BASE5"], 1)); step(0.25); ev((1, K.KEY_NAMES["BTN_BASE5"], 0))
check(kio.state["locked"] and kio.mode == "returning", "operator hold locks again")
step(0.05)
check(kio.mode == "returning", "waits for the reloaded menu core, not the old one")
newcore("MENU"); step(1.2)
check(kio.mode == "launcher" and kio.view.toast == "LOCKED", "list returns with LOCKED message")

# failed launch
ev((1, K.KEY_NAMES["BTN_TRIGGER"], 1)); ev((1, K.KEY_NAMES["BTN_TRIGGER"], 0))
kio.cfg["launch_timeout_s"] = "0.1"; step(0.15); step(0.05)
check(kio.mode == "launcher" and "COULD NOT" in (kio.view.toast or ""), "failed launch returns with message")

# control file
open(K.CTL_PATH, "w").write("unlock"); kio.check_control()
check(kio.mode == "unlocked", "--unlock control")

# ---- attract mode
open(K.CTL_PATH, "w").write("lock"); kio.check_control(); newcore("MENU"); step(0.05)
check(kio.mode == "launcher", "relocked for attract tests")
kio.cfg.update({"attract_idle_s": "0.2", "attract_game_s": "0.3"})
def loop_idle():
    now = time.monotonic()
    if kio.mode == "launcher" and float(kio.cfg["attract_idle_s"]) > 0 and now - kio.last_activity >= float(kio.cfg["attract_idle_s"]):
        kio.start_attract()
time.sleep(0.1); loop_idle()
check(kio.mode == "launcher", "no attract before idle time")
ev((3, K.ABS_Y, 255)); ev((3, K.ABS_Y, 127)); time.sleep(0.15); loop_idle()
check(kio.mode == "launcher", "stick movement resets idle timer")
time.sleep(0.1); loop_idle()
check(kio.mode == "attract" and cmds[-1].startswith("load_core") and "Galaga" not in cmds[-1], "attract starts a horizontal game: %s" % cmds[-1][-25:])
first = cmds[-1]
newcore("bombjack"); step(0.05)
check(kio.attract_seen_core, "attract game running")
time.sleep(0.3); step(0.0)
check(kio.mode == "attract" and cmds[-1] != "load_core " + K.MENU_RBF and cmds[-1].endswith(".mra"), "next demo loads directly, no menu: %s" % cmds[-1][-25:])
n = len(p1.virtual.out)
ev((3, K.ABS_X, 0))
check(kio.mode == "returning" and cmds[-1] == "load_core " + K.MENU_RBF, "stick movement ends attract")
check(len(p1.virtual.out) == n, "attract input not passed to the game")
ev((3, K.ABS_X, 127)); newcore("MENU"); step(0.05)
check(kio.mode == "launcher", "back on game list after attract")
kio.cfg["attract_mute"] = "1"; kio.start_attract()
check("volume mute" in cmds, "attract mutes when set")
ev((1, K.KEY_NAMES["BTN_TRIGGER"], 1))
check(cmds[-2:] == ["volume unmute", "load_core " + K.MENU_RBF], "button ends attract and unmutes")
ev((1, K.KEY_NAMES["BTN_TRIGGER"], 0)); newcore("MENU"); step(0.05)
check(kio.mode == "launcher", "button release after attract does not launch a game")
kio.cfg["attract_mute"] = "0"; kio.start_attract(); c0 = cmds[-1]
newcore("MENU"); step(0.0)
check(kio.mode == "attract" and cmds[-1].endswith(".mra"), "attract game that fails to load is skipped")
print("\n%d failure(s)" % fails)
