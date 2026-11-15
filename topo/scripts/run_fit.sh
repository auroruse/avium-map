#!/bin/zsh
# city anchors -> fit -> make neighbours agree along shared borders -> refit -> city and border corrections -> checks
set -e
cd "$(dirname "$0")/.."
PY=".venv/bin/python -I"
${=PY} scripts/anchors.py
${=PY} scripts/fit.py | tail -3
${=PY} scripts/seams.py --targets | grep -v "^  "
${=PY} scripts/fit.py --targets | tail -3
# no more fitting from here: carry the warps through the cities, then weld neighbours along shared borders
${=PY} scripts/donors.py
${=PY} scripts/postfit.py
${=PY} scripts/seams.py | head -1
${=PY} scripts/weld.py
${=PY} scripts/seams.py | head -1
${=PY} scripts/qa.py | head -1
${=PY} scripts/folds.py warps.pkl
