import os
import sys

sys.path.insert(0, os.getcwd())
from urls import path_join, slugify

ok = (
    slugify("Hello, World!") == "hello-world"
    and slugify("Crème Brûlée") == "creme-brulee"
    and slugify("aaa bbb", max_length=4) == "aaa"
    and path_join("/a/", "b c", "") == "/a/b%20c"
)
sys.exit(0 if ok else 1)
