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
${=PY} scripts/render.py
${=PY} scripts/install_rivers.py
${=PY} scripts/thumbs.py
