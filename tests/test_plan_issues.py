"""Tests for the plan-issues skill's script: check, render, record and used."""

from __future__ import annotations

import json
import pathlib
import tempfile
import textwrap
import unittest

from tests.helpers import SKILLS, load_script, run_script

SCRIPT = SKILLS / "plan-issues" / "scripts" / "plan-issues.py"
plan_issues = load_script(SCRIPT, "plan_issues_script")

PLAN = textwrap.dedent(
    """\
    ---
    name: Demo plan
    overview: Ship the demo.
    priority: 20
    stages:
      - id: first
        title: First stage
        goal: do the first thing
        verification: npm test
        todos:
          - id: first-todo
            content: Add the thing — see First stage
            status: pending
      - id: second
        title: Second stage
        goal: do the second thing
        verification: npm run e2e
        labels: [needs-decision]
        todos:
          - id: second-todo
            content: Wire it up
            status: pending
    ---

    ## Context

    Background, see [the notes](../../docs/notes.md#why).

    ## First stage

    Details for the first stage.

    ## Second stage

    Details for the second stage.
    """
)


class PlanTestCase(unittest.TestCase):
    """Runs each test in a throwaway repo root holding `.claude/plans/`."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.plans = self.root / ".claude" / "plans"
        self.plans.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, text: str = PLAN) -> pathlib.Path:
        path = self.plans / name
        path.write_text(text)
        return path

    def run_cli(self, *args: str):
        return run_script(SCRIPT, *args, cwd=self.root)

    def frontmatter(self, path: pathlib.Path) -> str:
        return path.read_text().split("\n---\n", 1)[0]


class RecordTest(PlanTestCase):
    def test_record_parent_inserts_issue_before_stages(self) -> None:
        # Regression: the parent branch of set_issue was unreachable and raised
        # AssertionError("unreachable") for every `record --parent N`.
        path = self.write("demo.plan.md")

        result = self.run_cli("record", ".claude/plans/demo.plan.md", "--parent", "2008")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "recorded in .claude/plans/demo.plan.md")
        lines = self.frontmatter(path).splitlines()
        self.assertEqual(lines[lines.index("stages:") - 1], "issue: 2008")
        self.assertEqual(plan_issues.check(path)["issue"], 2008)

    def test_record_parent_replaces_an_existing_issue_line(self) -> None:
        path = self.write("demo.plan.md", PLAN.replace("priority: 20\n", "priority: 20\nissue: 11\n"))

        result = self.run_cli("record", str(path), "--parent", "12")

        self.assertEqual(result.returncode, 0, result.stderr)
        head = self.frontmatter(path)
        self.assertEqual(head.count("\nissue: "), 1)
        self.assertIn("\nissue: 12\n", head)

    def test_record_stage_inserts_issue_before_todos(self) -> None:
        path = self.write("demo.plan.md")

        result = self.run_cli("record", str(path), "--stage", "first=31", "--stage", "second=32")

        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.frontmatter(path).splitlines()
        first = lines.index("  - id: first")
        self.assertEqual(lines[first + 4 : first + 6], ["    issue: 31", "    todos:"])
        stages = {s["id"]: s["issue"] for s in plan_issues.check(path)["stages"]}
        self.assertEqual(stages, {"first": 31, "second": 32})

    def test_record_parent_and_stage_in_one_call(self) -> None:
        path = self.write("demo.plan.md")

        result = self.run_cli("record", str(path), "--parent", "40", "--stage", "first=41")

        self.assertEqual(result.returncode, 0, result.stderr)
        plan = plan_issues.check(path)
        self.assertEqual((plan["issue"], plan["stages"][0]["issue"]), (40, 41))

    def test_record_related_merges_without_duplicates(self) -> None:
        path = self.write("demo.plan.md")
        self.run_cli("record", str(path), "--related", "first=5,6")

        result = self.run_cli("record", str(path), "--related", "first=6,7")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(plan_issues.check(path)["stages"][0]["related"], [5, 6, 7])

    def test_record_leaves_the_body_byte_for_byte(self) -> None:
        path = self.write("demo.plan.md")
        body = path.read_text().split("\n---\n", 1)[1]

        self.run_cli("record", str(path), "--parent", "9", "--stage", "second=10")

        self.assertEqual(path.read_text().split("\n---\n", 1)[1], body)

    def test_record_rejects_an_unknown_stage(self) -> None:
        path = self.write("demo.plan.md")
        before = path.read_text()

        result = self.run_cli("record", str(path), "--stage", "nope=3")

        self.assertEqual(result.returncode, 1)
        self.assertIn("no stage `nope`", result.stderr)
        self.assertEqual(path.read_text(), before)

    def test_record_rejects_a_malformed_stage_argument(self) -> None:
        path = self.write("demo.plan.md")

        result = self.run_cli("record", str(path), "--stage", "first=abc")

        self.assertEqual(result.returncode, 1)
        self.assertIn("expected <id>=<issue number>", result.stderr)

    def test_record_rejects_a_number_already_used_in_the_plan(self) -> None:
        path = self.write("demo.plan.md")

        result = self.run_cli("record", str(path), "--parent", "50", "--stage", "first=50")

        self.assertEqual(result.returncode, 1)
        self.assertIn("issue 50 is already used by the plan", result.stderr)

    def test_record_parent_without_stages_key_reports_it(self) -> None:
        lines = ["name: x\n", "overview: y\n"]

        with self.assertRaisesRegex(plan_issues.PlanError, "no `stages:` key"):
            plan_issues.set_issue(lines, None, 1, pathlib.Path("p.plan.md"))


class CheckTest(PlanTestCase):
    def test_check_accepts_a_valid_plan(self) -> None:
        self.write("demo.plan.md")

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1 plans OK, 2 stages")

    def test_check_skips_plans_that_do_not_opt_in(self) -> None:
        self.write("demo.plan.md")
        self.write("run.plan.md", PLAN.replace("priority: 20\n", ""))

        result = self.run_cli("check")

        self.assertEqual(result.stdout.strip(), "1 plans OK, 2 stages")

    def test_check_reports_a_broken_plan_that_opted_in(self) -> None:
        self.write("broken.plan.md", "---\npriority: 1\nname: [unclosed\n---\n")

        result = self.run_cli("check")

        self.assertEqual(result.returncode, 1)
        self.assertIn("broken.plan.md: frontmatter is not YAML", result.stderr)

    def test_check_rejects_each_invalid_plan(self) -> None:
        cases = {
            "missing overview": (PLAN.replace("overview: Ship the demo.\n", ""), "missing `overview`"),
            "non-kebab id": (PLAN.replace("id: first-todo", "id: First_Todo"), "is not kebab-case"),
            "duplicate id": (PLAN.replace("id: second-todo", "id: first-todo"), "`first-todo` is used twice"),
            "unknown label": (PLAN.replace("[needs-decision]", "[urgent]"), "unknown label(s) ['urgent']"),
            "string priority": (PLAN.replace("priority: 20", "priority: soon"), "priority must be an integer"),
            "zero issue": (PLAN.replace("priority: 20\n", "priority: 20\nissue: 0\n"), "positive issue number"),
            "missing roadmap": (PLAN.replace("priority: 20\n", "priority: 20\nroadmap: docs/nope.md\n"), "does not exist"),
            "stage without todos": (
                PLAN.replace("    todos:\n      - id: second-todo\n        content: Wire it up\n        status: pending\n", "    todos: []\n"),
                "stage second: missing `todos`",
            ),
            "no frontmatter": ("# just a heading\n", "no frontmatter"),
        }
        for label, (text, message) in cases.items():
            with self.subTest(label):
                path = self.write("bad.plan.md", text)
                result = self.run_cli("check", str(path))
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, result.stderr)


class RenderTest(PlanTestCase):
    def render(self) -> list[dict]:
        result = self.run_cli("render", "--repo", "acme/app", "--ref", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["plans"]

    def test_render_orders_plans_by_priority_then_file(self) -> None:
        self.write("b.plan.md", PLAN.replace("priority: 20", "priority: 5"))
        self.write("a.plan.md", PLAN.replace("priority: 20", "priority: 5"))
        self.write("c.plan.md", PLAN.replace("priority: 20", "priority: 1"))

        files = [p["file"] for p in self.render()]

        self.assertEqual(files, [".claude/plans/c.plan.md", ".claude/plans/a.plan.md", ".claude/plans/b.plan.md"])

    def test_render_parent_carries_marker_labels_and_absolute_links(self) -> None:
        self.write("demo.plan.md", PLAN.replace("priority: 20\n", "priority: 20\nlabels: [ready]\n"))

        (parent,) = self.render()

        self.assertEqual(parent["title"], "Demo plan")
        self.assertEqual(parent["labels"], ["plan", "ready"])
        self.assertTrue(parent["body"].startswith("<!-- plan: .claude/plans/demo.plan.md -->\n\nShip the demo."))
        self.assertIn("](https://github.com/acme/app/blob/main/docs/notes.md#why)", parent["body"])
        self.assertIn("Plan: [`.claude/plans/demo.plan.md`](https://github.com/acme/app/blob/main/.claude/plans/demo.plan.md)", parent["body"])

    def test_render_stage_body_holds_its_section_and_todos(self) -> None:
        self.write("demo.plan.md")

        first = self.render()[0]["stages"][0]

        self.assertEqual(first["title"], "First stage")
        self.assertTrue(first["body"].startswith("<!-- plan-stage: .claude/plans/demo.plan.md#first -->"))
        self.assertIn("**Verification:** `npm test`", first["body"])
        self.assertIn("Details for the first stage.", first["body"])
        self.assertNotIn("Details for the second stage.", first["body"])
        self.assertTrue(first["body"].endswith("### Todos\n\n- Add the thing — see First stage"))

    def test_render_leaves_out_finished_stages_without_an_issue(self) -> None:
        text = PLAN.replace("verification: npm test\n", "verification: npm test\n    status: completed\n")
        self.write("demo.plan.md", text)

        stages = self.render()[0]["stages"]

        self.assertEqual([s["id"] for s in stages], ["second"])
        self.assertEqual(stages[0]["labels"], ["needs-decision"])

    def test_render_keeps_finished_stages_that_have_an_issue(self) -> None:
        text = PLAN.replace("verification: npm test\n", "verification: npm test\n    status: completed\n    issue: 7\n")
        self.write("demo.plan.md", text)

        stages = self.render()[0]["stages"]

        self.assertEqual([(s["id"], s["issue"]) for s in stages], [("first", 7), ("second", None)])

    def test_render_lists_related_issues(self) -> None:
        self.write("demo.plan.md", PLAN.replace("verification: npm test\n", "verification: npm test\n    related: [3, 4]\n"))

        first = self.render()[0]["stages"][0]

        self.assertEqual(first["related"], [3, 4])
        self.assertIn("**Also resolves:** #3, #4", first["body"])


class UsedTest(PlanTestCase):
    def test_used_lists_every_number_the_plans_name(self) -> None:
        text = PLAN.replace("priority: 20\n", "priority: 20\nissue: 9\n").replace(
            "verification: npm test\n", "verification: npm test\n    issue: 3\n    related: [12, 4]\n"
        )
        self.write("demo.plan.md", text)

        result = self.run_cli("used")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [3, 4, 9, 12])


class HelperTest(unittest.TestCase):
    def test_section_stops_at_the_next_heading(self) -> None:
        body = "## A\n\none\n\n## B\n\ntwo\n"

        self.assertEqual(plan_issues.section(body, "A"), "one")
        self.assertEqual(plan_issues.section(body, "Missing"), "")

    def test_absolute_rewrites_only_relative_links(self) -> None:
        text = "[a](../x.md) [b](https://e.com) [c](#top) [d](mailto:x@y.z)"

        out = plan_issues.absolute(text, ".claude/plans/p.plan.md", "o/r", "main")

        self.assertEqual(out, "[a](https://github.com/o/r/blob/main/.claude/x.md) [b](https://e.com) [c](#top) [d](mailto:x@y.z)")


if __name__ == "__main__":
    unittest.main()
