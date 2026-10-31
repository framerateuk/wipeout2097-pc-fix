# Wipeout 2097 (PC, 1997): disc-free, widescreen, pad-friendly

## Why this exists

When Wipeout 2097 came out on PC in 1997 it was a real highlight. Since then it has become harder
and harder to get working on modern PCs: the installer, the CD check, the DirectX 3 renderer and
the CD-audio soundtrack all trip over Windows 10/11 and modern hardware.

It's also not just a port of the PlayStation game. The PC version has its own soundtrack, played
from the CD, and none of the Red Bull branding. That makes it a different experience from the
PlayStation release, and one worth keeping alive.

## What this does

Turns **your own** Wipeout 2097 PC CD into a folder that runs on Windows 10/11 and on the Steam Deck
(Proton), with no disc, no installer and no registry entries:

- **Widescreen**: 854x480 (16:9) and 768x480 (16:10, the Steam Deck) in the game's settings dialog.
  3D keeps its shape and shows more at the sides; HUD and menus stay 4:3 in the middle.
- **CD soundtrack** from OGG files ripped from your disc, with the in-game music volume working.
- **Correct speed** (30 fps cap; the game runs too fast above 30).
- **Modern pads**: no stuck thrust or pull to one side from the triggers, and a small steering deadzone.
- **The dgVoodoo crash after "PRESS START" fixed** (Dege's fix, ported from Wipeout XL).
- **Engine trails on FULL** from the first race (optional patch; the game's own default is on, or
  off). Draw distance and sky already start at maximum. Filtering starts on; F7 turns it off.
- Direct3D through dgVoodoo2, rendered at 4x the game's resolution (or the Deck's screen size).

**No game files are in this repository.** Everything from the game (the exe, data, videos and music)
comes from your disc when you run `build.py`. The exe is patched on your machine.

## What you need

| | |
|---|---|
| The game | The **European Direct3D CD** (volume label `WO2097D3D`, `D3D.EXE` dated 14 May 1997), as a disc image: `.cue` + `.bin` (one file or one per track) or CloneCD `.ccd` + `.img`. `build.py` checks the exe and stops if it's a different version. |
| Python | 3.8 or newer (python.org on Windows; already on macOS/Linux). |
| An OGG encoder | `oggenc` (vorbis-tools; Windows builds at rarewares.org) or `ffmpeg`, on the PATH. |
| dgVoodoo2 **2.79.3** | by Dege: [GitHub release v2.79.3](https://github.com/dege-diosg/dgVoodoo2/releases/tag/v2.79.3). Use 2.79.3: newer versions don't start under Wine/Proton. Keep the zip as downloaded. |
| ogg-winmm | by AyuanX: [GitHub releases](https://github.com/ayuanx/ogg-winmm/releases) (tested with v2025.01.16). Keep the zip as downloaded. |

## Build

```
python3 build.py "Wipeout 2097.cue" --dgvoodoo dgVoodoo2_79_3.zip --ogg-winmm ogg-winmm_binary.zip
```

Add `--steam-deck` when the folder is for the Deck (dgVoodoo then renders at the largest size that
fits the screen, with brightness 125, which suits the Deck's screen). `--out DIR` puts the result
somewhere else, and `--no-full-trails` leaves the engine trails at the game's own default.
It takes under a minute and creates:

```
Wipeout2097/
  game/                      the game: run D3D.EXE
  wipeout2097_launch.sh      Steam Deck / Linux launch wrapper
```

## Play on Windows

Run `game/D3D.EXE`. The game opens its own settings dialog first: pick **854x480** for 16:9 (or
768x480, 640x480, 800x600), keep **Direct 3D HAL** and **64K Colors using 3D Card**, then **Play Game**.

## Play on the Steam Deck

1. Copy `Wipeout2097/` to the Deck, for example to `/home/deck/Games/Wipeout2097/`.
2. Desktop Mode: Steam > Add a Non-Steam Game > Browse > `.../Wipeout2097/game/D3D.EXE`.
   Rename the shortcut "Wipeout 2097".
3. Properties > Compatibility: force **Proton 9.0**.
4. Properties > Launch Options:
   ```
   /home/deck/Games/Wipeout2097/wipeout2097_launch.sh %command%
   ```
   (The script tells Wine to use the dgVoodoo and ogg-winmm DLLs beside the exe; it also writes
   `launch.log`.)
5. Launch. In the settings dialog (touchscreen or trackpad) pick **768x480** (16:10, fills the
   Deck's screen; it sits above 320x240 in the list, so scroll up) or 854x480, then Play Game.

## Controls

- In the game's options set the control mode to **Keyboard and Joystick**. The stick steers
  (analogue); buttons can be redefined in the game's controls menu.
- The game doesn't see the triggers. Map them to buttons or keys in Steam Input if you want them.
- In a race: F1 internal / external view, F2 mouse sensitivity, F3 draw distance (1 is the
  farthest), F4 engine trails (off / on / full), F5 sky, F7 texture filtering. They're saved in
  `game/CONFIG.DAT`; delete it to go back to the defaults.

## Tuning

All in `game/dgVoodoo.conf`:
- Sharpness: `[DirectX] Resolution` (`unforced`, `2x`, `4x`, `max`, ...). The `[Glide]` one is not used.
- Brightness: `[General] Brightness` (percent).
- **Keep `FPSLimit = 30`.** The game runs one logic step per frame and plays too fast above 30.

Music level: `CDDAVolume` in `game/winmm.ini` (0-100), or the in-game music volume.

## Troubleshooting

- *"Make sure Wipeout 2097 CD is in the CD drive"*: ogg-winmm isn't loaded. On the Deck, check the
  launch options and `launch.log`; on Windows, check `game/winmm.dll` and `game/Music/`.
- *Silent exit after "PRESS START"*: the exe isn't patched (`python3 patch_exe.py game/D3D.EXE`
  lists what's applied).
- *Too fast*: `FPSLimit` in `game/dgVoodoo.conf` must be 30.
- *Judder on a G-Sync / FreeSync monitor*: turn variable refresh off for this game.
- Alt+Tab can break the controls; restart the game.

## What's in this repository

| File | What |
|---|---|
| `build.py` | Reads the disc image (ISO 9660 on the CD-XA data track, CD audio tracks), builds `game/`, encodes the soundtrack, patches the exe, adds the wrappers and settings. Python standard library only. |
| `patch_exe.py` | The exe patches, each documented at the top of the file. Can be run on its own: `python3 patch_exe.py [--full-trails] D3D.EXE`. |
| `config/dgVoodoo.conf` | dgVoodoo2 settings: 30 fps cap, 4x resolution, the two widescreen modes added to the mode list. |
| `steamdeck/wipeout2097_launch.sh` | Proton launch wrapper (DLL overrides, log). |
| `docs/TECHNICAL.md` | How each fix works. |

## Credits

- **Psygnosis**: Wipeout 2097. Please own the game: this kit needs your disc.
- **Dege**: dgVoodoo2, and the fix for the crash after "PRESS START" (his 2021 Wipeout XL patch,
  VOGONS thread "Wipeout XL/2097 broken on 2.63 and newer"), ported here to the 2097 exe.
- **AyuanX**: ogg-winmm.
- PCGamingWiki, for the 30 fps note.

## License

The scripts, patches and docs in this repository: MIT (see `LICENSE`). The license covers only
this repository's own files, not the game, dgVoodoo2 or ogg-winmm.

Not affiliated with or endorsed by Sony Interactive Entertainment or Psygnosis. Wipeout is a
trademark of Sony Interactive Entertainment.
