import os
import sys

sys.path.insert(0, os.getcwd())
from checkout import cart_total

sys.exit(0 if cart_total([(10, 3)]) == 30.0 else 1)
