"""Tests for evals/run.py.

Nothing here invokes `claude` or any model: only `--self-test`, which builds the
fixture repos and runs their probes and suites, and the pure grading,
transcript and summary functions, fed hand-written inputs.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from tests.helpers import ROOT, load_script, run_script

SCRIPT = ROOT / "evals" / "run.py"
FIXTURES = ROOT / "evals" / "fixtures"
run = load_script(SCRIPT, "evals_run_under_test")


def git_out(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def files_under(tree: pathlib.Path) -> list[str]:
    return sorted(str(p.relative_to(tree)) for p in tree.rglob("*") if p.is_file())


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = pathlib.Path(tmp.name)


class SelfTestCliTest(unittest.TestCase):
    def test_self_test_passes_on_every_real_fixture(self):
        result = run_script(SCRIPT, "--self-test", cwd=ROOT)

        names = sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual([line.split(":")[0] for line in result.stdout.splitlines()], names)

    def test_self_test_with_cases_runs_only_those_cases_in_the_given_order(self):
        result = run_script(SCRIPT, "--self-test", "--cases", "off-by-one,clean-slugify", cwd=ROOT)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "off-by-one: 1 bugs, 1 guards\nclean-slugify: 0 bugs, 1 guards\n")


class SelfTestDetectsUnfairFixtureTest(TempDirTestCase):
    def test_self_test_reports_failing_head_suite_blind_probe_and_failing_guard(self):
        case_dir = self.tmp / "broken"
        passing = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
        failing = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.fail()\n"
        write(case_dir / "base" / "m.py", "X = 1\n")
        write(case_dir / "base" / "tests" / "test_m.py", passing)
        write(case_dir / "head" / "m.py", "X = 2\n")
        write(case_dir / "head" / "tests" / "test_m.py", failing)
        write(case_dir / "probes" / "bug.py", "raise SystemExit(0)\n")
        write(case_dir / "probes" / "guard.py", "raise SystemExit(1)\n")
        write(case_dir / "case.json", json.dumps({
            "bugs": [{"id": "b", "locations": [{"file": "m.py", "contains": "X = 2"}], "probe": "probes/bug.py"}],
            "guards": ["probes/guard.py"],
        }))
        stdout, stderr = io.StringIO(), io.StringIO()

        with mock.patch.object(run, "FIXTURES", self.tmp), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = run.self_test([run.load_case("broken")])

        self.assertEqual(code, 1)
        self.assertEqual(stdout.getvalue(), "broken: 1 bugs, 1 guards\n")
        self.assertEqual(stderr.getvalue().splitlines(), [
            "error: broken: head's own tests fail",
            "error: broken: probe probes/bug.py passes on head, so it cannot detect the bug",
            "error: broken: guard probes/guard.py fails on head",
        ])


class LoadCaseTest(TempDirTestCase):
    def test_load_case_sets_name_and_resolves_contains_to_its_line_number(self):
        case = run.load_case("off-by-one")

        self.assertEqual(case["name"], "off-by-one")
        self.assertEqual(case["guards"], ["probes/guard_past_end.py"])
        self.assertEqual(case["bugs"][0]["locations"],
                         [{"file": "listing.py", "contains": "start = page * per_page", "line": 17}])

    def test_load_case_resolves_every_location_of_a_bug_in_its_own_file(self):
        case = run.load_case("changed-default")

        self.assertEqual([(loc["file"], loc["line"]) for loc in case["bugs"][0]["locations"]],
                         [("durations.py", 6), ("config.py", 10)])

    def test_load_case_of_clean_case_has_no_bugs(self):
        self.assertEqual(run.load_case("clean-slugify")["bugs"], [])

    def write_case(self, head_text: str, contains: str) -> None:
        write(self.tmp / "fake" / "head" / "m.py", head_text)
        write(self.tmp / "fake" / "case.json", json.dumps({
            "bugs": [{"id": "b", "locations": [{"file": "m.py", "contains": contains}], "probe": "p.py"}],
            "guards": [],
        }))

    def test_load_case_rejects_contains_that_matches_no_line(self):
        self.write_case("a = 1\n", "b = 2")

        with mock.patch.object(run, "FIXTURES", self.tmp), self.assertRaises(SystemExit) as raised:
            run.load_case("fake")

        self.assertEqual(str(raised.exception), "fake: 'b = 2' matches 0 lines of m.py, need exactly 1")

    def test_load_case_rejects_contains_that_matches_several_lines(self):
        self.write_case("x = 1\nx = 1\n", "x = 1")

        with mock.patch.object(run, "FIXTURES", self.tmp), self.assertRaises(SystemExit) as raised:
            run.load_case("fake")

        self.assertEqual(str(raised.exception), "fake: 'x = 1' matches 2 lines of m.py, need exactly 1")


class BuildRepoTest(TempDirTestCase):
    def test_build_repo_commits_base_on_main_and_head_on_feature_branch(self):
        repo = run.build_repo(run.load_case("off-by-one"), self.tmp, None)
        fixture = FIXTURES / "off-by-one"

        self.assertEqual(repo, self.tmp / "off-by-one")
        self.assertEqual(git_out(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split(),
                         ["feature", "main"])
        self.assertEqual(git_out(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(), "feature")
        self.assertEqual(git_out(repo, "log", "--format=%s", "main").splitlines(), ["base"])
        self.assertEqual(git_out(repo, "log", "--format=%s", "feature").splitlines(), ["feature", "base"])
        self.assertEqual(git_out(repo, "show", "main:listing.py"), (fixture / "base" / "listing.py").read_text())
        self.assertEqual(git_out(repo, "show", "feature:listing.py"), (fixture / "head" / "listing.py").read_text())
        self.assertEqual(git_out(repo, "status", "--porcelain"), "")

    def test_build_repo_trees_match_fixture_base_and_head_file_lists(self):
        repo = run.build_repo(run.load_case("changed-default"), self.tmp, None)
        fixture = FIXTURES / "changed-default"

        self.assertEqual(git_out(repo, "ls-tree", "-r", "--name-only", "main").split(),
                         files_under(fixture / "base"))
        self.assertEqual(git_out(repo, "ls-tree", "-r", "--name-only", "feature").split(),
                         files_under(fixture / "head"))

    def test_build_repo_puts_claude_dir_on_main_so_it_is_not_in_the_diff(self):
        claude_dir = self.tmp / "ref"
        write(claude_dir / ".claude" / "skills" / "check" / "SKILL.md", "---\nname: check\n---\n")
        repo = run.build_repo(run.load_case("off-by-one"), self.tmp / "work", claude_dir)

        self.assertIn(".claude/skills/check/SKILL.md",
                      git_out(repo, "ls-tree", "-r", "--name-only", "main").split())
        self.assertTrue((repo / ".claude" / "skills" / "check" / "SKILL.md").is_file())
        self.assertEqual(git_out(repo, "diff", "--name-only", "main", "feature").split(),
                         ["listing.py", "tests/test_listing.py"])

    def test_build_repo_drops_files_that_head_deletes(self):
        write(self.tmp / "fixtures" / "gone" / "base" / "keep.py", "k = 1\n")
        write(self.tmp / "fixtures" / "gone" / "base" / "drop.py", "d = 1\n")
        write(self.tmp / "fixtures" / "gone" / "head" / "keep.py", "k = 2\n")

        with mock.patch.object(run, "FIXTURES", self.tmp / "fixtures"):
            repo = run.build_repo({"name": "gone"}, self.tmp / "work", None)

        self.assertEqual(git_out(repo, "ls-tree", "-r", "--name-only", "main").split(), ["drop.py", "keep.py"])
        self.assertEqual(git_out(repo, "ls-tree", "-r", "--name-only", "feature").split(), ["keep.py"])
        self.assertEqual(git_out(repo, "show", "feature:keep.py"), "k = 2\n")


class ParseFindingsTest(unittest.TestCase):
    def test_parse_findings_returns_one_entry_per_body_bullet_with_its_citations(self):
        plan = "## Findings\n- listing.py:17 off by one\n- urls.py:4 nit\n"

        self.assertEqual(run.parse_findings(plan), [[("listing.py", 17, 17)], [("urls.py", 4, 4)]])

    def test_parse_findings_skips_frontmatter_todos(self):
        plan = "---\ntitle: x\ntodos:\n  - fix a.py:3\n---\n\n## Findings\n- b.py:9 bug\n"

        self.assertEqual(run.parse_findings(plan), [[("b.py", 9, 9)]])

    def test_parse_findings_keeps_findings_above_a_horizontal_rule(self):
        # Regression: splitting on the first "\n---" treated a body rule as the
        # end of the frontmatter and dropped every finding above it.
        plan = "---\ntodos: []\n---\n## Findings\n- a.py:1 bad\n\n---\n\n## More\n- b.py:2 bad\n"

        self.assertEqual(run.parse_findings(plan), [[("a.py", 1, 1)], [("b.py", 2, 2)]])

    def test_parse_findings_strips_each_joined_plans_frontmatter(self):
        first = "---\ntodos:\n  - fix c.py:9\n---\n## Findings\n- a.py:1 bad\n"
        second = "---\ntodos:\n  - fix d.py:4\n---\n## Findings\n- b.py:2 bad\n"

        plan = run.PLAN_SEPARATOR.join([first, second])

        self.assertEqual(run.parse_findings(plan), [[("a.py", 1, 1)], [("b.py", 2, 2)]])

    def test_parse_findings_skips_notes_section_but_resumes_after_it(self):
        plan = "## Findings\n- a.py:1 bug\n## Notes\n- b.py:2 not covered\n## Later\n- c.py:3 bug\n"

        self.assertEqual(run.parse_findings(plan), [[("a.py", 1, 1)], [("c.py", 3, 3)]])

    def test_parse_findings_ignores_bullets_without_citations_and_non_bullet_lines(self):
        plan = "## Findings\nSee a.py:1 in prose.\n- no citation here\n1. d.py:4 numbered\n- e.py:5 cited\n"

        self.assertEqual(run.parse_findings(plan), [[("e.py", 5, 5)]])

    def test_parse_findings_counts_indented_bullets(self):
        self.assertEqual(run.parse_findings("## Findings\n  - a.py:7 nested\n"), [[("a.py", 7, 7)]])

    def test_parse_findings_reads_hyphen_and_en_dash_ranges(self):
        plan = "- a.py:10-14 range\n- b.py:20 – 22 spaced en dash\n"

        self.assertEqual(run.parse_findings(plan), [[("a.py", 10, 14)], [("b.py", 20, 22)]])

    def test_parse_findings_reads_comma_separated_lines_as_separate_citations(self):
        self.assertEqual(run.parse_findings("- durations.py:6,12 both\n"),
                         [[("durations.py", 6, 6), ("durations.py", 12, 12)]])

    def test_parse_findings_keeps_every_citation_in_one_bullet(self):
        self.assertEqual(run.parse_findings("- durations.py:6 changes default; config.py:10 relies on it\n"),
                         [[("durations.py", 6, 6), ("config.py", 10, 10)]])

    def test_parse_findings_strips_leading_relative_prefixes_but_keeps_subdirectories(self):
        self.assertEqual(run.parse_findings("- ./a.py:3 and ../../pkg/b.py:4\n"),
                         [[("a.py", 3, 3), ("pkg/b.py", 4, 4)]])

    def test_parse_findings_reads_line_after_a_markdown_link(self):
        self.assertEqual(run.parse_findings("- [users.py](users.py):12 bug\n"), [[("users.py", 12, 12)]])

    def test_parse_findings_reads_line_inside_link_text(self):
        self.assertEqual(run.parse_findings("- [`users.py:12`](../../users.py) bug\n"), [[("users.py", 12, 12)]])

    def test_parse_findings_of_empty_text_is_empty(self):
        self.assertEqual(run.parse_findings(""), [])


class HitsTest(unittest.TestCase):
    LOC = {"file": "listing.py", "line": 17}

    def test_hits_cite_of_the_exact_line(self):
        self.assertTrue(run.hits([("listing.py", 17, 17)], self.LOC))

    def test_hits_cite_up_to_three_lines_either_side(self):
        self.assertTrue(run.hits([("listing.py", 14, 14)], self.LOC))
        self.assertTrue(run.hits([("listing.py", 20, 20)], self.LOC))

    def test_misses_cite_four_lines_away(self):
        self.assertFalse(run.hits([("listing.py", 13, 13)], self.LOC))
        self.assertFalse(run.hits([("listing.py", 21, 21)], self.LOC))

    def test_hits_range_that_covers_the_line(self):
        self.assertTrue(run.hits([("listing.py", 1, 30)], self.LOC))

    def test_hits_path_that_ends_with_the_file_after_a_slash(self):
        self.assertTrue(run.hits([("src/listing.py", 17, 17)], self.LOC))

    def test_misses_other_file_and_file_that_only_shares_a_suffix(self):
        self.assertFalse(run.hits([("urls.py", 17, 17)], self.LOC))
        self.assertFalse(run.hits([("mylisting.py", 17, 17)], self.LOC))

    def test_hits_when_any_one_citation_matches(self):
        self.assertTrue(run.hits([("urls.py", 1, 1), ("listing.py", 18, 18)], self.LOC))

    def test_misses_with_no_citations(self):
        self.assertFalse(run.hits([], self.LOC))


class GradeCheckTest(TempDirTestCase):
    CASE = {
        "name": "fake",
        "bugs": [
            {"id": "b1", "locations": [{"file": "a.py", "line": 10}]},
            {"id": "b2", "locations": [{"file": "b.py", "line": 40}, {"file": "c.py", "line": 5}]},
            {"id": "b3", "locations": [{"file": "d.py", "line": 1}]},
        ],
        "guards": [],
    }

    def grade(self, plan: str, reply: str = "") -> dict:
        write(self.tmp / "plan.md", plan)
        write(self.tmp / "result.txt", reply)
        return run.grade_check(self.CASE, self.tmp)

    def test_grade_check_scores_found_bugs_and_unmatched_findings_from_the_plan(self):
        plan = ("---\ntodos:\n  - d.py:1 restated todo\n---\n\n## Findings\n"
                "- a.py:11 off by one\n- c.py:5 caller not adapted\n- z.py:1 extra\n"
                "## Notes\n- d.py:1 not covered\n")

        self.assertEqual(self.grade(plan, "- d.py:1 reply is ignored when a plan exists"),
                         {"findings": 3, "found": ["b1", "b2"], "unmatched": 1, "graded_from": "plan"})

    def test_grade_check_falls_back_to_the_reply_when_the_plan_is_blank(self):
        self.assertEqual(self.grade(" \n\n", "Findings:\n- d.py:2 bug\n- q.py:9 other\n"),
                         {"findings": 2, "found": ["b3"], "unmatched": 1, "graded_from": "reply"})

    def test_grade_check_of_clean_reply_finds_nothing(self):
        self.assertEqual(self.grade("", "No findings: the diff is clean."),
                         {"findings": 0, "found": [], "unmatched": 0, "graded_from": "reply"})


def assistant(*blocks: dict, parent: str | None = None) -> dict:
    return {"type": "assistant", "parent_tool_use_id": parent, "message": {"content": list(blocks)}}


def tool_use(name: str) -> dict:
    return {"type": "tool_use", "name": name, "input": {}}


class ReadTranscriptTest(TempDirTestCase):
    def write_transcript(self, lines: list) -> pathlib.Path:
        path = self.tmp / "transcript.jsonl"
        path.write_text("\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines) + "\n")
        return path

    def test_read_transcript_skips_json_lines_that_are_not_events(self):
        # Regression: a bare number or list from stderr raised AttributeError.
        path = self.write_transcript(["42", "[1, 2]", "null", {"type": "result", "duration_ms": 5, "num_turns": 1}])

        result, spawns = run.read_transcript(path)

        self.assertEqual((result["duration_ms"], result["num_turns"], spawns), (5, 1, 0))

    def test_read_transcript_sums_duration_and_turns_and_keeps_last_result(self):
        path = self.write_transcript([
            {"type": "system", "subtype": "init"},
            "warning: not json from stderr",
            "",
            {"type": "result", "subtype": "success", "duration_ms": 1000, "num_turns": 3,
             "total_cost_usd": 0.05, "result": "first"},
            {"type": "result", "subtype": "success", "duration_ms": 2500, "num_turns": 4,
             "total_cost_usd": 0.11, "result": "final", "permission_denials": [{"tool_name": "Write"}]},
        ])

        result, spawns = run.read_transcript(path)

        self.assertEqual(result, {"type": "result", "subtype": "success", "duration_ms": 3500, "num_turns": 7,
                                  "total_cost_usd": 0.11, "result": "final",
                                  "permission_denials": [{"tool_name": "Write"}]})
        self.assertEqual(spawns, 0)

    def test_read_transcript_counts_only_top_level_agent_and_task_spawns(self):
        path = self.write_transcript([
            assistant({"type": "text", "text": "fanning out"}, tool_use("Agent"), tool_use("Read")),
            assistant(tool_use("Task")),
            assistant(tool_use("Agent"), parent="toolu_01"),
            assistant(tool_use("Bash")),
            {"type": "result", "subtype": "success", "duration_ms": 10, "num_turns": 1},
        ])

        _, spawns = run.read_transcript(path)

        self.assertEqual(spawns, 2)

    def test_read_transcript_treats_missing_duration_and_turns_as_zero(self):
        path = self.write_transcript([{"type": "result", "subtype": "error_during_execution",
                                       "duration_ms": None}])

        result, _ = run.read_transcript(path)

        self.assertEqual(result, {"type": "result", "subtype": "error_during_execution",
                                  "duration_ms": 0, "num_turns": 0})

    def test_read_transcript_without_result_returns_empty_result(self):
        path = self.write_transcript([assistant(tool_use("Agent")), "Error: crashed"])

        self.assertEqual(run.read_transcript(path), ({}, 1))


class MeanTest(unittest.TestCase):
    def test_mean_formats_to_two_decimals(self):
        self.assertEqual(run.mean([1, 2]), "1.50")

    def test_mean_ignores_none(self):
        self.assertEqual(run.mean([None, 3, None, 4]), "3.50")

    def test_mean_accepts_a_generator(self):
        self.assertEqual(run.mean(x for x in (0.1, 0.3, 0.2)), "0.20")

    def test_mean_of_nothing_or_only_none_is_a_dash(self):
        self.assertEqual(run.mean([]), "—")
        self.assertEqual(run.mean([None, None]), "—")


def record(ref: str, case: str, **fields) -> dict:
    base = {"ref": ref, "case": case, "rep": 1, "timed_out": False, "error": False, "denials": 0,
            "subagents": 0, "cost_usd": 0.1, "duration_s": 10.0}
    return {**base, **fields}


FOOTER = "⚠ = a run timed out, errored, hit a permission denial, or reported no cost; read its transcript under `runs/`."


class SummarizeTest(unittest.TestCase):
    CASES = [{"name": "bugcase", "bugs": [{"id": "b1"}]}, {"name": "cleancase", "bugs": []}]

    def test_summarize_check_tables_aggregate_per_ref_and_flag_suspect_runs(self):
        records = [
            record("main", "bugcase", found=["b1"], findings=2, unmatched=1, clean_case=False,
                   subagents=0, cost_usd=0.1, duration_s=20.0),
            record("main", "bugcase", rep=2, found=[], findings=0, unmatched=0, clean_case=False,
                   subagents=2, cost_usd=0.3, duration_s=40.0),
            record("main", "cleancase", found=[], findings=1, unmatched=1, clean_case=True,
                   subagents=1, cost_usd=0.2, duration_s=30.0),
            record("WORKTREE", "bugcase", found=["b1"], findings=1, unmatched=0, clean_case=False,
                   cost_usd=None, duration_s=10.0),
            record("WORKTREE", "cleancase", found=[], findings=0, unmatched=0, clean_case=True,
                   cost_usd=0.05, duration_s=5.0, timed_out=True),
        ]

        summary = run.summarize(records, self.CASES, ["main", "WORKTREE"], "check", 2)

        self.assertEqual(summary, "\n".join([
            "# check eval — 2 cases × 2 reps",
            "",
            "| ref | bugs found | findings / bug case | unmatched / bug case | findings / clean case "
            "| subagents | cost $ | time s |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
            "| `main` | 1/2 | 1.00 | 0.50 | 1.00 | 1.00 | 0.20 | 30.00 |",
            "| `WORKTREE` | 1/2 | 1.00 | 0.00 | 0.00 | 0.00 | 0.05 | 7.50 |",
            "",
            "## Per case",
            "",
            "| case | `main` | `WORKTREE` |",
            "| --- | --- | --- |",
            "| bugcase | 1/2 found | 1/1 found ⚠ |",
            "| cleancase | 1.00 findings | 0.00 findings ⚠ |",
            "",
            FOOTER,
        ]) + "\n")

    def test_summarize_check_iterate_tables_count_fixes_broken_guards_and_red_suites(self):
        records = [
            record("main", "bugcase", fixed=["b1"], guards_broken=[], tests_pass=True,
                   subagents=4, cost_usd=0.3, duration_s=60.0),
            record("main", "cleancase", fixed=[], guards_broken=["probes/guard.py"], tests_pass=False,
                   subagents=2, cost_usd=0.1, duration_s=20.0, error="error_max_turns"),
        ]

        summary = run.summarize(records, self.CASES, ["main"], "check-iterate", 1)

        self.assertEqual(summary, "\n".join([
            "# check-iterate eval — 2 cases × 1 reps",
            "",
            "| ref | bugs fixed | guards broken | suites red | subagents | cost $ | time s |",
            "| --- | --- | --- | --- | --- | --- | --- |",
            "| `main` | 1/1 | 1 | 1 | 3.00 | 0.20 | 40.00 |",
            "",
            "## Per case",
            "",
            "| case | `main` |",
            "| --- | --- |",
            "| bugcase | 1/1 fixed |",
            "| cleancase | 1 guards broken ⚠ |",
            "",
            FOOTER,
        ]) + "\n")

    def test_summarize_flags_runs_with_permission_denials(self):
        records = [record("main", "cleancase", found=[], findings=0, unmatched=0, clean_case=True, denials=1)]

        summary = run.summarize(records, [self.CASES[1]], ["main"], "check", 1)

        self.assertIn("| cleancase | 0.00 findings ⚠ |", summary.splitlines())


class RegradeTest(TempDirTestCase):
    TRANSCRIPT = [
        assistant(tool_use("Agent")),
        {"type": "result", "subtype": "success", "duration_ms": 18000, "num_turns": 5,
         "total_cost_usd": 0.12, "result": "done"},
    ]

    def make_run(self, name: str, plan: str | None = None, reply: str = "") -> pathlib.Path:
        run_dir = self.tmp / "runs" / name
        write(run_dir / "transcript.jsonl", "\n".join(json.dumps(e) for e in self.TRANSCRIPT) + "\n")
        if plan is not None:
            write(run_dir / "plan.md", plan)
            write(run_dir / "result.txt", reply)
        return run_dir

    def regrade(self) -> str:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(run.regrade(self.tmp), 0)
        return stdout.getvalue()

    def test_regrade_rescores_check_runs_from_saved_plans_and_transcripts(self):
        line = run.load_case("off-by-one")["bugs"][0]["locations"][0]["line"]
        stale = {"found": [], "findings": 0, "unmatched": 0, "cost_usd": None, "duration_s": 0,
                 "turns": None, "subagents": 0, "denials": 0, "timed_out": False, "error": False}
        records = [
            {"case": "off-by-one", "ref": "feature/x", "rep": 1, "clean_case": False, **stale},
            {"case": "off-by-one", "ref": "feature/x", "rep": 2, "clean_case": False, **stale},
            {"case": "clean-slugify", "ref": "feature/x", "rep": 1, "clean_case": True, **stale},
        ]
        write(self.tmp / "results.json", json.dumps(records))
        self.make_run("off-by-one--feature_x--1", f"## Findings\n- listing.py:{line} bug\n- listing.py:2 nit\n")
        self.make_run("off-by-one--feature_x--2", "", "No findings.")
        self.make_run("clean-slugify--feature_x--1", "", "- urls.py:3 nit")

        printed = self.regrade()

        saved = json.loads((self.tmp / "results.json").read_text())
        metrics = {"cost_usd": 0.12, "duration_s": 18.0, "turns": 5, "subagents": 1, "denials": 0}
        self.assertEqual(saved[0], {**records[0], **metrics, "findings": 2, "found": ["off-by-one"],
                                    "unmatched": 1, "graded_from": "plan"})
        self.assertEqual(saved[1], {**records[1], **metrics, "findings": 0, "found": [],
                                    "unmatched": 0, "graded_from": "reply"})
        self.assertEqual(saved[2], {**records[2], **metrics, "findings": 1, "found": [],
                                    "unmatched": 1, "graded_from": "reply"})
        self.assertEqual(json.loads((self.tmp / "runs" / "off-by-one--feature_x--1" / "record.json").read_text()),
                         saved[0])
        summary = (self.tmp / "summary.md").read_text()
        self.assertEqual(printed, summary + "\n")
        self.assertTrue(summary.startswith("# check eval — 2 cases × 2 reps\n"))
        self.assertIn("| `feature/x` | 1/2 | 1.00 | 0.50 | 1.00 | 1.00 | 0.12 | 18.00 |", summary.splitlines())

    def test_regrade_of_check_iterate_keeps_fix_verdicts_and_refreshes_metrics(self):
        records = [{"case": "off-by-one", "ref": "main", "rep": 1, "clean_case": False, "timed_out": False,
                    "error": False, "cost_usd": None, "duration_s": 0, "turns": None, "subagents": 0,
                    "denials": 3, "fixed": ["off-by-one"], "guards_broken": [], "tests_pass": True,
                    "staged": ["listing.py"]}]
        write(self.tmp / "results.json", json.dumps(records))
        self.make_run("off-by-one--main--1")

        self.regrade()

        saved = json.loads((self.tmp / "results.json").read_text())
        self.assertEqual(saved, [{**records[0], "cost_usd": 0.12, "duration_s": 18.0, "turns": 5,
                                  "subagents": 1, "denials": 0}])
        self.assertIn("| `main` | 1/1 | 0 | 0 | 1.00 | 0.12 | 18.00 |",
                      (self.tmp / "summary.md").read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
