import sys, time
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("menu_device", "16c0:05e1"), ("operator_device", "16c0:05e1"),
             ("exit_grace_s", "0"), ("nvram_save_s", "0.05"), ("operator_hold_ms", "0"),
             ("nvram_dir", T + "/nvram")):
    K.set_config_value(k, v)
K.set_config_value("operator_menu", "0")   # these tests cover the direct-to-stock-menu unlock
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1

games = {g["label"]: g for g in K.scan_games(K.load_config())}
check(games["NBA Jam TE"]["nvram"] and not games["Galaga"]["nvram"], "<nvram> in the .mra is detected")

log = []; core = {"name": "MENU", "stamp": 1}
K.mister_cmd = lambda t, quiet=False: log.append(t) or True
K.core_name = lambda: core["name"]; K.core_stamp = lambda: core["stamp"]; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
def newcore(n): core["name"] = n; core["stamp"] += 1
class Keys:
    def tap(s, c): log.append("TAP " + K.code_name(c))
    def close(s): pass
class FakeVirt:
    def __init__(s): s.out = []; s.name = "Encoder (clone)"
    def emit(s, t, c, v, sync=False): s.out.append((t, c, v))
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s, path="/dev/input/event1"):
        s.path, s.name, s.vendor, s.product, s.phys = path, "Encoder", 0x16c0, 0x05e1, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {}; s.keys = [0x120, 0x121, 0x129, 0x12a]
def fake_activate(self):
    self.canvas = K.Canvas(320, 240, K.PixelFormat())
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None})()
    return True
K.Kiosk.activate_framebuffer = fake_activate
real_scan = K.Kiosk.scan_devices
K.Kiosk.scan_devices = lambda self: None
k = K.Kiosk(); k.keys_dev = Keys(); d = FakeDev(); k.devices[d.path] = d
k.poll_core(time.monotonic())
ev = lambda *e: k.handle_events(d, list(e))
def tick():   # the operator-hold part of the main loop
    if k.op_down_at and not k.op_fired:
        k.op_fired = True; k.set_locked(not k.state["locked"])

def play(label):
    k.view.select_path(games[label]["path"]); ev((1, 0x120, 1)); ev((1, 0x120, 0))
    newcore("nba" if "NBA" in label else "galaga"); k.poll_core(time.monotonic())

play("NBA Jam TE")
del log[:]
ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(log == ["TAP KEY_F12", "TAP KEY_F12", "load_core " + K.MENU_RBF], "MENU on an NVRAM game: open MiSTer menu (saves), then quit: %s" % log)
newcore("MENU"); k.poll_core(time.monotonic())

play("Galaga"); del log[:]
ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(log == ["load_core " + K.MENU_RBF], "game without NVRAM quits straight away")
newcore("MENU"); k.poll_core(time.monotonic())

play("NBA Jam TE"); del log[:]
k.cfg["game_idle_exit_s"] = "0.01"; time.sleep(0.02)
now = time.monotonic()
if now - k.game_last_input >= 0.01: k.exit_game("no input")
check(log == ["TAP KEY_F12", "TAP KEY_F12", "load_core " + K.MENU_RBF], "idle exit also saves NVRAM")
k.cfg["game_idle_exit_s"] = "0"; newcore("MENU"); k.poll_core(time.monotonic())

play("NBA Jam TE"); del log[:]
ev((1, 0x12a, 1)); tick(); ev((1, 0x12a, 0))
check(k.mode == "unlocked" and log == ["TAP KEY_F12", "TAP KEY_F12", "load_core " + K.MENU_RBF],
      "OPERATOR during a game: saves NVRAM and goes to the stock MiSTer menu: %s" % log)
n = len(d.virtual.out); ev((1, 0x129, 1))
check(d.virtual.out[n:] == [(1, 0x129, 1)], "unlocked: MENU reaches the MiSTer (opens its menu)")
ev((1, 0x129, 0))
newcore("MENU"); del log[:]
ev((1, 0x12a, 1)); tick(); ev((1, 0x12a, 0))
check(k.state["locked"] and log == ["load_core " + K.MENU_RBF], "OPERATOR again locks")
newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "launcher", "back to the list")
# once (default): keeps saving until a save after a long enough game, then stops
import os
os.makedirs(T + "/nvram", exist_ok=True)
open(T + "/nvram/NBA Jam TE (rev 4.0 03-23-94).nvm", "wb").write(b"x")
check(k.nvram_mode() == "once", "default mode is once")
play("NBA Jam TE"); k.game_started -= 120; del log[:]
ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(log[0] == "TAP KEY_F12" and games["NBA Jam TE"]["path"] in k.state["nvram_good"], "long game: saved and marked good")
newcore("MENU"); k.poll_core(time.monotonic())
play("NBA Jam TE"); del log[:]
ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(log == ["load_core " + K.MENU_RBF], "once: no menu flash after a good save")
newcore("MENU"); k.poll_core(time.monotonic())
os.remove(T + "/nvram/NBA Jam TE (rev 4.0 03-23-94).nvm")
play("NBA Jam TE"); del log[:]
ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(log[0] == "TAP KEY_F12", "once: saves again if the .nvm file is gone")
newcore("MENU"); k.poll_core(time.monotonic())
k.cfg["save_nvram"] = "always"; play("NBA Jam TE"); k.game_started -= 120; del log[:]
ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(log[0] == "TAP KEY_F12", "always: saves every time")
newcore("MENU"); k.poll_core(time.monotonic())
k.cfg["save_nvram"] = "1"
check(k.nvram_mode() == "once", "save_nvram = 1 (v1.6 setting) means once")
k.cfg["save_nvram"] = "0"; play("NBA Jam TE"); del log[:]
ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(log == ["load_core " + K.MENU_RBF], "save_nvram = 0 turns it off")
newcore("MENU"); k.poll_core(time.monotonic())

# ---- grabbing: a controller the MiSTer holds is not cloned, and losing the
# MENU/OPERATOR controller mid-game sends the kiosk back to the list.
K.Kiosk.scan_devices = real_scan
class Busy(FakeDev):
    def __init__(s, path):
        FakeDev.__init__(s, path); s.grabbed = False; s.virtual = None; s.ev = [K.EV_KEY]; s.rel = []
        s.msc = []; s.abs = []; s.bustype = 3; s.version = 1
    def try_grab(s): return False
made = []
K.os.listdir = (lambda real: (lambda p: ["event1", "event5"] if p == "/dev/input" else real(p)))(K.os.listdir)
K.PhysicalDevice = Busy
K.VirtualDevice = lambda *a, **kw: made.append(a) or FakeVirt()
real_close = K.os.close
K.os.close = lambda fd: None if fd == -1 else real_close(fd)
play("Galaga")
k.scan_devices()
check("/dev/input/event5" in k.ungrabbed and "/dev/input/event5" not in k.devices and not made,
      "controller held by the MiSTer: not cloned, waiting for it")
check(k.ungrabbed["/dev/input/event5"][1], "it's recognised as the MENU/OPERATOR controller")
k.ungrabbed["/dev/input/event5"] = (time.monotonic() - 5, True)
now = time.monotonic()
lost = [p for p, (t0, ctl) in k.ungrabbed.items() if ctl and now - t0 > 3]
if lost and k.mode in ("game", "attract") and k.state["locked"]: k.go_menu()
check(k.mode == "returning" and log[-1] == "load_core " + K.MENU_RBF, "lost controller mid-game: back to the list")
print("%d failure(s)" % fails)
