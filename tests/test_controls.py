import sys, time, os, struct
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
SHOTS = os.environ.get("SHOTS")
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"; K.VOLUME_PATH = T + "/vol"
INPUTS = T + "/inputs"; os.makedirs(INPUTS)
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("exit_grace_s", "0"), ("operator_hold_ms", "1500"), ("inputs_dir", INPUTS),
             ("map_backup_dir", T + "/map_backup")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
cmds = []; core = {"name": "MENU", "stamp": 1}
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.core_name = lambda: core["name"]; K.core_stamp = lambda: core["stamp"]; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
def fake_activate(self):
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None,
                             "close": lambda s: None, "xres": 320, "yres": 240, "fmt": K.PixelFormat()})()
    self.make_canvases(); return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
class FakeVirt:
    def emit(s, t, c, v, sync=False): pass
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s, path, name, vid, pid):
        s.path, s.name, s.vendor, s.product, s.phys = path, name, vid, pid, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}
        s.keys = []
k = K.Kiosk()
pad = FakeDev("/dev/input/event1", "Arcade Stick", 0x0079, 0x0006)       # stick on axes, BTN_* buttons
kbd = FakeDev("/dev/input/event2", "I-PAC Keyboard", 0xd209, 0x0301)     # keyboard encoder
k.devices = {pad.path: pad, kbd.path: kbd}
def ev(dev, t, c, v): k.handle_events(dev, [(t, c, v)])
def press(c, dev=pad): ev(dev, 1, c, 1); ev(dev, 1, c, 0)
def axis(a, v, dev=pad): ev(dev, 3, a, v); ev(dev, 3, a, 127)
def op_tap(dev=pad): ev(dev, 1, K.parse_code("BTN_BASE5"), 1); ev(dev, 1, K.parse_code("BTN_BASE5"), 0)
def goto(label):
    k.opview.sel = [i for i, it in enumerate(k.opview.items()) if it[0] == label][0]
def shot(name):
    if SHOTS:
        k.need_redraw = True; k.draw(); k.canvas.save_ppm(os.path.join(SHOTS, name + ".ppm"))
def words(path):
    return list(struct.unpack("<38I", open(path, "rb").read()[:152]))

# an existing MiSTer mapping for the stick, with a menu button and extra v4 data
old = [0] * 38
old[K.PAD_SLOTS["A"]] = 0x999; old[23] = 0x12c          # SYS_BTN_MENU_FUNC kept
open(INPUTS + "/input_0079_0006_v4.map", "wb").write(struct.pack("<38I", *old) + b"EXTRA")
# a game map made earlier for this stick
open(INPUTS + "/galaga_input_0079_0006_v4.map", "wb").write(struct.pack("<38I", *([7] * 38)))

k.poll_core(time.monotonic()); k.set_locked(False)
check(k.mode == "operator", "operator menu open")
labels = [it[0] for it in k.opview.items()]
check("CONTROLLER SETUP" in labels and "240P TEST SUITE" not in labels, "CONTROLLER SETUP listed, 240p suite gone")
goto("CONTROLLER SETUP"); press(0x120)
check(k.opview.page == "controls", "wizard opens")
w = k.opview.wizard
check(w.prompt() == "PUSH THE STICK UP", "asks for UP first")
shot("wizard_start")
op_tap(); check(w.idx == 0 and "SKIP" in (w.msg or ""), "UP can't be skipped")
axis(K.ABS_Y, 0); check(w.assign["UP"] == K.axis_dir_code(K.ABS_Y, False) and w.idx == 1, "stick up recorded as Y-")
press(0x120, kbd); check(w.idx == 1 and "SAME" in (w.msg or ""), "other controller ignored")
ev(pad, 3, K.ABS_Y, 255)
ev(pad, 3, K.ABS_Y, 127)
check(w.assign.get("DOWN") == K.axis_dir_code(K.ABS_Y, True), "down recorded as Y+")
axis(K.ABS_X, 0); axis(K.ABS_X, 255)
check(w.prompt() == "PRESS BUTTON 1", "then BUTTON 1 (numbered, not B/A/R/Y/X/L)")
press(0x122); press(0x122)
check(w.assign["1"] == 0x122 and w.step() == "2" and "ALREADY" in (w.msg or ""), "button 1 recorded; same button again refused")
press(0x121); press(0x123); press(0x120)
shot("wizard_mid")
op_tap(); op_tap()                                          # skip 5 and 6
check(w.assign["5"] is None and w.assign["6"] is None and w.step() == "START", "buttons 5 and 6 skipped")
check(w.prompt() == "PRESS PLAYER START", "asks for player START")
press(0x129 + 0); check(w.step() == "START", "the MENU button isn't taken")  # 0x129 = BTN_BASE4 = MENU
check(k.opview.page == "main" and "CANCELLED" in (k.opview.toast or ""), "MENU cancels the wizard")
# again, all the way
goto("CONTROLLER SETUP"); press(0x120); w = k.opview.wizard
for a, v in ((K.ABS_Y, 0), (K.ABS_Y, 255), (K.ABS_X, 0), (K.ABS_X, 255)):
    axis(a, v)
for c in (0x122, 0x121, 0x123, 0x120, 0x124, 0x125):
    press(c)
press(0x12b); press(0x128)                                  # START, COIN
check(w.done, "all twelve steps done")
shot("wizard_done")
press(0x121); check(k.opview.page == "controls", "only button 1 or START saves")
press(0x122)
check(k.opview.page == "main" and "SAVED" in (k.opview.toast or ""), "button 1 saves")

m = open(INPUTS + "/input_0079_0006_v4.map", "rb").read()
mw = words(INPUTS + "/input_0079_0006_v4.map")
S = K.PAD_SLOTS
check(mw[S["UP"]] == K.KEY_EMU + 2 and mw[S["DOWN"]] == K.KEY_EMU + 3 and mw[S["LEFT"]] == K.KEY_EMU
      and mw[S["RIGHT"]] == K.KEY_EMU + 1, "stick directions in the map as the MiSTer codes axes")
check([mw[S[x]] for x in ("B", "A", "R", "Y", "X", "L")] == [0x122, 0x121, 0x123, 0x120, 0x124, 0x125],
      "buttons 1-6 stored in B,A,R,Y,X,L")
check(mw[S["START"]] == 0x12b and mw[S["SELECT"]] == 0x128, "START in Start, COIN in Select")
check(mw[23] == 0x12c and m.endswith(b"EXTRA"), "MiSTer menu button and the v4 extras kept")
check(os.path.exists(T + "/map_backup/input_0079_0006_v4.map"), "old map backed up")
gw = words(INPUTS + "/galaga_input_0079_0006_v4.map")
check(gw[:4] == mw[:4] and gw[4:] == [7] * 34, "existing game map gets the new directions only")

cfg = K.load_config()
check(cfg["panel_layout"] == "B,A,R,Y,X,L" and cfg["panel_start"] == "Start" and cfg["panel_coin"] == "Select",
      "panel_layout set to match")
lb = K.parse_code_list(cfg["launch_buttons"]); gb = K.parse_code_list(cfg["genre_buttons"])
check(0x122 in lb and 0x12b in lb and 0x122 not in gb and 0x121 in gb, "kiosk.ini: button 1 and START play, button 2 genre")
check(0x123 in K.parse_code_list(cfg["genre_back_buttons"]) and 0x120 in K.parse_code_list(cfg["letter_buttons"])
      and 0x120 not in lb, "button 3 genre back, button 4 letter (taken out of launch)")
check(0x128 in K.parse_code_list(cfg["coin_buttons"]), "COIN is a coin button")
check(cfg["dir_keys"] == "", "no extra direction keys for a stick on axes")
check(0x122 in k.launch_buttons and 0x120 in k.letter_buttons, "takes effect at once")

# a keyboard encoder with its P1 stick on unusual keys
goto("CONTROLLER SETUP"); press(0x122); w = k.opview.wizard
R, F, D, G = (K.parse_code(x) for x in ("KEY_R", "KEY_F", "KEY_D", "KEY_G"))
for c in (R, F, D, G):
    press(c, kbd)
for n in ("KEY_LEFTCTRL", "KEY_LEFTALT", "KEY_SPACE", "KEY_LEFTSHIFT", "KEY_Z", "KEY_X", "KEY_1", "KEY_5"):
    press(K.parse_code(n), kbd)
check(w.done and w.assign["UP"] == R, "keyboard encoder set up")
press(K.parse_code("KEY_1"), kbd)
check(os.path.exists(INPUTS + "/input_d209_0301_v4.map") and os.path.exists(T + "/map_backup/created.txt"),
      "new map file written (and noted for --restore-maps)")
cfg = K.load_config()
check(K.parse_dir_keys(cfg["dir_keys"]) == {R: ("y", -1), F: ("y", 1), D: ("x", -1), G: ("x", 1)},
      "dir_keys: %s" % cfg["dir_keys"])
check(k._direction_from(kbd, 1, R, 1) == ("y", -1), "and the list moves with those keys")
print("%d failure(s)" % fails)
