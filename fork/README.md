# Kiosk build of the MiSTer main program

The MiSTer's menu is drawn by its main program, `/media/fat/MiSTer`
([Main_MiSTer](https://github.com/MiSTer-devel/Main_MiSTer)). This folder holds a small
patch to it that makes the kiosk seamless:

| | Stock MiSTer main | Kiosk build |
|---|---|---|
| Boot / after a game | Stock menu shows for a moment, then the kiosk takes over | Straight to the kiosk |
| Saving NVRAM on quit | MiSTer menu flashes open for 0.3 s (`save_nvram = once` limits it) | Saved silently, every time |
| MiSTer menu while locked | Blocked by the kiosk intercepting buttons | Can't be opened at all |
| Volume changes | OSD volume bar pops up | Only the kiosk's own display |

The patch only does anything while the kiosk is running: the kiosk creates
`/tmp/kiosk_active` while it owns the screen, and removes it when the operator picks
**MiSTer menu** or **Game settings**. Without the kiosk, the build behaves exactly like
stock MiSTer.

The menu that appears over a running game (from **Game settings**) keeps each core's own
colour, because that is built into every core's FPGA design.

## Files

- `0001-MisterOperator-kiosk-support.patch`: the patch, against upstream Main_MiSTer:
  2 new files (`kiosk.cpp`, `kiosk.h`) and a few lines in `main.cpp`, `menu.cpp`,
  `input.cpp` and `audio.cpp`, plus a GitHub Actions workflow that builds it with the
  official ARM GCC 10.2 toolchain.
- `zigbuild.py`: a compile-and-link check that works without that toolchain
  (`pip install ziglang`, then `python3 zigbuild.py <Main_MiSTer dir> <build dir>`).

The patched source lives at `github.com/alex-acsit/Main_MiSTer` (branch `main`: a snapshot
of upstream plus the patch). Its GitHub Actions build it with the official ARM GCC 10.2
toolchain and publish the binary as the **kiosk-latest** release. That binary is included
here as `arcade_kiosk/MiSTer_kiosk`, built from upstream 8329c5a.

## Installing

1. `MiSTer_kiosk` is already in the kiosk folder (`/media/fat/arcade_kiosk/`). For a newer
   build, download `MiSTer` from the kiosk-latest release and save it there under that name.
2. Open the operator menu, go to **MiSTer main** (it shows `STOCK: 1 INSTALLS`) and
   press Button 1 twice. The kiosk keeps the original as `/media/fat/MiSTer.stock`, copies
   the kiosk build in, and reboots. The row then shows `KIOSK`.
3. **Safety net:** if the new main program hasn't started within 90 s of that reboot,
   the kiosk puts `MiSTer.stock` back and reboots again.

MiSTer's updaters (`update_all`, `downloader`) put the stock binary back. Nothing breaks:
the kiosk notices, works the way it does with stock MiSTer, and the operator menu shows
`STOCK: 1 INSTALLS` until you install it again.

To remove it for good, copy `MiSTer.stock` back over `MiSTer`. If the MiSTer menu ever
seems blocked with the kiosk stopped, `rm /tmp/kiosk_active` over SSH, or a reboot,
clears it.
