# MisterOperator manual

Version 2.4. MisterOperator turns a MiSTer FPGA into a locked-down, arcade-only cabinet:
players see a game list and one MENU button that always brings them back to it, and the
operator gets a hidden OPERATOR button that opens a service menu in the same look.

**Contents**

1. [What you need](#1-what-you-need)
2. [Installing](#2-installing)
3. [Using the cabinet](#3-using-the-cabinet)
4. [The operator menu](#4-the-operator-menu)
5. [Features in detail](#5-features-in-detail)
6. [Kiosk build of the MiSTer main program](#6-kiosk-build-of-the-mister-main-program)
7. [Updating](#7-updating)
8. [Settings reference (kiosk.ini)](#8-settings-reference-kioskini)
9. [Command line](#9-command-line)
10. [Files](#10-files)
11. [Troubleshooting](#11-troubleshooting)
12. [How it works](#12-how-it-works)
13. [Version history](#13-version-history)

---

## 1. What you need

- A MiSTer with an up-to-date SD card (`update_all` or `downloader` run at least once), so
  Python 3 and the arcade cores are present. Nothing else needs installing.
- Arcade games as `.mra` files in `/media/fat/_Arcade` (MiSTer's standard place). `.mgl`
  files there work too.
- A USB arcade encoder (or a keyboard encoder such as an I-PAC). Any number of them.
- Two spare buttons: a **player MENU** button on the control panel, and an **OPERATOR**
  button somewhere players can't reach (inside the coin door, for example).
- A 15 kHz CRT, or any HDMI screen. Landscape or vertical.
- For updating over the internet: a network connection on the MiSTer.

## 2. Installing

### 2.1 Getting the files onto the SD card

Either way leaves you with `/media/fat/arcade_kiosk/` and two scripts in
`/media/fat/Scripts/`.

**From the internet (once the GitHub repo is public):** copy
`Scripts/update_arcade_kiosk.sh` to `/media/fat/Scripts/` and run **update_arcade_kiosk**
from the MiSTer's Scripts menu. It downloads the latest release and runs the installer.

**By hand:** download `MisterOperator_v<version>.zip` from the GitHub releases page, unzip
it, and copy its `arcade_kiosk` and `Scripts` folders to the root of the SD card. Then run
**install_arcade_kiosk** from the Scripts menu.

The installer adds the kiosk to `/media/fat/linux/user-startup.sh`, so it starts at
every boot.

### 2.2 MiSTer.ini

Open `arcade_kiosk/MiSTer_ini_additions.txt` and copy its lines into
`/media/fat/MiSTer.ini` (back the file up first):

- `fb_terminal=1` (required): the kiosk draws on the menu core's terminal screen.
- `recents=0`: stops the MiSTer writing a "recent files" list on every launch.
- The `[menu]` section: 320×240 at 15 kHz on the analog output for the game list.
  Uncomment `composite_sync=1` for SCART, JAMMA or other monitors that need it.
- `osd_rotate=1` or `2`, only for a vertical monitor (see [5.1](#51-vertical-tate-monitors)).

Leave `osd_lock` unset; the kiosk does the locking, and `osd_lock` gets in the way of
saving game NVRAM with stock MiSTer.

### 2.3 Mapping your encoder

In the stock MiSTer menu (before the first reboot), map your encoder as you normally would,
and give the OSD **Menu** function to the button that will be the player MENU button.
The kiosk intercepts that button while the cabinet is locked, so players never see the
MiSTer menu.

### 2.4 First boot

Reboot. The game list appears and shows **BUTTON SETUP**:

1. Press the **player MENU** button.
2. Press the **OPERATOR** button (it has to be a different button).

Both are saved to `kiosk.ini` (`menu_button`, `operator_button`, and the controller each is
on). To set them again later: `arcadekiosk.py --relearn` over SSH.

### 2.5 Checklist

Check these once on the cabinet:

1. The game list appears after boot.
2. The stick and Buttons 1–4 work on the list.
3. A game starts and plays with every button, and one MENU press returns to the list.
4. A coin put in on the list shows as a credit, and goes into the next game after 30 s.
5. Holding OPERATOR opens the operator menu; holding it again locks.
6. In a locked game, no button or combination opens the MiSTer menu.

## 3. Using the cabinet

### 3.1 Controls

| Control | On the game list | In a game (locked) | Unlocked |
|---|---|---|---|
| Stick up / down | Move through the list | game | normal |
| Stick left / right | Previous / next letter | game | normal |
| Button 1 or Start | Play the selected game | game | normal |
| Button 2 / Button 3 | Next / previous genre | game | normal |
| Button 4 | Letter jump | game | normal |
| Coin | Add a credit | coin | coin |
| Player MENU | — | **Quit to the list** | Opens the MiSTer menu |
| OPERATOR (hold 1.5 s) | Operator menu | Quit to the operator menu | Back to the operator menu |

Keyboard encoders: Enter, Left Ctrl or 1 play; Left Alt or 2 next genre; Space or 3
previous genre; Left Shift or 4 letter jump; 5 or 6 coin. The arrow keys move.

### 3.2 The game list

The header shows the title (`title` setting) and the number of games, or the credits
waiting. Under it is the genre being shown. The selected game's picture (or its first
letter), maker, year and genre are on the right, or underneath on a vertical screen.
The footer shows "PRESS 1 TO PLAY" and the kiosk version.

When a game is chosen the list shows LOADING, and the game starts. If it doesn't start
within 12 s the list comes back with "COULD NOT START THAT GAME". After a game, the list
returns to the game that was just played (`remember_last`).

### 3.3 Genres and the letter jump

**Button 2** and **Button 3** step forwards and backwards through the genres of the games on
the list ("All games" first). If the list is limited to one genre, its name is shown and
the buttons do nothing.

**Button 4** opens the letter jump: a large letter with its neighbours, offering only letters
that have games ("#" for titles starting with a number). Move the stick to choose; the list
follows. Any button closes it, or it closes by itself after 6 s.

Left/right on the list (without the picker) jumps to the previous or next starting letter.

### 3.4 Coins and credits

A coin put in on the game list, or during a demo, isn't lost: it's held and shown as
**CREDITS n** in the header. When the player picks a game, the kiosk waits 30 s
(`coin_delay_s`) for the game to load, then presses coin in the game once per credit. Each
press goes to the controller the coin came from, so your coin mapping applies.

- Coins put in during a game go straight into the game as normal.
- If the player quits, or the game doesn't start, before the credits go in, they're kept
  for the next game.
- Credits survive a reboot, and at most 9 are held (`max_credits`).
- Demos don't start while credits are waiting.
- The operator can add free credits or clear them in the operator menu.

### 3.5 Attract mode

After 2 minutes on the game list with no input (`attract_idle_s`), demo games play, one
after another, for a minute each (`attract_game_s`). Any button or stick movement returns
to the list; that press doesn't reach the demo game. A coin put in during a demo is
banked as a credit.

### 3.6 Quitting a game

- **MENU** quits immediately (`menu_hold_ms = 0`), except in the first 3 s of a game
  (`exit_grace_s`), so a stray press during loading doesn't quit.
- A game nobody has touched for 5 minutes quits by itself (`game_idle_exit_s`), and the
  list shows "GAME ENDED / NO INPUT". Button presses, stick and d-pad moves, spinners,
  trackballs and paddles all count; small stick wobble doesn't.
- Games that keep settings or high scores in NVRAM are saved on the way out
  (see [5.5](#55-nvram-settings-and-high-scores)).

## 4. The operator menu

### 4.1 Opening, moving around, locking

Hold the **OPERATOR** button for 1.5 s (`operator_hold_ms`). On the game list it shows
"KEEP HOLDING TO UNLOCK" while you hold, and "HOLD THE OPERATOR BUTTON TO UNLOCK" if you let
go too early. During a game, holding OPERATOR quits the game (saving its NVRAM) and opens
the menu.

- **Stick up/down** moves.
- **Stick left/right** changes the setting on the selected row.
- **Button 1** selects.
- **Button 2, Button 3 or MENU** goes back. On the main page, that locks the cabinet.
- **Holding OPERATOR** locks the cabinet and returns to the game list.

Rows that do something drastic (clear credits, reset NVRAM, install the main program,
reboot) say **PRESS 1 AGAIN** before they act. Left alone for 5 minutes
(`operator_timeout_s`), the menu locks itself.

Every change is saved to `kiosk.ini` at once and keeps its comments.

### 4.2 Items

| Item | Values / what it does |
|---|---|
| **Back to games** | Lock and return to the game list. |
| **Volume** | 0–7, and mute below 0. The MiSTer's master volume. |
| **Credits** | Left/right removes or adds a free credit. Button 1 twice clears them all. |
| **Demo after** | Off, 30 s, 1, 2, 3, 5 or 10 min on the list before demos start. |
| **Demo length** | 30 s to 3 min per demo game. |
| **Idle game quit** | Never, 2, 3, 5, 10 or 15 min without input before a game quits. |
| **Coin delay** | 5–60 s between a game starting and held credits going in. |
| **Save NVRAM** | Once, Always or Off (see [5.5](#55-nvram-settings-and-high-scores)). |
| **Screen** | YOKO, TATE CW or TATE CCW (see [5.1](#51-vertical-tate-monitors)). Changes at once. |
| **Theme** | Green, Phosphor or Classic. Changes at once. |
| **Show games** | All, YOKO only (horizontal games) or TATE only (vertical games). |
| **Genres** | Opens the genre page (below). Shows how many genres are hidden. |
| **Game settings** | Runs the last game played *unlocked*: MENU then opens the MiSTer menu for that game's DIP switches and core options. Hold OPERATOR to come back. |
| **Play counts** | How many times each game has been played from the list, most played first. |
| **Reset NVRAM** | Lists the games with saved NVRAM. Button 1 twice wipes that game's settings and high scores. |
| **Rescan games** | Re-reads the arcade folder (after adding or removing games). |
| **Single game** | Locks the cabinet to one game (see [4.6](#46-single-game-mode)). Shows OFF or the game. |
| **Controller setup** | Sets up a controller, one press per control (see [4.7](#47-controller-setup)). |
| **Monitor test** | Full-screen test patterns for adjusting the monitor (see [4.5](#45-monitor-and-input-tests)). |
| **Input test** | Shows every button and stick as it's pressed (see [4.5](#45-monitor-and-input-tests)). |
| **View log** | The end of `/tmp/arcadekiosk.log`. Up/down scrolls, left/right pages. |
| **MiSTer menu** | The stock MiSTer menu, for anything else. Hold OPERATOR to come back. |
| **MiSTer main** | KIOSK, STOCK or OLD: which MiSTer main program is running. Installs or updates the kiosk build (see [6](#6-kiosk-build-of-the-mister-main-program)). |
| **Update kiosk** | Shows the version. Button 1 checks GitHub; if there's a newer one, Button 1 again installs it and the kiosk restarts into it. |
| **Reboot** | Restarts the MiSTer. |

### 4.3 The genre page

Lists every genre of your games with a tick box and its number of games. Button 1 ticks
or unticks the selected genre. **Show all** and **Hide all** are at the top. Unticked
genres disappear from the game list, from Button 2/3 cycling and from attract mode, once
you return to the list. (Hiding everything leaves the list empty; you'll get a warning.)

Genres here are each game's *main* genre, the first part of its category, so unticking
Shooter doesn't hide a Maze game whose category also mentions shooting. The choice is
saved as `hidden_genres`.

### 4.4 The stock MiSTer menu

`operator_menu = 0` brings back the original behaviour, where OPERATOR goes straight to
the stock MiSTer menu instead of the operator menu. `arcadekiosk.py --stock` over SSH always
gets there.

### 4.5 Monitor and input tests

**Monitor test** draws test patterns modelled on the 240p Test Suite's, at the list's own
320×240 resolution and refresh (15 kHz with the `[menu]` lines from `MiSTer.ini`). They go
straight onto the raster, so on a TATE monitor they fill the tube the same way; only the
name box is turned upright. Left/right or Button 1 changes the pattern, up/down its
variant; the name shows for a few seconds after each change. Button 2, MENU or a tap of
OPERATOR goes back. The operator menu doesn't lock itself for 30 minutes while a pattern
is up.

| Pattern | Variants | Use it for |
|---|---|---|
| Grid | 16, 20, 8, 32 px | Geometry, size and centring (red border and centre cross) |
| Convergence | Dots, crosses, red, green, blue grids | Static and dynamic convergence |
| Colour bars | 75%, 100% | Colour, tint and the colour decoder |
| Black/white level | Black, white | Brightness (lowest bars just visible) and contrast (top bars stay apart without blooming) |
| Grey ramps | 32 steps, 16 steps, smooth | Grey scale and colour balance, R/G/B and white |
| Purity | White, red, green, blue, 50% grey, black | Purity and degaussing; dead or stuck pixels on LCDs |
| Overscan | — | How much of the picture is hidden: frames at the edge, 2.5%, 5%, 7.5% and 10% |
| Linearity | With grid, without | Linearity (the circles should be round) |
| Sharpness | — | Focus: 1, 2 and 4 px stripes and a checkerboard |

**Input test** lists every controller the kiosk holds. Each one shows its stick as a 3×3
grid and a box for each button once it has been pressed, lit while held. Buttons with a
job in the kiosk are named by it (PLAY, GENRE+, GENRE-, LETTER, COIN, MENU, OPERATOR);
the rest go by their code name, which is what `kiosk.ini` and the log use. Stick and
analogue values and spinner/trackball counts are shown too, and the last press is at the
bottom. Every button is tested, MENU included, so to leave **hold any button for 3
seconds** or tap OPERATOR. (Holding OPERATOR locks the cabinet, as everywhere.)

### 4.6 Single-game mode

**Single game** opens a list of every game, with **OFF: the game list** at the top and a `*`
on the current choice. Button 1 picks one. From then on, whenever the cabinet is locked
(**Back to games**, after holding OPERATOR, after a power cut) it starts that game
straight away, with no game list:

- MENU does nothing, and the game never quits for being idle.
- If the game drops out on its own, it starts again.
- Coins go straight into the game.
- Hold OPERATOR for the operator menu as usual. **Back to games** goes back into the game.
- If the game won't start three times in a row, the game list shows with a message, so
  the cabinet isn't stuck reloading.

Set **Single game** to OFF to get the game list back. The choice is saved as
`single_game` in `kiosk.ini` (the path of the `.mra` or `.mgl`).

### 4.7 Controller setup

**Controller setup** sets up an arcade controller in one pass, without the MiSTer menu.
Press each control as the screen asks: stick up, down, left and right, then **buttons 1
to 6**, then **player Start**, then **Coin**. A picture of the panel lights up the control
to press next (4 5 6 on the top row, 1 2 3 underneath, as in the standard layout).
The first controller touched is the one being set up; set up player 2 by running it again
on the other controller.

- There are no MiSTer menu (OSD) or mouse steps, and buttons are asked for by number, not
  as B/A/R/Y/X/L.
- A tap of OPERATOR skips a step (buttons 2–6, Start and Coin can be skipped; the stick
  and button 1 can't). MENU cancels without changing anything. A control already used is
  refused.
- At the end, Button 1 or Start saves. A tap of OPERATOR starts again.

Saving writes the controller's MiSTer mapping (`config/inputs/input_<vid>_<pid>_v4.map`),
used by the MiSTer menu and as every core's default: buttons 1–6 go in B, A, R, Y, X, L,
Start in Start and Coin in Select, which is what `panel_layout` expects, so every game gets
the standard layout. The mapping's other entries (such as the MiSTer menu button) are kept,
the old file is backed up (`--restore-maps` puts it back), and games already set up for
the controller get the new directions. It also updates `kiosk.ini` so the game list
uses the same buttons: 1 and Start play, 2 and 3 change genre, 4 is the letter jump, Coin
adds a credit, and a stick on unusual keys moves the list (`dir_keys`).

## 5. Features in detail

### 5.1 Vertical (TATE) monitors

`screen = tate_cw` draws the list upright for a monitor turned on its side: the game list
across the top, the picture and details below. If it's upside down, use `tate_ccw`.
`screen = yoko` is a normal landscape monitor. For a vertical cabinet, also:

- set **Show games** to TATE only (or `orientation = vertical`), so only vertical games
  are listed;
- set `osd_rotate=1` or `2` in `MiSTer.ini`, so the MiSTer's own menu (Game settings,
  MiSTer menu) is readable.

The games themselves are rotated by their cores, as usual.

### 5.2 Choosing which games are listed

All of these combine:

| Setting | Effect |
|---|---|
| `arcade_dir`, `include_subdirs`, `exclude_dirs` | Where to look for `.mra`/`.mgl` files. |
| `game_list` | A text file of the only games to show, one file name per line. |
| `orientation` (**Show games**) | `all`, `horizontal` (YOKO) or `vertical` (TATE), from each `.mra`'s `<rotation>`. No rotation counts as horizontal. |
| `genres` | Show only these genres, comma-separated. Any part of a category matches, so `Vertical` picks up `Shooter / Vertical`. `Other` means games with no category. |
| `exclude_genres` | Hide these genres (any part matches). |
| `hidden_genres` (**Genres** page) | Hide games by main genre. |
| `include_mgl` | `0` hides `.mgl` files. |

`arcadekiosk.py --scan` lists every game found with its year, genre, H/V and MRA/MGL.
`arcadekiosk.py --genres` lists the genre names your games use.

`short_names = 1` shows "Pac-Man" rather than "Pac-Man (Midway)", unless two sets would
then look the same.

### 5.3 .mgl files

`.mgl` (MiSTer Game Launcher) files in the arcade folder are listed and launched like `.mra`
files (Neo Geo games, for example). A plain `.mgl` shows its file name and is grouped under
its core's name as its genre. For full details, add any of `<name>`, `<year>`,
`<manufacturer>`, `<category>` and `<rotation>` inside `<mistergamedescription>`; the MiSTer
ignores them, so the file still works everywhere else.

### 5.4 Standard button layout

Every game uses the same panel buttons, laid out as two rows of three:

```
4 5 6
1 2 3
```

Six-button games use 1–6 in order; one- to three-button games use 1, 2, 3; four-button
games put game button 1 on panel 4 and buttons 2–4 on panel 1–3. Start and Coin are kept,
and Pause, Service, Test, Tilt and "Core credits" are left unmapped, so players can't reach
them. Before each game starts, the kiosk writes that game's MiSTer button mapping, taking
your encoder's buttons from the mapping you made in the MiSTer menu.

- **Controller setup** in the operator menu maps your encoder for this in one pass.
- `panel_layout = B,A,R,Y,X,L` names the pad buttons that are panel 1–6 in your encoder's
  MiSTer mapping; `panel_start` and `panel_coin` do the same for Start and Coin.
- `layout_1` … `layout_6` set the order for games with that many buttons.
- `drop_buttons` lists the button names (words) that are left unmapped.
- `arcadekiosk.py --layout` shows what every game gets.
- Earlier mappings are backed up to `arcade_kiosk/map_backup/`. To undo it:
  `arcadekiosk.py --restore-maps`, then set `standard_layout = 0`.
- `.mgl` games, and `.mra` files without a `<buttons>` list, are left as they are. A game
  mapped by hand in the MiSTer menu (while unlocked) is overwritten at its next start.

### 5.5 NVRAM (settings and high scores)

Some games (NBA Jam, Mortal Kombat and other Midway games, for example) keep their settings
and high scores in NVRAM, marked by `<nvram>` in their `.mra`. Without a saved copy, they
show a CMOS error and reset on every start.

**With the stock MiSTer main program**, NVRAM is only saved when the MiSTer's own menu opens.
So when such a game is quit, the kiosk flashes that menu open for about 0.3 s
(`nvram_save_s`). `save_nvram` decides how often:

- `always` (default): on every quit, so high scores are kept. With the stock main program
  there's a flash each time.
- `once`: until the game has a good save (one made after at least a minute of play), then
  no more flashes. New high scores aren't kept after that.
- `off`: never.

**With the kiosk build** (section 6), NVRAM is saved silently on every quit, so `once`
and `always` both mean every time.

Updating to 2.4 moves an install still on the old default (`once`) to `always`, one time;
choose otherwise in **Save NVRAM** afterwards and it stays.

**High scores in cores with "Autosave Hiscores".** Many arcade cores (Pac-Man, Galaga,
Donkey Kong, Centipede, Robotron and others) keep high scores through an OSD option,
**Autosave Hiscores**, which is usually off. The kiosk build switches it on in every core
that has it, as the core loads, and saves that in the core's settings, so high scores are
written to `config/nvram/` and kept. With the stock main program, switch it on by hand
once per core: run the game from **Game settings**, open the MiSTer menu with MENU, set
**Autosave Hiscores** to On and save.

### 5.6 Themes and colours

`theme = green` (dark grey with green highlights and white text), `phosphor` (all-green
terminal) or `classic` (pink and amber on navy). Any single colour can be overridden with
`color_<name> = #RRGGBB`: `bg`, `panel`, `line`, `accent` (selection bar, rules, borders),
`title`, `info` (genre text), `text` (game names), `dim`, `select` (name on the selection
bar) and `white` (message text). `title` and `footer_play` set the words.

### 5.7 Box art

Name screenshots or flyers after each `.mra` file (or its MAME set name), then run
`python tools/make_art.py screenshots/ art/` on a PC (needs Pillow) and copy the `.rgb`
files to `/media/fat/arcade_kiosk/art/`. Games without art show their first letter.

## 6. Kiosk build of the MiSTer main program

The MiSTer's own menu belongs to its main program, `/media/fat/MiSTer`. With the stock
program, that menu shows for a moment at boot and after each game, and the NVRAM save
flashes it open. MisterOperator includes a lightly patched build, `arcade_kiosk/MiSTer_kiosk`
([source](https://github.com/alex-acsit/Main_MiSTer)), that removes all of that:

| | Stock MiSTer main | Kiosk build |
|---|---|---|
| Boot, and after a game | Stock menu for a moment, then the kiosk | Straight to the kiosk |
| Saving NVRAM | Menu flashes open on every quit | Silent, every time |
| Autosave Hiscores (core option) | As set in each core (usually Off) | Switched On in every core that has it |
| MiSTer menu while locked | Blocked by the kiosk intercepting buttons | Can't be opened at all |
| Volume changes | MiSTer volume bar pops up | Only the operator menu's own bar |

It only behaves differently while the kiosk is running. Without the kiosk, it's stock
MiSTer.

**Installing:** operator menu → **MiSTer main** shows `STOCK: 1 INSTALLS`. Press Button 1
twice. The kiosk keeps the original as `/media/fat/MiSTer.stock`, installs the kiosk build,
and reboots; the row then shows `KIOSK`. When a kiosk update brings a newer build, the row
shows `OLD: 1 UPDATES`.

**Safety net:** if the new program hasn't started within 90 s of that reboot, the kiosk puts
`MiSTer.stock` back and reboots again.

**MiSTer updates:** `update_all` and `downloader` put the stock program back. Nothing breaks:
the kiosk carries on as it does with stock MiSTer, and the row shows `STOCK` until you
install the kiosk build again.

**Removing it:** copy `/media/fat/MiSTer.stock` back over `/media/fat/MiSTer`, and delete
`/media/fat/config/kiosk_boot`.

## 7. Updating

New versions are published as releases on GitHub. Four ways to install the latest:

- **Operator menu → Update kiosk.** Button 1 checks; Button 1 again installs. The kiosk
  restarts into the new version.
- **Scripts menu → update_arcade_kiosk.** Shows its progress on screen. It also upgrades
  versions from before the updater existed (2.0.1 and earlier).
- **SSH:** `python3 /media/fat/arcade_kiosk/arcadekiosk.py --update` (`--check` only
  compares versions; `--force` reinstalls the latest).
- **Automatically:** `auto_update = 1` checks a minute after boot and then once a day. A new
  version is installed in the background, and the kiosk switches to it the next time
  nobody's playing.

An update keeps `kiosk.ini` (adding any new settings, with their comments), credits, play
counts, box art and saved NVRAM. A download that's damaged, or a new version that doesn't
run, is refused before anything changes. The version being replaced is saved in
`arcade_kiosk/backup/` (the last three are kept); `arcadekiosk.py --rollback` goes back one.

If an update includes a newer kiosk build of the MiSTer main program, install it from the
operator menu (**MiSTer main** shows `OLD: 1 UPDATES`).

Updates come from the GitHub repo in `update_repo`. While that repo is private, set
`update_token` to a GitHub token with read access to it.

## 8. Settings reference (kiosk.ini)

`/media/fat/arcade_kiosk/kiosk.ini`. Each setting is explained in the file itself. Lines
starting with `;` are comments, and so is anything after a `;` on a line. Restart the kiosk
(or reboot) after editing by hand; the operator menu applies its changes itself.

**Games**

| Setting | Default | |
|---|---|---|
| `arcade_dir` | `/media/fat/_Arcade` | Where the `.mra`/`.mgl` files are |
| `include_subdirs` | `0` | `1` = also look in sub-folders |
| `exclude_dirs` | `_alternatives,cores,_Organized` | Sub-folders to skip |
| `include_mgl` | `1` | `0` = ignore `.mgl` files |
| `game_list` | | File listing the only games to show |
| `orientation` | `all` | `horizontal` / `vertical` games only |
| `genres` | | Only these genres |
| `exclude_genres` | | Not these genres |
| `hidden_genres` | | Main genres hidden from the operator menu |
| `short_names` | `1` | Drop the "(set name)" part of titles where unambiguous |
| `remember_last` | `1` | Return to the last game played |

**Screen**

| Setting | Default | |
|---|---|---|
| `screen` | `yoko` | `tate_cw` / `tate_ccw` for a vertical monitor |
| `single_game` | blank | Lock the cabinet to this game (path of an `.mra`/`.mgl`) |
| `dir_keys` | blank | Extra keys that move the list, e.g. `KEY_R:up` (set by **Controller setup**) |
| `theme` | `green` | `phosphor`, `classic`; plus `color_<name> = #RRGGBB` |
| `title` | `ARCADE` | Heading on the list |
| `footer_play` | `PRESS 1 TO PLAY` | Blinking footer text |
| `art_dir` | `/media/fat/arcade_kiosk/art` | Box art folder |
| `fb_width`, `fb_height` | `320`, `240` | Resolution of the list |

**Buttons and controllers**

| Setting | Default | |
|---|---|---|
| `menu_button`, `menu_device` | (learned) | Player MENU button, and its controller |
| `operator_button`, `operator_device` | (learned) | OPERATOR button, and its controller |
| `operator_hold_ms` | `1500` | Hold time for OPERATOR (`0` = single press) |
| `menu_hold_ms` | `0` | Hold time for MENU to quit (`0` = single press) |
| `exit_grace_s` | `3` | MENU ignored for this long after a game starts |
| `launch_buttons` | `BTN_TRIGGER,BTN_SOUTH,BTN_START,KEY_ENTER,KEY_LEFTCTRL,KEY_1` | Play |
| `genre_buttons` | `BTN_THUMB,BTN_EAST,KEY_LEFTALT,KEY_2` | Next genre |
| `genre_back_buttons` | `BTN_THUMB2,BTN_NORTH,KEY_SPACE,KEY_3` | Previous genre |
| `letter_buttons` | `BTN_TOP,BTN_WEST,KEY_LEFTSHIFT,KEY_4` | Letter jump |
| `ignore_devices` | | Controllers the kiosk leaves alone (vid:pid or name) |
| `log_inputs` | `0` | `1` = log every button press (to find codes) |

**Coins**

| Setting | Default | |
|---|---|---|
| `coin_buttons` | `KEY_5,KEY_6,BTN_SELECT,BTN_BASE3` | Codes your coin buttons send |
| `coin_delay_s` | `30` | Seconds after a game starts before held credits go in |
| `max_credits` | `9` | Most credits held at once |

**Operator and locking**

| Setting | Default | |
|---|---|---|
| `operator_menu` | `1` | `0` = OPERATOR opens the stock MiSTer menu instead |
| `operator_timeout_s` | `300` | Operator menu locks itself after this long (`0` = never) |
| `lock_on_boot` | `1` | Always start locked after power-on |

**Games running**

| Setting | Default | |
|---|---|---|
| `game_idle_exit_s` | `300` | Quit a game after this long with no input (`0` = never) |
| `save_nvram` | `always` | `once` or `off` |
| `nvram_save_s` | `0.3` | How long the MiSTer menu stays open to save NVRAM (stock main) |
| `launch_timeout_s` | `12` | Give up on a game that hasn't started after this long |

**Attract mode**

| Setting | Default | |
|---|---|---|
| `attract_idle_s` | `120` | Seconds on the list before demos (`0` = off) |
| `attract_game_s` | `60` | Seconds per demo game |
| `attract_list` | | File of the only games to use as demos |
| `attract_vertical` | `0` | Include vertical games in demos when showing all games |
| `attract_mute` | `0` | `1` = mute demos |

**Standard button layout**

| Setting | Default | |
|---|---|---|
| `standard_layout` | `1` | `0` = leave games' button mappings alone |
| `panel_layout` | `B,A,R,Y,X,L` | Pad buttons that are panel 1–6 |
| `panel_start`, `panel_coin` | `Start`, `Select` | Pad buttons for Start and Coin |
| `drop_buttons` | `pause,service,test,tilt,core credits,reset,freeze,slam` | Left unmapped |
| `layout_1` … `layout_6` | `1` … `1,2,3,4,5,6` (`layout_4` = `4,1,2,3`) | Panel order by button count |

**Updates**

| Setting | Default | |
|---|---|---|
| `update_repo` | `alex-acsit/MisterOperator` | Where releases come from |
| `update_token` | | GitHub token, only while that repo is private |
| `auto_update` | `0` | `1` = install new releases by itself |

**Advanced**

| Setting | Default | |
|---|---|---|
| `menu_settle_s` | `0` | Extra wait before taking over the screen from the MiSTer menu |

## 9. Command line

Over SSH (`root` / `1` by default), `python3 /media/fat/arcade_kiosk/arcadekiosk.py` takes:

| Option | Does |
|---|---|
| `--lock` | Lock and return to the game list |
| `--unlock` | Open the operator menu |
| `--stock` | Go to the stock MiSTer menu |
| `--status` | What the kiosk is doing, which core is running, its controllers |
| `--relearn` | Forget the MENU and OPERATOR buttons and ask for them again |
| `--rescan` | Re-read the arcade folder |
| `--scan` | List the games found (year, genre, H/V, MRA/MGL, path) |
| `--genres` | List the genre names your games use, with counts |
| `--devices` | List input devices and whether the kiosk uses them |
| `--layout` / `--restore-maps` | Show each game's button layout / restore the mappings from before |
| `--preview out.ppm` | Draw the list to an image (`--demo` for sample games, `--raw` for TATE as sent) |
| `--update` / `--check` / `--rollback` | Install the latest release / compare versions / go back one |

`/media/fat/arcade_kiosk/run.sh start|stop|restart` starts, stops or restarts the kiosk.

## 10. Files

**On the SD card**

| Path | |
|---|---|
| `arcade_kiosk/arcadekiosk.py`, `font8x8.py`, `monitor_test.py` | The kiosk (`monitor_test.py`: test patterns, input test) |
| `arcade_kiosk/kiosk.ini` | Settings |
| `arcade_kiosk/state.json` | Lock state, credits, play counts, last game played |
| `arcade_kiosk/run.sh` | Starts the kiosk at boot and restarts it if it stops |
| `arcade_kiosk/MiSTer_kiosk` | Kiosk build of the MiSTer main program |
| `arcade_kiosk/MiSTer_ini_additions.txt` | Lines for `MiSTer.ini` |
| `arcade_kiosk/MANUAL.md` | This manual |
| `arcade_kiosk/art/` | Box art |
| `arcade_kiosk/backup/` | Previous versions (from updates) |
| `arcade_kiosk/map_backup/` | Button mappings from before the standard layout |
| `arcade_kiosk/tools/make_art.py` | Box art converter (run on a PC) |
| `Scripts/install_arcade_kiosk.sh` | Installer |
| `Scripts/update_arcade_kiosk.sh` | Installs or updates from GitHub |
| `linux/user-startup.sh` | Starts the kiosk at boot (the `# Arcade Kiosk` lines) |
| `config/kiosk_boot` | Tells the kiosk build to skip its menu at power-on |
| `config/nvram/` | Saved NVRAM of games |
| `MiSTer.stock` | The original MiSTer main program, after installing the kiosk build |

**While running (`/tmp`, cleared at power-off)**

| Path | |
|---|---|
| `/tmp/arcadekiosk.log` | The log |
| `/tmp/arcadekiosk.status` | What `--status` shows |
| `/tmp/kiosk_active` | Present while the kiosk owns the screen (read by the kiosk build) |
| `/tmp/MiSTer_features` | Written by the kiosk build at start-up |

## 11. Troubleshooting

Everything is written to `/tmp/arcadekiosk.log` (also readable in **View log**).

| Problem | What to do |
|---|---|
| The MiSTer menu shows instead of the list | Check `fb_terminal=1` is in `MiSTer.ini`. Look for `framebuffer NOT confirmed` in the log; try `menu_settle_s = 1`. With the kiosk build, the kiosk reloads the menu core once if the menu won't give way. |
| The list shows on HDMI but not the CRT | The `[menu]` section of `MiSTer.ini` needs `vga_scaler=1` and the 15 kHz `video_mode` line. Try `composite_sync=1` for SCART/JAMMA. |
| The list is upside down on a vertical screen | Switch **Screen** between TATE CW and TATE CCW. |
| OPERATOR does nothing | It has to be held for 1.5 s. Each press is logged as `operator button down`; if there's no such line, run `--relearn`. |
| Wrong buttons for MENU / OPERATOR | `--relearn`, or set `log_inputs = 1`, press the buttons and read their names in the log. |
| A controller is ignored | `--devices`. Check it isn't in `ignore_devices`. |
| Controls stop working mid-game | `can't take ... (in use by the MiSTer)` in the log means a controller was reconnected during a game. The kiosk goes back to the list to recover. |
| Coins aren't held as credits | Set `log_inputs = 1`, drop a coin, and add the code from the log to `coin_buttons`. |
| CMOS error on NBA Jam or another Midway game | It appears once. Play for at least a minute, then quit with MENU so NVRAM is saved. **Reset NVRAM** starts a game afresh. |
| A game is missing from the list | Check **Show games**, the **Genres** page, `genres`/`exclude_genres` and `game_list`. `--scan` lists what's found. |
| The MiSTer menu seems blocked with the kiosk stopped | `rm /tmp/kiosk_active` over SSH, or reboot. |
| The kiosk build won't start | The safety net restores `MiSTer.stock` within 90 s. By hand: copy `MiSTer.stock` over `MiSTer` on the SD card. |
| "Update check failed" | Check the MiSTer's network. While the GitHub repo is private, set `update_token`. The log has the details. |
| A button or stick seems dead | **Input test** shows whether the kiosk sees it, and its code name. |
| A button does the wrong thing in games | Run **Controller setup** for that controller. |
| The cabinet keeps starting the same game | **Single game** is on. Hold OPERATOR, set **Single game** to OFF. |
| A new version misbehaves | `--rollback`, or copy a folder from `arcade_kiosk/backup/` back. |
| Turn the kiosk off for good | Remove the `# Arcade Kiosk` lines from `/media/fat/linux/user-startup.sh`, and remove the kiosk build (section 6). Reboot. |

## 12. How it works

- **Controllers:** the kiosk takes exclusive control of every USB controller and gives the
  MiSTer a virtual copy with the same IDs, so your mappings still apply. During a game,
  everything passes through except MENU and OPERATOR (and the coin presses it adds). On the
  list and in the operator menu, nothing reaches the MiSTer.
- **Screen:** the list and the operator menu are drawn on the menu core's Linux framebuffer
  (the F9 terminal screen), switched to 320×240 with the MiSTer's `fb_cmd1` command. In TATE
  they're drawn upright and turned onto the screen.
- **Games:** started with `load_core <game>` and quit with `load_core menu.rbf`, written to
  `/dev/MiSTer_cmd`. `/tmp/CORENAME` tells the kiosk what's running.
- **The kiosk build** watches for `/tmp/kiosk_active` and `config/kiosk_boot`, and adds a
  `save_nvram` command. See `fork/README.md` in the repo.

## 13. Version history

| Version | Date | Changes |
|---|---|---|
| 2.4 | 2026-11-14 | NVRAM saved on every quit by default (`save_nvram = always`; older installs moved over once). Kiosk build switches on every core's "Autosave Hiscores" option. |
| 2.3 | 2026-11-14 | Single-game mode. Controller setup wizard (buttons 1–6, Start, Coin; no MiSTer menu or mouse steps). The 240p Test Suite launcher is gone again. |
| 2.2 | 2026-11-14 | Operator menu: Monitor test (nine test patterns) and Input test. |
| 2.1.1 | 2026-11-13 | The update script can replace itself safely, and upgrades 2.0.1 installs directly. |
| 2.1 | 2026-11-13 | Operator menu: Show games (YOKO/TATE only) and a Genres page. Version in the footer instead of button hints. Updates over the internet (operator menu, Scripts menu, `--update`, `auto_update`). `#RRGGBB` colours in `kiosk.ini` now work. |
| 2.0.1 | 2026-11-13 | Fixed booting to the MiSTer menu with the kiosk build; `.mgl` games work with it. |
| 2.0 | 2026-11-13 | Kiosk build of the MiSTer main program: no stock menu, silent NVRAM saves, real lock. |
| 1.9 | 2026-11-13 | Themed operator menu replaces the stock menu on unlock. Play counts. |
| 1.8 | 2026-11-08 | Coins on the list are held as credits. Previous-genre and letter-jump buttons. Attract after 2 minutes. Standard 1–6 button layout. |
| 1.7 | 2026-11-07 | Vertical (TATE) screen layout. |
| 1.6 | 2026-11-06 | NVRAM saved on quit (no more CMOS errors). More robust controller handling. |
| 1.5 | 2026-11-06 | Idle games quit after 5 minutes. Green theme. |
| 1.4 | 2026-11-03 | `.mgl` files listed and launched. |
| 1.3 | 2026-11-02 | Lock the list to chosen genres. |
| 1.2 | 2026-11-01 | Horizontal-only / vertical-only game lists. |
| 1.1 | 2026-11-01 | Attract mode. Faster takeover from the MiSTer menu. |
| 1.0 | 2026-10-31 | First version: locked game list, one-button return, operator lock. |
