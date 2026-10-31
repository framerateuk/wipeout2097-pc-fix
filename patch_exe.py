#!/usr/bin/env python3
"""Patch Wipeout 2097's D3D.EXE (European Direct3D retail, 769,024 bytes, 14 May 1997) in place.

Usage:  patch_exe.py [--full-trails] D3D.EXE    each patch must match exactly once (or already be applied)

Patches 1-7 are fixes and always applied. 8 (fulltrails) is optional: --full-trails.

After these patches the exe runs from its own folder: no registry keys, no CD, no fake drive.

1. noreg (1 byte). At start-up 0x45b010 reads HKLM\\SOFTWARE\\Psygnosis\\Studios\\Wipeout2097
   values "DirectoryName" (install folder) and "Source Directory" (CD), written by the installer.
   If the key is missing it returns 1 and the caller (0x456fd2) clears the main-loop "running"
   flag 0x492888, so the game quits before its window opens. The patch makes that `je` a `jmp`:
   a missing key is ignored and the built-in defaults stay in use.

2. rootdirs (2 x 10 bytes). Those defaults are "C:\\WOBBLE\\" (a Psygnosis dev path) in the two
   buffers 0x48e440 (install folder) and 0x48e540 (CD). 0x45acd0 builds every asset folder path
   from them: <install>\\<sub>\\ if it exists, else <CD>\\<sub>\\. Both become ".\\" so everything,
   including CONFIG.DAT and SAVEGAME.BIN, is read from and written to the working directory.

2b. nochdir (5 bytes). "If it exists" is tested by 0x474c80, the C runtime's _chdir: it changes
   into the folder and stays there. Harmless with the installer's absolute paths, fatal with ".\\":
   the first test moves the working directory into a subfolder and every later ".\\" path misses
   ("File could not be found: .\\blitsurf\\HI-RES\\2097copy.ppm"). The call
   in the folder loop (0x45ae33) becomes `mov eax,1`: every folder is taken as .\\<sub>\\ and the
   working directory never moves. (The only other caller, 0x45e151, probes <CD>\\directx, which
   doesn't exist in the package, so _chdir fails there without moving anything.)

3. cdtoc (2 x 1 byte). 0x41dd09 is the "Wipeout 2097 CD Validator": it reads the disc's table
   of contents over MCI cdaudio and sets the flag 0x48f44c ("Make sure Wipeout 2097 CD is in the
   CD drive", retry/cancel) if fewer than 3 tracks are reported, or if any of tracks 2-9 differs
   from the exe's table of lengths (0x48bbf0, frames, next start - start - 150) by even one frame.
   ogg-winmm reports positions summed from the OGG lengths in milliseconds and rounds them to
   frames, so exact lengths are luck. The patch makes those two stores write 0 instead of 1.
   A failing MCI call (no cdaudio device at all) still sets the flag.

4. keepsurf (2 x 6 bytes). Dege's 2021 fix for "Wipeout XL/2097 broken on dgVoodoo 2.63 and
   newer" (VOGONS; his patched XL exe is http://dege.fw.hu/temp/WipeOut_patch.zip). Two
   screen routines (0x430d3b, 0x4315d5) Release() the DirectDraw objects held in 0x4bae60 and
   0x4bae64 (`push eax / mov ebx,[eax] / call [ebx+8]`) while the game still uses them later.
   Older DirectX and dgVoodoo <= 2.62 survived the use-after-free by luck; 2.63+ (we ship
   2.79.3 for Proton) crash silently after "PRESS START". The patch NOPs both Release calls,
   as Dege did; the objects simply live until the game exits. Found by matching his XL exe
   (same code, different addresses: his 0x431f00 / 0x43279a) against this one.

5. nozr (2 x 1 byte). At start-up (0x43b0d3) the game asks joyGetPosEx for X, Y and buttons,
   plus Z if the pad reports JOYCAPS_HASZ and R if it reports JOYCAPS_HASR. It reads Z as a
   throttle (Z > 0x4000 = thrust held) and R as a rudder (R < 0x4000 / > 0xc000 = left / right
   airbrake held), as on 1997 flight sticks. A modern pad under Proton (and an Xbox pad on
   Windows) reports both: Z is the two triggers on one axis, resting at the centre, so thrust was
   stuck on and the triggers moved it; R rests at one end, so an airbrake was stuck on and the
   craft pulled to one side. The patch turns the two `je` after the caps
   tests into `jmp`: Z and R are never requested, so they read 0 and the game ignores them.
   Steering (X), Y and the buttons are unchanged; bind triggers to buttons in Steam Input.

6. deadzone (14 + 72 + 4 bytes). Analogue steering is the raw stick X / 256 (0x43bc35), and the
   race code steers by (value - 128) with no deadzone (0x45ee2e). A centred pad must read exactly
   32768; Wine's 0..65535 conversion can give 32767 (127 = a constant slight turn), and worn sticks
   drift: the craft pulls to one side. The 14-byte computation
   becomes a call to a routine in the unused tail of .text (0x488e20; zeros on the disc): within
   +-0x800 of centre (about 6%) steering is exactly 128, beyond it the rest of the travel is scaled
   to the full 1..255. The .text VirtualSize grows from 0x87e1b to 0x88000 (its raw size) so the
   loader maps the routine instead of zero-filling it.

7. widescreen (16 + 44 + 8 + 14 bytes). Every part is identical to the original at 4:3; at
   16:10 / 16:9 the picture keeps its shape and shows more at the sides, like the PS1 widescreen
   hacks (which work well with this game's culling), and the HUD and menus stay 4:3 in the middle.
   Two launcher modes nobody needs are replaced: 320x200 -> 768x480 (16:10, the Steam Deck) and
   511x384 -> 854x480 (16:9), in the mode table (0x4928d8) and the dialog's labels.
   dgVoodoo.conf lists both under ExtraEnumeratedResolutions.
   2D (HUD, menus, sprites) is built as PS1 primitives and placed by three helpers that scaled X
   by the width; each now scales by the 4:3 width around the centre:
   0x4565c0 (x in 320x240 space):  X = (x - 160) * height / 240 + width / 2     routine 0x488e70
   0x456690 (x in 640x480 space):  X = (x - 320) * height / 480 + width / 2     routine 0x488ea0
   0x456770 (x in screen pixels):  X = (x - width/2) * (4/3 * height / width) + width / 2
                                                                                 routine 0x488ee0
   The 3D is projected by Direct3D itself: the D3DVIEWPORT set up at 0x458ef8 (struct 0x49ddc0)
   has dvScaleX = width, dvScaleY = height and dvMaxX/Y = size / (2 * scale). The two reads of
   width there (0x458f29: 2 * width for dvMaxX, 0x458f35: dvScaleX) now call routines returning
   height * 4/3 instead (0x488f20, 0x488f30): the 3D keeps 4:3 proportions and dvMaxX grows, so
   a wider screen shows more at the sides. Identical at 4:3.

8. fulltrails (11 bytes, optional). The in-race settings live in the struct at [0xa34df8]:
   +0x19 engine trails (F4: 0 off, 1 on, 2 full), +0x1a sky (F5), +0x1b draw distance (F3:
   0..7, shown as 1..8; 0 is the farthest, 36000 in the table at 0x4927f0), +0x1e filtering
   (F7). CONFIG.DAT saves them at 0x1f, 0x20, 0x23 and 0x22. When there is no valid CONFIG.DAT
   (none, or the disc's copy, marked 1234 / 5678 at 0x0e / 0x10), 0x42eaa0 fills in defaults
   once and the game saves them straight away: draw distance 0 (farthest), sky on, filtering on,
   and trails on, or off if the 16-bit colour / CPU flag 0x48f460 isn't set yet. The patch makes
   the trails default 2 (full), always: `cmp edx,ebx / mov [ebp+0x19],cl / jne / mov
   [ebp+0x19],0` becomes `mov byte [ebp+0x19],2` + 7 nops (no flags are used after it). Only the
   defaults change: F4 still cycles the trails in a race and the choice is saved.
"""
import re, sys

# deadzone routine (see 6): eax = |X - 0x8000| - 0x800 (0 if negative), * 128 / 0x7800, max 127,
# sign restored, + 0x80 -> [0xa2970e]. ecx/edx are live in the caller, so saved.
DZ_ROUTINE = bytes.fromhex(
    "51 52 a1 28 49 a2 00 2d 00 80 00 00 99 89 d1 31 d0 29 d0 2d 00 08 00 00 7f 02 31 c0"
    "c1 e0 07 31 d2 68 00 78 00 00 f7 34 24 83 c4 04 83 f8 7f 76 05 b8 7f 00 00 00"
    "31 c8 29 c8 05 80 00 00 00 66 a3 0e 97 a2 00 5a 59 c3")
assert len(DZ_ROUTINE) == 72

# widescreen routine (see 7), at VA 0x488e70: st0 = (x - 160) * height / 240 + width / 2;
# x is the float the original read at [esp+8] (+4 for our return address); 160.0 at +0x28.
WS_ROUTINE = (bytes.fromhex(
    "d9 44 24 0c d8 25 98 8e 48 00 d8 0d 90 b9 4b 00 d8 0d b4 96 48 00"
    "d9 05 14 21 4a 00 d8 0d f8 91 48 00 de c1 c3") + b"\x90" * 3 + bytes.fromhex("00 00 20 43"))
assert len(WS_ROUTINE) == 0x2c
WS640_ROUTINE = bytes.fromhex(
    "db44240cd825cc8e4800d80d90b94b00d83588914800d90514214a00d80df8914800dec1c3"
    "909090909090900000a043")
WSPIX_ROUTINE = bytes.fromhex(
    "db44240cd90514214a00d80df8914800dce9d9c9d80d90b94b00d83514214a00d80d148f4800"
    "dec18b4c2408c390909090909090abaaaa3f")
assert len(WS640_ROUTINE) == 0x30 and len(WSPIX_ROUTINE) == 0x38
# viewport routines (0x488f20: st0 = 2 * height * 4/3;  0x488f30: ecx = height * 4/3)
WSVP_ROUTINES = (bytes.fromhex("d90590b94b00d80d148f4800d8c0c3") + b"\x00" +
                 bytes.fromhex("d90590b94b00d80d148f480083ec04d91c2459c3"))
assert len(WSVP_ROUTINES) == 36

PATCHES = [
    # name, pattern (each group = bytes to replace), replacement, already-applied pattern, expected hits
    ("noreg",
     re.compile(rb"\xe8....\x85\xc0(\x74)\x13\xc7\x05\x88\x28\x49\x00\x00\x00\x00\x00", re.S),
     b"\xeb",
     re.compile(rb"\xe8....\x85\xc0\xeb\x13\xc7\x05\x88\x28\x49\x00\x00\x00\x00\x00", re.S), 1),
    ("rootdirs",
     re.compile(rb"(C:\\WOBBLE\\)\x00.{245}(C:\\WOBBLE\\)\x00(?=(?:.{245}C:\\WOBBLE\\\x00){14}\x00)", re.S),
     b".\\" + bytes(8),
     re.compile(rb"\.\\\x00{9}.{245}\.\\\x00{9}(?=(?:.{245}C:\\WOBBLE\\\x00){14}\x00)", re.S), 1),
    ("nochdir",
     re.compile(rb"\x8d\x44\x24\x68\x50(\xe8....)\x83\xc4\x04\x85\xc0\x74\x57", re.S),
     b"\xb8\x01\x00\x00\x00",
     re.compile(rb"\x8d\x44\x24\x68\x50\xb8\x01\x00\x00\x00\x83\xc4\x04\x85\xc0\x74\x57", re.S), 1),
    ("nozr",
     re.compile(rb"\xf6\xc1\x01(\x74)\x0a\xc7\x05\x24\x49\xa2\x00\x87\x0c\x00\x00\xa1\xe0\x4b\xa2\x00\xa8\x02(\x74)\x07\x83\x0d\x24\x49\xa2\x00\x08", re.S),
     b"\xeb",
     re.compile(rb"\xf6\xc1\x01\xeb\x0a\xc7\x05\x24\x49\xa2\x00\x87\x0c\x00\x00\xa1\xe0\x4b\xa2\x00\xa8\x02\xeb\x07\x83\x0d\x24\x49\xa2\x00\x08", re.S), 1),
    ("deadzone",   # .text VirtualSize 0x87e1b -> 0x88000
     re.compile(rb"\.text\x00\x00\x00(\x1b\x7e\x08\x00)\x00\x10\x00\x00\x00\x80\x08\x00", re.S),
     b"\x00\x80\x08\x00",
     re.compile(rb"\.text\x00\x00\x00\x00\x80\x08\x00\x00\x10\x00\x00\x00\x80\x08\x00", re.S), 1),
    ("deadzone",   # the routine, at VA 0x488e20
     re.compile(rb"\x5d\x61\x8b\x44\x24\xc8\xc3\x00{5}(\x00{72})", re.S),
     DZ_ROUTINE,
     re.compile(rb"\x5d\x61\x8b\x44\x24\xc8\xc3\x00{5}" + re.escape(DZ_ROUTINE), re.S), 1),
    ("deadzone",   # mov eax,[X] / shr eax,8 / mov [steer],ax  ->  call 0x488e20 + 9 nops
     re.compile(rb"(\xa1\x28\x49\xa2\x00\xc1\xe8\x08\x66\xa3\x0e\x97\xa2\x00)\xa1\x28\x49\xa2\x00\x3d\x00\x40\x00\x00", re.S),
     b"\xe8\xe6\xd1\x04\x00" + b"\x90" * 9,
     re.compile(rb"\xe8\xe6\xd1\x04\x00\x90{9}\xa1\x28\x49\xa2\x00\x3d\x00\x40\x00\x00", re.S), 1),
    ("widescreen",   # routine after the deadzone one (0x488e68 .. 0x488e70 stays zero)
     re.compile(rb"\x5a\x59\xc3\x00{8}(\x00{44})", re.S),
     WS_ROUTINE,
     re.compile(rb"\x5a\x59\xc3\x00{8}" + re.escape(WS_ROUTINE), re.S), 1),
    ("widescreen",   # fld [width] / fmul [esp+8] / fmul [1/320]  ->  call 0x488e70 + 11 nops
     re.compile(rb"(\xd9\x05\x14\x21\x4a\x00\xd8\x4c\x24\x08\xd8\x0d\xb0\x96\x48\x00)\x8b\x4c\x24\x04", re.S),
     b"\xe8\xab\x28\x03\x00" + b"\x90" * 11,
     re.compile(rb"\xe8\xab\x28\x03\x00\x90{11}\x8b\x4c\x24\x04", re.S), 1),
    ("widescreen",   # 640-space and pixel-space routines at 0x488ea0 / 0x488ee0
     re.compile(rb"\x90\x90\x90\x00\x00\x20\x43\x00{4}(\x00{48})\x00{16}(\x00{56})", re.S),
     None,
     re.compile(rb"\x90\x90\x90\x00\x00\x20\x43\x00{4}" + re.escape(WS640_ROUTINE) + rb"\x00{16}" + re.escape(WSPIX_ROUTINE), re.S), 1),
    ("widescreen",   # 0x456690: fild [esp+8] / movsx ecx,[shakeX] / fmul [width] / sub esp,8 / fmul [1/640]
     re.compile(rb"(\xdb\x44\x24\x08\x0f\xbf\x0d\x38\x49\xb4\x00\xd8\x0d\x14\x21\x4a\x00\x83\xec\x08\xd8\x0d\xcc\x96\x48\x00)\x89\x4c\x24\x00", re.S),
     b"\xe8\x0b\x28\x03\x00\x0f\xbf\x0d\x38\x49\xb4\x00\x83\xec\x08" + b"\x90" * 11,
     re.compile(rb"\xe8\x0b\x28\x03\x00\x0f\xbf\x0d\x38\x49\xb4\x00\x83\xec\x08\x90{11}\x89\x4c\x24\x00", re.S), 1),
    ("widescreen",   # 0x456770: fild [esp+8] / mov ecx,[esp+4]  ->  call 0x488ee0 (does both) + 3 nops
     re.compile(rb"(\xdb\x44\x24\x08\x8b\x4c\x24\x04)\x83\xec\x08\x0f\xbf\x05\x38\x49\xb4\x00", re.S),
     b"\xe8\x6b\x27\x03\x00\x90\x90\x90",
     re.compile(rb"\xe8\x6b\x27\x03\x00\x90\x90\x90\x83\xec\x08\x0f\xbf\x05\x38\x49\xb4\x00", re.S), 1),
    ("widescreen",   # viewport routines, after the 4/3 constant at 0x488f14
     re.compile(rb"\xab\xaa\xaa\x3f\x00{8}(\x00{36})", re.S),
     WSVP_ROUTINES,
     re.compile(rb"\xab\xaa\xaa\x3f\x00{8}" + re.escape(WSVP_ROUTINES), re.S), 1),
    ("widescreen",   # viewport: fld [width] / fmul [2.0]  and  mov ecx,[width]
     re.compile(rb"(\xd9\x05\x14\x21\x4a\x00\xd8\x0d\xe8\x96\x48\x00)(\x8b\x0d\x14\x21\x4a\x00)\x8b\x15\x90\xb9\x4b\x00", re.S),
     None,
     re.compile(rb"\xe8\xf2\xff\x02\x00\x90{7}\xe8\xf6\xff\x02\x00\x90\x8b\x15\x90\xb9\x4b\x00", re.S), 1),
    ("widescreen",   # mode table: 320x200 -> 768x480, (320x240 kept), 511x384 -> 854x480
     re.compile(rb"(\x40\x01\xc8\x00)\x40\x01\xf0\x00(\xff\x01\x80\x01)\x80\x02\xe0\x01\x20\x03\x58\x02", re.S),
     None,
     re.compile(rb"\x00\x03\xe0\x01\x40\x01\xf0\x00\x56\x03\xe0\x01\x80\x02\xe0\x01\x20\x03\x58\x02", re.S), 1),
    ("widescreen",   # dialog labels
     re.compile(rb"(320x200)\x00(320x240)\x00(511x384)\x00640x480\x00", re.S),
     None,
     re.compile(rb"768x480\x00320x240\x00854x480\x00640x480\x00", re.S), 1),
    ("cdtoc",
     re.compile(rb"\x66\xc7\x05\x4c\xf4\x48\x00(\x01)\x00(?=\xe9\x88\xff\xff\xff|\x33\xc0)", re.S),
     b"\x00",
     re.compile(rb"\x66\xc7\x05\x4c\xf4\x48\x00\x00\x00(?=\xe9\x88\xff\xff\xff|\x33\xc0)", re.S), 2),
    ("keepsurf",
     re.compile(rb"\xa1\x60\xae\x4b\x00(\x50\x8b\x18\xff\x53\x08)\xc7\x05....\x00\x00\x00\x00\xc7\x05....\x01\x00\x00\x00\x5d", re.S),
     b"\x90" * 6,
     re.compile(rb"\xa1\x60\xae\x4b\x00\x90{6}\xc7\x05....\x00\x00\x00\x00\xc7\x05....\x01\x00\x00\x00\x5d", re.S), 1),
    ("keepsurf",
     re.compile(rb"\xa1\x64\xae\x4b\x00(\x50\x8b\x18\xff\x53\x08)\xc7\x05....\x00\x00\x00\x00\x5f\x5e\x5b\x81\xc4\x00\x01\x00\x00\xc3", re.S),
     b"\x90" * 6,
     re.compile(rb"\xa1\x64\xae\x4b\x00\x90{6}\xc7\x05....\x00\x00\x00\x00\x5f\x5e\x5b\x81\xc4\x00\x01\x00\x00\xc3", re.S), 1),
]

OPTIONAL = {
    "--full-trails": [
        ("fulltrails",   # 0x42eb2e, in the defaults branch of 0x42eaa0
         re.compile(rb"\x88\x5d\x18(\x3b\xd3\x88\x4d\x19\x75\x04\xc6\x45\x19\x00)\xc6\x45\x1b\x00\xb8\x01\x00\x00\x00", re.S),
         b"\xc6\x45\x19\x02" + b"\x90" * 7,
         re.compile(rb"\x88\x5d\x18\xc6\x45\x19\x02\x90{7}\xc6\x45\x1b\x00\xb8\x01\x00\x00\x00", re.S), 1),
    ],
}

# replacements for patches whose groups each get different bytes (new = None)
PER_GROUP = {
    ("widescreen", b"\x40\x01\xc8\x00"): b"\x00\x03\xe0\x01",   # 768x480
    ("widescreen", b"\xff\x01\x80\x01"): b"\x56\x03\xe0\x01",   # 854x480
    ("widescreen", b"320x200"): b"768x480",
    ("widescreen", b"320x240"): b"320x240",
    ("widescreen", b"511x384"): b"854x480",
    ("widescreen", bytes(48)): WS640_ROUTINE,
    ("widescreen", bytes.fromhex("d90514214a00d80de8964800")): b"\xe8\xf2\xff\x02\x00" + b"\x90" * 7,
    ("widescreen", bytes.fromhex("8b0d14214a00")): b"\xe8\xf6\xff\x02\x00\x90",
    ("widescreen", bytes(56)): WSPIX_ROUTINE,
}

flags = [a for a in sys.argv[1:] if a.startswith("--")]
for f in flags:
    if f not in OPTIONAL: sys.exit(f"unknown option {f} (known: {', '.join(OPTIONAL)})")
patches = PATCHES + [p for f in flags for p in OPTIONAL[f]]
for path in [a for a in sys.argv[1:] if not a.startswith("--")]:
    d = bytearray(open(path, "rb").read())
    for name, pat, new, done, n in patches:
        if len(list(done.finditer(d))) == n:
            print(f"{path}: {name} already applied"); continue
        hits = list(pat.finditer(d))
        if len(hits) != n:
            sys.exit(f"{path}: {name}: expected {n} matches, found {len(hits)}; file left unchanged")
        for h in hits:
            for g in range(1, len(h.groups()) + 1):
                o = h.start(g)
                rep = new if new is not None else PER_GROUP[(name, h.group(g))]
                d[o:o + len(rep)] = rep
                print(f"{path}: {name} at file offset {o:#x}")
    open(path, "wb").write(d)
