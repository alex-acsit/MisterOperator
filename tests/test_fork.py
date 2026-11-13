import sys, time, os
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.MAIN_BIN = T + "/fat/MiSTer"; K.KIOSK_MAIN = T + "/kiosk/MiSTer_kiosk"; K.VOLUME_PATH = T + "/Volume.dat"
os.makedirs(T + "/fat"); open(K.MAIN_BIN, "wb").write(b"STOCK MAIN")
if os.path.exists(K.KIOSK_MAIN):
    os.remove(K.KIOSK_MAIN)           # the shipped binary; these tests bring their own
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
def fake_activate(self):
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None,
                             "xres": 320, "yres": 240, "fmt": K.PixelFormat()})()
    self.make_canvases(); return True
real_activate = K.Kiosk.activate_framebuffer
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
        s.keys = [0x120, 0x121, 0x129, 0x12a]
flag = lambda: os.path.exists(K.KIOSK_FLAG)
k = K.Kiosk(); k.keys_dev = Keys(); d = FakeDev(); k.devices = {d.path: d}
def ev(*e): k.handle_events(d, list(e))
def press(code): ev((1, code, 1)); ev((1, code, 0))
def hold_op():
    ev((1, 0x12a, 1)); k.op_fired = True
    if not k.state["locked"] and k.mode in ("unlocked", "returning"): k.open_operator()
    else: k.set_locked(not k.state["locked"])
    ev((1, 0x12a, 0))
def loop():
    k.poll_core(time.monotonic()); k.sync_flag()

loop()
check(k.mode == "launcher" and flag(), "kiosk owns the screen: flag file present")

# ---- stock main: NVRAM falls back to the F12 menu flash
check(k.main_status() == "STOCK", "no features file: stock MiSTer main")
nba = [g for g in k.all_games() if g["label"] == "NBA Jam TE"][0]
k.view.select_path(nba["path"]); press(0x120); newcore("nba"); loop()
del cmds[:]; press(0x129)
check(cmds[0] == "TAP KEY_F12", "stock main: NVRAM saved by opening the menu")
newcore("MENU"); loop()

# ---- kiosk main: save_nvram command, no flash, every time
open(K.FEATURES_PATH, "w").write("kiosk_active\nsave_nvram\nquiet_volume\n")
check(k.main_status() == "KIOSK", "features file: kiosk build detected")
for n in range(2):
    k.view.select_path(nba["path"]); press(0x120); newcore("nba"); loop()
    del cmds[:]; press(0x129)
    check(cmds == ["save_nvram", "load_core " + K.MENU_RBF] and not any("TAP" in c for c in cmds),
          "kiosk main: save_nvram command, no menu flash (quit %d)" % (n + 1))
    newcore("MENU"); loop()
k.cfg["save_nvram"] = "off"
k.view.select_path(nba["path"]); press(0x120); newcore("nba"); loop()
del cmds[:]; press(0x129)
check(cmds == ["load_core " + K.MENU_RBF], "save_nvram = off still respected")
k.cfg["save_nvram"] = "once"; newcore("MENU"); loop()

# ---- flag follows who owns the screen
hold_op(); loop()
check(k.mode == "operator" and flag(), "operator menu: flag stays (kiosk draws it)")
order = []
real_cmd = K.mister_cmd
K.mister_cmd = lambda t, quiet=False: order.append(("cmd", t, flag())) or True
k.operator_stock_menu()
check(order and order[-1] == ("cmd", "load_core " + K.MENU_RBF, False), "stock MiSTer menu: flag removed before the new main starts")
K.mister_cmd = real_cmd
newcore("MENU"); loop()
check(k.mode == "unlocked" and not flag(), "and stays off while the operator uses it")
hold_op(); newcore("MENU"); loop()
check(k.mode == "operator" and flag(), "back to the operator menu: flag back")
order = []; K.mister_cmd = lambda t, quiet=False: order.append(("cmd", t, flag())) or True
k.operator_game_settings(k.last_game())
check(order[-1][2] is False and k.mode == "unlocked", "game settings: flag removed before the game loads")
K.mister_cmd = real_cmd
hold_op(); newcore("MENU"); loop()
check(k.mode == "operator" and flag(), "operator again")

# ---- installing the kiosk build
os.remove(K.FEATURES_PATH)
if os.path.exists(K.KIOSK_MAIN):
    os.remove(K.KIOSK_MAIN)           # the shipped binary; this part starts without one
k.opview = K.OperatorView(k)
row = [it for it in k.opview.items() if it[0] == "MISTER MAIN"][0]
check(row[1]() == "STOCK" and row[3] is None, "no MiSTer_kiosk file: shows STOCK, nothing to install")
open(K.KIOSK_MAIN, "wb").write(b"KIOSK MAIN")
row = [it for it in k.opview.items() if it[0] == "MISTER MAIN"][0]
check(row[1]() == "STOCK: 1 INSTALLS" and row[3] is not None, "MiSTer_kiosk present: offers to install")
rebooted = []
K.os.system = lambda c: rebooted.append(c) or 0
k.opview.sel = [i for i, it in enumerate(k.opview.items()) if it[0] == "MISTER MAIN"][0]
press(0x120)
check(open(K.MAIN_BIN, "rb").read() == b"STOCK MAIN" and k.opview.confirm == "MISTER MAIN", "asks before installing")
press(0x120)
check(open(K.MAIN_BIN, "rb").read() == b"KIOSK MAIN" and open(K.MAIN_BIN + ".stock", "rb").read() == b"STOCK MAIN"
      and os.access(K.MAIN_BIN, os.X_OK) and rebooted, "installs it, keeps MiSTer.stock, reboots")
open(K.FEATURES_PATH, "w").write("kiosk_active\nsave_nvram\n")
row = [it for it in k.opview.items() if it[0] == "MISTER MAIN"][0]
check(row[1]() == "KIOSK" and row[3] is None, "after reboot: shows KIOSK")
open(K.KIOSK_MAIN, "wb").write(b"KIOSK MAIN v2")     # a newer kiosk build copied in
row = [it for it in k.opview.items() if it[0] == "MISTER MAIN"][0]
check(row[1]() == "OLD: 1 UPDATES" and row[3] is not None, "newer MiSTer_kiosk: offers an update")
k.state.pop("main_install_check", None); rebooted.clear()
k.opview.sel = [i for i, it in enumerate(k.opview.items()) if it[0] == "MISTER MAIN"][0]
press(0x120); press(0x120)
check(open(K.MAIN_BIN, "rb").read() == b"KIOSK MAIN v2" and open(K.MAIN_BIN + ".stock", "rb").read() == b"STOCK MAIN"
      and rebooted, "update installed; MiSTer.stock still the original stock program")
row = [it for it in k.opview.items() if it[0] == "MISTER MAIN"][0]
check(row[1]() == "KIOSK", "then shows KIOSK")

# ---- safety net: a main program that never starts is rolled back
check(k.state.get("main_install_check"), "install marks the next boot for checking")
K.mister_ready = lambda: False
rebooted.clear()
ok = k.check_new_main(wait=0.2)
check(not ok and open(K.MAIN_BIN, "rb").read() == b"STOCK MAIN" and rebooted and not k.state.get("main_install_check"),
      "new main never starts: MiSTer.stock restored and rebooted")
k.state["main_install_check"] = True; K.mister_ready = lambda: True; rebooted.clear()
check(k.check_new_main(wait=1) and not rebooted and not k.state.get("main_install_check"), "new main starts: check cleared")

# ---- boot flag on the SD card
K.KIOSK_BOOT_FLAG = T + "/fat/config/kiosk_boot"
K.set_boot_flag(True)
check(os.path.exists(K.KIOSK_BOOT_FLAG), "boot flag written (so the kiosk build skips its menu at power-on)")
K.set_boot_flag(True); K.set_boot_flag(False)
check(not os.path.exists(K.KIOSK_BOOT_FLAG), "and removed when the kiosk shouldn't own the boot")

# ---- the kiosk never leaves the MiSTer menu blocked
K.set_kiosk_flag(False)
check(not flag(), "flag can be cleared (done on exit)")
# ---- early kiosk build stuck on its menu at boot: the kiosk reloads the menu core
import threading
m = {"fb": False, "param": "8888 1 640 480 2560", "stamp": 1, "reloads": 0}
K.read_fb_param = lambda: m["param"].split()
K.write_fb_param = lambda v: m.__setitem__("param", " ".join(map(str, v)))
K.core_stamp = lambda: m["stamp"]
def cmd(t, quiet=False):
    if t.startswith("fb_cmd1") and m["fb"]:
        p = t.split(); m["param"] = "%s %s %s %s %d" % (p[1], p[2], p[3], p[4], int(p[3]) * 4)
    if t == "load_core " + K.MENU_RBF:      # new main process: flag present -> straight to fb
        m["reloads"] += 1; m["stamp"] += 1; m["fb"] = True
K.mister_cmd = cmd
class DeadF9:
    def tap(s, c): pass                     # the early build ignores F9 while the flag exists
K.Framebuffer = lambda: type("F", (), {"xres": 320, "yres": 240, "fmt": K.PixelFormat()})()
open(K.FEATURES_PATH, "w").write("kiosk_active\nsave_nvram\n"); K.set_kiosk_flag(True)
k3 = K.Kiosk.__new__(K.Kiosk); k3.cfg = dict(K.DEFAULTS); k3.keys_dev = DeadF9(); k3.own_nodes = set()
K.Kiosk.activate_framebuffer = real_activate
t0 = time.monotonic(); ok = k3.activate_framebuffer(timeout=8)
check(ok and m["reloads"] == 1 and m["param"].startswith("8888 1 320 240"),
      "menu stuck with F9 blocked: kiosk reloads the menu core once and takes over (%.1f s)" % (time.monotonic() - t0))
K.set_kiosk_flag(False)

print("%d failure(s)" % fails)
