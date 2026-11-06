# Arcade Kiosk for MiSTer FPGA

A locked-down, arcade-only frontend for a MiSTer cabinet.

- **Players** pick an arcade game from a full-screen list, play it, and press the
  **player MENU button once** to go straight back to the list.
- **The operator** holds the **OPERATOR button** (1.5 s) to unlock the stock MiSTer
  menu for servicing, and holds it again to lock the cabinet.
- While locked, players can't reach the MiSTer OSD, settings, console cores or scripts.
- **Idle games end themselves:** if nobody touches the controls for 5 minutes during a
  game, it quits back to the list (`game_idle_exit_s`).
- **Attract mode:** after 90 s with no input on the list, demo games play one after
  another; any button or stick movement goes back to the list.

Built for a 15 kHz CRT (320×240 game list) and USB arcade encoders.

## What's in the folder

| File | Goes to | Purpose |
|---|---|---|
| `arcadekiosk.py`, `font8x8.py` | `/media/fat/arcade_kiosk/` | The kiosk (Python 3, standard library only) |
| `kiosk.ini` | `/media/fat/arcade_kiosk/` | Settings |
| `run.sh` | `/media/fat/arcade_kiosk/` | Starts the kiosk at boot and restarts it if it stops |
| `install_arcade_kiosk.sh` | `/media/fat/Scripts/` | One-time installer |
| `MiSTer_ini_additions.txt` | (copy lines into `MiSTer.ini`) | 15 kHz output for the game list |
| `tools/make_art.py` | your PC | Optional: turns screenshots into box art |

## Install

1. Copy the `arcade_kiosk` folder to the root of the SD card so you have
   `/media/fat/arcade_kiosk/arcadekiosk.py`.
2. Copy `install_arcade_kiosk.sh` to `/media/fat/Scripts/` and run it from the
   MiSTer **Scripts** menu (or over SSH).
3. Add the lines from `MiSTer_ini_additions.txt` to `/media/fat/MiSTer.ini`.
4. **Controller mapping:** in the stock MiSTer menu, map your encoder as usual and
   assign the OSD **Menu** function to the button you'll use as the player MENU
   button. The kiosk intercepts that button when locked, so players can't open the
   OSD; when unlocked, the same button opens the OSD for the operator.
5. Reboot. The game list appears and asks you to press the **player MENU** button,
   then the **OPERATOR** button. They're saved to `kiosk.ini`.

## Using it

| Control | Game list | In a game (locked) | Unlocked |
|---|---|---|---|
| Stick up / down | Move | game | normal |
| Stick left / right | Jump to previous / next letter | game | normal |
| Button 1 or Start | Play | game | normal |
| Button 2 | Next genre | game | normal |
| Player MENU | — | **Quit to game list** | Opens MiSTer OSD |
| OPERATOR (hold) | Unlock | Unlock | Lock and return to list |

During attract mode, any button or stick movement returns to the game list. Nothing
you press reaches the demo game.

Over SSH: `arcadekiosk.py --lock`, `--unlock`, `--status`, `--scan` (list the games
found), `--devices` (list controllers), `--relearn` (set the two buttons again).

## Customising

Everything is in `kiosk.ini`: title text, which games show (`game_list` whitelist,
`orientation`), button names, hold times, and whether a hold is needed to quit a game.

**Horizontal or vertical only:** set `orientation = horizontal` for a landscape monitor
or `orientation = vertical` for a monitor turned on its side (`all` shows both). It uses
the `<rotation>` in each `.mra`; a file with no rotation counts as horizontal. Attract mode
follows the same setting. `arcadekiosk.py --scan` lists each game with H or V so you can
check how a game is classed. (The older `hide_vertical = 1` still works and means
`horizontal`.)

**Colours:** `theme = green` (default, phosphor green) or `theme = classic` (the
original pink and amber on navy). Any colour can be changed on its own, e.g.
`color_accent = #00C850` for the selection bar; `kiosk.ini` lists every colour name.

**Idle games:** `game_idle_exit_s = 300` quits a game back to the list after 5 minutes
with no input (`0` = never). Button presses, stick or d-pad moves, spinners, trackballs
and paddles all count; small stick wobble around centre doesn't. The list then shows
"GAME ENDED / NO INPUT" for a few seconds. It only applies while locked.

**.mgl files:** `.mgl` (MiSTer Game Launcher) files in the arcade folder are listed and
launched just like `.mra` files (for example Neo Geo games). A plain `.mgl` shows its file
name and is grouped under its core's name as the genre (e.g. `Neogeo`). To show full
details, add any of `<name>`, `<year>`, `<manufacturer>`, `<category>` and `<rotation>`
inside `<mistergamedescription>`. The MiSTer ignores those tags, so the file still works
everywhere else. `include_mgl = 0` hides them. `--scan` marks each game MRA or MGL.

**Lock to genres:** `genres = Shooter, Maze` shows only those genres (comma-separated,
not case-sensitive); `exclude_genres = Mahjong, Quiz` hides genres instead. Names come
from the `<category>` in each `.mra`, and any part matches, so `Vertical` also picks up
`Shooter / Vertical`. `Other` means games with no category. Run
`arcadekiosk.py --genres` to list the genre names your games actually use. Locked to one
genre, the list shows that genre's name and Button 2 does nothing; with several, Button 2
cycles through only those. Attract mode and `orientation` combine with it.

**Attract mode:** `attract_idle_s` (seconds before demos start, `0` turns it off),
`attract_game_s` (seconds per demo), `attract_list` (a file of chosen demo games),
`attract_vertical` and `attract_mute`. Demos move from game to game directly, so the
stock menu never appears between them.

**Box art (optional):** collect screenshots named after each `.mra` (or MAME set name),
then on your PC run `python tools/make_art.py screenshots/ art/` and copy the `.rgb`
files to `/media/fat/arcade_kiosk/art/`. Games without art show their initial.

## How it works

- The kiosk takes exclusive control of each USB controller and gives the MiSTer a
  virtual copy with the same IDs, so your existing mappings still apply. During a
  game, every press is passed through except the MENU and OPERATOR buttons; on the
  game list, nothing reaches the MiSTer.
- The game list is drawn on the menu core's Linux framebuffer (the screen the F9
  terminal uses), switched to 320×240 with the MiSTer's `fb_cmd1` command.
- Games start with `load_core <file>.mra` and quit with `load_core menu.rbf`, both
  written to `/dev/MiSTer_cmd`. `/tmp/CORENAME` tells the kiosk what's running.
- If a game fails to load, the list comes back with a message. If the kiosk itself
  stops, `run.sh` restarts it within a couple of seconds.

### Why the stock menu flashes briefly

The MiSTer always opens its own menu when the menu core starts, at boot and after
quitting a game, and no setting turns that off. The kiosk takes over the moment the
new menu core is ready to accept commands, so the stock menu shows for well under a
second instead of several. Going from the list into a game, and between demo games,
never passes through the menu at all. Removing the flash completely would need a
modified build of the MiSTer main program.

## First-boot checklist on the cabinet

This was built and tested off-hardware, so check these on the real machine:

1. The game list appears on the CRT after boot (not the stock menu or a text console).
2. Stick, Button 1 and Button 2 work on the list.
3. A game starts, plays with all buttons, and one MENU press returns to the list.
4. Holding OPERATOR unlocks to the stock menu; holding it again locks.
5. In a locked game, no button (or combination) opens the MiSTer OSD.

## Troubleshooting

Everything is logged to `/tmp/arcadekiosk.log`.

- **Stock menu shows instead of the list:** check the log for `framebuffer NOT confirmed`.
  Make sure `fb_terminal=1` is in `MiSTer.ini`. Try raising `menu_settle_s` to `1`.
  The log line `framebuffer ready in …s` shows how long the takeover took.
- **List shows on HDMI but not the CRT:** the `[menu]` section in `MiSTer.ini` needs
  `vga_scaler=1` and the 15 kHz `video_mode` line. Try `composite_sync=1` for SCART/JAMMA.
- **Colours look wrong:** the log line `framebuffer ... rgb=` shows the layout the
  MiSTer reported. Send that line along with a description.
- **Wrong button is MENU/OPERATOR:** run `arcadekiosk.py --relearn`, or set
  `log_inputs = 1`, press buttons, and read their names in the log.
- **A controller is ignored:** run `arcadekiosk.py --devices`.
- **Turn the kiosk off:** unlock, then remove the `# Arcade Kiosk` lines from
  `/media/fat/linux/user-startup.sh` and reboot.
