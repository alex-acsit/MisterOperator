import sys, io, contextlib
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.LOG_PATH = T + "/mlog.txt"; K.CACHE_PATH = T + "/mcache.json"
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
_real_load = K.load_config
def cfgw(**kw):
    c = _real_load(T + "/kiosk/kiosk.ini"); c["arcade_dir"] = T + "/_Arcade"; c.update(kw); return c
games = {g["label"]: g for g in K.scan_games(cfgw())}
print(" found:", sorted(games))
check({"Metal Slug", "Puzzle Bobble", "Tate Shmup"} <= set(games), ".mgl files are listed alongside .mra")
check("Galaga" in games, ".mra files still listed")
ms = games["Metal Slug"]
check(ms["mgl"] and ms["genre"] == "Neogeo" and not ms["vertical"], "plain .mgl: file name, genre from core, horizontal")
pb = games["Puzzle Bobble"]
check(pb["name"] == "Puzzle Bobble (Neo Geo)" and pb["year"] == "1994" and pb["maker"] == "Taito" and pb["genre"] == "Puzzle",
      "added <name>/<year>/<manufacturer>/<category> tags are shown")
check(games["Tate Shmup"]["vertical"] and games["Tate Shmup"]["genre"] == "Somecore", "<rotation> in .mgl; date stripped from core name")
check(sorted(g["label"] for g in K.scan_games(cfgw(genres="NeoGeo"))) == ["Metal Slug"], "genre filter by core name")
check("Tate Shmup" not in [g["label"] for g in K.scan_games(cfgw(orientation="horizontal"))], "orientation filter applies to .mgl")
check(not any(g["mgl"] for g in K.scan_games(cfgw(include_mgl="0"))), "include_mgl = 0 hides them")
# launching an .mgl sends load_core with the .mgl path
cmds = []
K.mister_cmd = lambda t, quiet=False: cmds.append(t) or True
K.set_tty_mode = lambda m: None
k = K.Kiosk.__new__(K.Kiosk)
k.view = K.LauncherView(cfgw(), K.scan_games(cfgw())); k.devices = {}; k.state = {"locked": True}; k.fb = None
k.cfg = cfgw(); k.release_framebuffer = lambda **kw: None; k.write_status = lambda: None
K.STATE_PATH = T + "/mstate.json"
k.launch(ms)
check(cmds[-1] == "load_core " + ms["path"] and cmds[-1].endswith("Metal Slug.mgl"), "launch sends load_core with the .mgl")
k.cfg = cfgw(genres="Puzzle"); k.view = None
check([g["label"] for g in k.attract_pool()] == ["Puzzle Bobble"], "attract mode can pick .mgl games")
print("%d failure(s)" % fails)
