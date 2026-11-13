# MisterOperator (Arcade Kiosk)

This copy lives on the SD card. Full README with screenshots:
https://github.com/alex-acsit/MisterOperator

**A locked-down, arcade-only frontend for MiSTer FPGA cabinets, built for retrobar operators.**

Players get a simple game list and one button to get back to it. The operator gets a
hidden button that opens an operator menu in the same look, for servicing. Nothing
else on the MiSTer is reachable while the cabinet is locked.

Current version: **2.1**, for 15 kHz CRTs and USB arcade encoders. It also works on HDMI.

## Features

**For players**
- A full-screen list of arcade games (`.mra` and `.mgl`), with genres, year, maker and
  optional box art
- One press of the **MENU** button quits any game straight back to the list
- Button 2 and 3 step through genres; Button 4 opens an **A–Z letter jump**
- **Coins put in on the list are held** as credits and inserted into the game the
  player picks once it has loaded
- The same panel layout (buttons 1–6) in every game

**For operators**
- Hold the **OPERATOR** button for a themed **operator menu**: volume, credits, demo and
  idle timings, NVRAM, screen and theme, play counts, a game's DIP switches, the log and
  reboot. Hold it again to lock. The stock MiSTer menu is still one item away.
- Players can't reach the MiSTer menu, settings, console cores or scripts
- **Attract mode:** after 2 minutes on the list, demo games play until someone
  touches the controls
- **Idle games quit themselves** after 5 minutes with no input
- Saves game NVRAM, so games like NBA Jam keep their settings instead of showing a
  CMOS error
- Restarts itself if it ever stops, and starts locked after a power cut

**For the cabinet**
- Landscape (YOKO) or vertical (TATE) screen layouts
- Show only horizontal or only vertical games, or lock the list to chosen genres
- Dark grey and green theme (or `phosphor` / `classic`), with every colour adjustable
- Python 3 standard library only, so there's nothing to install on the MiSTer

## Quick start

1. Download this repo (**Code → Download ZIP**) and copy the `arcade_kiosk` and `Scripts`
   folders to the root of the MiSTer's SD card.
2. On the MiSTer, run **Scripts → install_arcade_kiosk**.
3. Copy the lines from `arcade_kiosk/MiSTer_ini_additions.txt` into
   `/media/fat/MiSTer.ini`. These set 15 kHz output for the list and the terminal screen
   it draws on.
4. In the stock MiSTer menu, map your encoder as usual and assign the OSD **Menu**
   function to the button that will be the player MENU button.
5. Reboot. The list appears and asks you to press the **player MENU** button, then the
   **OPERATOR** button. That's it.

Settings live in `/media/fat/arcade_kiosk/kiosk.ini`. Each one is explained in the file.

## Controls

| Control | On the game list | In a game (locked) | Unlocked |
|---|---|---|---|
| Stick up / down | Move through the list | game | normal |
| Stick left / right | Previous / next letter | game | normal |
| Button 1 or Start | Play | game | normal |
| Button 2 / Button 3 | Next / previous genre | game | normal |
| Button 4 | Letter jump (A–Z picker) | game | normal |
| Coin | Add a credit | coin | coin |
| Player MENU | — | **Quit to the list** | Opens the MiSTer menu |
| OPERATOR (hold 1.5 s) | Operator menu | Quit to the operator menu | Back to the operator menu |

During attract mode, any button or stick movement returns to the list. A coin also
counts as a credit, and nothing pressed reaches the demo game.

### Operator menu

Hold OPERATOR on the list, or during a game, to open it. Move with the stick; left/right
changes a setting, and Button 1 picks an item. Button 2 or MENU goes back, and on the
main page that locks the cabinet, as does holding OPERATOR again. Changes are saved to
`kiosk.ini` straight away. Left alone for 5 minutes, it locks itself.

| Item | Does |
|---|---|
| Back to games | Lock and return to the list |
| Volume | 0–7 and mute (the MiSTer's master volume) |
| Credits | Add or remove free credits; Button 1 twice clears them |
| Demo after / Demo length | Attract mode timings |
| Idle game quit / Coin delay | The in-game timers |
| Save NVRAM | `once`, `always` or `off` |
| Screen / Theme | YOKO or TATE; green, phosphor or classic |
| Show games | All, YOKO only or TATE only (horizontal or vertical games) |
| Genres | Tick or untick each genre to show or hide its games; Show all / Hide all |
| Game settings | Runs the last game played unlocked, so MENU opens the MiSTer menu for its DIP switches and core options. Hold OPERATOR to come back |
| Play counts | How often each game has been played |
| Reset NVRAM | Wipe one game's saved settings and high scores (asks first) |
| Rescan games / View log | Pick up new `.mra` files; read the kiosk log |
| MiSTer menu | The stock MiSTer menu, for anything else. Hold OPERATOR to come back |
| MiSTer main | Whether the kiosk build of the MiSTer main program is running; installs it if not (see below) |
| Update kiosk | Shows the version; press to check GitHub, press again to install a newer one |
| Reboot | Restart the MiSTer (asks first) |

`operator_menu = 0` brings back the old behaviour, where OPERATOR goes straight to the
stock menu.

## Settings

The most-used `kiosk.ini` settings:

| Setting | Default | What it does |
|---|---|---|
| `screen` | `yoko` | `tate_cw` / `tate_ccw` for a monitor on its side |
| `orientation` | `all` | `horizontal` or `vertical` to list only those games (also in the operator menu) |
| `genres` / `exclude_genres` | — | Show only, or hide, these genres (e.g. `Shooter, Maze`) |
| `theme` | `green` | `phosphor` or `classic`; `color_<name> = #RRGGBB` for single colours |
| `title` | `ARCADE` | Heading on the list |
| `attract_idle_s` | `120` | Seconds on the list before demos start (`0` = off) |
| `attract_game_s` | `60` | Seconds per demo game |
| `game_idle_exit_s` | `300` | Quit a game after this long with no input (`0` = never) |
| `coin_buttons` | `KEY_5, KEY_6, BTN_SELECT, BTN_BASE3` | Codes your coin buttons send |
| `coin_delay_s` | `30` | Seconds after launch before held credits go in |
| `operator_hold_ms` | `1500` | Hold time for OPERATOR (`0` = single press) |
| `operator_menu` | `1` | Themed operator menu (`0` = straight to the stock menu) |
| `save_nvram` | `once` | `always` keeps high scores (brief menu flash on quit); `off` never saves |
| `standard_layout` | `1` | Same panel buttons 1–6 for every game (`0` = leave mappings alone) |
| `auto_update` | `0` | `1` = install new releases by itself (checked at boot and daily) |

<details>
<summary><b>More about each feature</b></summary>

**Vertical (TATE) monitor:** with `screen = tate_cw`, the list is drawn upright in a
portrait layout: list on top, picture and details below. If it comes out upside down,
use `screen = tate_ccw`. Pair it with `orientation = vertical`, and set `osd_rotate` in
`MiSTer.ini` so the stock menu is readable after unlocking. Each game core handles its
own rotation.

**Horizontal or vertical games only:** `orientation` uses the `<rotation>` in each
`.mra`, and a file with no rotation counts as horizontal. `arcadekiosk.py --scan` marks
each game H or V.

**Genres:** names come from each `.mra`'s `<category>`, and any part matches, so
`Vertical` picks up `Shooter / Vertical`. `Other` means games with no category. Run
`arcadekiosk.py --genres` to see the names your games use. Locked to one genre, the list
shows its name and the genre buttons do nothing.

**Letter jump:** Button 4 shows only the letters that have games. Move the stick to
choose (the list follows), then press any button, or leave it for 6 s. The buttons are
set with `genre_buttons`, `genre_back_buttons` and `letter_buttons`.

**Coins:** coins put in on the list or during a demo are held, shown as `CREDITS n`, and
pressed into the chosen game after `coin_delay_s`, on the controller each one came from.
If the player quits or the game fails before then, the credits are kept. They survive a
reboot, demos don't start while any are waiting, and `max_credits` (9) caps them. To find
your coin button's code, set `log_inputs = 1`, drop a coin and read
`/tmp/arcadekiosk.log`.

**Standard button layout:** every game uses the same panel buttons, laid out `4 5 6` over
`1 2 3`. Six-button games use 1–6 in order; 1–3 button games use 1, 2, 3; 4-button games
put game button 1 on panel 4 and buttons 2–4 on panel 1–3. Start and Coin are kept, and
Pause, Service, Test, Tilt and "Core credits" are left unmapped. Before each game starts,
the kiosk writes that game's MiSTer mapping
(`/media/fat/config/inputs/<setname>_input_<vid>_<pid>_v4.map`), taking your encoder's
buttons from its mapping in the MiSTer menu.
- `panel_layout = B,A,R,Y,X,L` says which pad buttons are panel 1–6, and `panel_start`
  and `panel_coin` work the same way.
- `layout_4 = 4,1,2,3` and the other `layout_N` lines set the order for each button count.
- `drop_buttons` lists the words to unmap.
- `arcadekiosk.py --layout` shows what every game gets.
- Earlier mappings are backed up to `map_backup/`. `--restore-maps` puts them back; then
  set `standard_layout = 0`.
- `.mgl` games and `.mra` files without a `<buttons>` list are left as they are.

**NVRAM (settings and high scores):** the MiSTer only saves a game's NVRAM when its own
menu opens. So on quitting a game whose `.mra` has `<nvram>`, the kiosk flashes that menu
for about 0.3 s. With `save_nvram = once`, this stops after the game has a good save, made
after at least a minute of play. Don't set `osd_lock` in `MiSTer.ini` if you use these
games, as it blocks the save.

**.mgl files:** listed and launched like `.mra` files (Neo Geo games, for example). A plain
`.mgl` shows its file name and is grouped under its core's name. For full details, add
`<name>`, `<year>`, `<manufacturer>`, `<category>` or `<rotation>` inside
`<mistergamedescription>`; the MiSTer ignores them. `include_mgl = 0` hides `.mgl` files.

**Attract mode:** `attract_list` (a file of chosen demo games), `attract_vertical` and
`attract_mute` fine-tune it. Demos move from game to game directly, without the stock
menu in between.

**Box art:** name screenshots after each `.mra` (or MAME set name), then run
`python tools/make_art.py screenshots/ art/` on your PC and copy the `.rgb` files to
`/media/fat/arcade_kiosk/art/`. Games without art show their initial.

</details>

## Updating

New versions are published as GitHub releases, and the kiosk can fetch them from any
MiSTer with an internet connection:

- **Operator menu → Update kiosk:** press once to check, again to install.
- **MiSTer Scripts menu → update_arcade_kiosk.** On a MiSTer without the kiosk, this same
  script downloads and installs it from scratch, so it's all you need to set up a new
  cabinet: copy `Scripts/update_arcade_kiosk.sh` to `/media/fat/Scripts` and run it.
- **Over SSH:** `arcadekiosk.py --update` (`--check` only looks; `--rollback` goes back).
- **Automatically:** `auto_update = 1` checks after boot and once a day. A new version
  installs in the background and takes over the next time nobody's playing.

Updates keep `kiosk.ini` (adding any new settings), credits, play counts and box art. The
previous version is saved in `arcade_kiosk/backup/`. A download that's damaged or doesn't
run is refused before anything changes. Updates come from `update_repo`; while that repo
is private, set `update_token` to a GitHub token with read access.

**Publishing a release:** set `VERSION` in `arcadekiosk.py`, commit, then tag it
(`git tag v2.1 && git push origin v2.1`). GitHub Actions runs the tests, builds
`MisterOperator_v2.1.zip` and publishes the release.

## Kiosk build of the MiSTer main program (optional)

With stock MiSTer, its own menu shows for a moment at boot and after each game, and
saving a game's NVRAM briefly flashes it open. The kiosk build of the MiSTer main program
removes all of that: the MiSTer goes straight to the kiosk, saves NVRAM silently on every
quit, and its menu can't be opened at all while the cabinet is locked. It's included as
`arcade_kiosk/MiSTer_kiosk`; install it from the operator menu (**MiSTer main**). The kiosk keeps the original, rolls back by itself if
the new one doesn't start, and keeps working if an update puts the stock one back. See
[`fork/`](fork/README.md) for details.

## Command line

Over SSH, `python3 /media/fat/arcade_kiosk/arcadekiosk.py` accepts:

| Option | Does |
|---|---|
| `--lock` / `--unlock` | Lock, or open the operator menu |
| `--stock` | Go to the stock MiSTer menu |
| `--status` | What the kiosk is doing, and its controllers |
| `--relearn` | Set the MENU and OPERATOR buttons again |
| `--scan` / `--genres` | List the games found / the genre names they use |
| `--devices` | List input devices |
| `--layout` / `--restore-maps` | Show each game's button layout / undo it |
| `--preview out.ppm` | Draw the list to an image file (`--raw` for TATE as sent) |
| `--update` / `--check` / `--rollback` | Install the latest release / just compare versions / go back one |

## How it works

- **Controllers:** the kiosk takes exclusive control of each USB controller and gives the
  MiSTer a virtual copy with the same IDs, so your mappings still apply. In a game,
  everything passes through except MENU, OPERATOR and held coins. On the list, nothing
  reaches the MiSTer.
- **The list:** it's drawn on the menu core's Linux framebuffer (the F9 terminal screen),
  set to 320×240 with the MiSTer's `fb_cmd1` command.
- **Launching:** games start with `load_core <game>` and quit with `load_core menu.rbf`,
  written to `/dev/MiSTer_cmd`. `/tmp/CORENAME` tells the kiosk what's running.
- **The brief stock-menu flash:** the MiSTer always shows its own menu for a moment when
  the menu core starts, and no setting turns that off. The kiosk takes over as soon as
  the MiSTer accepts commands, so this lasts well under a second. Going into a game, and
  between demos, never passes through it.

## First boot checklist

Most of this was built and tested off-hardware, so check these on the cabinet:

1. The list appears on the screen after boot.
2. Stick and Buttons 1–4 work on the list.
3. A game starts, plays with all buttons, and one MENU press returns to the list.
4. A coin put in on the list shows as a credit and goes into the next game after 30 s.
5. Holding OPERATOR opens the operator menu; holding it again locks.
6. In a locked game, no button or combination opens the MiSTer menu.

## Troubleshooting

Everything is logged to `/tmp/arcadekiosk.log`.

- **Stock menu shows instead of the list:** look for `framebuffer NOT confirmed` in the
  log. Check `fb_terminal=1` is in `MiSTer.ini`, or try `menu_settle_s = 1`.
- **List on HDMI but not the CRT:** the `[menu]` section of `MiSTer.ini` needs
  `vga_scaler=1` and the 15 kHz `video_mode` line. Try `composite_sync=1` for SCART/JAMMA.
- **CMOS error on NBA Jam or another Midway game:** you'll see it once. Clear it, play
  for a minute, then quit with MENU so the kiosk saves NVRAM.
- **Operator button does nothing:** it must be held for 1.5 s, and the list shows "KEEP
  HOLDING TO UNLOCK" while you do. Each press is logged as `operator button down`; if
  there's no such line, run `--relearn`.
- **Coins aren't held:** set `log_inputs = 1`, drop a coin, and add the code from the log
  to `coin_buttons`.
- **Controls stop working mid-game:** `can't take ... (in use by the MiSTer)` in the log
  means a controller reconnected during a game. The kiosk returns to the list to recover,
  and `--stock` over SSH always reaches the stock menu.
- **A controller is ignored:** run `--devices`.
- **Turn the kiosk off:** unlock, then remove the `# Arcade Kiosk` lines from
  `/media/fat/linux/user-startup.sh` and reboot.

## Repo layout

| Path | Goes to | Purpose |
|---|---|---|
| `arcade_kiosk/` | `/media/fat/arcade_kiosk/` | The kiosk, its settings (`kiosk.ini`) and boot script (`run.sh`) |
| `arcade_kiosk/MiSTer_ini_additions.txt` | lines for `MiSTer.ini` | 15 kHz menu output and related settings |
| `arcade_kiosk/tools/make_art.py` | your PC | Turns screenshots into box art |
| `Scripts/install_arcade_kiosk.sh` | `/media/fat/Scripts/` | One-time installer |
| `Scripts/update_arcade_kiosk.sh` | `/media/fat/Scripts/` | Installs or updates from GitHub |
| `tests/` | — | Off-hardware tests: `tests/run_tests.sh` (Python 3 only) |
| `docs/` | — | Screenshots |

The tests fake the MiSTer's command pipe, core name, framebuffer and input devices. They
check game scanning and filters, button setup, launching and quitting, lock/unlock,
attract mode, coins, NVRAM saving, screen rotation, button layouts and the operator menu.

## Licence

GPL-3.0, see [LICENSE](LICENSE). The bundled 8×8 font (`font8x8.py`) is public domain
(font8x8 by Daniel Hepper, from IBM public-domain VGA fonts).
