#!/bin/bash
# Wipeout 2097 (PC, 1997) Steam Deck / Proton launch wrapper.
#
# Keep it beside game/ (build.py puts it there). With the folder at /home/deck/Games/Wipeout2097:
#   Shortcut target: /home/deck/Games/Wipeout2097/game/D3D.EXE, Start In: .../game/
#   Steam > Wipeout 2097 > Properties > Launch Options:
#     /home/deck/Games/Wipeout2097/wipeout2097_launch.sh %command%
#
# D3D.EXE is the disc's Direct3D build, patched (patch_exe.py): no registry, no CD check,
# Dege's dgVoodoo crash fix. Every asset loads from game/, so no fake CD-ROM drive is needed.
#
# Every launch sets DLL overrides so Wine loads the wrappers sitting beside the exe:
#   winmm.dll            ogg-winmm: CD audio from Music/TrackNN.ogg, plus the CD-audio volume control
#   ddraw.dll, d3dimm.dll  dgVoodoo2 2.79.3: DirectDraw + Direct3D 3 -> D3D11 -> DXVK.
#                        dgVoodoo.conf caps the game at 30 fps; above that it runs too fast.
#
# RENDERER (set before the script path in Launch Options, default dgvoodoo):
#   dgvoodoo  ddraw+d3dimm from dgVoodoo2 (30 fps cap from dgVoodoo.conf)
#   wined3d   plain Wine ddraw/d3d (no fps cap: set Steam's frame limit to 30)
#   Example:  RENDERER=wined3d /home/deck/Games/Wipeout2097/wipeout2097_launch.sh %command%

set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$HERE/launch.log"
RENDERER="${RENDERER:-dgvoodoo}"
log() { echo "[$(date '+%H:%M:%S')] $*" >>"$LOG"; }
: >"$LOG"
log "args: $*"
log "RENDERER=$RENDERER  STEAM_COMPAT_DATA_PATH=${STEAM_COMPAT_DATA_PATH:-unset}"

# Proton appends its own overrides after ours.
OVR="winmm=n,b"
case "$RENDERER" in
  dgvoodoo) OVR="$OVR;ddraw=n,b;d3dimm=n,b" ;;
  wined3d)  OVR="$OVR;ddraw=b;d3dimm=b" ;;
  *)        log "unknown RENDERER '$RENDERER', using dgvoodoo"; OVR="$OVR;ddraw=n,b;d3dimm=n,b" ;;
esac
export WINEDLLOVERRIDES="${OVR}${WINEDLLOVERRIDES:+;$WINEDLLOVERRIDES}"
log "WINEDLLOVERRIDES=$WINEDLLOVERRIDES"

# Debugging: if a file named PROTON_LOG exists beside this script, Proton writes
# steam-<appid>.log here (crash addresses, exceptions). Create/delete it over SSH; no launch-option edit.
if [ -e "$HERE/PROTON_LOG" ]; then
  export PROTON_LOG=1 PROTON_LOG_DIR="$HERE"
  log "PROTON_LOG on -> $HERE/steam-*.log"
fi

for f in D3D.EXE winmm.dll winmm.ini ddraw.dll d3dimm.dll dgVoodoo.conf Music/Track02.ogg; do
  [ -e "$HERE/game/$f" ] || log "WARNING: game/$f missing"
done

log "exec: $*"
exec "$@"
