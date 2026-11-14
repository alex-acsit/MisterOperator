import sys, time, os
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
import monitor_test as M
T = sys.argv[2]
SHOTS = os.environ.get("SHOTS")            # set to a folder to keep screenshots
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"; K.VOLUME_PATH = T + "/vol"
K.SUITE_MGL = T + "/suite.mgl"
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("exit_grace_s", "0"), ("operator_hold_ms", "1500")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
cmds = []; core = {"name": "MENU", "stamp": 1}
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.core_name = lambda: core["name"]; K.core_stamp = lambda: core["stamp"]; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
presented = []
def fake_activate(self):
    self.fb = type("F", (), {"present": lambda s, c: presented.append(bytes(c.buf)), "clear": lambda s: None,
                             "close": lambda s: None, "xres": 320, "yres": 240, "fmt": K.PixelFormat()})()
    self.make_canvases(); return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
class FakeVirt:
    def __init__(s): s.out = []
    def emit(s, t, c, v, sync=False): s.out.append((t, c, v))
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s, path="/dev/input/event1", name="Encoder P1"):
        s.path, s.name, s.vendor, s.product, s.phys = path, name, 0xd209, 0x0501, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}
        s.keys = [0x120, 0x121, 0x122, 0x123, 0x124, 0x125, 0x129, 0x12a, 0x12b]
k = K.Kiosk(); d = FakeDev(); d2 = FakeDev("/dev/input/event2", "Encoder P2")
k.devices = {d.path: d, d2.path: d2}
def ev(dev, t, c, v): k.handle_events(dev, [(t, c, v)])
def press(c, dev=d): ev(dev, 1, c, 1); ev(dev, 1, c, 0)
def goto(label):
    k.opview.sel = [i for i, it in enumerate(k.opview.items()) if it[0] == label][0]
def stick(axis, v): ev(d, 3, axis, v); ev(d, 3, axis, 127)
def shot(name):
    if SHOTS:
        k.need_redraw = True; k.draw(); k.canvas.save_ppm(os.path.join(SHOTS, name + ".ppm"))

k.poll_core(time.monotonic())
k.set_locked(False); check(k.mode == "operator", "operator menu open")
labels = [it[0] for it in k.opview.items()]
check({"MONITOR TEST", "INPUT TEST", "240P TEST SUITE"} <= set(labels), "test items in the menu")

# ---- monitor test
goto("MONITOR TEST"); row = k.opview.sel
press(0x120); check(k.opview.page == "patterns", "button 1 opens the monitor test")
k.draw(); check(presented and len(set(presented[-1][i:i + 4] for i in range(0, 320 * 4 * 20, 4))) > 1,
                "drew a pattern on the screen")
stick(K.ABS_X, 255); check(k.opview.patterns.idx == 1, "right: next pattern")
stick(K.ABS_X, 0); stick(K.ABS_X, 0); check(k.opview.patterns.idx == len(M.PATTERNS) - 1, "left wraps round")
press(0x120); check(k.opview.patterns.idx == 0, "button 1: next pattern")
stick(K.ABS_Y, 0); check(k.opview.patterns.variant == 1, "up: next variant")
# every pattern and variant draws without error at YOKO and TATE sizes
ok = True
for w, h in ((320, 240), (240, 320), (640, 480)):
    c = K.Canvas(w, h, K.PixelFormat())
    for i, (name, fn, n) in enumerate(M.PATTERNS):
        for v in range(n):
            try:
                title = fn(c, v); assert title
            except Exception as e:
                ok = False; print("  %s v%d at %dx%d: %r" % (name, v, w, h, e))
check(ok, "all %d patterns draw at every size" % sum(p[2] for p in M.PATTERNS))
if SHOTS:
    for i, (name, fn, n) in enumerate(M.PATTERNS):
        for v in range(n):
            k.opview.patterns.idx, k.opview.patterns.variant = i, v
            k.opview.patterns.label_until = time.monotonic() + (10 if v == 0 else -1)
            shot("pattern_%d_%d" % (i, v))
# operator timeout stretched while a pattern is up
K.set_config_value("operator_timeout_s", "60"); k.cfg["operator_timeout_s"] = "60"
k.op_activity = time.monotonic() - 120
now = time.monotonic()
timeout = float(k.cfg["operator_timeout_s"])
if k.opview.page == "patterns":
    timeout = max(timeout, 1800)
check(now - k.op_activity < timeout, "no auto-lock while adjusting the monitor")
k.op_activity = time.monotonic()
press(0x121); check(k.opview.page == "main" and k.opview.sel == row, "button 2 back to the menu, on the same row")

# TATE: the pattern stays on the raster, the label is turned
K.set_config_value("screen", "tate_cw"); k.cfg["screen"] = "tate_cw"; k.make_canvases()
goto("MONITOR TEST"); press(0x120)
k.draw(); check(k.canvas.w == 320 and k.opview.patterns.rotation == 90, "TATE: drawn on the 320x240 raster")
shot("pattern_tate")
# tap OPERATOR leaves the test (short press, under the hold time)
ev(d, 1, K.parse_code("BTN_BASE5"), 1); ev(d, 1, K.parse_code("BTN_BASE5"), 0)
check(k.opview.page == "main" and k.state["locked"] is False, "a tap of OPERATOR leaves the test, still unlocked")
K.set_config_value("screen", "yoko"); k.cfg["screen"] = "yoko"; k.make_canvases()

# ---- input test
goto("INPUT TEST"); press(0x120); check(k.opview.page == "inputs", "input test opens")
ev(d, 1, 0x120, 1); check(0x120 in k.opview.inputs.seen[d.path], "button press is recorded")
check(k.opview.page == "inputs", "button 1 doesn't do anything else here")
ev(d, 1, 0x120, 0)
for c in (0x121, 0x122, 0x123, 0x124, 0x125):
    press(c)
press(K.parse_code("BTN_BASE4"))
check(k.opview.page == "inputs" and k.mode == "operator", "MENU and button 2 are tested, not acted on")
check(k.opview.inputs.role(d, K.parse_code("BTN_BASE4")) == "MENU", "MENU button named as such")
ev(d2, 1, 0x12b, 1); check(k.opview.inputs.role(d2, 0x12b) == "" and k.opview.inputs.seen[d2.path] == [0x12b],
                         "second controller tested too; unassigned buttons go by their code")
ev(d, 3, K.ABS_X, 255); ev(d, 3, K.ABS_Y, 0)
check(M.stick_direction(d) == (1, -1), "stick up-right shown")
ev(d, 1, 0x120, 1)
shot("input_test")
ev(d, 1, 0x120, 0); ev(d2, 1, 0x12b, 0)
ev(d, 3, K.ABS_X, 127); ev(d, 3, K.ABS_Y, 127)
# hold a button 3 s to leave
ev(d, 1, 0x123, 1)
k.opview.inputs.held[(d.path, 0x123)] = time.monotonic() - 1.5
k.opview.tick(time.monotonic()); check(k.opview.page == "inputs", "1.5 s: still testing (counting down)")
k.opview.inputs.held[(d.path, 0x123)] = time.monotonic() - 3.1
k.opview.tick(time.monotonic()); check(k.opview.page == "main", "held 3 s: back to the menu")
ev(d, 1, 0x123, 0)
check(k.mode == "operator", "and still in the operator menu")

# ---- 240p Test Suite lookup and launch
fat = T + "/fat"
os.makedirs(fat + "/_Console"); os.makedirs(fat + "/games/MegaDrive/Tools")
check(M.find_test_suite("", None, fat) is None, "nothing there: not found")
check(k.opview.suite_text() == "NOT FOUND", "menu says NOT FOUND")
open(fat + "/_Console/MegaDrive_20240101.rbf", "w").close()
open(fat + "/games/MegaDrive/Tools/240pSuite-1.23.bin", "w").close()
info = M.find_test_suite("", None, fat)
check(info and info["rbf"] == "_Console/MegaDrive" and info["index"] == 1 and info["rom"].endswith("240pSuite-1.23.bin"),
      "finds the Mega Drive suite, slot 1: %s" % info)
mgl = M.suite_mgl(info)
check('<rbf>_Console/MegaDrive</rbf>' in mgl and 'index="1"' in mgl and 'path="%s"' % info["rom"] in mgl, "MGL is right")
os.makedirs(fat + "/games/NES"); open(fat + "/_Console/NES_20240101.rbf", "w").close()
open(fat + "/games/NES/240pee.nes", "w").close()
os.remove(fat + "/games/MegaDrive/Tools/240pSuite-1.23.bin")
info2 = M.find_test_suite("", None, fat)
check(info2 and info2["system"] == "NES" and info2["index"] == 0, "falls back to NES, slot 0")
check(M.find_test_suite("games/NES/240pee.nes", None, fat)["system"] == "NES", "test_suite = a ROM path")
open(fat + "/my.mgl", "w").write("<mistergamedescription/>")
check(M.find_test_suite(fat + "/my.mgl", None, fat) == {"system": "MGL", "mgl": fat + "/my.mgl"}, "test_suite = an .mgl")
check(M.find_test_suite(fat + "/missing.mgl", None, fat) is None, "missing .mgl: not found")

k.opview._suite = info
goto("240P TEST SUITE"); check(k.opview.suite_text() == "MEGA DRIVE >", "menu shows the system")
cmds.clear(); press(0x120)
check(cmds and cmds[-1] == "load_core " + K.SUITE_MGL and open(K.SUITE_MGL).read() == mgl, "launches the suite's MGL")
check(k.mode == K.S_UNLOCKED and k.opview is None and not os.path.exists(K.KIOSK_FLAG), "runs unlocked, MiSTer menu allowed")
# hold OPERATOR comes back to the operator menu
core["name"] = "MegaDrive"; core["stamp"] += 1; k.poll_core(time.monotonic())
k.op_down_at = time.monotonic() - 2; k.op_fired = False
if k.op_down_at and not k.op_fired:
    k.op_fired = True
    if not k.state["locked"] and k.mode in (K.S_UNLOCKED, K.S_RETURNING) and K.flag(k.cfg, "operator_menu"):
        k.open_operator()
core["name"] = "MENU"; core["stamp"] += 1
for _ in range(3):
    k.poll_core(time.monotonic())
check(k.mode == "operator", "holding OPERATOR returns to the operator menu")
print("%d failure(s)" % fails)
