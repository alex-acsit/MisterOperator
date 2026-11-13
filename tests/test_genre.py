import sys, io, contextlib
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.LOG_PATH = T + "/glog.txt"; K.CACHE_PATH = T + "/gcache.json"
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
_real_load = K.load_config
def cfgw(**kw):
    c = _real_load(T + "/kiosk/kiosk.ini"); c["arcade_dir"] = T + "/_Arcade"; c.update(kw); return c
def labels(**kw): return sorted(g["label"] for g in K.scan_games(cfgw(**kw)))
print(" all:", labels())
check(labels(genres="Platform") == ["Bomb Jack", "Ghosts'n Goblins"], "genres = Platform")
check(labels(genres="platform, MAZE") == ["Bomb Jack", "Ghosts'n Goblins", "Pengo"], "several genres, any case")
check(labels(genres="Vertical") == ["Galaga"], "matches second part of 'Shooter / Vertical'")
check(labels(genres="Other") == ["No Category Game"], "Other = no category")
check(labels(exclude_genres="Platform, Other") == ["Galaga", "Pengo"], "exclude_genres")
check(labels(genres="Maze", orientation="horizontal") == [], "genre and orientation combine")
check(labels(genres="Racing") == [], "unknown genre gives empty list (shows NO GAMES FOUND)")
# launcher with one genre
v = K.LauncherView(cfgw(), K.scan_games(cfgw(genres="Platform")))
check(v.genres == ["Platform"], "single genre: no 'All Games' entry")
v.set_genre(v.genre_idx + 1)
check(len(v.games) == 2, "genre button does nothing when locked to one genre")
c = K.Canvas(320, 240, K.PixelFormat()); v.draw(c); c.save_ppm(T + "/genre_one.ppm")
v2 = K.LauncherView(cfgw(), K.scan_games(cfgw(genres="Platform, Maze")))
check(v2.genres == ["All Games", "Maze", "Platform"], "two genres: cycle within them only")
v2.set_genre(1); check([g["label"] for g in v2.games] == ["Pengo"], "cycling to Maze")
# attract follows
k = K.Kiosk.__new__(K.Kiosk); k.view = None; k.cfg = cfgw(genres="Maze", attract_vertical="1")
check([g["label"] for g in k.attract_pool()] == ["Pengo"], "attract uses only the locked genre")
# --genres output
K.load_config = lambda path=None: cfgw(genres="Maze")
buf = io.StringIO()
with contextlib.redirect_stdout(buf): K.main(["--genres"])
out = buf.getvalue(); print(out)
check("Platform" in out and "Vertical" in out and "Other" in out, "--genres lists every genre, ignoring the filter")
print("%d failure(s)" % fails)
