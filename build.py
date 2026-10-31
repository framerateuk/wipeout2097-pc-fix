#!/usr/bin/env python3
"""Build a ready-to-run, disc-free Wipeout 2097 folder from your own CD image.

Usage:
  python3 build.py DISC.cue|DISC.ccd --dgvoodoo DGVOODOO.zip --ogg-winmm OGG-WINMM.zip [--out DIR]
                   [--steam-deck] [--no-full-trails]

  DISC        your European Direct3D CD (volume label WO2097D3D) as .cue + .bin/.img (one file or
              one file per track) or CloneCD .ccd + .img
  --dgvoodoo  dgVoodoo2 2.79.3 zip (or its unpacked folder): MS/x86/DDraw.dll and D3DImm.dll are used
  --ogg-winmm ogg-winmm release zip (or folder): winmm.dll and winmm.ini are used
  --out       where to create Wipeout2097/ (default: this folder)
  --steam-deck  dgVoodoo renders at the largest size that fits the screen, brightness 125
                (default: 4x the game's resolution, brightness 100)
  --no-full-trails  leave engine trails at the game's own default (on, or off) instead of full
                    (patch_exe.py --full-trails); F4 changes them in a race either way

Needs Python 3.8+ and an Ogg Vorbis encoder on the PATH: oggenc (vorbis-tools) or ffmpeg.
Nothing from the game is in this repository: every game file comes from your disc.
"""
import argparse, fnmatch, hashlib, os, re, shutil, struct, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXE_MD5 = "8e64a41b7c71554284ebe795e84ab776"       # D3D.EXE on the disc (769,024 bytes, 14 May 1997)
PATCHED_MD5 = {False: "b146467374995f5d664a3c2ae0164105",   # after patch_exe.py
               True: "fdcb2255e0e517db2867a058936bc98f"}    # after patch_exe.py --full-trails
# Left out of the game folder (same rules at any depth): installer, DirectX 3 redistributable,
# launcher, PowerVR build, and the *.SWP directory entries that point at the audio tracks.
EXCLUDE = ["DIRECTX", "DSETUP*.DLL", "DXLINK.DLL", "SETUP.*", "_*", "UNINST*", "INSTAL97.BMP",
           "AUTORUN.INF", "LAUNCHER.EXE", "POWERVR.EXE", "DEBUG.TXT", "*.SWP"]
SPARE = ["D3D.EXE", "POWERVR.EXE", "LAUNCHER.EXE"]  # untouched copies in game/_spare/


# ---- disc image -------------------------------------------------------------------------------

class Track:
    def __init__(self, n, kind, path, start, end, sector):
        self.n, self.kind, self.path, self.start, self.end, self.sector = n, kind, path, start, end, sector

def parse_cue(cue):
    base = os.path.dirname(os.path.abspath(cue)); files = []
    for line in open(cue, encoding="utf-8", errors="replace"):
        t = line.strip()
        m = re.match(r'FILE\s+"?(.*?)"?\s+\w+$', t)
        if m: files.append((os.path.join(base, m.group(1)), [])); continue
        m = re.match(r'TRACK\s+(\d+)\s+(\S+)', t)
        if m: files[-1][1].append([int(m.group(1)), m.group(2).upper(), {}]); continue
        m = re.match(r'INDEX\s+(\d+)\s+(\d+):(\d+):(\d+)', t)
        if m:
            i, mm, ss, ff = map(int, m.groups()); files[-1][1][-1][2][i] = (mm * 60 + ss) * 75 + ff
    tracks = []
    for path, trks in files:
        sector = 2048 if trks and trks[0][1].endswith("/2048") else 2352
        total = os.path.getsize(path) // sector
        for i, (n, kind, idx) in enumerate(trks):
            start = idx.get(1, idx.get(0, 0))
            end = (trks[i + 1][2].get(0) or trks[i + 1][2][1]) if i + 1 < len(trks) else total
            tracks.append(Track(n, kind, path, start, end, sector))
    return tracks

def parse_ccd(ccd):
    sec, cur = {}, None
    for line in open(ccd, encoding="utf-8", errors="replace"):
        t = line.strip()
        if t.startswith("["): cur = t[1:-1]; sec[cur] = {}
        elif "=" in t and cur: k, v = t.split("=", 1); sec[cur][k.strip()] = v.strip()
    img = os.path.splitext(ccd)[0] + ".img"
    starts = {}
    for name, e in sec.items():
        if name.startswith("Entry") and int(e["Point"], 0) <= 99:
            starts[int(e["Point"], 0)] = int(e["PLBA"])
    total = os.path.getsize(img) // 2352
    nums = sorted(starts); tracks = []
    for i, n in enumerate(nums):
        mode = sec.get(f"TRACK {n}", {}).get("MODE", "0")
        kind = {"0": "AUDIO", "1": "MODE1/2352", "2": "MODE2/2352"}[mode]
        end = starts[nums[i + 1]] if i + 1 < len(nums) else total
        tracks.append(Track(n, kind, img, starts[n], end, 2352))
    return tracks

class DataTrack:
    """2048-byte user data of an ISO 9660 data track, by logical sector."""
    def __init__(self, t):
        self.f = open(t.path, "rb"); self.t = t
        self.skip = {"MODE1/2352": 16, "MODE2/2352": 24}.get(t.kind, 0)   # MODE2: CD-XA Form 1
    def read(self, lba, count=1):
        s = self.t.sector
        self.f.seek((self.t.start + lba) * s); raw = self.f.read(count * s)
        if s == 2048: return raw
        return b"".join(raw[i * s + self.skip:i * s + self.skip + 2048] for i in range(len(raw) // s))

def walk_iso(dt):
    """Yields (relative path, is_dir, lba, size) for every entry, depth first."""
    pvd = dt.read(16)
    if pvd[1:6] != b"CD001": sys.exit("data track has no ISO 9660 volume (wrong image or not this disc)")
    label = pvd[40:72].decode("ascii", "replace").strip()
    if label != "WO2097D3D":
        print(f"warning: volume label is {label!r}, this kit was made for WO2097D3D")
    def records(lba, size):
        data = dt.read(lba, (size + 2047) // 2048)
        for s in range(0, len(data), 2048):
            o = s
            while o < s + 2048 and data[o]:
                r = data[o:o + data[o]]; o += data[o]
                name = r[33:33 + r[32]]
                if name in (b"\x00", b"\x01"): continue
                yield (name.decode("ascii").split(";")[0].rstrip("."), bool(r[25] & 2),
                       struct.unpack_from("<I", r, 2)[0], struct.unpack_from("<I", r, 10)[0])
    def walk(lba, size, prefix):
        for name, is_dir, l, sz in records(lba, size):
            path = prefix + name
            yield path, is_dir, l, sz
            if is_dir: yield from walk(l, sz, path + "/")
    root = pvd[156:190]
    yield from walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")

def excluded(path):
    return any(fnmatch.fnmatchcase(part.upper(), pat) for part in path.split("/") for pat in EXCLUDE)

def extract(dt, game):
    n = 0
    for path, is_dir, lba, size in walk_iso(dt):
        top = path.split("/")[0]
        if top.upper() in SPARE and "/" not in path:
            write_extent(dt, lba, size, os.path.join(game, "_spare", path))
        if excluded(path): continue
        dst = os.path.join(game, *path.split("/"))
        if is_dir: os.makedirs(dst, exist_ok=True)
        else: write_extent(dt, lba, size, dst); n += 1
    return n

def write_extent(dt, lba, size, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as o:
        left = size
        while left > 0:
            chunk = dt.read(lba, min(512, (left + 2047) // 2048))
            o.write(chunk[:left]); left -= len(chunk); lba += 512


# ---- music ------------------------------------------------------------------------------------

def encoder():
    if shutil.which("oggenc"): return lambda wav, ogg: ["oggenc", "-Q", "-q", "7", wav, "-o", ogg]
    if shutil.which("ffmpeg"):
        return lambda wav, ogg: ["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-c:a", "libvorbis", "-q:a", "7", ogg]
    sys.exit("needs oggenc (vorbis-tools) or ffmpeg on the PATH to encode the soundtrack")

def rip(tracks, music, tmp):
    enc = encoder(); os.makedirs(music, exist_ok=True)
    for t in tracks:
        if t.kind != "AUDIO": continue
        with open(t.path, "rb") as f:
            f.seek(t.start * 2352); data = f.read((t.end - t.start) * 2352)
        wav = os.path.join(tmp, f"track{t.n:02d}.wav")
        with open(wav, "wb") as o:
            o.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " +
                    struct.pack("<IHHIIHH", 16, 1, 2, 44100, 176400, 4, 16) + b"data" +
                    struct.pack("<I", len(data)) + data)
        ogg = os.path.join(music, f"Track{t.n:02d}.ogg")
        subprocess.run(enc(wav, ogg), check=True); os.remove(wav)
        print(f"  Music/Track{t.n:02d}.ogg  {len(data) / 2352 / 75:6.1f} s")


# ---- wrappers and settings --------------------------------------------------------------------

def take(src, member, dst):
    """Copies the file whose path ends with `member` (case-insensitive) from a zip or folder."""
    want = member.lower()
    if os.path.isdir(src):
        for d, _, fs in os.walk(src):
            for f in fs:
                p = os.path.join(d, f)
                if os.path.relpath(p, src).replace(os.sep, "/").lower().endswith(want):
                    shutil.copyfile(p, dst); return
    else:
        with zipfile.ZipFile(src) as z:
            for name in z.namelist():
                if name.lower().endswith(want):
                    with z.open(name) as i, open(dst, "wb") as o: shutil.copyfileobj(i, o)
                    return
    sys.exit(f"{member} not found in {src}")

def dgvoodoo_conf(dst, deck):
    text = open(os.path.join(HERE, "config", "dgVoodoo.conf"), encoding="latin-1", newline="").read()
    if deck:
        out, section = [], ""
        for line in text.splitlines(keepends=True):
            if line.startswith("["): section = line.strip()
            if section == "[DirectX]" and re.match(r"Resolution\s*=", line):
                line = re.sub(r"=\s*\S+", "= max", line)
            if section == "[General]" and re.match(r"Brightness\s*=", line):
                line = re.sub(r"=\s*\S+", "= 125", line)
            out.append(line)
        text = "".join(out)
    open(dst, "w", encoding="latin-1", newline="").write(text)

def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("disc"); ap.add_argument("--dgvoodoo", required=True)
    ap.add_argument("--ogg-winmm", required=True); ap.add_argument("--out", default=HERE)
    ap.add_argument("--steam-deck", action="store_true"); ap.add_argument("--no-full-trails", action="store_true")
    a = ap.parse_args()

    tracks = parse_ccd(a.disc) if a.disc.lower().endswith(".ccd") else parse_cue(a.disc)
    data = [t for t in tracks if t.kind != "AUDIO"]
    if not data: sys.exit("no data track in " + a.disc)
    pkg = os.path.join(os.path.abspath(a.out), "Wipeout2097"); game = os.path.join(pkg, "game")
    if os.path.exists(game): sys.exit(f"{game} already exists: move or delete it first")

    print("1/5 game files from the data track")
    print(f"  {extract(DataTrack(data[0]), game)} files")
    exe = os.path.join(game, "D3D.EXE")
    if md5(exe) != EXE_MD5:
        sys.exit(f"D3D.EXE on this disc is not the one the patches are for (MD5 {md5(exe)}, "
                 f"expected {EXE_MD5}: European Direct3D CD, 14 May 1997)")

    print("2/5 patching D3D.EXE")
    trails = not a.no_full_trails
    subprocess.run([sys.executable, os.path.join(HERE, "patch_exe.py")] + ["--full-trails"] * trails + [exe],
                   check=True, stdout=subprocess.DEVNULL)
    print("  matches the tested exe" if md5(exe) == PATCHED_MD5[trails] else "  warning: result differs from the tested exe")
    # CONFIG.DAT stays the disc's: its 1234 / 5678 marker makes the game set its defaults and save them

    print("3/5 soundtrack")
    with tempfile.TemporaryDirectory() as tmp: rip(tracks, os.path.join(game, "Music"), tmp)

    print("4/5 wrappers")
    take(a.dgvoodoo, "MS/x86/DDraw.dll", os.path.join(game, "ddraw.dll"))
    take(a.dgvoodoo, "MS/x86/D3DImm.dll", os.path.join(game, "d3dimm.dll"))
    take(a.ogg_winmm, "winmm.dll", os.path.join(game, "winmm.dll"))
    take(a.ogg_winmm, "winmm.ini", os.path.join(game, "winmm.ini"))
    dgvoodoo_conf(os.path.join(game, "dgVoodoo.conf"), a.steam_deck)

    print("5/5 Steam Deck / Linux launch script")
    launch = os.path.join(pkg, "wipeout2097_launch.sh")
    shutil.copyfile(os.path.join(HERE, "steamdeck", "wipeout2097_launch.sh"), launch)
    os.chmod(launch, 0o755)
    print(f"\ndone: {pkg}\n  Windows: run game/D3D.EXE   Steam Deck: see README.md")

if __name__ == "__main__":
    main()
