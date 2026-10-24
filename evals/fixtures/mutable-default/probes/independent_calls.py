import os
import sys

sys.path.insert(0, os.getcwd())
from tags import with_tag

sys.exit(0 if with_tag("A") == ["a"] and with_tag("B") == ["b"] else 1)
