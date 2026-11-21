"""Every script in the repo has a test file that exercises it.

A script counts as covered when some `tests/test_*.py` names its path relative
to the directory the script lives under: `"plan-issues" / "scripts" /
"plan-issues.py"`, or the same path written with slashes. Adding a script
without tests fails this check, so coverage cannot quietly lapse.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from tests.helpers import ROOT

# Fixture code under evals/fixtures is test data for the evals, not tooling.
EXCLUDED = ("evals/fixtures/", "tests/")


def scripts() -> list[pathlib.Path]:
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        hidden = any(part.startswith(".") and part != ".claude" for part in rel.parts)
        if hidden or rel.as_posix().startswith(EXCLUDED):
            continue
        found.append(path)
    return found


def mentioned(path: pathlib.Path, test_sources: str) -> bool:
    """True when the test sources name this script by its last path parts.

    Matches both `"skill" / "scripts" / "x.py"` and `"skill/scripts/x.py"`.
    """
    parts = path.relative_to(ROOT).parts[-3:]
    separator = r"""(?:["']\s*/\s*["']|/)"""
    return re.search(separator.join(re.escape(p) for p in parts), test_sources) is not None


class EveryScriptIsTestedTest(unittest.TestCase):
    def test_the_repo_has_scripts_to_check(self) -> None:
        names = {p.relative_to(ROOT).as_posix() for p in scripts()}

        self.assertIn(".claude/skills/plan-issues/scripts/plan-issues.py", names)
        self.assertIn("scripts/validate.py", names)
        self.assertIn("evals/run.py", names)

    def test_every_script_has_a_test_file_that_names_it(self) -> None:
        sources = "\n".join(p.read_text() for p in sorted((ROOT / "tests").glob("test_*.py")) if p.name != pathlib.Path(__file__).name)

        untested = [p.relative_to(ROOT).as_posix() for p in scripts() if not mentioned(p, sources)]

        self.assertEqual(untested, [], "scripts with no tests; add tests/test_<name>.py that loads or runs each one")


if __name__ == "__main__":
    unittest.main()
