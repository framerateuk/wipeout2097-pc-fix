# How it works

Notes on the European Direct3D release of Wipeout 2097 (`D3D.EXE`, 769,024 bytes, 14 May 1997,
MD5 `8e64a41b7c71554284ebe795e84ab776`). Addresses are virtual addresses in that exe. The byte-level
detail of every patch is at the top of `patch_exe.py`.

## The disc

The data track is CD-XA (MODE2/2352, Form 1 sectors, user data at bytes 24..2072); tracks 2-10 are
the CD audio. The root directory also has nine entries, `BODY.SWP`, `CANADA.SWP`, `HAKAPIK.SWP`, ...
(36-86 MB each), whose extents are exactly the audio tracks (`BODY.SWP` starts at sector 46995 =
track 02). Reading those "files" as data fails, which is why many tools (and Windows) error out on
this disc. Nothing references them; `build.py` skips them. The volume claims all 247,532 sectors.

`build.py` reads the ISO 9660 file system straight from the raw image, so it needs no mount or
conversion tool. It leaves out the installer, the DirectX 3 redistributable, the autorun launcher
and `POWERVR.EXE` (still Direct3D, but it checks for a VideoLogic PowerVR by PCI ID and draws
without additive blending); the untouched `D3D.EXE`, `POWERVR.EXE` and `LAUNCHER.EXE` go in
`game/_spare/`.

## Running without installer, registry or CD (`noreg`, `rootdirs`, `nochdir`, `cdtoc`)

* **Registry.** At start-up the exe reads `HKLM\SOFTWARE\Psygnosis\Studios\Wipeout2097` (values
  `DirectoryName`, the install folder, and `Source Directory`, the CD). Without the key it clears
  its main-loop flag and quits before the window opens. `noreg` ignores the missing key.
* **Folders.** The built-in defaults for both are `C:\WOBBLE\` (a Psygnosis development path).
  Every asset folder is looked up as `<install>\<sub>\` if it exists, else `<CD>\<sub>\`; that is
  all "installing" ever meant. `rootdirs` makes both `.\`, so everything, saves included, lives in
  the working directory.
* **The folder test moves the working directory.** "If it exists" is tested with the C runtime's
  `_chdir`, which changes into the folder and stays there: harmless with the installer's absolute
  paths, but with `.\` the first test moves into a subfolder and the first image load fails ("File
  could not be found: .\blitsurf\HI-RES\2097copy.ppm"). `nochdir` replaces that call with "exists".
* **CD check.** The "Wipeout 2097 CD Validator" reads the CD's table of contents over MCI and wants
  at least 3 tracks, each of tracks 2-9 exactly as long as a table in the exe. ogg-winmm builds its
  table of contents from the OGG lengths in milliseconds, so lengths come out a frame or so off.
  `cdtoc` drops the length and count tests; a missing MCI CD device still fails the check.

## Graphics, speed and the dgVoodoo crash (`keepsurf`)

DirectDraw and Direct3D (DirectX 3) go through dgVoodoo2 2.79.3, which turns them into
Direct3D 11 (and, under Proton, DXVK turns that into Vulkan). Newer dgVoodoo versions fail under
Wine; on Windows they work too.

* **Crash after "PRESS START".** Two screen routines `Release()` the DirectDraw objects held in
  `0x4bae60` and `0x4bae64` and keep using them. Old DirectX and dgVoodoo up to 2.62 survived it;
  2.63 and newer free them and the game crashes silently. Dege (dgVoodoo's author) fixed the Wipeout
  XL exe in 2021 by removing the two `Release` calls (VOGONS: "Wipeout XL/2097 broken on 2.63 and
  newer"). XL and 2097 share the code at different addresses; `keepsurf` applies his change to this
  exe (`0x430d3b`, `0x4315d5`). The objects simply live until the game exits.
* **Speed.** Game logic runs once per frame and expects 30 fps; above that the game plays too fast
  (at 60 Hz with vsync, double speed). It has no limiter of its own, so `dgVoodoo.conf` has
  `FPSLimit = 30` and `ForceVerticalSync = true`.
* Forced resolution (`[DirectX] Resolution`) only applies with the settings dialog's **Direct 3D HAL**
  device and **64K Colors using 3D Card**; the Ramp/RGB devices render in software at the game's
  own size.

## CD audio

The game plays its soundtrack with `mciSendCommandA` (`cdaudio`) and sets the music volume with
`auxSetVolume`. ogg-winmm provides both from `Music/Track02.ogg` ... `Track10.ogg`. `build.py`
rips each audio track from its start (INDEX 01) to the next track's start and encodes it with
Vorbis quality 7.

## Gamepad (`nozr`, `deadzone`)

The game reads one joystick through winmm `joyGetPosEx`: X steers (analogue), the buttons are
actions (redefinable in the controls menu). If the device reports Z and R axes it also reads them,
as a throttle (Z above a quarter of its range = thrust held) and a rudder (R near either end =
airbrake held), as on 1997 flight sticks. Modern pads (an Xbox pad on Windows, the Steam Deck under
Proton) put both triggers on Z, resting at the centre, and R rests at one end: thrust was stuck on
and the craft pulled to one side. `nozr` stops the game requesting Z and R, so the triggers do
nothing in the game; bind them to buttons or keys in Steam Input if you want them.

Steering is the raw stick X / 256, and the race code steers by (value - 128) with no deadzone, so a
centred stick must read exactly 32768. Wine's conversion can give 32767 (a constant slight turn),
and worn sticks drift. `deadzone` snaps the stick to centre within about 6% and scales the rest of
the travel to full lock (a 72-byte routine in the unused tail of `.text`).

Closest to the PlayStation's digital pad: Steam Input keyboard emulation with the game's control
mode set to **Keyboard**. Default keys: accelerate S, fire Space, drop weapon Left Alt, airbrakes A
and D, nose down Up, nose up Down, steer Left / Right.

## Widescreen (`widescreen`)

PlayStation widescreen hacks (squeezing the projected X) work well with this game's culling, so
the PC version gets the same treatment. Every part is identical to the original at 4:3.

* **3D** is projected by Direct3D through the `D3DVIEWPORT` set up at `0x458ef8`: dvScaleX = width,
  dvScaleY = height, dvMaxX/Y = size / (2 * scale), so any non-4:3 mode stretched. dvScaleX (and the
  2 * width behind dvMaxX) now come from height * 4/3: proportions stay 4:3 and dvMaxX grows, so a
  wider screen shows more at the sides.
* **2D** (HUD, menus, sprites) is built as PlayStation-style primitives and placed by three helpers
  (`0x4565c0` in 320x240 space, `0x456690` in 640x480, `0x456770` in pixels), which scaled X by the
  width. They now scale by the 4:3 width around the centre, so 2D keeps its shape in the middle.
* **Modes.** 320x200 and 511x384 in the settings dialog (table `0x4928d8` and its labels) became
  768x480 (16:10) and 854x480 (16:9). The dialog lists a mode only if DirectDraw reports exactly
  that size, so `dgVoodoo.conf` adds both with `ExtraEnumeratedResolutions`. The list order is
  768x480, 320x240, 854x480, 640x480, 800x600; the dropdown shows four rows, scrolled to the
  selected one, so 768x480 can be hidden above. 1024x768 never appears: the game's table entry is
  1025x767 (disabled by Psygnosis, left alone).
* The game's mode callback (`0x45bfb0`) prints every mode DirectDraw offers with
  `OutputDebugString` (visible with DebugView, or `PROTON_LOG=1` on Linux).

## In-race settings and the engine trails default (`fulltrails`, optional)

The in-race keys change a settings struct (pointer at `0xa34df8`) that `CONFIG.DAT` saves:

| Key | Setting | Struct | CONFIG.DAT | Default |
|---|---|---|---|---|
| F1 | internal / external view | | | |
| F2 | mouse sensitivity | | | |
| F3 | draw distance 1-8 (stored 0-7; 0 = farthest, 36000 units, down to 3000) | +0x1b | 0x23 | 0 (farthest) |
| F4 | engine trails off / on / full | +0x19 | 0x1f | on (off if a colour/CPU flag isn't set yet) |
| F5 | sky | +0x1a | 0x20 | on |
| F7 | texture filtering | +0x1e | 0x22 | on |

The disc's `CONFIG.DAT` is a template: 1234 / 5678 at 0x0e / 0x10 tells the game to ignore it. With
no valid file the game sets the defaults above once and saves them at once, so later changes stick.
`fulltrails` makes the trails default full, always (11 bytes at `0x42eb2e`). The other defaults
are already the maximum; filtering is left as a choice.
