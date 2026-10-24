import os
import sys

sys.path.insert(0, os.getcwd())
from tags import with_tag

got = with_tag("x", ["y"])
sys.exit(0 if sorted(got) == ["x", "y"] else 1)
