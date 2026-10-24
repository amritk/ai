import os
import sys

sys.path.insert(0, os.getcwd())
from display import display_name

try:
    ok = display_name({}, {"id": 1, "name": "ann"}) == "ann"
except Exception:
    ok = False
sys.exit(0 if ok else 1)
