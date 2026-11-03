import sys, time, threading
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
def run(ready_after, keys_after, offload_delay, stale):
    t0 = time.monotonic()
    m = {"fb": False, "param": "8888 1 320 240 1280" if stale else "8888 1 640 480 2560", "toggles": 0}
    K.mister_ready = lambda: time.monotonic() - t0 > ready_after
    K.read_fb_param = lambda: m["param"].split()
    def wp(v): m["param"] = " ".join(map(str, v))
    K.write_fb_param = wp
    def cmd(text, quiet=False):
        if text.startswith("fb_cmd1") and m["fb"]:
            p = text.split(); m["param"] = "%s %s %s %s %d" % (p[1], p[2], p[3], p[4], int(p[3]) * 4)
    K.mister_cmd = cmd
    class Keys:
        def tap(s, c):
            if time.monotonic() - t0 < keys_after: return       # Main not reading keys yet
            m["fb"] = not m["fb"]; m["toggles"] += 1
            if m["fb"]:  # Main's background write of the console mode
                threading.Timer(offload_delay, lambda: m.__setitem__("param", "8888 1 640 480 2560")).start()
    K.set_tty_mode = lambda x: None
    class FB:
        def __init__(s): s.xres, s.yres, s.fmt = 320, 240, K.PixelFormat()
    K.Framebuffer = FB
    k = K.Kiosk.__new__(K.Kiosk); k.cfg = dict(K.DEFAULTS); k.keys_dev = Keys(); k.own_nodes = set()
    class FB2(FB):
        def close(s): pass
    K.Framebuffer = FB2
    k.activate_framebuffer()
    time.sleep(0.3)
    k.check_fb_mode()       # the once-a-second watchdog
    ok = m["fb"] and m["param"].startswith("8888 1 320 240")
    print("%s ready@%.1fs keys@%.1fs offload=%.2fs stale=%s -> fb_on=%s param=%s toggles=%d" % (
        "PASS" if ok else "FAIL", ready_after, keys_after, offload_delay, stale, m["fb"], m["param"], m["toggles"]))
K.log = lambda msg: print("   log:", msg)
run(0.0, 0.0, 0.05, False)
run(0.5, 1.0, 0.05, False)
run(0.3, 0.3, 0.20, True)
run(0.2, 0.2, 0.40, False)
