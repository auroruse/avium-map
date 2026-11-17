#!/bin/zsh
# Everything after the georeference: elevation -> Avium terrain -> rivers -> the drawings in layers/.
set -e
cd "$(dirname "$0")/.."
PY=".venv/bin/python -I"
${=PY} scripts/fwd.py
${=PY} scripts/relax.py | tail -2
${=PY} scripts/assemble.py | tail -1
${=PY} scripts/rivers.py | tail -1
${=PY} scripts/nudge.py | tail -3
${=PY} scripts/terrain.py
${=PY} scripts/riverlayer.py
${=PY} scripts/carve.py
${=PY} scripts/place.py
${=PY} scripts/colour.py
rm -f work/sea_off.npy work/sea_polar.npy
${=PY} scripts/render.py
rm -f work/fine/col.npy work/fine/trust.npy work/fine/soft.npy work/fine/ks.npy work/fine/isl_row.npy work/fine/isl_col.npy work/fine/cells.npz
${=PY} scripts/hybrid.py
${=PY} scripts/install_rivers.py
${=PY} scripts/riverfine.py
${=PY} scripts/thumbs.py
