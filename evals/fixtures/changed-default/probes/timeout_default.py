import os
import sys

sys.path.insert(0, os.getcwd())
os.environ.pop("REQUEST_TIMEOUT", None)
from config import request_timeout

sys.exit(0 if request_timeout() == 30 else 1)
