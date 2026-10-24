import unittest

from urls import path_join


class PathJoinTest(unittest.TestCase):
    def test_joins_and_encodes(self):
        self.assertEqual(path_join("/a/", "b c", ""), "/a/b%20c")


if __name__ == "__main__":
    unittest.main()
