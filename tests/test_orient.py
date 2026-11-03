import sys
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]; K.LOG_PATH = T + "/olog.txt"; K.CACHE_PATH = T + "/ocache.json"
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
def labels(**kw):
    cfg = K.load_config(T + "/kiosk/kiosk.ini"); cfg["arcade_dir"] = T + "/_Arcade"; cfg.update(kw)
    return sorted(g["label"] for g in K.scan_games(cfg))
allg = labels()
check(allg == ["Angle Game", "Bomb Jack", "Galaga", "Ghosts'n Goblins", "Pengo"], "all: %s" % allg)
check(labels(orientation="horizontal") == ["Bomb Jack", "Ghosts'n Goblins"], "horizontal only (missing rotation = horizontal)")
check(labels(orientation="vertical") == ["Angle Game", "Galaga", "Pengo"], "vertical only (CCW case, angle 270)")
check(labels(orientation="TATE") == labels(orientation="vertical"), "TATE alias")
check(labels(orientation="yoko") == labels(orientation="horizontal"), "YOKO alias")
check(labels(orientation="", hide_vertical="1") == labels(orientation="horizontal"), "old hide_vertical still works")
check(labels(orientation="sideways") == allg, "unknown value falls back to all")
# attract pool follows orientation
k = K.Kiosk.__new__(K.Kiosk); k.view = None
k.cfg = K.load_config(T + "/kiosk/kiosk.ini"); k.cfg.update(arcade_dir=T + "/_Arcade", orientation="vertical")
check(sorted(g["label"] for g in k.attract_pool()) == ["Angle Game", "Galaga", "Pengo"], "attract uses vertical games when orientation = vertical")
k.cfg["orientation"] = "all"
check(all(not g["vertical"] for g in k.attract_pool()), "attract still skips vertical on a mixed list by default")
print("%d failure(s)" % fails)
