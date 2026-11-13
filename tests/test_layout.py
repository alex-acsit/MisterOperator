import os, struct, sys, time, subprocess
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"
INP = T + "/inputs"; os.makedirs(INP)
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("menu_device", "16c0:05e1"), ("operator_device", "16c0:05e1"), ("exit_grace_s", "0"),
             ("operator_hold_ms", "0"), ("inputs_dir", INP), ("map_backup_dir", T + "/backup")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1

# The encoder as mapped in the MiSTer menu: 1=B 2=A 3=R / 4=Y 5=X 6=L, Coin=Select, Start=Start.
CODE = {"B": 0x120, "A": 0x121, "R": 0x122, "Y": 0x123, "X": 0x124, "L": 0x125,
        "SELECT": 0x128, "START": 0x129}
PANEL = [CODE[n] for n in "B A R Y X L".split()]          # panel 1..6
mmap = [0] * 38
mmap[0:4] = [0x223, 0x222, 0x221, 0x220]                  # d-pad codes
for n, c in CODE.items(): mmap[K.PAD_SLOTS[n]] = c
mmap[28], mmap[29] = 0, 1                                 # stick on ABS_X / ABS_Y
open(INP + "/input_16c0_05e1_v4.map", "wb").write(struct.pack("<38I", *mmap))

def readmap(name):
    return list(struct.unpack("<38I", open(INP + "/" + name, "rb").read()))

cfg = K.load_config()
games = {g["label"]: g for g in K.scan_games(cfg, use_cache=False)}
sf2 = games["Street Fighter II"]
check(sf2["buttons"].startswith("Jab,Strong"), "button names read from the .mra")

# An earlier map from the MiSTer OSD, to check it is backed up and its directions kept.
old = [0] * 38; old[0:4] = [1, 2, 3, 4]; old[4] = 0x999
open(INP + "/sf2_input_16c0_05e1_v4.map", "wb").write(struct.pack("<38I", *old))

n = K.write_game_maps(cfg, sf2, [(0x16c0, 0x05e1)])
m = readmap("sf2_input_16c0_05e1_v4.map")
check(n == 2 and m[4:10] == PANEL, "6-button game: panel 1-6 in order: %s" % [hex(x) for x in m[4:10]])
check(m[10] == CODE["START"] and m[11] == CODE["SELECT"], "Start and Coin kept")
check(m[12] == 0 and m[13] == 0, "Core credits and Pause removed")
check(m[0:4] == [1, 2, 3, 4], "directions from the earlier map kept")
check(readmap("sf2_input_16c0_05e1_v3.map") == m, "v3 copy written for older MiSTer builds")
check(os.path.exists(T + "/backup/sf2_input_16c0_05e1_v4.map"), "earlier map backed up")

K.write_game_maps(cfg, games["Four Button"], [(0x16c0, 0x05e1)])
m = readmap("fourbtn_input_16c0_05e1_v4.map")
check(m[4:8] == [PANEL[3], PANEL[0], PANEL[1], PANEL[2]],
      "4-button game: game 1 on panel 4, game 2-4 on panel 1-3")
check(m[8] == CODE["START"] and m[9] == CODE["SELECT"] and m[10] == 0 and m[11] == 0,
      "4-button: Start/Coin kept, Pause/Service removed")
check(m[2] == (0x221 | ((K.KEY_EMU + 3) << 16)) and m[3] == (0x220 | ((K.KEY_EMU + 2) << 16)),
      "no earlier map: directions built from the menu mapping (d-pad + stick)")

K.write_game_maps(cfg, games["Two Button"], [(0x16c0, 0x05e1)])
m = readmap("twobtn_input_16c0_05e1_v4.map")
check(m[4:6] == PANEL[:2], "2-button game: panel 1-2")
check(m[6] == CODE["START"] and m[7] == 0 and m[8] == CODE["SELECT"] and m[9] == 0 and m[10] == 0,
      "P1 Start mapped, P2 Start / Test / Tilt left off")

K.write_game_maps(cfg, games["Eight Button"], [(0x16c0, 0x05e1)])
m = readmap("eightbtn_input_16c0_05e1_v4.map")
check(m[4:10] == PANEL and m[10] == 0 and m[11] == 0, "8-button game: 1-6 mapped, 7-8 off")

check(K.write_game_maps(cfg, sf2, [(0x16c0, 0x05e1)]) == 0, "unchanged map is not rewritten")

# Launching through the kiosk writes the map.
os.unlink(INP + "/twobtn_input_16c0_05e1_v4.map")
K.mister_cmd = lambda t, quiet=False: True
K.core_name = lambda: "MENU"; K.core_stamp = lambda: 1; K.mister_ready = lambda: True
K.set_tty_mode = lambda m: None
K.Kiosk.activate_framebuffer = lambda self: (setattr(self, "canvas", K.Canvas(320, 240, K.PixelFormat())) or
    setattr(self, "fb", type("F", (), {"present": lambda s, c: None, "clear": lambda s: None, "close": lambda s: None})()) or True)
K.Kiosk.scan_devices = lambda self: None
class D(K.PhysicalDevice):
    def __init__(s):
        s.path, s.name, s.vendor, s.product, s.phys = "/dev/input/event1", "Encoder", 0x16c0, 0x05e1, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = type("V", (), {"emit": lambda *a, **k: None, "close": lambda s: None})(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {}; s.keys = [0x120, 0x121]
d = D()
k = K.Kiosk(); k.devices[d.path] = d; k.poll_core(time.monotonic())
k.launch(games["Two Button"])
check(os.path.exists(INP + "/twobtn_input_16c0_05e1_v4.map"), "launching a game writes its map")

# Off switch
K.set_config_value("standard_layout", "0")
check(K.write_game_maps(K.load_config(), games["Eight Button"], [(0x1, 0x2)]) == 0, "standard_layout = 0 writes nothing")

r, rm = K.restore_maps(K.load_config())
check(readmap("sf2_input_16c0_05e1_v4.map")[4] == 0x999 and not os.path.exists(INP + "/fourbtn_input_16c0_05e1_v4.map"),
      "--restore-maps puts the old map back and removes the kiosk's own (%d, %d)" % (r, rm))

out = subprocess.run([sys.executable, sys.argv[1] + "/arcadekiosk.py", "--layout"], capture_output=True, text=True)
print(out.stdout.strip())
print("%d failure(s)" % fails)
