import os
import sys

sys.path.insert(0, os.getcwd())
from checkout import cart_total

try:
    ok = cart_total([(50, 2)], 15) == 85.0 and cart_total([(100, 1)], 1) == 99.0
except Exception:
    ok = False
sys.exit(0 if ok else 1)
