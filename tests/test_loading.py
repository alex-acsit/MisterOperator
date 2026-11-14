import sys, time
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("exit_grace_s", "0"), ("nvram_dir", T + "/nvram")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1

check(K.DEFAULTS["launch_timeout_s"] == "12" and K.DEFAULTS["launch_max_s"] == "120",
      "12 s to start loading, up to 120 s to finish")

# ---- main_loading() reads the MiSTer main program's arguments
args = {"v": ["/media/fat/MiSTer", "/media/fat/_Arcade/cores/blahm1d_wolfunit.rbf",
              "/media/fat/_Arcade/_Blahm1d/Ultimate Mortal Kombat 3 [blahm1d].mra"]}
real_cmdline = K.main_cmdline
K.main_cmdline = lambda: args["v"]
check(K.main_loading("/media/fat/_Arcade/_Blahm1d/Ultimate Mortal Kombat 3 [blahm1d].mra"),
      "main started for this game: loading")
check(not K.main_loading("/media/fat/_Arcade/Galaga.mra"), "main started for another game: not this one")
args["v"] = ["/media/fat/MiSTer"]
check(not K.main_loading("/media/fat/_Arcade/Galaga.mra"), "plain menu main: not loading")
args["v"] = None
check(not K.main_loading("/media/fat/_Arcade/Galaga.mra"), "no main program found: not loading")
check(real_cmdline() is None or isinstance(real_cmdline(), list), "main_cmdline() is safe off the MiSTer")

# ---- the kiosk waits for a slow load instead of giving up at 12 s
cmds = []; core = {"name": "MENU", "stamp": 1}; ready = {"v": True}
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.core_name = lambda: core["name"]; K.core_stamp = lambda: core["stamp"]; K.mister_ready = lambda: ready["v"]
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
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}
        s.keys = [0x120, 0x121, 0x129, 0x12a, K.KEY_NAMES["KEY_5"]]
def fake_activate(self):
    self.canvas = K.Canvas(320, 240, K.PixelFormat())
    self.fb = type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None})()
    return True
K.Kiosk.activate_framebuffer = fake_activate
K.Kiosk.scan_devices = lambda self: None
k = K.Kiosk(); d = FakeDev(); k.devices[d.path] = d
k.poll_core(time.monotonic())
check(k.mode == "launcher", "launcher up")
ev = lambda *e: k.handle_events(d, list(e))
games = {g["label"]: g for g in k.all_games()}
g = games["Galaga"]

def launch():
    k.view.select_path(g["path"]); ev((1, 0x120, 1)); ev((1, 0x120, 0))

args["v"] = ["/media/fat/MiSTer", "/media/fat/_Arcade/cores/galaga.rbf", g["path"]]
launch()
check(k.mode == "game", "game launched")
k.game_started -= 30                                   # 30 s in, ROMs still going in
k.poll_core(time.monotonic())
check(k.mode == "game" and "pending_toast" not in k.state, "30 s into a slow load: still waiting, no error")
check("still loading" in open(K.LOG_PATH).read(), "logged as still loading")
newcore("galaga"); k.poll_core(time.monotonic())
check(k.mode == "game" and k.game_seen_core, "the game comes up after the long load")
del cmds[:]; ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(cmds[-1:] == ["load_core " + K.MENU_RBF], "MENU quits it as normal")
newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "launcher", "back on the list")

# main never picked the game up: give up after launch_timeout_s as before
args["v"] = ["/media/fat/MiSTer"]
launch(); k.game_started -= 13
k.poll_core(time.monotonic()); k.poll_core(time.monotonic())
check(k.mode == "launcher" and "pending_toast" not in k.state and "COULD NOT START" in (k.view.toast or ""),
      "never started loading: back to the list after 12 s with COULD NOT START")

# a load that never finishes: give up at launch_max_s
args["v"] = ["/media/fat/MiSTer", "/media/fat/_Arcade/cores/galaga.rbf", g["path"]]
launch(); k.game_started -= 121
k.poll_core(time.monotonic()); k.poll_core(time.monotonic())
check(k.mode == "launcher", "still loading after launch_max_s: give up")

# ---- held credits go in coin_delay_s after the game is up, not after the launch
k.state["coins"] = [["16c0:05e1", K.KEY_NAMES["KEY_5"]]]
launch(); k.game_started -= 40                         # a 40 s load
n = len(d.virtual.out); k.tick_coins(time.monotonic())
check(len(d.virtual.out) == n, "no coin is sent while the game is still loading")
k.poll_core(time.monotonic())
newcore("galaga"); now = time.monotonic(); k.poll_core(now)
check(abs(k.coin_next - (now + 30)) < 1, "coin delay counted from when the game came up")
check(k.game_last_input >= now - 0.1, "idle timer starts when the game comes up")
k.coin_next = 0; k.tick_coins(time.monotonic())
check(d.virtual.out and d.virtual.out[-1][1] == K.KEY_NAMES["KEY_5"], "then the credit goes in")
k.release_coin(); del cmds[:]
ev((1, 0x129, 1)); ev((1, 0x129, 0)); newcore("MENU"); k.poll_core(time.monotonic())

# ---- MENU pressed while loading: the menu request is lost, so ask again
launch(); k.game_started -= 5
ready["v"] = False                                     # loading: nobody reads MiSTer_cmd
del cmds[:]; ev((1, 0x129, 1)); ev((1, 0x129, 0))
check(k.mode == "returning", "MENU during the load: returning")
newcore("galaga"); k.poll_core(time.monotonic())        # the game comes up anyway
check(k.mode == "returning" and cmds == ["load_core " + K.MENU_RBF], "first request sent once")
ready["v"] = True; k.return_at -= 6; k.poll_core(time.monotonic())
check(cmds[-1:] == ["load_core " + K.MENU_RBF] and len(cmds) == 2, "game still up after 5 s: menu asked for again")
newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "launcher", "and the list comes back")

# a normal quit isn't asked twice while the menu is on its way
launch(); newcore("galaga"); k.poll_core(time.monotonic())
del cmds[:]; ev((1, 0x129, 1)); ev((1, 0x129, 0))
ready["v"] = False; k.return_at -= 6; k.poll_core(time.monotonic())
check(cmds == ["load_core " + K.MENU_RBF], "main restarting for the menu: not asked again")
ready["v"] = True; newcore("MENU"); k.poll_core(time.monotonic())

# ---- attract: a slow demo isn't skipped, and gets its full time once it's up
k.state["coins"] = []
k.cfg["attract_list"] = ""
k.attract_pool = lambda: [g]
k.start_attract()
args["v"] = ["/media/fat/MiSTer", "/media/fat/_Arcade/cores/galaga.rbf", g["path"]]
k.attract_started -= 30; del cmds[:]
k.poll_core(time.monotonic())
check(k.mode == "attract" and not cmds, "slow demo load: waits")
newcore("galaga"); k.poll_core(time.monotonic())
check(k.attract_seen_core and not cmds, "demo up: shown for its full minute from now")
k.attract_shown -= 61; k.poll_core(time.monotonic())
check(cmds and cmds[-1].startswith("load_core"), "then on to the next demo")

# ---- NVRAM diagnostics in the log
import os
k.stop_attract(); newcore("MENU"); k.poll_core(time.monotonic())
check(k.mode == "launcher", "back on the list after the demo")
K.main_features = lambda: {"save_nvram", "nvram_trigger"}
nv = [x for x in k.all_games() if x.get("nvram")][0]
os.makedirs(K.load_config()["nvram_dir"], exist_ok=True)
k.cfg["nvram_dir"] = K.load_config()["nvram_dir"]
path = k.nvram_file(nv)
open(path, "wb").write(b"\0" * 64)
def cmd_writes(t, quiet=False):
    cmds.append(t)
    if t == "save_nvram":
        open(path, "wb").write(b"\1" * 64)
    return True
K.mister_cmd = cmd_writes
g = nv; args["v"] = ["/media/fat/MiSTer", "x.rbf", nv["path"]]
launch(); newcore("nba"); k.poll_core(time.monotonic())
logtxt = open(K.LOG_PATH).read()
check("factory default in .mra" in logtxt and "ALL ZERO" in logtxt, "launch logs the core, NVRAM layout and save file state")
ev((1, 0x129, 1)); ev((1, 0x129, 0))
check("written: 64 bytes" in open(K.LOG_PATH).read(), "save on quit: file written, logged")
newcore("MENU"); k.poll_core(time.monotonic())
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.main_features = lambda: {"save_nvram"}
launch(); newcore("nba"); k.poll_core(time.monotonic())
t0 = time.monotonic(); ev((1, 0x129, 1)); ev((1, 0x129, 0))
logtxt = open(K.LOG_PATH).read()
check("NOT written" in logtxt and "can't save cores that need their Save NVRAM item" in logtxt,
      "save on quit: file unchanged, logged with a hint for an old main program")
check(time.monotonic() - t0 < 2.5, "gives up waiting after 1.5 s")
newcore("MENU"); k.poll_core(time.monotonic())

print("%d failure(s)" % fails)
