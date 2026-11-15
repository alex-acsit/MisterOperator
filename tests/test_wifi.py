import sys, time, os
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
import wifi as W
T = sys.argv[2]
SHOTS = os.environ.get("SHOTS")
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.KIOSK_BOOT_FLAG = T + "/kiosk_boot"
K.CONFIG_PATH = T + "/kiosk/kiosk.ini"; K.STATE_PATH = T + "/state.json"; K.CACHE_PATH = T + "/cache.json"
K.LOG_PATH = T + "/log.txt"; K.STATUS_PATH = T + "/status.json"; K.CTL_PATH = T + "/ctl"; K.VOLUME_PATH = T + "/vol"
for k, v in (("arcade_dir", T + "/_Arcade"), ("menu_button", "BTN_BASE4"), ("operator_button", "BTN_BASE5"),
             ("exit_grace_s", "0"), ("operator_hold_ms", "1500"), ("wifi_country", "AU")):
    K.set_config_value(k, v)
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1

# ---- the WPA key (IEEE 802.11i test vector)
check(W.wpa_psk("IEEE", "password") == "f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e",
      "PSK matches wpa_passphrase")

# ---- scan parsing
wpa = ("bssid / frequency / signal level / flags / ssid\n"
       "aa:bb:cc:dd:ee:01\t2437\t-45\t[WPA2-PSK-CCMP][ESS]\tBarNet\n"
       "aa:bb:cc:dd:ee:02\t5180\t-70\t[WPA2-PSK-CCMP][ESS]\tBarNet\n"
       "aa:bb:cc:dd:ee:03\t2412\t-80\t[ESS]\tFree WiFi\n"
       "aa:bb:cc:dd:ee:04\t2412\t-60\t[WPA2-EAP-CCMP][ESS]\tCorp\n"
       "aa:bb:cc:dd:ee:05\t2412\t-65\t[WPA2-SAE-CCMP][ESS]\tCaf\\xc3\\xa9\n")
nets = W.merge_networks(W.parse_wpa_scan(wpa))
check([n["ssid"] for n in nets] == ["BarNet", "Corp", "Café", "Free WiFi"], "wpa_cli results: strongest first, one per name, UTF-8 names (%s)" % [n["ssid"] for n in nets])
check([n["security"] for n in nets] == ["wpa", "enterprise", "wpa", "open"] and nets[0]["signal"] == 100, "security types and signal")
iw = '''wlan0     Scan completed :
          Cell 01 - Address: AA:BB:CC:DD:EE:01
                    Quality=60/70  Signal level=-50 dBm
                    Encryption key:on
                    ESSID:"BarNet"
                    IE: IEEE 802.11i/WPA2 Version 1
                        Authentication Suites (1) : PSK
          Cell 02 - Address: AA:BB:CC:DD:EE:03
                    Quality=20/70  Signal level=-90 dBm
                    Encryption key:off
                    ESSID:"Free WiFi"
          Cell 03 - Address: AA:BB:CC:DD:EE:09
                    Quality=30/70  Signal level=-80 dBm
                    Encryption key:on
                    ESSID:"OldRouter"
'''
nets2 = W.merge_networks(W.parse_iwlist(iw))
check([(n["ssid"], n["security"]) for n in nets2] == [("BarNet", "wpa"), ("OldRouter", "wep"), ("Free WiFi", "open")]
      and nets2[0]["signal"] == 85, "iwlist results parsed")

# ---- wpa_supplicant.conf: keeps what's there, replaces the same network
conf = T + "/linux/wpa_supplicant.conf"; os.makedirs(T + "/linux")
open(conf, "w").write('''ctrl_interface=/run/wpa_supplicant
update_config=1

network={
    ssid="Home"
    psk="secret123"
    priority=5
}

network={
    ssid=4261724e6574
    psk=0000
}
''')
out = W.save_network("BarNet", "pinball wizard", conf=conf, country="au")
check('ssid="Home"' in out and "psk=\"secret123\"" in out, "other networks kept")
check(out.count("network={") == 2 and "psk=0000" not in out, "old BarNet entry replaced")
check(W.wpa_psk("BarNet", "pinball wizard") in out and "pinball wizard" not in out, "only the key is stored, not the password")
check(out.count("priority=5") == 1 and out.rstrip().endswith("priority=5\n}") , "the new network is preferred")
check("country=AU" in out and os.path.exists(conf + ".bak"), "country added; old file backed up")
out = W.save_network("Free WiFi", "", conf=conf)
check("key_mgmt=NONE" in out and out.count("country=") == 1, "open network: no key")
out = W.save_network("Secret", "abcdefgh", hidden=True, conf=T + "/new/wpa.conf")
check(out.startswith("ctrl_interface=/run/wpa_supplicant\nupdate_config=1") and "scan_ssid=1" in out, "new file; hidden network")

# ---- keyboard
kb = W.Keyboard("WI-FI", "PASSWORD", min_len=8)
kb.press(); check(kb.text == "a", "button 1 types the key")
kb.move(1, 0); kb.press(); kb.move(0, 2); kb.press()           # b, then row 2 (capitals) -> 'B'
check(kb.text == "abB", "moving the cursor: %r" % kb.text)
kb.move(0, -3); check(kb.row == len(W.KEY_ROWS), "up from the top wraps to the special keys")
kb.col = W.SPECIAL_KEYS.index("SPACE"); kb.press(); check(kb.text == "abB ", "SPACE")
kb.col = W.SPECIAL_KEYS.index("DONE"); check(kb.press() is None and "8" in kb.msg, "DONE needs 8 characters")
kb.backspace(); check(kb.text == "abB", "button 2 deletes")
kb.text = "x" * 63; kb.row, kb.col = 0, 0; kb.press(); check(len(kb.text) == 63, "63 characters at most")
allc = "".join(W.KEY_ROWS)
check(len(set(allc)) == 94 and all(chr(i) in allc for i in range(33, 127)), "every printable character is on the keyboard")

# ---- the operator-menu page, with the system commands faked
cmds_run = []
state = {"connected": None, "pong": True}
def fake_run(cmd, timeout=20):
    cmds_run.append(cmd)
    if cmd[0] == "wpa_cli":
        a = cmd[3]
        if a == "ping": return (0, "PONG\n") if state["pong"] else (1, "")
        if a == "scan_results": return 0, wpa
        if a == "status":
            return 0, ("wpa_state=COMPLETED\nssid=%s\n" % state["connected"]) if state["connected"] else "wpa_state=SCANNING\n"
        if a == "reconfigure": state["connected"] = state.get("will"); return 0, "OK\n"
        return 0, "OK\n"
    if cmd[0] == "ip" and "addr" in cmd:
        return 0, ("2: wlan0    inet 192.168.1.50/24 brd 192.168.1.255 scope global wlan0\n" if state["connected"] else "")
    if cmd[0] == "iwgetid": return 1, ""
    return 0, ""
W.run = fake_run
W.time.sleep = lambda s: None
W.find_interface = lambda sys_net="/sys/class/net": "wlan0"
W.WPA_CONF = conf

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
real_setup = W.WifiSetup
class SyncSetup(real_setup):
    def __init__(s, *a, **kw):
        kw["background"] = False; kw["conf"] = conf; real_setup.__init__(s, *a, **kw)
W.WifiSetup = SyncSetup
class FakeVirt:
    def emit(s, t, c, v, sync=False): pass
    def close(s): pass
class FakeDev(K.PhysicalDevice):
    def __init__(s):
        s.path, s.name, s.vendor, s.product, s.phys = "/dev/input/event1", "Encoder", 1, 2, "usb"
        s.fd = -1; s.grabbed = True; s.virtual = FakeVirt(); s.pressed = set(); s.abs_state = {}
        s.absinfo = {K.ABS_X: (127, 0, 255, 0, 0, 0), K.ABS_Y: (127, 0, 255, 0, 0, 0)}; s.keys = []
k = K.Kiosk(); d = FakeDev(); k.devices = {d.path: d}
def ev(t, c, v): k.handle_events(d, [(t, c, v)])
def press(c): ev(1, c, 1); ev(1, c, 0)
def stick(axis, v): ev(3, axis, v); ev(3, axis, 127)
def shot(name):
    if SHOTS:
        k.need_redraw = True; k.draw(); k.canvas.save_ppm(os.path.join(SHOTS, name + ".ppm"))

k.poll_core(time.monotonic()); k.set_locked(False)
labels = [it[0] for it in k.opview.items()]
check("WI-FI" in labels, "WI-FI in the operator menu")
time.sleep(0.2); k.opview._wifi_status()
check(k.opview.wifi_text == "NOT CONNECTED >", "row shows NOT CONNECTED (%s)" % k.opview.wifi_text)
k.opview.sel = labels.index("WI-FI"); press(0x120)
w = k.opview.wifi
check(k.opview.page == "wifi" and [r[0] for r in w.rows()][1:3] == ["BarNet", "Corp"], "page lists the scanned networks")
shot("wifi_list")
stick(K.ABS_Y, 255); press(0x120)
check(w.keyboard is not None and "BARNET" in w.keyboard.prompt.upper(), "choosing a WPA network opens the keyboard")
# type "Pin8ball!" with the stick
def type_text(text):
    kb = w.keyboard
    for ch in text:
        r = [i for i, row in enumerate(W.KEY_ROWS) if ch in row][0]
        cidx = W.KEY_ROWS[r].index(ch)
        while kb.row != r: stick(K.ABS_Y, 255)
        while kb.col != cidx: stick(K.ABS_X, 255)
        press(0x120)
type_text("Pin8ball")
press(0x121); press(0x121); type_text("ll!")
check(w.keyboard.text == "Pin8ball!", "typed with the stick and buttons: %r" % w.keyboard.text)
shot("wifi_keyboard")
state["will"] = "BarNet"
cmds_run.clear(); press(0x122)                                  # button 3: done
check(w.keyboard is None and not w.busy and "192.168.1.50" in (k.opview.toast or ""), "button 3 connects: %s" % k.opview.toast)
check(W.wpa_psk("BarNet", "Pin8ball!") in open(conf).read(), "network saved with its key")
check(["wpa_cli", "-i", "wlan0", "reconfigure"] in cmds_run, "wpa_supplicant told to reload")
check("Pin8ball" not in open(K.LOG_PATH).read(), "password never written to the log")
press(0x121); check(k.opview.page == "main", "button 2 back to the menu")
k.opview._wifi_status(); check(k.opview.wifi_text == "BARNET >", "row now shows the network")

# wrong password: says so
k.opview.sel = [it[0] for it in k.opview.items()].index("WI-FI"); press(0x120); w = k.opview.wifi
state["connected"] = None; state["will"] = None
stick(K.ABS_Y, 255); press(0x120)
w.keyboard.text = "wrongpass"; press(0x122)
check("NOT CONNECTED" in (k.opview.toast or ""), "no connection: says to check the password")
# enterprise network refused, MENU leaves the keyboard
k.opview.wifi.sel = 2; press(0x120); check(w.keyboard is None and "802.1X" in (k.opview.toast or ""), "802.1X refused")
k.opview.wifi.sel = 1; press(0x120); press(K.parse_code("BTN_BASE4"))
check(w.keyboard is None and k.opview.page == "wifi", "MENU cancels the keyboard")
press(K.parse_code("BTN_BASE4")); check(k.opview.page == "main", "MENU again leaves Wi-Fi")
# hidden network: name, then password
k.opview.sel = [it[0] for it in k.opview.items()].index("WI-FI"); press(0x120); w = k.opview.wifi
w.sel = len(w.rows()) - 1; press(0x120)
check(w.keyboard and "SSID" in w.keyboard.prompt, "hidden network asks for the name")
w.keyboard.text = "Back Room"; press(0x122)
check(w.keyboard and "PASSWORD" in w.keyboard.prompt, "then the password")
state["will"] = "Back Room"; w.keyboard.text = "hunter22"; press(0x122)
cf = open(conf).read()
check("scan_ssid=1" in cf and "Back Room".encode().hex() in cf and "CONNECTED" in k.opview.toast, "hidden network saved and connected")
# no adapter
W.find_interface = lambda sys_net="/sys/class/net": None
press(0x121); k.opview.sel = [it[0] for it in k.opview.items()].index("WI-FI"); press(0x120)
check(k.opview.wifi.iface is None, "no adapter: page says so")
shot("wifi_none")
print("%d failure(s)" % fails)
