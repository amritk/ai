import os
import sys

sys.path.insert(0, os.getcwd())
from listing import paginate

items = list(range(10))
ok = paginate(items, 1, 3) == [0, 1, 2] and paginate(items, 4, 3) == [9]
sys.exit(0 if ok else 1)
