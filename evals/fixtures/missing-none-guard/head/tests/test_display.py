import unittest

from display import display_name


class DisplayNameTest(unittest.TestCase):
    def test_prefers_nickname(self):
        store = {"profiles": {1: {"nickname": "Annie"}}}
        self.assertEqual(display_name(store, {"id": 1, "name": "ann"}), "Annie")


if __name__ == "__main__":
    unittest.main()
