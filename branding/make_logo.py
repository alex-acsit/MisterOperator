#!/usr/bin/env python3
"""Draws the MisterOperator logo as SVG.

The wordmark is built from the kiosk's own 8x8 pixel font (font8x8, public
domain), one square per pixel, so it needs no font files and matches what the
cabinet shows. Writes, next to this script:

  logo.svg           horizontal logo for dark backgrounds
  logo_light.svg     horizontal logo for white backgrounds (print)
  logo_stacked.svg   icon above the wordmark, for dark backgrounds
  icon.svg           the joystick icon on its own
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "arcade_kiosk"))
from font8x8 import FONT  # noqa: E402

BG = "#1a1c1b"
PANEL = "#262a28"
LINE = "#40463f"
GREEN = "#289655"
GREEN_LIGHT = "#5fc882"
WHITE = "#f5f7f6"
INK = "#1a1c1b"


def pixel_text(text, x, y, px, colour, gap=0.12, shadow=None):
    """SVG rects for text in the 8x8 font; px = size of one pixel."""
    out = []
    g = px * gap
    for i, ch in enumerate(text):
        glyph = FONT[ord(ch) & 0x7F]
        for row in range(8):
            bits = glyph[row]
            for col in range(8):
                if bits >> col & 1:
                    rx, ry = x + (i * 8 + col) * px, y + row * px
                    if shadow:
                        out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>'
                                   % (rx + px * 0.5, ry + px * 0.5, px - g, px - g, shadow))
                    out.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="%.2f" fill="%s"/>'
                               % (rx, ry, px - g, px - g, px * 0.12, colour))
    if shadow:   # shadows first, then letters on top
        sh = [r for r in out if shadow in r]
        fg = [r for r in out if shadow not in r]
        out = sh + fg
    return "\n".join(out)


def icon(x, y, s, badge=BG, ring=GREEN):
    """The joystick icon in a rounded badge, s units square at (x, y)."""
    k = s / 100.0

    def p(v):
        return "%.2f" % (v * k)
    return f'''<g transform="translate({x},{y})">
  <rect x="0" y="0" width="{p(100)}" height="{p(100)}" rx="{p(22)}" fill="{badge}"/>
  <rect x="{p(4)}" y="{p(4)}" width="{p(92)}" height="{p(92)}" rx="{p(19)}" fill="none" stroke="{ring}" stroke-width="{p(3)}"/>
  <!-- scanlines -->
  <g opacity="0.10" fill="{WHITE}">
    {''.join('<rect x="%s" y="%s" width="%s" height="%s"/>' % (p(10), p(14 + i * 8), p(80), p(1.2)) for i in range(10))}
  </g>
  <!-- base -->
  <ellipse cx="{p(50)}" cy="{p(80)}" rx="{p(30)}" ry="{p(8)}" fill="{PANEL}"/>
  <ellipse cx="{p(50)}" cy="{p(77)}" rx="{p(30)}" ry="{p(8)}" fill="{LINE}"/>
  <ellipse cx="{p(50)}" cy="{p(76)}" rx="{p(12)}" ry="{p(3.6)}" fill="{BG}"/>
  <!-- shaft -->
  <rect x="{p(46)}" y="{p(44)}" width="{p(8)}" height="{p(33)}" rx="{p(3)}" fill="#c9cfcc"/>
  <rect x="{p(46)}" y="{p(44)}" width="{p(3)}" height="{p(33)}" rx="{p(1.5)}" fill="{WHITE}" opacity="0.7"/>
  <!-- ball with a keyhole: the operator's key -->
  <circle cx="{p(50)}" cy="{p(36)}" r="{p(20)}" fill="{GREEN}"/>
  <circle cx="{p(50)}" cy="{p(36)}" r="{p(20)}" fill="none" stroke="{GREEN_LIGHT}" stroke-width="{p(1.5)}" opacity="0.6"/>
  <ellipse cx="{p(43)}" cy="{p(27)}" rx="{p(6)}" ry="{p(4)}" fill="{WHITE}" opacity="0.55" transform="rotate(-30 {p(43)} {p(27)})"/>
  <circle cx="{p(50)}" cy="{p(33)}" r="{p(5.5)}" fill="{BG}"/>
  <path d="M{p(47)} {p(35)} L{p(53)} {p(35)} L{p(55)} {p(47)} L{p(45)} {p(47)} Z" fill="{BG}"/>
</g>'''


def svg(w, h, body, bg=None):
    rect = '<rect width="100%%" height="100%%" fill="%s"/>' % bg if bg else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">\n'
            '<title>MisterOperator</title>\n%s\n%s\n</svg>\n' % (w, h, w, h, rect, body))


def horizontal(top, bottom, shadow, badge, bg):
    px_big, px_small = 7, 4.2
    icon_s = 120
    wx = icon_s + 28
    word = (pixel_text("MISTER", wx + 2, 18, px_small, top) + "\n" +
            pixel_text("OPERATOR", wx, 18 + 8 * px_small + 12, px_big, bottom, shadow=shadow))
    w = int(wx + 8 * 8 * px_big + 12)
    return svg(w, icon_s, icon(0, 0, icon_s, badge=badge) + "\n" + word, bg)


def stacked():
    px_big, px_small = 7, 4.2
    W = int(8 * 8 * px_big + 40)
    icon_s = 150
    body = icon((W - icon_s) / 2, 20, icon_s)
    y = 20 + icon_s + 26
    body += "\n" + pixel_text("MISTER", (W - 6 * 8 * px_small) / 2, y, px_small, GREEN_LIGHT)
    y += 8 * px_small + 12
    body += "\n" + pixel_text("OPERATOR", 20, y, px_big, WHITE, shadow=GREEN)
    return svg(W, int(y + 8 * px_big + 26), body)


def main():
    files = {
        "logo.svg": horizontal(GREEN_LIGHT, WHITE, GREEN, BG, None),
        "logo_light.svg": horizontal(GREEN, INK, GREEN_LIGHT, BG, None),
        "logo_stacked.svg": stacked(),
        "icon.svg": svg(120, 120, icon(0, 0, 120)),
    }
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w") as f:
            f.write(text)
        print(name)


if __name__ == "__main__":
    main()
