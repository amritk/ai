"""Tests for scripts/validate.py.

The script does all its work at import time and ends in `sys.exit`, so its
module attributes cannot be patched before the checks run. Each failure case
instead copies the script into a temporary `scripts/` directory, so its `ROOT`
resolves to the temporary tree, writes a minimal `.claude/` beside it, and runs
it as a subprocess.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import tempfile
import unittest

from tests.helpers import ROOT, run_script

SCRIPT = ROOT / "scripts" / "validate.py"

SKILL_MD = ".claude/skills/demo/SKILL.md"
AGENT_MD = ".claude/agents/helper.md"

RUBRIC = (
    "- **high** — breaks on an ordinary input.\n"
    "- **medium** — breaks on an edge input.\n"
    "- **low** — drift or missing coverage.\n"
)


def skill_text(frontmatter: str, body: str = "Run `<skill dir>/scripts/run.py` to build.\n") -> str:
    return f"---\n{frontmatter}---\n\n{body}"


VALID_SKILL = skill_text("name: demo\ndescription: Demo skill used by the validator tests.\n")
VALID_AGENT = (
    "---\nname: helper\ndescription: Helper agent used by the validator tests.\n"
    "tools: Read, Grep\nmodel: sonnet\n---\n\nYou help.\n"
)


class ValidateRealRepoTest(unittest.TestCase):
    def test_passes_on_the_real_repo_and_counts_every_skill_and_agent(self):
        result = run_script(SCRIPT, cwd=ROOT)

        skills = len(list((ROOT / ".claude" / "skills").glob("*/SKILL.md")))
        agents = len(list((ROOT / ".claude" / "agents").glob("*.md")))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, f"{skills} skills, {agents} agents\n")


class ValidateFakeTreeTest(unittest.TestCase):
    """Starts from a tree that passes, then breaks one thing per test."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts" / "validate.py")
        self.write(SKILL_MD, VALID_SKILL)
        self.write(".claude/skills/demo/scripts/run.py", "print('run')\n")
        self.write(AGENT_MD, VALID_AGENT)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_validate(self):
        return run_script(self.root / "scripts" / "validate.py", cwd=self.root)

    def errors(self, result) -> list[str]:
        return [line.removeprefix("error: ") for line in result.stderr.splitlines()]

    def assertReports(self, *expected: str) -> None:
        """The run exits 1 and reports exactly these errors."""
        result = self.run_validate()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(self.errors(result), list(expected))

    def assertPasses(self) -> None:
        result = self.run_validate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")

    # The baseline.

    def test_minimal_valid_tree_passes_and_reports_counts(self):
        result = self.run_validate()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, "1 skills, 1 agents\n")

    # Skill structure.

    def test_reports_no_skills_when_skills_directory_is_empty(self):
        shutil.rmtree(self.root / ".claude" / "skills")

        self.assertReports("no skills found under .claude/skills")

    def test_reports_skill_without_frontmatter(self):
        self.write(SKILL_MD, "# demo\n\nRun `<skill dir>/scripts/run.py`.\n")

        self.assertReports(f"{SKILL_MD}: missing frontmatter")

    def test_reports_skill_with_unterminated_frontmatter(self):
        self.write(SKILL_MD, "---\nname: demo\ndescription: Demo.\n\nRun `<skill dir>/scripts/run.py`.\n")

        self.assertReports(f"{SKILL_MD}: unterminated frontmatter")

    def test_reports_skill_name_that_does_not_match_its_directory(self):
        self.write(SKILL_MD, skill_text("name: other\ndescription: Demo.\n"))

        self.assertReports(f"{SKILL_MD}: name 'other' != directory 'demo'")

    def test_reports_skill_with_no_name_field(self):
        self.write(SKILL_MD, skill_text("description: Demo.\n"))

        self.assertReports(f"{SKILL_MD}: name 'None' != directory 'demo'")

    def test_reports_skill_name_that_is_not_kebab_case(self):
        self.write(".claude/skills/Demo_Skill/SKILL.md",
                   skill_text("name: Demo_Skill\ndescription: Demo.\n", "No files.\n"))

        self.assertReports(".claude/skills/Demo_Skill/SKILL.md: name 'Demo_Skill' is not kebab-case")

    def test_reports_skill_with_no_description_field(self):
        self.write(SKILL_MD, skill_text("name: demo\n"))

        self.assertReports(f"{SKILL_MD}: no description (it is what makes the skill trigger)")

    def test_reports_skill_with_empty_description_value(self):
        self.write(SKILL_MD, skill_text("name: demo\ndescription:\n"))

        self.assertReports(f"{SKILL_MD}: no description (it is what makes the skill trigger)")

    def test_reports_skill_with_quoted_empty_description(self):
        # Regression: `""` was read as a two-character description.
        for quoted in ('""', "''"):
            with self.subTest(quoted):
                self.write(SKILL_MD, skill_text(f"name: demo\ndescription: {quoted}\n"))

                self.assertReports(f"{SKILL_MD}: no description (it is what makes the skill trigger)")

    def test_accepts_folded_description_on_continuation_lines(self):
        self.write(SKILL_MD, skill_text("name: demo\ndescription: >\n  Folded onto\n  two lines.\n"))

        self.assertPasses()

    def test_reports_description_longer_than_1536_characters(self):
        self.write(SKILL_MD, skill_text(f"name: demo\ndescription: {'x' * 1537}\n"))

        self.assertReports(f"{SKILL_MD}: description is 1537 chars; Claude Code lists at most 1536")

    def test_accepts_description_of_exactly_1536_characters(self):
        self.write(SKILL_MD, skill_text(f"name: demo\ndescription: {'x' * 1536}\n"))

        self.assertPasses()

    # Skill frontmatter fields.

    def test_reports_task_in_comma_separated_allowed_tools(self):
        self.write(SKILL_MD, skill_text("name: demo\ndescription: Demo.\nallowed-tools: Read, Task, Grep\n"))

        self.assertReports(f"{SKILL_MD}: allowed-tools lists 'Task'; the subagent tool is 'Agent'")

    def test_reports_task_in_yaml_list_allowed_tools(self):
        self.write(SKILL_MD, skill_text("name: demo\ndescription: Demo.\nallowed-tools:\n  - Read\n  - Task\n"))

        self.assertReports(f"{SKILL_MD}: allowed-tools lists 'Task'; the subagent tool is 'Agent'")

    def test_accepts_agent_in_allowed_tools(self):
        self.write(SKILL_MD, skill_text("name: demo\ndescription: Demo.\nallowed-tools:\n  - Read\n  - Agent\n"))

        self.assertPasses()

    def test_reports_skill_effort_outside_the_allowed_levels(self):
        self.write(SKILL_MD, skill_text("name: demo\ndescription: Demo.\neffort: extreme\n"))

        self.assertReports(
            f"{SKILL_MD}: effort 'extreme' is not one of ['high', 'low', 'max', 'medium', 'xhigh']")

    def test_accepts_every_allowed_skill_effort_level(self):
        for effort in ("low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                self.write(SKILL_MD, skill_text(f"name: demo\ndescription: Demo.\neffort: {effort}\n"))

                self.assertPasses()

    # Bundled files and links.

    def test_reports_dangling_skill_dir_reference(self):
        self.write(SKILL_MD, skill_text(
            "name: demo\ndescription: Demo.\n",
            "Run `<skill dir>/scripts/run.py`, then `<skill dir>/scripts/gone.py`.\n"))

        self.assertReports(f"{SKILL_MD}: points at missing 'scripts/gone.py'")

    def test_skill_dir_reference_ending_a_sentence_drops_the_full_stop(self):
        # Regression: the trailing "." was read as part of the path.
        self.write(SKILL_MD, skill_text("name: demo\ndescription: Demo.\n", "Run <skill dir>/scripts/run.py.\n"))

        self.assertPasses()

    def test_reports_markdown_link_to_missing_file(self):
        self.write(SKILL_MD, skill_text(
            "name: demo\ndescription: Demo.\n",
            "Run `<skill dir>/scripts/run.py`. See [the guide](references/guide.md).\n"))

        self.assertReports(f"{SKILL_MD}: link to missing 'references/guide.md'")

    def test_ignores_links_inside_code_and_external_or_anchor_links(self):
        self.write(SKILL_MD, skill_text(
            "name: demo\ndescription: Demo.\n",
            "Run `<skill dir>/scripts/run.py`.\n"
            "`[example](missing/inline.md)`\n"
            "```\n[example](missing/fenced.md)\n```\n"
            "[docs](https://example.com/x) [top](#usage) [script](scripts/run.py#main)\n"))

        self.assertPasses()

    def test_reports_cursor_mdc_links(self):
        self.write(SKILL_MD, skill_text(
            "name: demo\ndescription: Demo.\n",
            "Run `<skill dir>/scripts/run.py`. See [rules](mdc:scripts/run.py).\n"))

        self.assertReports(f"{SKILL_MD}: contains Cursor 'mdc:' links; use plain Markdown links")

    def test_reports_bundled_file_the_skill_never_mentions(self):
        self.write(".claude/skills/demo/scripts/orphan.py", "pass\n")

        self.assertReports(f"{SKILL_MD}: bundles unreferenced 'scripts/orphan.py'")

    # Spawned agents.

    def test_reports_skill_that_spawns_an_unknown_agent(self):
        self.write(SKILL_MD, skill_text(
            "name: demo\ndescription: Demo.\n",
            "Run `<skill dir>/scripts/run.py`.\nSpawn with `subagent_type: \"ghost\"`.\n"))

        self.assertReports(f"{SKILL_MD}: spawns unknown agent 'ghost' (no .claude/agents/ghost.md)")

    def test_accepts_spawns_of_repo_agents_and_builtin_agents(self):
        self.write(SKILL_MD, skill_text(
            "name: demo\ndescription: Demo.\n",
            "Run `<skill dir>/scripts/run.py`.\n"
            'subagent_type: "helper"\nsubagent_type: "Explore"\n'
            'subagent_type: "Plan"\nsubagent_type: "general-purpose"\n'))

        self.assertPasses()

    def test_reports_agent_that_spawns_an_unknown_agent(self):
        self.write(AGENT_MD, VALID_AGENT + 'Delegate with subagent_type: "ghost".\n')

        self.assertReports(f"{AGENT_MD}: spawns unknown agent 'ghost' (no .claude/agents/ghost.md)")

    # Agent frontmatter.

    def test_reports_agent_name_that_does_not_match_its_filename(self):
        self.write(AGENT_MD, VALID_AGENT.replace("name: helper", "name: assistant"))

        self.assertReports(f"{AGENT_MD}: name 'assistant' != filename 'helper'")

    def test_reports_agent_filename_that_is_not_kebab_case(self):
        (self.root / AGENT_MD).unlink()
        self.write(".claude/agents/Helper_Bot.md", VALID_AGENT.replace("name: helper", "name: Helper_Bot"))

        self.assertReports(".claude/agents/Helper_Bot.md: name 'Helper_Bot' is not kebab-case")

    def test_reports_agent_without_frontmatter(self):
        self.write(AGENT_MD, "You help.\n")

        self.assertReports(f"{AGENT_MD}: missing frontmatter")

    def test_reports_agent_with_no_description(self):
        self.write(AGENT_MD, "---\nname: helper\n---\n\nYou help.\n")

        self.assertReports(f"{AGENT_MD}: no description (it is how the orchestrator picks the agent)")

    def test_reports_agent_model_that_is_neither_alias_nor_claude_id(self):
        self.write(AGENT_MD, VALID_AGENT.replace("model: sonnet", "model: gpt-4"))

        self.assertReports(
            f"{AGENT_MD}: model 'gpt-4' is neither an alias "
            "['fable', 'haiku', 'inherit', 'opus', 'sonnet'] nor a claude-* id")

    def test_accepts_agent_model_given_as_claude_id(self):
        self.write(AGENT_MD, VALID_AGENT.replace("model: sonnet", "model: claude-sonnet-5-5"))

        self.assertPasses()

    def test_reports_agent_effort_outside_the_allowed_levels(self):
        self.write(AGENT_MD, VALID_AGENT.replace("model: sonnet", "model: sonnet\neffort: huge"))

        self.assertReports(
            f"{AGENT_MD}: effort 'huge' is not one of ['high', 'low', 'max', 'medium', 'xhigh']")

    def test_reports_agent_color_outside_the_allowed_colors(self):
        self.write(AGENT_MD, VALID_AGENT.replace("model: sonnet", "model: sonnet\ncolor: magenta"))

        self.assertReports(
            f"{AGENT_MD}: color 'magenta' is not one of "
            "['blue', 'cyan', 'green', 'orange', 'pink', 'purple', 'red', 'yellow']")

    def test_reports_task_in_agent_tools(self):
        self.write(AGENT_MD, VALID_AGENT.replace("tools: Read, Grep", "tools: Read, Task"))

        self.assertReports(f"{AGENT_MD}: tools lists 'Task'; the subagent tool is 'Agent'")

    def test_reports_agent_link_to_missing_file(self):
        self.write(AGENT_MD, VALID_AGENT + "See [notes](notes.md).\n")

        self.assertReports(f"{AGENT_MD}: link to missing 'notes.md'")

    # Severity rubric shared by rating agents.

    def rating_agent(self, name: str, rubric: str) -> str:
        return (f"---\nname: {name}\ndescription: Rates findings.\n---\n\n"
                f"## Severity\n\n{rubric}\n## Output\n\n- severity: high | medium | low\n")

    def test_accepts_rating_agents_with_identical_rubrics(self):
        self.write(".claude/agents/alpha.md", self.rating_agent("alpha", RUBRIC))
        self.write(".claude/agents/beta.md", self.rating_agent("beta", RUBRIC))

        self.assertPasses()

    def test_reports_rating_agent_missing_a_rubric_level(self):
        partial = "".join(line + "\n" for line in RUBRIC.splitlines() if "**low**" not in line)
        self.write(".claude/agents/alpha.md", self.rating_agent("alpha", partial))

        self.assertReports(
            ".claude/agents/alpha.md: emits severity high | medium | low "
            "but does not define all three in a rubric")

    def test_reports_rating_agent_whose_rubric_differs_from_the_first(self):
        self.write(".claude/agents/alpha.md", self.rating_agent("alpha", RUBRIC))
        self.write(".claude/agents/beta.md",
                   self.rating_agent("beta", RUBRIC.replace("drift or missing coverage", "style nits")))

        self.assertReports(
            ".claude/agents/beta.md: severity rubric differs from .claude/agents/alpha.md; "
            "keep the copies identical")

    def test_ignores_rubric_in_agents_that_do_not_emit_severity(self):
        self.write(AGENT_MD, VALID_AGENT + "\n- **high** — something else entirely.\n")

        self.assertPasses()

    # Several problems at once.

    def test_reports_every_problem_in_one_run(self):
        self.write(SKILL_MD, skill_text("name: other\n", "Run `<skill dir>/scripts/run.py`.\n"))
        self.write(AGENT_MD, VALID_AGENT.replace("model: sonnet", "model: gpt-4"))

        result = self.run_validate()

        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(self.errors(result)), 3)
        self.assertTrue(all(re.match(r"\.claude/(skills|agents)/", e) for e in self.errors(result)))
        self.assertEqual(result.stdout, "1 skills, 1 agents\n")


if __name__ == "__main__":
    unittest.main()
