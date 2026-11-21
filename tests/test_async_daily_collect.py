"""Tests for the async-daily `collect.py` CLI.

Most tests build throwaway git repos with fixed identities and dates, run the
CLI the way the skill does, and assert on the JSON it prints. A local bare repo
stands in as `origin` wherever "landed" (reachable from a remote ref) matters;
nothing touches the network.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from tests.helpers import SKILLS, load_script, run_script

SCRIPT = SKILLS / "async-daily" / "scripts" / "collect.py"
collect = load_script(SCRIPT, "async_daily_collect")

JANE = ("Jane Doe", "jane@example.com")
BOB = ("Bob Smith", "bob@example.com")
AGENT = ("Claude", "noreply@anthropic.com")
RENOVATE = ("renovate[bot]", "29139614+renovate[bot]@users.noreply.github.com")

SINCE = "2026-01-01T00:00:00+00:00"
OLD = "2025-12-01T10:00:00+00:00"


def day(n: int, hour: int = 10) -> str:
    """A fixed timestamp inside the window: 2026-01-<n> at <hour>:00 UTC."""
    return f"2026-01-{n:02d}T{hour:02d}:00:00+00:00"


def clean_env(**extra: str) -> dict[str, str]:
    """The current environment minus anything that would leak real git config or identity."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_") and k != "ASYNC_DAILY_AUTHORS"
    }
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env.update(extra)
    return env


class Repo:
    """A scratch git repo whose commits get deterministic identities and dates."""

    def __init__(self, path: pathlib.Path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")

    def git(
        self,
        *args: str,
        who: tuple[str, str] = JANE,
        date: str = day(2),
        committer: tuple[str, str] | None = None,
    ) -> str:
        cname, cemail = committer or who
        env = clean_env(
            GIT_AUTHOR_NAME=who[0],
            GIT_AUTHOR_EMAIL=who[1],
            GIT_AUTHOR_DATE=date,
            GIT_COMMITTER_NAME=cname,
            GIT_COMMITTER_EMAIL=cemail,
            GIT_COMMITTER_DATE=date,
        )
        done = subprocess.run(
            ["git", "-C", str(self.path), *args], env=env, capture_output=True, text=True, check=True
        )
        return done.stdout

    def write(self, name: str, content: str = "x\n") -> None:
        target = self.path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def commit(
        self,
        subject: str,
        files: list[str],
        *,
        who: tuple[str, str] = JANE,
        date: str = day(2),
        body: str | None = None,
        committer: tuple[str, str] | None = None,
    ) -> str:
        for name in files:
            self.write(name, f"{subject}\n")
        self.git("add", "--", *files)
        message = ["-m", subject] + (["-m", body] if body else [])
        self.git("commit", "-q", *message, who=who, date=date, committer=committer)
        return self.git("rev-parse", "HEAD").strip()

    def add_origin(self, bare: pathlib.Path, slug: str = "acme/widgets") -> None:
        """Point origin's fetch URL at GitHub (never fetched) and its push URL at a local bare repo."""
        subprocess.run(
            ["git", "init", "-q", "--bare", "-b", "main", str(bare)], env=clean_env(), check=True
        )
        self.git("remote", "add", "origin", f"git@github.com:{slug}.git")
        self.git("config", "remote.origin.pushurl", str(bare))

    def push(self, branch: str = "main") -> None:
        self.git("push", "-q", "origin", branch)


def run_collect(*args: str, cwd: pathlib.Path | None = None, env: dict[str, str] | None = None):
    return run_script(SCRIPT, *args, cwd=cwd, env=env or clean_env())


def collect_json(*args: str, cwd: pathlib.Path | None = None, env: dict[str, str] | None = None) -> dict:
    done = run_collect(*args, cwd=cwd, env=env)
    if done.returncode != 0:
        raise AssertionError(f"collect.py exited {done.returncode}: {done.stderr}")
    return normalise_dates(json.loads(done.stdout))


def normalise_dates(value):
    """Spell every UTC `date` as `+00:00`.

    git's `%aI` writes UTC as `+00:00` up to some version and as `Z` after it
    (the CI runner's git does the latter), so exact-string assertions would
    otherwise depend on the machine's git.
    """
    if isinstance(value, dict):
        return {
            k: v[:-1] + "+00:00" if k == "date" and isinstance(v, str) and v.endswith("Z") else normalise_dates(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [normalise_dates(v) for v in value]
    return value


def only_repo(output: dict) -> dict:
    assert len(output["repos"]) == 1, output["repos"]
    return output["repos"][0]


def record(*fields: str) -> str:
    """One record in the delimited stream `collect_repo` asks `git log` for."""
    return collect.RS + collect.FS.join(fields)


class ParseLogTest(unittest.TestCase):
    def test_parse_log_splits_each_record_into_named_fields(self):
        raw = record(
            " abc123 ",
            "2026-01-02T10:00:00+00:00",
            "jane@example.com",
            "Jane Doe",
            "jane@example.com",
            "Add parser (#12)",
            "Body line\n",
            "\n\nsrc/parser.py\nREADME.md\n",
        )

        self.assertEqual(
            collect.parse_log(raw),
            [
                {
                    "sha": "abc123",
                    "date": "2026-01-02T10:00:00+00:00",
                    "author_email": "jane@example.com",
                    "author_name": "Jane Doe",
                    "committer_email": "jane@example.com",
                    "subject": "Add parser (#12)",
                    "body": "Body line",
                    "files": ["src/parser.py", "README.md"],
                }
            ],
        )

    def test_parse_log_keeps_a_multi_paragraph_body_out_of_the_file_list(self):
        raw = record("a1", "d", "e", "n", "c", "Subject", "First paragraph.\n\nSecond paragraph.\n", "\nfile.txt\n")

        (commit,) = collect.parse_log(raw)

        self.assertEqual(commit["body"], "First paragraph.\n\nSecond paragraph.")
        self.assertEqual(commit["files"], ["file.txt"])

    def test_parse_log_returns_one_record_per_commit_in_stream_order(self):
        raw = record("a1", "d", "e", "n", "c", "First", "", "\na.txt\n") + record(
            "b2", "d", "e", "n", "c", "Second", "", "\nb.txt\n"
        )

        self.assertEqual([c["sha"] for c in collect.parse_log(raw)], ["a1", "b2"])

    def test_parse_log_skips_blank_and_truncated_records(self):
        raw = collect.RS + "  \n" + record("a1", "d", "e", "n", "c", "Too few fields")

        self.assertEqual(collect.parse_log(raw), [])

    def test_parse_log_reads_a_commit_with_no_files_as_an_empty_list(self):
        (commit,) = collect.parse_log(record("a1", "d", "e", "n", "c", "Empty", "", "\n"))

        self.assertEqual(commit["files"], [])


class MatchesTest(unittest.TestCase):
    def commit(self, **overrides: str) -> dict:
        base = {
            "author_email": "bob@example.com",
            "author_name": "Bob Smith",
            "committer_email": "bob@example.com",
            "body": "",
        }
        return {**base, **overrides}

    def test_matches_author_email_by_case_insensitive_substring(self):
        self.assertTrue(collect.matches(self.commit(author_email="Jane.Doe@Example.com"), ["jane"]))

    def test_matches_author_name_by_case_insensitive_substring(self):
        self.assertTrue(collect.matches(self.commit(author_name="Jane Doe"), ["JANE D"]))

    def test_matches_committer_email(self):
        self.assertTrue(collect.matches(self.commit(committer_email="jane@example.com"), ["jane@"]))

    def test_matches_co_authored_by_trailer_in_body(self):
        body = "Did the thing.\n\nCo-authored-by: Jane Doe <jane@example.com>"

        self.assertTrue(collect.matches(self.commit(body=body), ["jane@example.com"]))

    def test_matches_co_authored_by_trailer_regardless_of_case(self):
        body = "CO-AUTHORED-BY: Jane Doe <jane@example.com>"

        self.assertTrue(collect.matches(self.commit(body=body), ["jane"]))

    def test_matches_ignores_a_name_only_mentioned_in_body_prose(self):
        body = "Reviewed with Jane, thanks jane@example.com for the idea."

        self.assertFalse(collect.matches(self.commit(body=body), ["jane"]))

    def test_matches_is_true_when_any_of_several_patterns_match(self):
        self.assertTrue(collect.matches(self.commit(), ["jane", "bob@"]))

    def test_matches_is_false_for_an_unrelated_identity(self):
        self.assertFalse(collect.matches(self.commit(), ["jane"]))


class RegexTest(unittest.TestCase):
    def test_squash_pattern_extracts_trailing_pr_number(self):
        match = collect.SQUASH_PR_RE.search("feat: add parser (#1354)")

        self.assertEqual(match.group(1), "1354")
        self.assertEqual(collect.SQUASH_PR_RE.sub("", "feat: add parser (#1354)"), "feat: add parser")

    def test_squash_pattern_ignores_a_pr_reference_mid_subject(self):
        self.assertIsNone(collect.SQUASH_PR_RE.search("revert (#12) and retry"))

    def test_merge_pattern_reads_number_and_source_branch(self):
        match = collect.MERGE_PR_RE.match("Merge pull request #344 from jane/feature")

        self.assertEqual(match.groups(), ("344", "jane/feature"))

    def test_release_pattern_matches_release_automation_subjects(self):
        for subject in ["Release v1.2.0", "chore: release 3.0", "Version Packages", "chore: version packages"]:
            with self.subTest(subject=subject):
                self.assertIsNotNone(collect.RELEASE_RE.match(subject))

    def test_release_pattern_does_not_match_ordinary_subjects(self):
        for subject in ["fix release script", "Releases page copy", "chore: bump deps"]:
            with self.subTest(subject=subject):
                self.assertIsNone(collect.RELEASE_RE.match(subject))

    def test_bot_pattern_matches_bot_identities_but_not_people(self):
        self.assertIsNotNone(collect.BOT_PATTERN.search("dependabot[bot]"))
        self.assertIsNotNone(collect.BOT_PATTERN.search("github-actions@github.com"))
        self.assertIsNotNone(collect.BOT_PATTERN.search("Renovate Bot"))
        self.assertIsNone(collect.BOT_PATTERN.search("jane@example.com"))


class InstantTest(unittest.TestCase):
    def test_instant_reads_newer_gits_z_suffix_as_utc(self):
        self.assertEqual(collect.instant("2026-01-02T08:00:00Z"), collect.instant("2026-01-02T08:00:00+00:00"))

    def test_instant_reads_an_offset_date_as_the_same_moment_in_utc(self):
        self.assertEqual(
            collect.instant("2026-01-02T10:00:00+05:00"),
            datetime(2026, 1, 2, 5, 0, tzinfo=timezone.utc),
        )

    def test_instant_orders_dates_by_moment_where_string_order_disagrees(self):
        earlier, later = "2026-01-02T10:00:00+05:00", "2026-01-02T08:00:00+00:00"

        self.assertGreater(earlier, later)
        self.assertLess(collect.instant(earlier), collect.instant(later))


class HasWorkTest(unittest.TestCase):
    def repo(self, **overrides) -> dict:
        base = {
            "prs": [],
            "loose_commits": [],
            "local": {"unpushed": [], "staged": [], "unstaged": [], "untracked": []},
        }
        return {**base, **overrides}

    def test_has_work_is_false_for_an_empty_repo_summary(self):
        self.assertFalse(collect.has_work(self.repo()))

    def test_has_work_is_true_for_any_pr_loose_commit_or_local_change(self):
        cases = {
            "pr": self.repo(prs=[{"number": 1}]),
            "loose": self.repo(loose_commits=[{"subject": "x"}]),
            "untracked": self.repo(
                local={"unpushed": [], "staged": [], "unstaged": [], "untracked": ["a.txt"]}
            ),
        }
        for name, summary in cases.items():
            with self.subTest(name):
                self.assertTrue(collect.has_work(summary))


class RemoteSlugTest(unittest.TestCase):
    def test_remote_slug_reads_owner_and_repo_from_each_url_form(self):
        urls = {
            "git@github.com:acme/widgets.git": "acme/widgets",
            "https://github.com/acme/widgets.git": "acme/widgets",
            "https://github.com/acme/widgets": "acme/widgets",
            "ssh://git@github.com/acme/widgets.git": "acme/widgets",
        }
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo(pathlib.Path(tmp) / "r")
            repo.git("remote", "add", "origin", "placeholder")
            for url, slug in urls.items():
                with self.subTest(url=url):
                    repo.git("remote", "set-url", "origin", url)
                    self.assertEqual(collect.remote_slug(repo.path), slug)

    def test_remote_slug_is_empty_without_an_origin_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo(pathlib.Path(tmp) / "r")

            self.assertEqual(collect.remote_slug(repo.path), "")


class DiscoverTest(unittest.TestCase):
    def test_discover_keeps_only_explicit_paths_that_are_repos(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            repo = Repo(base / "real")
            (base / "plain").mkdir()

            found = collect.discover([str(repo.path), str(base / "plain"), str(base / "missing")], None)

            self.assertEqual(found, [repo.path.resolve()])

    def test_discover_lists_child_repos_of_root_in_name_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            Repo(base / "zeta")
            Repo(base / "alpha")
            (base / "notes").mkdir()

            found = collect.discover([], str(base))

            self.assertEqual(found, [(base / "alpha").resolve(), (base / "zeta").resolve()])

    def test_discover_falls_back_to_root_itself_when_it_is_a_repo_with_no_child_repos(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo(pathlib.Path(tmp) / "solo")
            (repo.path / "src").mkdir()

            self.assertEqual(collect.discover([], str(repo.path)), [repo.path.resolve()])

    def test_discover_returns_nothing_for_a_root_that_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(collect.discover([], str(pathlib.Path(tmp) / "missing")), [])


class CollectCliTest(unittest.TestCase):
    """End-to-end runs of the CLI against scratch repos."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = pathlib.Path(self._tmp.name)
        self.repo = Repo(self.base / "widgets")
        self.repo.add_origin(self.base / "origin.git")

    def run_jane(self, *extra: str) -> dict:
        return collect_json("--repo", str(self.repo.path), "--author", "jane", "--since", SINCE, *extra)

    # --- merge styles -------------------------------------------------------

    def test_squash_merged_commit_is_grouped_under_its_pr_number_with_suffix_stripped(self):
        self.repo.commit("Add parser (#12)", ["src/parser.py", "README.md"], date=day(2))
        self.repo.push()

        repo = only_repo(self.run_jane())

        self.assertEqual(
            repo["prs"],
            [
                {
                    "number": 12,
                    "title": "Add parser",
                    "date": day(2),
                    "commits": ["Add parser (#12)"],
                    "files": ["README.md", "src/parser.py"],
                }
            ],
        )
        self.assertEqual(repo["loose_commits"], [])

    def test_merge_commit_pr_groups_the_commits_underneath_it_and_takes_title_from_merge_body(self):
        self.repo.commit("Initial", ["README.md"], date=day(1))
        self.repo.git("checkout", "-q", "-b", "feature")
        self.repo.commit("Sketch widget", ["src/widget.py"], date=day(2, 9))
        self.repo.commit("Test widget", ["tests/test_widget.py", "src/widget.py"], date=day(2, 11))
        self.repo.git("checkout", "-q", "main")
        self.repo.git(
            "merge", "-q", "--no-ff", "feature",
            "-m", "Merge pull request #344 from jane/feature", "-m", "Add a widget",
            date=day(2, 12),
        )
        self.repo.push()

        repo = only_repo(self.run_jane())

        self.assertEqual(
            repo["prs"],
            [
                {
                    "number": 344,
                    "title": "Add a widget",
                    "date": day(2, 11),
                    "commits": ["Test widget", "Sketch widget"],
                    "files": ["src/widget.py", "tests/test_widget.py"],
                }
            ],
        )
        self.assertEqual(
            repo["loose_commits"], [{"subject": "Initial", "date": day(1), "files": ["README.md"]}]
        )

    def test_merge_commit_without_a_body_falls_back_to_the_source_branch_as_title(self):
        self.repo.commit("Initial", ["README.md"], date=day(1), who=BOB)
        self.repo.git("checkout", "-q", "-b", "feature")
        self.repo.commit("Tweak copy", ["copy.txt"], date=day(2))
        self.repo.git("checkout", "-q", "main")
        self.repo.git(
            "merge", "-q", "--no-ff", "feature", "-m", "Merge pull request #7 from jane/copy", date=day(3)
        )
        self.repo.push()

        (pr,) = only_repo(self.run_jane())["prs"]

        self.assertEqual((pr["number"], pr["title"], pr["commits"]), (7, "jane/copy", ["Tweak copy"]))

    def test_both_merge_styles_in_one_repo_are_listed_newest_pr_first(self):
        self.repo.commit("Add parser (#12)", ["parser.py"], date=day(2))
        self.repo.git("checkout", "-q", "-b", "feature")
        self.repo.commit("Add lexer", ["lexer.py"], date=day(3))
        self.repo.git("checkout", "-q", "main")
        self.repo.git(
            "merge", "-q", "--no-ff", "feature",
            "-m", "Merge pull request #13 from jane/lexer", "-m", "Lexer",
            date=day(4),
        )
        self.repo.commit("Fix parser (#14)", ["parser.py"], date=day(5))
        self.repo.push()

        output = self.run_jane()

        self.assertEqual([(p["number"], p["title"]) for p in only_repo(output)["prs"]],
                         [(14, "Fix parser"), (13, "Lexer"), (12, "Add parser")])
        self.assertEqual(output["totals"]["prs"], 3)

    def test_merge_commit_pr_only_counts_the_authors_own_commits(self):
        self.repo.commit("Initial", ["README.md"], date=day(1), who=BOB)
        self.repo.git("checkout", "-q", "-b", "feature")
        self.repo.commit("Jane part", ["a.txt"], date=day(2, 9))
        self.repo.commit("Bob part", ["b.txt"], date=day(2, 10), who=BOB)
        self.repo.git("checkout", "-q", "main")
        self.repo.git(
            "merge", "-q", "--no-ff", "feature",
            "-m", "Merge pull request #5 from jane/pair", "-m", "Pair on a and b",
            date=day(2, 11), who=BOB,
        )
        self.repo.push()

        repo = only_repo(self.run_jane())

        (pr,) = repo["prs"]
        self.assertEqual((pr["commits"], pr["files"]), (["Jane part"], ["a.txt"]))
        self.assertEqual(repo["other_commits"], 2)

    # --- commits outside any PR --------------------------------------------

    def test_pushed_commit_without_a_pr_number_is_a_loose_commit(self):
        self.repo.commit("Tidy docs", ["docs/index.md"], date=day(2))
        self.repo.commit("Tidy more docs", ["docs/more.md"], date=day(3))
        self.repo.push()

        output = self.run_jane()
        repo = only_repo(output)

        self.assertEqual(repo["prs"], [])
        self.assertEqual(
            repo["loose_commits"],
            [
                {"subject": "Tidy more docs", "date": day(3), "files": ["docs/more.md"]},
                {"subject": "Tidy docs", "date": day(2), "files": ["docs/index.md"]},
            ],
        )
        self.assertEqual(output["totals"]["loose_commits"], 2)

    def test_commits_on_a_pushed_but_unmerged_branch_count_as_landed_loose_commits(self):
        self.repo.commit("Initial", ["README.md"], date=day(1), who=BOB)
        self.repo.push()
        self.repo.git("checkout", "-q", "-b", "wip")
        self.repo.commit("Start refactor", ["core.py"], date=day(2))
        self.repo.push("wip")

        repo = only_repo(self.run_jane())

        self.assertEqual(repo["loose_commits"], [{"subject": "Start refactor", "date": day(2), "files": ["core.py"]}])
        self.assertEqual(repo["local"]["unpushed"], [])
        self.assertEqual(repo["branch"], "wip")

    # --- author filtering ---------------------------------------------------

    def test_author_filter_counts_teammate_commits_as_other_and_leaves_them_out(self):
        self.repo.commit("Jane change (#1)", ["a.txt"], date=day(2))
        self.repo.commit("Bob change (#2)", ["b.txt"], date=day(3), who=BOB)
        self.repo.commit("Bob loose", ["c.txt"], date=day(4), who=BOB)
        self.repo.push()

        repo = only_repo(self.run_jane())

        self.assertEqual([p["number"] for p in repo["prs"]], [1])
        self.assertEqual(repo["loose_commits"], [])
        self.assertEqual((repo["other_commits"], repo["agent_commits"]), (2, 0))

    def test_agent_commits_are_counted_separately_unless_co_authored_by_the_user(self):
        self.repo.commit("Agent alone", ["a.txt"], date=day(2), who=AGENT)
        self.repo.commit(
            "Agent with Jane (#9)", ["b.txt"], date=day(3), who=AGENT,
            body="Co-authored-by: Jane Doe <jane@example.com>",
        )
        self.repo.push()

        output = self.run_jane()
        repo = only_repo(output)

        self.assertEqual([(p["number"], p["title"]) for p in repo["prs"]], [(9, "Agent with Jane")])
        self.assertEqual((repo["agent_commits"], repo["other_commits"]), (1, 0))
        self.assertEqual(output["totals"]["agent_commits"], 1)

    def test_commit_authored_by_someone_else_but_committed_by_the_user_is_included(self):
        self.repo.commit("Cherry-picked fix", ["fix.txt"], date=day(2), who=BOB, committer=JANE)
        self.repo.push()

        repo = only_repo(self.run_jane())

        self.assertEqual([c["subject"] for c in repo["loose_commits"]], ["Cherry-picked fix"])

    def test_bot_and_release_commits_are_dropped_without_being_counted(self):
        self.repo.commit("Bump lodash", ["package.json"], date=day(2), who=RENOVATE)
        self.repo.commit("chore: release 1.2.0", ["CHANGELOG.md"], date=day(3))
        self.repo.commit("Version Packages (#30)", ["CHANGELOG.md"], date=day(4))
        self.repo.commit("Real work (#31)", ["src.py"], date=day(5))
        self.repo.push()

        repo = only_repo(self.run_jane())

        self.assertEqual([p["number"] for p in repo["prs"]], [31])
        self.assertEqual(repo["loose_commits"], [])
        self.assertEqual((repo["other_commits"], repo["agent_commits"]), (0, 0))

    def test_repeated_author_flags_match_any_of_the_identities(self):
        self.repo.commit("From work address", ["a.txt"], date=day(2))
        self.repo.commit("From personal address", ["b.txt"], date=day(3), who=("J. Doe", "jd@personal.dev"))
        self.repo.commit("Bob loose", ["c.txt"], date=day(4), who=BOB)
        self.repo.push()

        output = collect_json(
            "--repo", str(self.repo.path), "--author", "jane@", "--author", "jd@personal", "--since", SINCE
        )

        self.assertEqual(output["authors"], ["jane@", "jd@personal"])
        self.assertEqual(
            [c["subject"] for c in only_repo(output)["loose_commits"]],
            ["From personal address", "From work address"],
        )

    def test_authors_come_from_async_daily_authors_env_when_no_flag_is_given(self):
        self.repo.commit("Bob loose", ["c.txt"], date=day(2), who=BOB)
        self.repo.push()

        output = collect_json(
            "--repo", str(self.repo.path), "--since", SINCE,
            env=clean_env(ASYNC_DAILY_AUTHORS="nobody,bob@,"),
        )

        self.assertEqual(output["authors"], ["nobody", "bob@"])
        self.assertEqual([c["subject"] for c in only_repo(output)["loose_commits"]], ["Bob loose"])

    def test_authors_from_env_are_stripped_of_spaces_around_commas(self):
        github = ("GitHub", "noreply@github.com")
        self.repo.commit("Bob work", ["b.txt"], date=day(2), who=BOB, committer=github)
        self.repo.push()

        output = collect_json(
            "--repo", str(self.repo.path), "--since", SINCE,
            env=clean_env(ASYNC_DAILY_AUTHORS="jane@example.com, bob@example.com"),
        )

        self.assertEqual(output["authors"], ["jane@example.com", "bob@example.com"])
        self.assertEqual([c["subject"] for c in only_repo(output)["loose_commits"]], ["Bob work"])

    def test_missing_author_exits_2_with_guidance_and_no_output(self):
        done = run_collect("--repo", str(self.repo.path))

        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stdout, "")
        self.assertIn("error: no author identity given", done.stderr)
        self.assertIn("ASYNC_DAILY_AUTHORS", done.stderr)

    # --- time window --------------------------------------------------------

    def test_since_excludes_commits_older_than_the_window(self):
        self.repo.commit("Old work (#1)", ["old.txt"], date=OLD)
        self.repo.commit("New work (#2)", ["new.txt"], date=day(2))
        self.repo.push()

        output = self.run_jane()

        self.assertEqual(output["since"], SINCE)
        self.assertEqual([p["number"] for p in only_repo(output)["prs"]], [2])

    def test_days_sets_the_window_relative_to_now(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.repo.commit("Three days ago", ["a.txt"], date=(now - timedelta(days=3)).isoformat())
        self.repo.commit("Two hours ago", ["b.txt"], date=(now - timedelta(hours=2)).isoformat())
        self.repo.push()

        for days, expected in [("1", ["Two hours ago"]), ("5", ["Two hours ago", "Three days ago"])]:
            with self.subTest(days=days):
                output = collect_json("--repo", str(self.repo.path), "--author", "jane", "--days", days)

                self.assertEqual(output["days"], float(days))
                self.assertEqual([c["subject"] for c in only_repo(output)["loose_commits"]], expected)

    def test_repo_with_only_old_work_is_scanned_but_not_reported(self):
        self.repo.commit("Old work (#1)", ["old.txt"], date=OLD)
        self.repo.push()

        output = self.run_jane()

        self.assertEqual(output["repos_scanned"], ["widgets"])
        self.assertEqual(output["remotes"], ["acme/widgets"])
        self.assertEqual(output["repos"], [])
        self.assertEqual(output["totals"], {"prs": 0, "loose_commits": 0, "agent_commits": 0})

    # --- mixed time zones ---------------------------------------------------
    # 10:00+05:00 is 05:00 UTC, three hours before 08:00+00:00, though it sorts
    # after it as a string.

    def test_prs_are_ordered_newest_first_by_moment_across_utc_offsets(self):
        self.repo.commit("Earlier in UTC+5 (#1)", ["a.txt"], date="2026-01-02T10:00:00+05:00")
        self.repo.commit("Later in UTC (#2)", ["b.txt"], date="2026-01-02T08:00:00+00:00")
        self.repo.push()

        prs = only_repo(self.run_jane())["prs"]

        self.assertEqual(
            [(p["number"], p["date"]) for p in prs],
            [(2, "2026-01-02T08:00:00+00:00"), (1, "2026-01-02T10:00:00+05:00")],
        )

    def test_loose_commits_are_ordered_newest_first_by_moment_across_utc_offsets(self):
        self.repo.commit("Earlier in UTC+5", ["a.txt"], date="2026-01-02T10:00:00+05:00")
        self.repo.commit("Later in UTC", ["b.txt"], date="2026-01-02T08:00:00+00:00")
        self.repo.push()

        loose = only_repo(self.run_jane())["loose_commits"]

        self.assertEqual([c["subject"] for c in loose], ["Later in UTC", "Earlier in UTC+5"])

    def test_pr_date_is_its_latest_commit_by_moment_across_utc_offsets(self):
        self.repo.commit("Initial", ["README.md"], date=day(1), who=BOB)
        self.repo.git("checkout", "-q", "-b", "feature")
        self.repo.commit("Earlier in UTC+5", ["a.txt"], date="2026-01-02T10:00:00+05:00")
        self.repo.commit("Later in UTC", ["b.txt"], date="2026-01-02T08:00:00+00:00")
        self.repo.git("checkout", "-q", "main")
        self.repo.git(
            "merge", "-q", "--no-ff", "feature",
            "-m", "Merge pull request #3 from jane/tz", "-m", "Cross time zones",
            date=day(3), who=BOB,
        )
        self.repo.push()

        (pr,) = only_repo(self.run_jane())["prs"]

        self.assertEqual((pr["number"], pr["date"]), (3, "2026-01-02T08:00:00+00:00"))

    # --- local work ---------------------------------------------------------

    def test_commits_not_on_any_remote_are_reported_as_unpushed(self):
        self.repo.commit("Pushed (#1)", ["a.txt"], date=day(2))
        self.repo.push()
        self.repo.commit("Local only (#2)", ["b.txt", "c.txt"], date=day(3))

        repo = only_repo(self.run_jane())

        self.assertEqual([p["number"] for p in repo["prs"]], [1])
        self.assertEqual(repo["local"]["unpushed"], [{"subject": "Local only (#2)", "files": ["b.txt", "c.txt"]}])

    def test_without_any_remote_every_commit_is_unpushed(self):
        lone = Repo(self.base / "lone")
        lone.commit("First", ["a.txt"], date=day(2))

        output = collect_json("--repo", str(lone.path), "--author", "jane", "--since", SINCE)
        repo = only_repo(output)

        self.assertEqual(repo["remote"], "")
        self.assertEqual(output["remotes"], [])
        self.assertEqual(repo["local"]["unpushed"], [{"subject": "First", "files": ["a.txt"]}])
        self.assertEqual((repo["prs"], repo["loose_commits"]), ([], []))

    def test_dirty_working_tree_is_split_into_staged_unstaged_and_untracked(self):
        self.repo.commit("Base", ["tracked.txt", "both.txt"], date=OLD)
        self.repo.write("new_staged.txt")
        self.repo.git("add", "new_staged.txt")
        self.repo.write("both.txt", "staged\n")
        self.repo.git("add", "both.txt")
        self.repo.write("both.txt", "then edited\n")
        self.repo.write("tracked.txt", "edited\n")
        self.repo.write("skills/async-daily/SKILL.md")

        repo = only_repo(self.run_jane())

        self.assertEqual(
            repo["local"],
            {
                "unpushed": [],
                "staged": ["both.txt", "new_staged.txt"],
                "unstaged": ["both.txt", "tracked.txt"],
                "untracked": ["skills/"],
            },
        )
        self.assertEqual((repo["prs"], repo["loose_commits"]), ([], []))

    def test_dirty_tree_is_reported_even_when_it_belongs_to_nobody_in_the_author_list(self):
        self.repo.write("scratch.txt")

        output = collect_json("--repo", str(self.repo.path), "--author", "nobody", "--since", SINCE)

        self.assertEqual(only_repo(output)["local"]["untracked"], ["scratch.txt"])

    def test_repo_summary_carries_name_path_remote_and_branch(self):
        self.repo.commit("Work (#1)", ["a.txt"], date=day(2))
        self.repo.push()

        repo = only_repo(self.run_jane())

        self.assertEqual(
            (repo["name"], repo["path"], repo["remote"], repo["branch"]),
            ("widgets", str(self.repo.path.resolve()), "acme/widgets", "main"),
        )


class DiscoveryCliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = pathlib.Path(self._tmp.name)

    def make_workspace(self) -> tuple[Repo, Repo]:
        alpha = Repo(self.base / "alpha")
        alpha.commit("Alpha work", ["a.txt"], date=day(2))
        beta = Repo(self.base / "beta")
        beta.commit("Beta work", ["b.txt"], date=day(3))
        (self.base / "notes").mkdir()
        (self.base / "notes" / "todo.txt").write_text("x\n")
        return alpha, beta

    def test_root_scans_every_child_repo_and_skips_plain_directories(self):
        self.make_workspace()

        output = collect_json("--root", str(self.base), "--author", "jane", "--since", SINCE)

        self.assertEqual(output["repos_scanned"], ["alpha", "beta"])
        self.assertEqual(
            [(r["name"], r["local"]["unpushed"][0]["subject"]) for r in output["repos"]],
            [("alpha", "Alpha work"), ("beta", "Beta work")],
        )

    def test_running_inside_a_repo_without_flags_scans_it_and_its_siblings(self):
        alpha, _ = self.make_workspace()

        output = collect_json("--author", "jane", "--since", SINCE, cwd=alpha.path)

        self.assertEqual(output["repos_scanned"], ["alpha", "beta"])

    def test_repo_flag_scans_only_the_named_repos(self):
        _, beta = self.make_workspace()

        output = collect_json("--repo", str(beta.path), "--author", "jane", "--since", SINCE)

        self.assertEqual(output["repos_scanned"], ["beta"])

    def test_repo_flag_ignores_paths_that_are_not_repos(self):
        alpha, _ = self.make_workspace()

        output = collect_json(
            "--repo", str(self.base / "notes"), "--repo", str(alpha.path), "--author", "jane", "--since", SINCE
        )

        self.assertEqual(output["repos_scanned"], ["alpha"])

    def test_non_repo_path_alone_exits_2_with_no_repositories_found(self):
        self.make_workspace()

        done = run_collect("--repo", str(self.base / "notes"), "--author", "jane")

        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stdout, "")
        self.assertEqual(done.stderr.strip(), "error: no git repositories found to scan")

    def test_root_without_any_repos_exits_2(self):
        (self.base / "empty").mkdir()

        for root in [self.base / "empty", self.base / "missing"]:
            with self.subTest(root=root.name):
                done = run_collect("--root", str(root), "--author", "jane")

                self.assertEqual(done.returncode, 2)
                self.assertEqual(done.stderr.strip(), "error: no git repositories found to scan")


if __name__ == "__main__":
    unittest.main()
