import os
import sys

sys.path.insert(0, os.getcwd())
from listing import page_count, paginate

ok = paginate(list(range(10)), 5, 3) == [] and page_count(10, 3) == 4
sys.exit(0 if ok else 1)
