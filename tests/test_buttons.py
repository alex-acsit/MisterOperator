import sys, time
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
for k, v in (("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
cfg = K.load_config()
check(cfg["attract_idle_s"] == "120" and K.DEFAULTS["attract_idle_s"] == "120", "attract mode starts after 2 minutes by default")

cmds = []
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.core_name = lambda: "MENU"; K.core_stamp = lambda: 1; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
def fake_activate(self):
    self.canvas = K.Canvas(320, 240, K.PixelFormat())
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None})()
    return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
K.scan_games = lambda cfg, use_cache=True: K.demo_games()
class FakeDev(K.PhysicalDevice):
    def __init__(s):
        s.path, s.name, s.vendor, s.product, s.phys = "/dev/input/event1", "Encoder", 1, 2, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = None; s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}
k = K.Kiosk(); d = FakeDev(); k.devices[d.path] = d
k.poll_core(time.monotonic())
check(k.mode == "launcher", "launcher up")
v = k.view
def press(code): k.handle_events(d, [(1, code, 1)]); k.handle_events(d, [(1, code, 0)])
def stick(axis, val): k.handle_events(d, [(3, axis, val)]); k.handle_events(d, [(3, axis, 127)])
B = K.KEY_NAMES

# genres forward and back
names = v.genres
press(B["BTN_THUMB"]); check(v.genre_idx == 1, "button 2: next genre (%s)" % names[1])
press(B["BTN_THUMB2"]); check(v.genre_idx == 0, "button 3: previous genre")
press(B["BTN_THUMB2"]); check(v.genre_idx == len(names) - 1, "previous from All Games wraps to the last genre (%s)" % names[-1])
press(B["KEY_SPACE"]); check(v.genre_idx == len(names) - 2, "keyboard: space = previous genre")
press(B["BTN_THUMB"]); press(B["BTN_THUMB"]); check(v.genre_idx == 0, "and next wraps back to All Games")

# letter picker
press(B["BTN_TOP"])
check(v.picker is not None and v.picker_letters()[v.picker] == "#", "button 4 opens the picker on the current letter (#)")
check(v.picker_letters()[:3] == ["#", "B", "C"] and "A" not in v.picker_letters(), "picker only offers letters that have games")
stick(K.ABS_X, 255); stick(K.ABS_X, 255)
check(v.picker_letters()[v.picker] == "C" and v.current()["label"] == "Centipede", "stick moves the letter; list follows")
stick(K.ABS_Y, 0)
check(v.current()["label"] == "Bomb Jack", "up goes back a letter (first B game)")
stick(K.ABS_X, 0); stick(K.ABS_X, 0)
check(v.picker_letters()[v.picker] == "X", "left from # wraps round to the last letter (X)")
del cmds[:]
press(B["BTN_TRIGGER"])
check(v.picker is None and k.mode == "launcher" and not cmds and v.current()["label"] == "Xevious",
      "button 1 closes the picker on Xevious without launching")
press(B["BTN_TRIGGER"])
check(k.mode == "game" and cmds[-1].endswith("Xevious (Namco).mra"), "next press of 1 plays it")
K.core_name = lambda: "MENU"
k.mode = "returning"; k.await_stamp = None; k.poll_core(time.monotonic())
v = k.view
press(B["KEY_LEFTSHIFT"]); check(v.picker is not None, "keyboard: left shift opens the picker")
v.picker_until = time.monotonic() - 1
now = time.monotonic()
if v.picker is not None and now > v.picker_until: v.close_picker()
check(v.picker is None, "picker closes by itself after a few seconds")
stick(K.ABS_X, 0)
check(v.current()["label"] == "Tetris", "left/right without the picker still jump a letter at a time")

# footer hints
c = K.Canvas(320, 240, K.PixelFormat())
one = K.LauncherView(dict(cfg), [g for g in K.demo_games() if g["genre"] == "Maze"])
one.draw(c)
check(one.genres == ["Maze"], "locked to one genre")
import io
hint_line = lambda view: " ".join(h for h in ((view.cfg["footer_genre"] if len(view.genres) > 1 else ""), view.cfg["footer_letter"]) if h.strip())
check(hint_line(one) == "4:A-Z" and hint_line(v) == "2/3:GENRE 4:A-Z", "footer hints drop GENRE when locked to one genre")
print("%d failure(s)" % fails)
