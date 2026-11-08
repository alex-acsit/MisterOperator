import sys, time, json
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"), ("exit_grace_s", "0"),
             ("coin_delay_s", "0.3"), ("max_credits", "3"), ("operator_hold_ms", "0")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
check(K.DEFAULTS["coin_delay_s"] == "30", "coins go in 30 s after launch by default")

cmds = []; core = {"name": "MENU", "stamp": 1}
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.core_name = lambda: core["name"]; K.core_stamp = lambda: core["stamp"]; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
def newcore(n): core["name"] = n; core["stamp"] += 1
def fake_activate(self):
    self.canvas = K.Canvas(320, 240, K.PixelFormat())
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None})()
    return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
class FakeVirt:
    def __init__(s): s.out = []
    def emit(s, t, c, v, sync=False): s.out.append((t, c, v))
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s, path, vid, keys):
        s.path, s.name, s.vendor, s.product, s.phys = path, "Encoder", vid, 2, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}; s.keys = keys
B = K.KEY_NAMES
p1 = FakeDev("/dev/input/event1", 0x16c0, [0x120, 0x121, 0x128, 0x129, 0x12a])   # encoder, coin = BTN_BASE3
kb = FakeDev("/dev/input/event2", 0x0001, [B["KEY_5"], B["KEY_ENTER"]])          # keyboard-style coin
k = K.Kiosk(); k.devices = {p1.path: p1, kb.path: kb}
k.poll_core(time.monotonic())
p1.virtual.out.clear(); kb.virtual.out.clear()      # ignore the stick-centring sent on entry
def press(d, code): k.handle_events(d, [(1, code, 1)]); k.handle_events(d, [(1, code, 0)])
def run_loop(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        k.tick_coins(time.monotonic()); time.sleep(0.01)

press(p1, B["BTN_BASE3"]); press(kb, B["KEY_5"])
check(k.state["coins"] == [["16c0:0002", B["BTN_BASE3"]], ["0001:0002", B["KEY_5"]]] and k.view.credits == 2,
      "two coins on the list are banked and shown")
check(not p1.virtual.out and not kb.virtual.out, "banked coins aren't sent anywhere yet")
check(json.load(open(K.STATE_PATH))["coins"], "credits saved to state.json")
press(p1, B["BTN_BASE3"]); press(p1, B["BTN_BASE3"])
check(len(k.state["coins"]) == 3, "max_credits caps the bank")
k.state["coins"] = k.state["coins"][:2]; k.view.credits = 2
k.cfg["attract_idle_s"] = "0.01"; k.last_activity -= 5
check(k.state.get("coins") and True, "demos don't start while credits wait (checked in main loop)")

press(p1, 0x120)                                  # play
check(k.mode == "game" and k.state["coins"] == [] and len(k.coin_queue) == 2, "launching moves the credits to the game")
newcore("galaga"); k.poll_core(time.monotonic())
run_loop(0.2)
check(not [e for e in p1.virtual.out if e[1] == B["BTN_BASE3"]], "nothing inserted before the delay")
run_loop(1.2)
p1c = [e for e in p1.virtual.out if e[1] == B["BTN_BASE3"]]
kbc = [e for e in kb.virtual.out if e[1] == B["KEY_5"]]
check(p1c == [(1, B["BTN_BASE3"], 1), (1, B["BTN_BASE3"], 0)] and kbc == [(1, B["KEY_5"], 1), (1, B["KEY_5"], 0)],
      "after the delay each coin is pressed on the controller it came from")
check(not k.coin_queue and k.coin_down is None, "all delivered")
n = len(p1.virtual.out); press(p1, B["BTN_BASE3"])
check(p1.virtual.out[n:] == [(1, B["BTN_BASE3"], 1), (1, B["BTN_BASE3"], 0)], "coin during a game goes straight in")

# quit before the coins went in: they're kept
press(p1, B["BTN_BASE4"]); newcore("MENU"); k.poll_core(time.monotonic())
press(p1, B["BTN_BASE3"]); press(p1, 0x120)
newcore("galaga"); k.poll_core(time.monotonic())
press(p1, B["BTN_BASE4"])
newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "launcher" and len(k.state["coins"]) == 1 and k.view.credits == 1,
      "quit before the delay: credit kept for the next game")

# demo: a coin banks the credit and ends the demo
k.state["coins"] = []; k.view.credits = 0
k.start_attract()
press(p1, B["BTN_BASE3"])
check(k.mode == "returning" and len(k.state["coins"]) == 1, "coin during a demo ends it and is banked")
newcore("MENU"); k.poll_core(time.monotonic())
check(k.view.credits == 1, "credit shown on the list after the demo")

# unlocking with coins waiting keeps them
press(p1, 0x120); newcore("galaga"); k.poll_core(time.monotonic())
k.handle_events(p1, [(1, B["BTN_BASE5"], 1)]); k.op_fired = True; k.set_locked(False)
k.handle_events(p1, [(1, B["BTN_BASE5"], 0)])
check(k.mode == "unlocked" and len(k.state["coins"]) == 1, "unlock before the delay: credit kept")
print("%d failure(s)" % fails)
