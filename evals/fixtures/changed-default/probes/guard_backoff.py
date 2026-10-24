import os
import sys

sys.path.insert(0, os.getcwd())
from retry import backoff_schedule

got = backoff_schedule("100,250")
sys.exit(0 if len(got) == 2 and abs(got[0] - 0.1) < 1e-9 and abs(got[1] - 0.25) < 1e-9 else 1)
