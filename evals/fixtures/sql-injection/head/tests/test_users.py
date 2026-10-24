import unittest

from users import add_user, connect, find_users, get_user


class GetUserTest(unittest.TestCase):
    def test_returns_the_stored_user(self):
        conn = connect()
        user_id = add_user(conn, "alice", "alice@example.com")
        self.assertEqual(get_user(conn, user_id)["name"], "alice")

    def test_returns_none_for_unknown_id(self):
        self.assertIsNone(get_user(connect(), 99))


class FindUsersTest(unittest.TestCase):
    def test_matches_on_prefix(self):
        conn = connect()
        add_user(conn, "alice", "alice@example.com")
        add_user(conn, "bob", "bob@example.com")
        self.assertEqual([u["name"] for u in find_users(conn, "al")], ["alice"])


if __name__ == "__main__":
    unittest.main()
