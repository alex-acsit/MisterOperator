# Kiosk build of the MiSTer main program

The MiSTer's menu is drawn by its main program, `/media/fat/MiSTer`
([Main_MiSTer](https://github.com/MiSTer-devel/Main_MiSTer)). This folder holds a small
patch to it that makes the kiosk seamless:

| | Stock MiSTer main | Kiosk build |
|---|---|---|
| Boot / after a game | Stock menu shows for a moment, then the kiosk takes over | Straight to the kiosk |
| Saving NVRAM on quit | MiSTer menu flashes open for 0.3 s on every quit; cores that only save from their own "Save NVRAM" item aren't saved | Saved silently, every time, including those cores |
| "Autosave Hiscores" core option | As each core's settings say (usually Off) | Switched On when the core loads, and saved |
| MiSTer menu while locked | Blocked by the kiosk intercepting buttons | Can't be opened at all |
| Volume changes | OSD volume bar pops up | Only the kiosk's own display |

The patch only does anything while the kiosk is running: the kiosk creates
`/tmp/kiosk_active` while it owns the screen, and removes it when the operator picks
**MiSTer menu** or **Game settings**. Without the kiosk, the build behaves exactly like
stock MiSTer.

The menu that appears over a running game (from **Game settings**) keeps each core's own
colour, because that is built into every core's FPGA design.

## Files

- `patches/`: the patch series against upstream Main_MiSTer (apply with `git am`):
  2 new files (`kiosk.cpp`, `kiosk.h`) and a few lines in `main.cpp`, `menu.cpp`,
  `input.cpp`, `user_io.cpp` and `audio.cpp`, plus a GitHub Actions workflow that builds it with the
  official ARM GCC 10.2 toolchain.
- `zigbuild.py`: a compile-and-link check that works without that toolchain
  (`pip install ziglang`, then `python3 zigbuild.py <Main_MiSTer dir> <build dir>`).

The patched source lives at `github.com/alex-acsit/Main_MiSTer` (branch `main`: a snapshot
of upstream plus the patch). Its GitHub Actions build it with the official ARM GCC 10.2
toolchain and publish the binary as the **kiosk-latest** release. That binary is included
here as `arcade_kiosk/MiSTer_kiosk`, built from upstream 8329c5a.

At power-on the main program starts before the kiosk. So the kiosk also leaves
`/media/fat/config/kiosk_boot` on the SD card, which this build treats as the kiosk flag
for the first 2 minutes after power-on: no MiSTer menu at boot either. After that only
`/tmp/kiosk_active` counts, so a missing or broken kiosk can't keep the menu blocked. If
the kiosk takes over while the MiSTer menu is already showing, the build closes it.

**Cores with a "Save NVRAM" item.** Most arcade cores ask the MiSTer to save their NVRAM
when it changes, and the OSD (and this build's `save_nvram` command) only saves when asked.
Some never ask by themselves: blahm1d's Midway Wolf/T/Y/X/V Unit, NARC and Gladiator cores
only ask when their own **Save NVRAM** OSD item is used. For a core that hasn't asked,
`save_nvram` looks for a trigger option named Save NVRAM (or Save CMOS; never Autosave or
Clear), fires it as the OSD would, waits up to 0.5 s for the core to ask, then saves. It's
listed as `nvram_trigger` in `/tmp/MiSTer_features` (patch 0007).

**High scores.** Many arcade cores (Pac-Man, Galaga, Donkey Kong, Centipede, Robotron and
others using the MiSTer hiscore module) have an OSD option **Autosave Hiscores**, at a
different status bit in each core. While the kiosk flag is present, this build reads the
core's option list as it loads, finds any option whose name is an autosave of high scores,
sets it to its `On` value and saves the core's settings (`config/<core>.CFG`), as if the
operator had switched it on in the OSD. Cores without the option are untouched. It's
listed as `hiscore_autosave` in `/tmp/MiSTer_features`.

## Installing

1. `MiSTer_kiosk` is already in the kiosk folder (`/media/fat/arcade_kiosk/`). For a newer
   build, download `MiSTer` from the kiosk-latest release and save it there under that name.
2. Open the operator menu, go to **MiSTer main** (it shows `STOCK: 1 INSTALLS`, or
   `OLD: 1 UPDATES` when the kiosk folder has a newer build than the installed one) and
   press Button 1 twice. The kiosk keeps the original as `/media/fat/MiSTer.stock`, copies
   the kiosk build in, and reboots. The row then shows `KIOSK`.
3. **Safety net:** if the new main program hasn't started within 90 s of that reboot,
   the kiosk puts `MiSTer.stock` back and reboots again.

MiSTer's updaters (`update_all`, `downloader`) put the stock binary back. Nothing breaks:
the kiosk notices, works the way it does with stock MiSTer, and the operator menu shows
`STOCK: 1 INSTALLS` until you install it again.

To remove it for good, copy `MiSTer.stock` back over `MiSTer` and delete
`/media/fat/config/kiosk_boot`. If the MiSTer menu ever
seems blocked with the kiosk stopped, `rm /tmp/kiosk_active` over SSH, or a reboot,
clears it.
