#!/usr/bin/env python3
"""Builds the printable MisterOperator manual (A4 PDF) from MANUAL.md.

    python3 docs/print/make_manual_pdf.py [output.pdf]

Needs Python's markdown, playwright (with Chromium), pypdf and pdfplumber.
The cover, contents (with page numbers), quick-reference card, screenshots and
Ope-chan's tips are added here; the text is MANUAL.md as it is.
"""
import html
import os
import re
import sys
import tempfile

import logging

import markdown
import pdfplumber
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BRAND = os.path.join(ROOT, "branding")
DOCS = os.path.join(ROOT, "docs")

with open(os.path.join(ROOT, "arcade_kiosk", "arcadekiosk.py")) as f:
    VERSION = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M).group(1)

# Screenshots placed right after these headings: (file, caption, width %)
FIGURES = {
    "3.2 The game list": ("screens.png", "The game list on a landscape (YOKO) and a vertical (TATE) monitor.", 92),
    "3.3 Genres and the letter jump": ("letter_picker.png", "The letter jump (Button 4).", 52),
    "4.1 Opening, moving around, locking": ("operator.png", "The operator menu.", 52),
    "4.3 The genre page": ("genres.png", "The genre page: Button 1 shows or hides a genre.", 52),
    "4.5 Monitor and input tests": ("tests.png", "Input test, colour bars and the linearity pattern.", 100),
    "4.7 Controller setup": ("controls.png", "Controller setup part-way through, and the single-game page.", 96),
    "4.8 Wi-Fi": ("wifi.png", "Choosing a network and typing its password with the stick.", 96),
}

# Ope-chan's tips, after the section with this heading
TIPS = {
    "2.4 First boot": "Put the OPERATOR button somewhere players can't reach. Inside the coin door is perfect!",
    "4.1 Opening, moving around, locking": "Holding OPERATOR in the operator menu locks the cabinet straight away. Handy when a player walks up!",
    "4.6 Single-game mode": "Single game is great for a cabinet that should only ever be one game, like a dedicated Galaga.",
    "5.5 NVRAM (settings and high scores)": "High scores are saved every time a game quits, so the best players stay on the board!",
    "7. Updating": "Set auto_update = 1 and I'll fetch new versions by myself.",
    "11. Troubleshooting": "Still stuck? VIEW LOG in the operator menu shows what I've been up to.",
}

QUICK_REF = """
<section class="quickref">
  <h1 class="qr-title">Quick reference</h1>
  <p class="qr-sub">Keep this page with the cabinet.</p>
  <div class="qr-grid">
    <div class="qr-box">
      <h3>Players</h3>
      <table>
        <tr><td>Stick up / down</td><td>Move through the list</td></tr>
        <tr><td>Stick left / right</td><td>Previous / next letter</td></tr>
        <tr><td>Button 1 or Start</td><td>Play</td></tr>
        <tr><td>Button 2 / 3</td><td>Next / previous genre</td></tr>
        <tr><td>Button 4</td><td>Letter jump</td></tr>
        <tr><td>Coin</td><td>Add a credit (held until the game loads)</td></tr>
        <tr><td><b>MENU</b></td><td><b>Quit the game, back to the list</b></td></tr>
      </table>
    </div>
    <div class="qr-box">
      <h3>Operator</h3>
      <table>
        <tr><td><b>Hold OPERATOR</b><br>1.5 seconds</td><td>Open the operator menu (from the list or a game)</td></tr>
        <tr><td>Stick</td><td>Move; left / right changes a setting</td></tr>
        <tr><td>Button 1</td><td>Choose</td></tr>
        <tr><td>Button 2</td><td>Back</td></tr>
        <tr><td>BACK TO GAMES</td><td>Lock the cabinet again</td></tr>
        <tr><td>Hold OPERATOR again</td><td>Lock straight away</td></tr>
      </table>
    </div>
  </div>
  <div class="qr-box qr-wide">
    <h3>In the operator menu</h3>
    <div class="qr-cols">
      <div><b>Volume, Credits</b><br>sound level; free credits</div>
      <div><b>Demo after / length</b><br>attract mode timing</div>
      <div><b>Idle game quit</b><br>quit unattended games</div>
      <div><b>Coin delay</b><br>when held coins go in</div>
      <div><b>Save NVRAM</b><br>settings and high scores</div>
      <div><b>Screen, Theme</b><br>YOKO/TATE; colours</div>
      <div><b>Show games, Genres</b><br>which games are listed</div>
      <div><b>Single game</b><br>lock to one game</div>
      <div><b>Controller setup</b><br>stick, 1&ndash;6, Start, Coin</div>
      <div><b>Wi-Fi</b><br>connect to a network</div>
      <div><b>Monitor / Input test</b><br>patterns; button tester</div>
      <div><b>Game settings</b><br>a game's DIP switches</div>
      <div><b>Play counts, Reset NVRAM</b></div>
      <div><b>Update kiosk</b><br>press twice to install</div>
      <div><b>MiSTer main</b><br>kiosk build of the MiSTer</div>
      <div><b>View log, Reboot</b></div>
    </div>
  </div>
  <div class="qr-panel">
    <div class="panel-pic">
      <div class="stick"></div>
      <div class="btns"><span>1</span><span>2</span><span>3</span><span>4</span><span>5</span><span>6</span></div>
    </div>
    <p>Every game uses the same panel: buttons <b>1 2 3</b> on the top row, <b>4 5 6</b> underneath,
    plus <b>Start</b> and <b>Coin</b>. Set it up once with <b>Controller setup</b>.</p>
    <img class="qr-mascot" src="mascot.svg" alt="">
  </div>
  <div class="qr-box qr-notes">
    <h3>Cabinet notes</h3>
    <div class="notes-grid">
      <div><span>Cabinet / location</span></div><div><span>Installed by, date</span></div>
      <div><span>MisterOperator version</span></div><div><span>Wi-Fi network</span></div>
      <div><span>Where the OPERATOR button is</span></div><div><span>Operator contact</span></div>
    </div>
    <div class="notes-lines"><span>Notes</span></div>
  </div>
</section>
"""


def tip_html(text):
    return ('<div class="tip"><img src="mascot_head.svg" alt=""><div><b>Ope-chan&rsquo;s tip</b><br>%s</div></div>'
            % html.escape(text))


def figure_html(name, caption, width):
    return ('<figure style="width:%d%%"><img src="%s" alt="%s"><figcaption>%s</figcaption></figure>'
            % (width, os.path.join(DOCS, name), html.escape(caption), html.escape(caption)))


def manual_body():
    with open(os.path.join(ROOT, "MANUAL.md")) as f:
        md = f.read()
    # The title, intro and contents list come from the cover and contents pages here.
    md = md[md.index("## 1. "):]
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "toc", "sane_lists"])

    def add_after_heading(text, extra):
        nonlocal body
        m = re.search(r"(<h[23] id=\"[^\"]*\">%s</h[23]>)" % re.escape(html.escape(text, quote=False)), body)
        if not m:
            raise SystemExit("heading not found: %s" % text)
        body = body[:m.end()] + extra + body[m.end():]

    def add_before_next_heading(text, extra):
        nonlocal body
        m = re.search(r"<h([23]) id=\"[^\"]*\">%s</h[23]>" % re.escape(html.escape(text, quote=False)), body)
        if not m:
            raise SystemExit("heading not found: %s" % text)
        level = int(m.group(1))
        nxt = re.compile(r"<h[2-%d] " % level).search(body, m.end())
        at = nxt.start() if nxt else len(body)
        body = body[:at] + extra + body[at:]

    for heading, (name, caption, width) in FIGURES.items():
        add_after_heading(heading, figure_html(name, caption, width))
    for heading, text in TIPS.items():
        add_before_next_heading(heading, tip_html(text))
    # tables: give the settings reference its own class (it's the widest)
    body = body.replace("<table>", '<table class="t">')
    return body


def headings(body):
    """[(level, id, text)] for the contents."""
    out = []
    for m in re.finditer(r'<h([23]) id="([^"]+)">(.*?)</h[23]>', body):
        out.append((int(m.group(1)), m.group(2), re.sub("<[^>]+>", "", html.unescape(m.group(3)))))
    return out


CSS = r"""
@page { size: A4; margin: 18mm 17mm 20mm 17mm; }
@page cover { margin: 0; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Inter", "DejaVu Sans", sans-serif; font-feature-settings: "calt" 0, "case" 0, "tnum" 0; font-size: 9.6pt; line-height: 1.45; color: #1d2120; margin: 0; }
a { color: #1f7a45; text-decoration: none; }
a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 7.5pt; color: #6b736f; word-break: break-all; }
h2 { font-family: "Inter Display", "Inter", sans-serif; font-weight: 800; font-size: 20pt; color: #1a1c1b;
     margin: 0 0 4mm; padding: 0 0 2.5mm; border-bottom: 2.5pt solid #289655; break-before: page; break-after: avoid; }
h3 { font-weight: 700; font-size: 12.5pt; color: #1f7a45; margin: 6mm 0 2mm; break-after: avoid; }
h2 + h3 { margin-top: 2mm; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 5mm; margin: 1.5mm 0 3mm; }
li { margin: 0.6mm 0; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8.4pt; background: #eef3f0; padding: 0.2mm 1mm; border-radius: 1mm; }
pre { background: #1a1c1b; color: #e8ece9; padding: 3mm 4mm; border-radius: 2mm; break-inside: avoid; white-space: pre-wrap; }
pre code { background: none; color: inherit; padding: 0; font-size: 8.4pt; }
table.t { width: 100%; border-collapse: collapse; margin: 2mm 0 4mm; font-size: 8.6pt; }
table.t th { background: #1a1c1b; color: #fff; text-align: left; font-weight: 600; padding: 1.4mm 2mm; }
table.t td { padding: 1.2mm 2mm; border-bottom: 0.5pt solid #d5ddd8; vertical-align: top; }
table.t tr:nth-child(even) td { background: #f3f7f5; }
table.t tr { break-inside: avoid; }
table.t td code { overflow-wrap: anywhere; }
table.t td:first-child code { white-space: nowrap; overflow-wrap: normal; }
hr { border: none; border-top: 0.5pt solid #ccd5d0; margin: 5mm 0; }
blockquote { margin: 3mm 0; padding: 2mm 4mm; border-left: 2pt solid #289655; background: #f3f7f5; }
figure { margin: 3mm auto 5mm; break-inside: avoid; text-align: center; }
figure img { width: 100%; border-radius: 1.5mm; box-shadow: 0 0 0 0.6pt #1a1c1b; }
figcaption { font-size: 8pt; color: #5d6662; margin-top: 1.5mm; font-style: italic; }
.tip { display: flex; align-items: center; gap: 4mm; margin: 4mm 0 5mm; padding: 3mm 5mm 3mm 3mm;
       background: #eaf7ef; border: 1pt solid #9fdcb6; border-radius: 4mm; break-inside: avoid; font-size: 9.3pt; }
.tip img { width: 17mm; flex: none; }
.tip b { color: #1f7a45; }

/* cover */
.cover { page: cover; width: 210mm; height: 297mm; background: #1a1c1b; color: #f5f7f6; position: relative; overflow: hidden;
         display: flex; flex-direction: column; align-items: center; }
.cover .lines { position: absolute; inset: 0; background: repeating-linear-gradient(0deg, rgba(255,255,255,0.035) 0 1.2mm, transparent 1.2mm 3.2mm); }
.cover .logo { width: 150mm; margin-top: 30mm; position: relative; }
.cover .mascot { width: 92mm; margin-top: 12mm; position: relative; }
.cover .glow { position: absolute; width: 140mm; height: 140mm; left: 35mm; top: 110mm; border-radius: 50%;
               background: radial-gradient(circle, rgba(40,150,85,0.35), rgba(40,150,85,0) 65%); }
.cover h1 { font-family: "Inter Display", "Inter", sans-serif; font-weight: 800; font-size: 26pt; margin: 8mm 0 1mm; letter-spacing: 0.5pt; position: relative; }
.cover .sub { color: #5fc882; font-size: 11pt; position: relative; }
.cover .band { position: absolute; bottom: 0; left: 0; right: 0; height: 18mm; background: #289655; display: flex;
               align-items: center; justify-content: space-between; padding: 0 17mm; font-size: 10pt; font-weight: 600; color: #fff; }
.cover .jp { font-family: "IPAPGothic", "IPAGothic", sans-serif; }

/* contents */
.contents h1, .quickref h1 { font-family: "Inter Display", "Inter", sans-serif; font-weight: 800; font-size: 22pt; margin: 0 0 5mm;
                padding-bottom: 2.5mm; border-bottom: 2.5pt solid #289655; }
.toc { list-style: none; padding: 0; margin: 0; }
.toc li { display: flex; align-items: baseline; margin: 0; }
.toc li.l2 { font-weight: 700; font-size: 10.5pt; margin-top: 2.6mm; }
.toc li.l3 { padding-left: 7mm; font-size: 9pt; color: #3a413e; }
.toc li .dots { flex: 1; border-bottom: 0.8pt dotted #9aa39f; margin: 0 2mm; transform: translateY(-1mm); }
.toc li .pg { min-width: 7mm; text-align: right; }
.contents { break-after: page; }

/* quick reference */
.quickref { break-after: page; }
.qr-sub { color: #5d6662; margin: -3mm 0 4mm; }
.qr-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; }
.qr-box { border: 1pt solid #c9d4ce; border-radius: 3mm; padding: 3mm 4mm; break-inside: avoid; }
.qr-box h3 { margin: 0 0 2mm; color: #fff; background: #1a1c1b; margin: -3mm -4mm 2.5mm; padding: 2mm 4mm; border-radius: 3mm 3mm 0 0; font-size: 11pt; }
.qr-box table { width: 100%; border-collapse: collapse; font-size: 9pt; }
.qr-box td { padding: 1.1mm 1mm; border-bottom: 0.5pt solid #e1e8e4; vertical-align: top; }
.qr-box td:first-child { width: 40%; font-weight: 600; }
.qr-wide { margin-top: 4mm; }
.qr-cols { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 2.2mm 4mm; font-size: 8.3pt; color: #3a413e; }
.qr-cols b { color: #1d2120; }
.qr-panel { margin-top: 4mm; display: flex; align-items: center; gap: 6mm; background: #1a1c1b; color: #e8ece9; border-radius: 4mm; padding: 4mm 6mm; position: relative; }
.qr-panel p { flex: 1; margin: 0; font-size: 9.5pt; }
.qr-panel b { color: #5fc882; }
.panel-pic { display: flex; align-items: center; gap: 5mm; flex: none; }
.panel-pic .stick { width: 9mm; height: 9mm; border-radius: 50%; background: #ff5c7a; box-shadow: 0 0 0 1mm #40463f; }
.panel-pic .btns { display: grid; grid-template-columns: repeat(3, 8mm); gap: 2mm; }
.panel-pic .btns span { width: 8mm; height: 8mm; border-radius: 50%; background: #289655; color: #fff; font-weight: 800;
                        display: flex; align-items: center; justify-content: center; font-size: 9pt; }
.qr-mascot { width: 30mm; margin: -12mm -2mm -6mm 0; }
.qr-notes { margin-top: 4mm; }
.notes-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 8mm; }
.notes-grid div { height: 9mm; border-bottom: 0.6pt solid #9aa39f; position: relative; }
.notes-grid span, .notes-lines span { position: absolute; top: 1.2mm; font-size: 7.5pt; color: #6b736f; }
.notes-lines { position: relative; height: 17.2mm; margin-top: 1mm;
               background: repeating-linear-gradient(180deg, transparent 0 8mm, #c9d4ce 8mm 8.6mm); }
"""


def cover_html():
    return """
<section class="cover">
  <div class="lines"></div>
  <div class="glow"></div>
  <img class="logo" src="logo_stacked.svg" alt="MisterOperator">
  <img class="mascot" src="mascot.svg" alt="Ope-chan">
  <h1>Operator&rsquo;s Manual</h1>
  <div class="sub">Locked-down arcade frontend for MiSTer FPGA &middot; Version %s</div>
  <div class="band"><span>Ope-chan <span class="jp">オペちゃん</span> says: hold OPERATOR to open the menu!</span>
  <span>github.com/alex-acsit/MisterOperator</span></div>
</section>
""" % html.escape(VERSION)


def contents_html(heads, pages):
    items = []
    for level, hid, text in heads:
        pg = pages.get(hid, "")
        items.append('<li class="l%d"><a href="#%s">%s</a><span class="dots"></span><span class="pg">%s</span></li>'
                     % (level, hid, html.escape(text), pg))
    return ('<section class="contents"><h1>Contents</h1><ul class="toc">'
            '<li class="l2"><a href="#quickref">Quick reference</a><span class="dots"></span><span class="pg">%s</span></li>'
            '%s</ul></section>' % (pages.get("quickref", ""), "".join(items)))


def page_html(inner):
    return ('<!doctype html><html><head><meta charset="utf-8"><title>MisterOperator manual</title>'
            '<base href="file://%s/"><style>%s</style></head><body>%s</body></html>' % (BRAND, CSS, inner))


def render(page, html_text, path, footer=True):
    tmp = os.path.join(tempfile.gettempdir(), "mo_manual_%d.html" % os.getpid())
    with open(tmp, "w") as f:
        f.write(html_text)
    page.goto("file://" + tmp)
    page.wait_for_load_state("networkidle")
    opts = dict(path=path, format="A4", print_background=True, prefer_css_page_size=True)
    if footer:
        opts.update(display_header_footer=True, header_template="<span></span>", footer_template=(
            '<div style="width:100%%;font-family:Inter,sans-serif;font-size:7.5pt;color:#7a837f;'
            'padding:0 17mm;display:flex;justify-content:space-between;">'
            '<span>MisterOperator %s &middot; Operator&rsquo;s manual</span>'
            '<span><span class="pageNumber"></span></span></div>' % html.escape(VERSION)))
    page.pdf(**opts)
    os.remove(tmp)


def find_pages(pdf_path, heads, offset):
    """Page number (as printed) of each heading, found in the rendered PDF."""
    want = [("quickref", "Quick reference")] + [(hid, text) for _, hid, text in heads]
    pages = {}
    with pdfplumber.open(pdf_path) as pdf:
        texts = [(p.extract_text() or "") for p in pdf.pages]
    # skip the contents pages themselves: start at the quick-reference card
    i = next((n for n, t in enumerate(texts) if "Keep this page with the cabinet." in t), 0)
    def norm(t):
        return re.sub(r"[^0-9a-z]+", "", t.lower())
    for hid, text in want:
        key = norm(text)
        for n in range(i, len(texts)):
            lines = [norm(l) for l in texts[n].splitlines()]
            if key in lines:
                pages[hid] = n + 1 + offset
                i = n
                break
    return pages


def main():
    logging.disable(logging.WARNING)       # pdfplumber's font warnings
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DOCS, "MisterOperator_Manual.pdf")
    # the mascot's head for the tip boxes
    with open(os.path.join(BRAND, "mascot.svg")) as f:
        svg = f.read()
    with open(os.path.join(BRAND, "mascot_head.svg"), "w") as f:
        f.write(svg.replace('viewBox="0 0 400 480" width="400" height="480"',
                            'viewBox="84 14 236 300" width="236" height="300"'))

    body = manual_body()
    heads = headings(body)
    quick = QUICK_REF.replace('<section class="quickref">', '<section class="quickref" id="quickref">')
    tmpdir = tempfile.mkdtemp()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        render(page, page_html(cover_html()), os.path.join(tmpdir, "cover.pdf"), footer=False)
        # pass 1 without page numbers, to find where each heading lands; the
        # contents page is the same length both times, so the numbers hold
        main_html = lambda pages: page_html(contents_html(heads, pages) + quick + body)
        render(page, main_html({}), os.path.join(tmpdir, "pass1.pdf"))
        pages = find_pages(os.path.join(tmpdir, "pass1.pdf"), heads, 0)
        render(page, main_html(pages), os.path.join(tmpdir, "main.pdf"))
        browser.close()

    w = PdfWriter()
    for part in ("cover.pdf", "main.pdf"):
        for p in PdfReader(os.path.join(tmpdir, part)).pages:
            w.add_page(p)
    # bookmarks: page n as printed is PDF page n (the cover comes first, unnumbered)
    w.add_outline_item("Cover", 0)
    w.add_outline_item("Contents", 1)
    if "quickref" in pages:
        w.add_outline_item("Quick reference", pages["quickref"])
    parent = None
    for level, hid, text in heads:
        if hid not in pages:
            continue
        if level == 2:
            parent = w.add_outline_item(text, pages[hid])
        else:
            w.add_outline_item(text, pages[hid], parent=parent)
    w.add_metadata({"/Title": "MisterOperator %s - Operator's Manual" % VERSION, "/Author": "MisterOperator",
                    "/Subject": "Locked-down arcade frontend for MiSTer FPGA"})
    w.page_mode = "/UseOutlines"
    with open(out, "wb") as f:
        w.write(f)
    missing = [t for _, hid, t in heads if hid not in pages]
    print("%s: %d pages%s" % (out, len(w.pages), (" (no page found for: %s)" % ", ".join(missing)) if missing else ""))


if __name__ == "__main__":
    main()
