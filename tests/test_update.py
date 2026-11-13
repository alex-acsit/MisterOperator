import sys, os, io, json, shutil, time, zipfile
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.LOG_PATH = T + "/log.txt"
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_VERSION = K.VERSION

check(K.ini_line("color_accent = #123456   ; note") == "color_accent = #123456" and K.ini_line("# old comment") == ""
      and K.ini_line("; c") == "", "kiosk.ini: # colours are values, ; and leading # are comments")
check(K.version_tuple("v2.1") > K.version_tuple("2.0.1") and K.version_tuple("2.10") > K.version_tuple("2.9")
      and K.version_tuple("2.1") == K.version_tuple("v2.1"), "version comparison")

# ---- an "installed" kiosk to update, with the operator's own data
inst = T + "/fat/arcade_kiosk"; scripts = T + "/fat/Scripts"
shutil.copytree(os.path.join(REPO, "arcade_kiosk"), inst, ignore=shutil.ignore_patterns("__pycache__"))
os.makedirs(scripts); os.makedirs(inst + "/art", exist_ok=True)
open(inst + "/art/Galaga.rgb", "wb").write(b"my art")
open(inst + "/state.json", "w").write('{"coins": [["", 6]], "plays": {"x": 5}}')
ini = open(inst + "/kiosk.ini").read()
ini = ini.replace("title = ARCADE", "title = JOES BAR").replace("operator_button =", "operator_button = BTN_BASE5")
ini += "footer_genre = 2:GENRE\ncolor_accent = #123456\n"
open(inst + "/kiosk.ini", "w").write(ini)
K.HERE = inst; K.BACKUP_DIR = inst + "/backup"; K.SCRIPTS_DIR = scripts; K.UPDATE_TMP = T + "/upd"
K.CONFIG_PATH = inst + "/kiosk.ini"
K.load_config.__defaults__ = (K.CONFIG_PATH,)

# ---- a release zip built from this repo, pretending to be 9.9 with a new setting
def make_release(path, version="9.9", break_it=False, top=""):
    with zipfile.ZipFile(path, "w") as z:
        for base in ("arcade_kiosk", "Scripts"):
            for root, dirs, files in os.walk(os.path.join(REPO, base)):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    full = os.path.join(root, f); rel = os.path.relpath(full, REPO)
                    data = open(full, "rb").read()
                    if rel == "arcade_kiosk/arcadekiosk.py":
                        data = data.replace(b'VERSION = "%s"' % REAL_VERSION.encode(), b'VERSION = "%s"' % version.encode())
                        if break_it: data += b"\nthis is not python(\n"
                    if rel == "arcade_kiosk/kiosk.ini":
                        data += b"\n; new in 9.9\nshiny_new_setting = 42\n"
                    if rel == "arcade_kiosk/README.md":
                        data = b"new readme"
                    z.writestr(top + rel, data)
    return path

served = {}
real_http_get = K.http_get
def fake_get(url, headers=None, timeout=60):
    if url.startswith("https://api.github.com/"):
        return json.dumps(served["api"]).encode()
    return open(served[url], "rb").read()
K.http_get = fake_get
served["api"] = {"tag_name": "v9.9", "body": "notes", "assets": [
    {"name": "MisterOperator_v9.9.zip", "browser_download_url": "https://x/rel.zip", "url": "https://api/asset/1"}]}
served["https://x/rel.zip"] = make_release(T + "/rel.zip")

cfg = K.load_config()
rel = K.latest_release(cfg)
check(rel["version"] == "9.9" and rel["url"] == "https://x/rel.zip" and not rel["headers"], "latest release found (public download)")
rel_tok = K.latest_release(dict(cfg, update_token="abc"))
check(rel_tok["url"] == "https://api/asset/1" and rel_tok["headers"]["Accept"] == "application/octet-stream",
      "with update_token: private-repo download through the API")
served["api"] = {"message": "Not Found"}
try:
    K.latest_release(cfg); check(False, "missing release reported")
except K.UpdateError as e:
    check("Not Found" in str(e), "repo not found / private: clear error (%s)" % e)
served["api"] = {"tag_name": "v9.9", "assets": [
    {"name": "MisterOperator_v9.9.zip", "browser_download_url": "https://x/rel.zip", "url": "u"}]}

# ---- a broken release changes nothing
before = open(inst + "/arcadekiosk.py").read()
served["https://x/bad.zip"] = make_release(T + "/bad.zip", break_it=True)
try:
    K.install_release(dict(rel, url="https://x/bad.zip"), say=lambda m: None); check(False, "broken release refused")
except K.UpdateError as e:
    check(open(inst + "/arcadekiosk.py").read() == before, "release that doesn't compile: refused, nothing changed")
open(T + "/notzip.zip", "wb").write(b"<html>rate limited</html>"); served["https://x/notzip"] = T + "/notzip.zip"
try:
    K.install_release(dict(rel, url="https://x/notzip"), say=lambda m: None); check(False, "html refused")
except K.UpdateError:
    check(open(inst + "/arcadekiosk.py").read() == before, "download that isn't a zip: refused, nothing changed")

# ---- the real thing
v = K.install_release(rel, say=lambda m: None)
new_py = open(inst + "/arcadekiosk.py").read()
check(v == "9.9" and 'VERSION = "9.9"' in new_py, "installed 9.9")
newcfg = K.load_config(inst + "/kiosk.ini")
check(newcfg["title"] == "JOES BAR" and newcfg["operator_button"] == "BTN_BASE5", "operator's settings kept")
check(newcfg.get("shiny_new_setting") == "42", "new setting added from the release's kiosk.ini")
txt = open(inst + "/kiosk.ini").read()
check("footer_genre" not in txt and "color_accent = #123456" in txt, "retired setting dropped, custom colour kept")
check("; Quit a game back to the list" in txt or ";" in txt.splitlines()[1], "kiosk.ini keeps its comments")
check(open(inst + "/art/Galaga.rgb", "rb").read() == b"my art" and json.load(open(inst + "/state.json"))["plays"] == {"x": 5},
      "box art, credits and play counts untouched")
check(open(inst + "/README.md").read() == "new readme", "program files replaced")
check(os.access(inst + "/arcadekiosk.py", os.X_OK) and os.access(inst + "/run.sh", os.X_OK), "scripts executable")
check(os.path.exists(scripts + "/update_arcade_kiosk.sh") and os.path.exists(scripts + "/install_arcade_kiosk.sh"),
      "Scripts-menu scripts installed")
bk = inst + "/backup/" + K.VERSION
check(os.path.exists(bk + "/arcadekiosk.py") and before == open(bk + "/arcadekiosk.py").read()
      and "JOES BAR" in open(bk + "/kiosk.ini").read(), "previous version backed up (with its settings)")
check(not os.path.exists(T + "/upd"), "temp files cleaned up")

K.VERSION = "9.9"                      # the kiosk restarts into the new version
# zip with an extra top folder (e.g. a source archive) also works
served["https://x/top.zip"] = make_release(T + "/top.zip", version="9.9.1", top="MisterOperator-9.9.1/")
check(K.install_release(dict(rel, url="https://x/top.zip"), say=lambda m: None) == "9.9.1", "zip with a top-level folder")

# ---- rollback to the newest older backup
K.VERSION = "9.9.1"
v = K.rollback(say=lambda m: None)
check(v == "9.9" and 'VERSION = "9.9"' in open(inst + "/arcadekiosk.py").read(), "rollback restores the previous version")

# ---- update_command output and restart request
K.VERSION = "9.9"
K.CTL_PATH = T + "/ctl"
out = io.StringIO(); sys.stdout = out
rc = K.update_command(["--update"]); sys.stdout = sys.__stdout__
check(rc == 0 and "Already up to date" in out.getvalue(), "--update when current: up to date")
out = io.StringIO(); sys.stdout = out
rc = K.update_command(["--check"]); sys.stdout = sys.__stdout__
check(rc == 0 and "Latest: 9.9" in out.getvalue(), "--check shows installed and latest")

# ---- merge_ini on its own
m = K.merge_ini("[kiosk]\n; comment\na = 1   ; note\nb = 2\n", "a = 5\nzz = 9\nfooter_letter = x\n")
check("a = 5   ; note" in m and "b = 2" in m and "zz = 9" in m and "footer_letter" not in m and "; comment" in m,
      "merge_ini keeps values, comments, extras; drops retired keys")

# ---- curl path really works (file:// URL)
open(T + "/hello.txt", "w").write("hi")
check(real_http_get("file://" + T + "/hello.txt") == b"hi", "http_get fetches with curl")

print("%d failure(s)" % fails)
