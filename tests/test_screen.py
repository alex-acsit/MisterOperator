import sys
sys.path.insert(0, sys.argv[1]); import arcadekiosk as K
T = sys.argv[2]
K.KIOSK_FLAG = T + "/kiosk_active"; K.FEATURES_PATH = T + "/MiSTer_features"; K.LOG_PATH = T + "/slog.txt"
fails = 0
def check(c, m):
    global fails; print(("PASS " if c else "FAIL ") + m); fails += 0 if c else 1
cfg = K.load_config(sys.argv[1] + "/kiosk.ini")
check(cfg["screen"] == "yoko" and K.screen_rotation(cfg) == 0, "default screen is yoko")
for v, want in (("tate_cw", 90), ("TATE", 90), ("tate_ccw", 270), ("vertical ccw", 270), ("yoko", 0), ("sideways", 0)):
    check(K.screen_rotation({"screen": v}) == want, "screen = %s -> %d" % (v, want))

# rotation maps every pixel exactly (checked pixel by pixel, 32-bit and 16-bit)
for fmt in (K.PixelFormat(), K.PixelFormat(16, (11, 5), (5, 6), (0, 5), (0, 0))):
    src = K.Canvas(6, 4, fmt)
    for i in range(len(src.buf)): src.buf[i] = (i * 7 + 3) % 256
    B = fmt.Bpp
    px = lambda c, x, y: bytes(c.buf[(y * c.w + x) * B:(y * c.w + x + 1) * B])
    for rot in (90, 270):
        dst = K.Canvas(4, 6, fmt); K.rotate_canvas(src, dst, rot)
        ok = all(px(dst, x, y) == (px(src, y, src.h - 1 - x) if rot == 90 else px(src, src.w - 1 - y, x))
                 for y in range(dst.h) for x in range(dst.w))
        check(ok, "%d-bit pixels rotated %d exactly" % (fmt.bpp, rot))

# portrait layout
tcfg = dict(cfg, screen="tate_cw")
v = K.LauncherView(tcfg, K.demo_games())
check(v.portrait and v.LIST_W == 232, "TATE uses the portrait layout")
c = K.Canvas(240, 320, K.PixelFormat()); v.draw(c)
bg = c.col(K.BG)
row = lambda y: bytes(c.buf[y * c.stride:(y + 1) * c.stride])
check(any(row(y) != bg * 240 for y in range(308, 320)), "footer drawn at the bottom of the portrait screen")
check(v.LIST_Y + v.ROWS * v.ROW_H < v.PANEL_Y, "list and picture don't overlap")
v.move(30)
check(v.current() is v.games[-1] and v.top == len(v.games) - v.ROWS, "scrolling works in TATE")
y = K.LauncherView(cfg, K.demo_games())
check(not y.portrait and y.LIST_W == 204 and y.PANEL_X == 214, "YOKO layout unchanged")

# kiosk draws through the portrait canvas when TATE
k = K.Kiosk.__new__(K.Kiosk); k.cfg = tcfg
class FB:
    xres, yres, fmt = 320, 240, K.PixelFormat()
    def present(s, canvas): s.got = (canvas.w, canvas.h)
k.fb = FB(); k.make_canvases(); k.view = v; k.blink_on = True; k.need_redraw = True
k.draw()
check(k.lcanvas.w == 240 and k.lcanvas.h == 320 and k.fb.got == (320, 240), "TATE draws 240x320 upright, sends 320x240")
k.cfg = cfg; k.make_canvases(); k.view = y; k.draw()
check(k.lcanvas is None and k.fb.got == (320, 240), "YOKO draws straight to the screen")
print("%d failure(s)" % fails)
