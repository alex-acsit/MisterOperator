#!/usr/bin/env python3
"""
Convert game screenshots / title images into the small raw files the kiosk shows.

Run this on your PC (needs Pillow:  pip install pillow):

    python make_art.py  <folder of images>  <output folder>

Name each image after the .mra file without ".mra" (e.g. "Galaga (Namco rev. B).png")
or after the MAME set name (e.g. "galaga.png"). Each one becomes a 100x75 .rgb
file; copy the output folder's contents to /media/fat/arcade_kiosk/art/ on the MiSTer.
Vertical games are letterboxed so the whole picture fits.
"""
import os
import sys

from PIL import Image

W, H = 100, 75
BG = (18, 21, 44)


def convert(src, dst):
    img = Image.open(src).convert("RGB")
    img.thumbnail((W, H), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
    with open(dst, "wb") as f:
        f.write(canvas.tobytes())


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for name in sorted(os.listdir(src_dir)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
            continue
        try:
            convert(os.path.join(src_dir, name), os.path.join(out_dir, stem + ".rgb"))
            n += 1
        except Exception as e:
            print("skipped %s: %s" % (name, e))
    print("converted %d images into %s" % (n, out_dir))


if __name__ == "__main__":
    main()
