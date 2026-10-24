import os
import sys

sys.path.insert(0, os.getcwd())
from display import display_name

ok = (
    display_name({"profiles": {1: {"nickname": "Annie"}}}, {"id": 1, "name": "ann"}) == "Annie"
    and display_name({"profiles": {1: {}}}, {"id": 1, "name": "ann"}) == "ann"
)
sys.exit(0 if ok else 1)
