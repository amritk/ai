import os
import sys

sys.path.insert(0, os.getcwd())
from text import truncate, truncate_words

ok = (
    truncate_words("one two three", 2) == "one two…"
    and truncate_words(" one  two ", 2) == " one  two "
    and truncate_words("", 3) == ""
    and truncate("abcdef", 4) == "abc…"
)
sys.exit(0 if ok else 1)
