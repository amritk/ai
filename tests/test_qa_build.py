"""Tests for the QA report builder (.claude/skills/qa/scripts/build.py)."""

from __future__ import annotations

import copy
import json
import pathlib
import re
import tempfile
import unittest

from tests.helpers import SKILLS, load_script, run_script

BUILD = SKILLS / "qa" / "scripts" / "build.py"
build = load_script(BUILD, "qa_build")

PLACEHOLDER = re.compile(r"__[A-Z_]{3,}__")
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"


def make_check(check_id: str, status: str = "pass", **overrides) -> dict:
    check = {
        "id": check_id,
        "title": f"Check {check_id}",
        "area": "checkout",
        "type": "specified",
        "status": status,
        "steps": ["Open /cart", "Click Pay"],
        "expected": "Order confirmed.",
        "actual": "Order confirmed.",
    }
    check.update(overrides)
    return check


def make_finding(finding_id: str, severity: str = "minor", status: str = "confirmed", **overrides) -> dict:
    finding = {
        "id": finding_id,
        "title": f"Finding {finding_id}",
        "severity": severity,
        "area": "checkout",
        "status": status,
        "repro": ["Open /cart", "Click Pay twice"],
        "expected": "One order.",
        "actual": "Two orders.",
        "impact": "Customers are charged twice.",
    }
    finding.update(overrides)
    return finding


def make_results(checks: list[dict] | None = None, findings: list[dict] | None = None, **overrides) -> dict:
    """A minimal valid results.json: one passing check, no findings."""
    data = {
        "title": "Checkout",
        "date": "2026-11-20",
        "driver": "playwright-local",
        "depth": "standard",
        "target": {"url": "https://staging.example.com", "env": "staging", "build": "a1b2c3d"},
        "scope": {"asked": "Check checkout before release."},
        "verdict_note": "Checkout works.",
        "checks": checks if checks is not None else [make_check("C1")],
        "findings": findings if findings is not None else [],
    }
    data.update(overrides)
    return data


def with_finding() -> dict:
    """A valid result with a failing check tied to one minor finding, for finding-level mutations."""
    return make_results(
        checks=[make_check("C1"), make_check("C2", "fail", actual="Charged twice.", findings=["F1"])],
        findings=[make_finding("F1", checks=["C2"])],
    )


def tile_count(page: str, status: str) -> int:
    match = re.search(rf'data-status="{status}" aria-pressed="false"><span class="n">(\d+)</span>', page)
    assert match, f"{status} tile not found"
    return int(match.group(1))


def severity_count(page: str, severity: str) -> int:
    match = re.search(rf'data-sev="{severity}" aria-pressed="false"><span class="n">(\d+)</span>', page)
    assert match, f"{severity} button not found"
    return int(match.group(1))


def extract_data(page: str) -> dict:
    match = re.search(r"const DATA = (.*);\n", page)
    assert match, "DATA assignment not found in page"
    return json.loads(match.group(1))


class BuildCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.results = self.root / "results.json"
        self.out_dir = self.root / "report"
        self.out_dir.mkdir()
        self.out = self.out_dir / "qa.html"

    def run_build(self, data: dict | None, *extra: str):
        if data is not None:
            self.results.write_text(json.dumps(data), encoding="utf-8")
        return run_script(BUILD, "--results", str(self.results), "--out", str(self.out), *extra)

    def build_page(self, data: dict, *extra: str) -> str:
        result = self.run_build(data, *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.out.read_text(encoding="utf-8")

    def make_shots(self, *names: str) -> pathlib.Path:
        shots = self.root / "captures"
        shots.mkdir(exist_ok=True)
        for name in names:
            (shots / name).write_bytes(PNG_BYTES + name.encode())
        return shots

    def assert_rejected(self, result, message: str) -> None:
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertFalse(self.out.exists(), "no page should be written on a rejected build")


class RenderTests(BuildCase):
    def test_minimal_clean_pass_fills_every_placeholder(self) -> None:
        result = self.run_build(make_results())
        self.assertEqual(result.returncode, 0, result.stderr)
        page = self.out.read_text(encoding="utf-8")

        self.assertEqual(PLACEHOLDER.findall(page), [])
        self.assertIn("<title>Checkout QA</title>", page)
        self.assertIn("<h1>Checkout</h1>", page)
        self.assertIn('<p class="eyebrow">QA pass &middot; staging &middot; 2026-11-20</p>', page)
        self.assertIn('<a href="https://staging.example.com"><b>https://staging.example.com</b></a>', page)
        self.assertIn('build: <b class="mono">a1b2c3d</b>', page)
        self.assertIn("driver: <b>playwright-local</b>", page)
        self.assertIn("browser: <b>unspecified</b>", page)
        self.assertIn("viewport: <b>unspecified</b>", page)
        self.assertIn("depth: <b>standard</b>", page)
        self.assertIn('<div class="verdict clean">\n    <span class="label">Clean</span>', page)
        self.assertIn('<span class="note">Checkout works.</span>', page)
        self.assertIn("1 checks, 100% of the ones that ran passed &middot; 0 findings", page)
        self.assertIn("<h2>Nothing to fix first</h2><p>No critical or major findings, and every check ran.</p>", page)
        self.assertEqual(
            result.stdout.strip(),
            f"{self.out}: 1 checks (1 pass, 0 fail, 0 blocked), 0 findings, verdict Clean",
        )

    def test_counts_checks_by_status_and_findings_by_severity(self) -> None:
        data = make_results(
            checks=[
                make_check("C1"),
                make_check("C2"),
                make_check("C3", "fail", findings=["F1", "F2"]),
                make_check("C4", "partial"),
                make_check("C5", "blocked", actual="No test card."),
                make_check("C6", "skipped", actual="Out of time."),
            ],
            findings=[
                make_finding("F1", "major", checks=["C3"]),
                make_finding("F2", "nit", checks=["C3"]),
                make_finding("F3", "nit"),
            ],
        )

        page = self.build_page(data)

        self.assertEqual(
            {s: tile_count(page, s) for s in build.CHECK_STATUSES},
            {"pass": 2, "fail": 1, "partial": 1, "blocked": 1, "skipped": 1},
        )
        self.assertEqual(
            {s: severity_count(page, s) for s in build.SEVERITIES},
            {"critical": 0, "major": 1, "minor": 0, "nit": 2},
        )
        self.assertIn("6 checks, 50% of the ones that ran passed &middot; 3 findings", page)
        self.assertIn('<div class="verdict major">\n    <span class="label">Fix before release</span>', page)

    def test_pass_rate_is_na_and_blocked_checks_are_listed_when_nothing_ran(self) -> None:
        data = make_results(checks=[
            make_check("C1", "blocked", title="Pay by card", actual="No test card on staging."),
            make_check("C2", "skipped", actual="Out of scope."),
        ])

        page = self.build_page(data)

        self.assertIn("2 checks, n/a of the ones that ran passed &middot; 0 findings", page)
        self.assertIn('<div class="verdict gaps">\n    <span class="label">Clean, with gaps</span>', page)
        self.assertIn(
            "<p>No critical or major findings. These checks could not run:</p>"
            "<ul><li><b>C1</b> Pay by card — No test card on staging.</li></ul>",
            page,
        )

    def test_fix_first_lists_critical_then_major_findings_and_omits_minor(self) -> None:
        data = make_results(
            checks=[make_check("C1", "fail", findings=["F1", "F2", "F3"])],
            findings=[
                make_finding("F1", "major", title="Slow totals", checks=["C1"]),
                make_finding("F2", "critical", title="Double charge", impact="Money lost.", checks=["C1"]),
                make_finding("F3", "minor", title="Typo", checks=["C1"]),
            ],
        )

        page = self.build_page(data)

        fix_first = re.search(r'<div class="fix-first"><h2>Fix first</h2><ul>(.*?)</ul></div>', page)
        self.assertIsNotNone(fix_first)
        self.assertEqual(re.findall(r'<a href="#(F\d)">', fix_first.group(1)), ["F2", "F1"])
        self.assertIn(
            '<li class="sev-critical"><a href="#F2"><b>F2</b> Double charge</a>'
            '<span class="sev">critical</span><span class="why">Money lost.</span></li>',
            fix_first.group(1),
        )
        self.assertNotIn("Typo", fix_first.group(1))
        self.assertIn('<div class="verdict crit">\n    <span class="label">Ship blocked</span>', page)

    def test_date_option_overrides_the_results_date(self) -> None:
        page = self.build_page(make_results(), "--date", "2026-12-01")

        self.assertIn("QA pass &middot; staging &middot; 2026-12-01</p>", page)
        self.assertIn("Run on 2026-12-01 against", page)
        self.assertNotIn("2026-11-20", page)

    def test_scope_baseline_gaps_and_notes_render_into_their_panels(self) -> None:
        data = make_results(
            scope={"asked": "Check checkout.", "in_scope": ["Paying"], "out_of_scope": ["Refunds"]},
            baseline={"console": ["[vite] connected"], "notes": "favicon 404 on every page"},
            coverage_gaps=["Mobile widths"],
            notes=["Left a test order."],
        )

        page = self.build_page(data)

        self.assertIn("<h2>Scope</h2>\n  <p>Check checkout.</p>", page)
        self.assertIn("<h3>Asked for</h3><ul><li>Paying</li></ul></section>", page)
        self.assertIn("<h3>Not covered</h3><ul><li>Refunds</li><li>Mobile widths</li></ul></section>", page)
        self.assertIn(
            "<h3>Baseline noise</h3><ul><li>[vite] connected</li><li>favicon 404 on every page</li></ul></section>",
            page,
        )
        self.assertIn("<h3>Notes</h3><ul><li>Left a test order.</li></ul></section>", page)

    def test_absent_optional_sections_render_their_empty_text(self) -> None:
        page = self.build_page(make_results())

        self.assertIn("<h3>Asked for</h3><p class='muted'>Not recorded.</p></section>", page)
        self.assertIn("<h3>Baseline noise</h3><p class='muted'>No baseline recorded.</p>", page)
        self.assertIn("<h3>Not covered</h3><p class='muted'>Nothing recorded as out of scope", page)
        self.assertIn("<h3>Notes</h3><p class='muted'>None.</p>", page)

    def test_checks_and_findings_are_embedded_as_page_data(self) -> None:
        data = with_finding()

        page = self.build_page(data)

        self.assertEqual(extract_data(page), {"checks": data["checks"], "findings": data["findings"]})


class EscapingTests(BuildCase):
    def test_hostile_text_is_escaped_in_markup_and_cannot_close_the_data_script(self) -> None:
        hostile = "<script>alert(1)</script>"
        data = make_results(
            title=hostile,
            verdict_note=hostile,
            scope={"asked": hostile, "in_scope": [hostile]},
            notes=[hostile],
            checks=[make_check("C1", "blocked", title=hostile, actual=hostile)],
            target={"url": "https://example.com/?q=\"><b>", "env": "staging", "build": hostile, "browser": hostile},
        )

        page = self.build_page(data)
        escaped = "&lt;script&gt;alert(1)&lt;/script&gt;"

        self.assertIn(f"<title>{escaped} QA</title>", page)
        self.assertIn(f"<h1>{escaped}</h1>", page)
        self.assertIn(f'<span class="note">{escaped}</span>', page)
        self.assertIn(f"<h2>Scope</h2>\n  <p>{escaped}</p>", page)
        self.assertIn(f'build: <b class="mono">{escaped}</b>', page)
        self.assertIn(f"browser: <b>{escaped}</b>", page)
        self.assertIn(f"<li><b>C1</b> {escaped} — {escaped}</li>", page)
        self.assertIn('<a href="https://example.com/?q=&quot;&gt;&lt;b&gt;">', page)
        self.assertEqual(page.count("</script>"), 1, "only the template's own closing tag may appear")
        self.assertEqual(extract_data(page)["checks"][0]["title"], hostile)


    def test_comment_then_script_in_check_text_cannot_swallow_the_closing_tag(self) -> None:
        # Regression: only `</` was escaped, and `<!--<script>` left the browser
        # unable to end the data script, so the page rendered no checks.
        text = "Help text shows <!--<script> literally"
        page = self.build_page(make_results(checks=[make_check("C1", "pass", actual=text)]))

        self.assertNotIn("<!--<script>", page)
        self.assertEqual(extract_data(page)["checks"][0]["actual"], text)

    def test_placeholder_like_text_in_results_is_shown_as_written(self) -> None:
        # Regression: placeholder replacement ran over the inserted data, so
        # `__NEXT_DATA__` failed the build and `__N_PASS__` became a count.
        checks = [
            make_check("C1", "pass", actual="window.__NEXT_DATA__ was present"),
            make_check("C2", "pass", actual="Badge shows __N_PASS__ literally"),
        ]
        page = self.build_page(make_results(checks=checks))

        actual = [c["actual"] for c in extract_data(page)["checks"]]
        self.assertEqual(actual, ["window.__NEXT_DATA__ was present", "Badge shows __N_PASS__ literally"])


class ScreenshotTests(BuildCase):
    def test_referenced_screenshots_are_copied_beside_the_output(self) -> None:
        shots = self.make_shots("C1-ok.png", "F1-dup.jpg", "unused.png")
        data = with_finding()
        data["checks"][0]["evidence"] = [{"kind": "screenshot", "path": "C1-ok.png", "caption": "ok"}]
        data["checks"][1]["evidence"] = [{"kind": "screenshot", "path": "F1-dup.jpg"}]
        data["findings"][0]["evidence"] = [
            {"kind": "screenshot", "path": "F1-dup.jpg"},
            {"kind": "console", "text": "TypeError: x is undefined"},
        ]

        self.build_page(data, "--shots", str(shots))

        copied = self.out_dir / "shots"
        self.assertEqual(sorted(p.name for p in copied.iterdir()), ["C1-ok.png", "F1-dup.jpg"])
        self.assertEqual((copied / "C1-ok.png").read_bytes(), (shots / "C1-ok.png").read_bytes())
        self.assertEqual((copied / "F1-dup.jpg").read_bytes(), (shots / "F1-dup.jpg").read_bytes())

    def test_no_shots_directory_is_created_without_screenshot_evidence(self) -> None:
        shots = self.make_shots("C1.png")
        data = make_results(checks=[make_check("C1", evidence=[{"kind": "note", "text": "looked fine"}])])

        self.build_page(data, "--shots", str(shots))

        self.assertFalse((self.out_dir / "shots").exists())

    def test_screenshots_already_beside_the_output_are_left_in_place(self) -> None:
        shots = self.out_dir / "shots"
        shots.mkdir()
        (shots / "C1.png").write_bytes(PNG_BYTES)
        data = make_results(checks=[make_check("C1", evidence=[{"kind": "screenshot", "path": "C1.png"}])])

        self.build_page(data, "--shots", str(shots))

        self.assertEqual((shots / "C1.png").read_bytes(), PNG_BYTES)

    def test_rejects_a_screenshot_missing_from_the_shots_directory(self) -> None:
        shots = self.make_shots("other.png")
        data = make_results(checks=[make_check("C1", evidence=[{"kind": "screenshot", "path": "C1.png"}])])

        result = self.run_build(data, "--shots", str(shots))

        self.assert_rejected(result, f"results.json: check 'C1' references missing screenshot 'C1.png' in {shots}")

    def test_rejects_a_screenshot_when_no_shots_directory_is_given(self) -> None:
        data = make_results(checks=[make_check("C1", evidence=[{"kind": "screenshot", "path": "C1.png"}])])

        result = self.run_build(data)

        self.assert_rejected(result, "results.json: check 'C1' references a screenshot but --shots was not given")

    def test_rejects_a_shots_path_that_is_not_a_directory(self) -> None:
        missing = self.root / "nope"

        result = self.run_build(make_results(), "--shots", str(missing))

        self.assert_rejected(result, f"--shots {missing} is not a directory")

    def test_rejects_screenshot_paths_that_are_not_bare_image_filenames(self) -> None:
        shots = self.make_shots("ok.png")
        (self.root / "secret.png").write_bytes(PNG_BYTES)
        for path in ["../secret.png", "sub/ok.png", "ok.svg", ".hidden.png", ""]:
            with self.subTest(path=path):
                data = make_results(checks=[make_check("C1", evidence=[{"kind": "screenshot", "path": path}])])

                result = self.run_build(data, "--shots", str(shots))

                self.assert_rejected(
                    result,
                    f"results.json: check 'C1' screenshot path {path!r} must be a bare image filename",
                )


class RejectionTests(BuildCase):
    def test_rejects_invalid_results_with_a_message_naming_the_problem(self) -> None:
        def set_top(key, value):
            return lambda d: d.__setitem__(key, value)

        def set_target(key, value):
            return lambda d: d["target"].__setitem__(key, value)

        def set_check(index, key, value):
            return lambda d: d["checks"][index].__setitem__(key, value)

        def set_finding(key, value):
            return lambda d: d["findings"][0].__setitem__(key, value)

        def drop(path_fn, key):
            return lambda d: path_fn(d).pop(key)

        cases = [
            ("missing top-level key", drop(lambda d: d, "verdict_note"), "top level is missing ['verdict_note']"),
            ("missing target key", drop(lambda d: d["target"], "build"), "target is missing ['build']"),
            ("missing check key", drop(lambda d: d["checks"][0], "expected"), "check 'C1' is missing ['expected']"),
            ("missing finding key", drop(lambda d: d["findings"][0], "impact"), "finding 'F1' is missing ['impact']"),
            ("bad driver", set_top("driver", "selenium"), "driver 'selenium' is not one of"),
            ("bad depth", set_top("depth", "thorough"), "depth 'thorough' is not one of ['deep', 'smoke', 'standard']"),
            ("bad date", set_top("date", "20/11/2026"), "date '20/11/2026' is not YYYY-MM-DD"),
            ("bad env", set_target("env", "qa"), "target.env 'qa' is not one of"),
            ("non-http url", set_target("url", "javascript:alert(1)"), "target.url must be http(s), got 'javascript:alert(1)'"),
            ("latest build", set_target("build", " Latest "), "target.build must identify the build under test"),
            ("blank build", set_target("build", "  "), "target.build must identify the build under test"),
            ("no checks", set_top("checks", []), "no checks; a pass with nothing in it is not a report"),
            ("blank verdict note", set_top("verdict_note", "  "), "verdict_note is empty"),
            ("bad check status", set_check(0, "status", "passed"), "check 'C1' has unknown status 'passed'"),
            ("bad check type", set_check(0, "type", "manual"), "check 'C1' has unknown type 'manual'"),
            ("no steps", set_check(0, "steps", []), "check 'C1' has no steps"),
            ("steps not a list", set_check(0, "steps", "Open /cart"), "check 'C1' has no steps"),
            ("empty actual", set_check(0, "actual", " "), "check 'C1' has an empty 'actual'"),
            ("duplicate check id", set_check(1, "id", "C1"), "duplicate check id 'C1'"),
            ("bad severity", set_finding("severity", "blocker"), "finding 'F1' has unknown severity 'blocker'"),
            ("bad finding status", set_finding("status", "maybe"), "finding 'F1' has unknown status 'maybe'"),
            ("no repro", set_finding("repro", []), "finding 'F1' has no repro steps"),
            ("finding cites unknown check", set_finding("checks", ["C9"]), "finding 'F1' references unknown check 'C9'"),
            ("check cites unknown finding", set_check(1, "findings", ["F9"]), "check 'C2' references unknown finding 'F9'"),
            ("fail without finding", set_check(1, "findings", []), "check 'C2' failed but names no finding"),
            (
                "duplicate finding id",
                lambda d: d["findings"].append(make_finding("F1")),
                "duplicate finding id 'F1'",
            ),
            (
                "bad evidence kind",
                set_check(0, "evidence", [{"kind": "video", "path": "x.mp4"}]),
                "check 'C1' has evidence of unknown kind 'video'",
            ),
            (
                "text evidence without text",
                set_finding("evidence", [{"kind": "console", "text": " "}]),
                "finding 'F1' has console evidence with no text",
            ),
        ]
        for name, mutate, message in cases:
            with self.subTest(name):
                data = copy.deepcopy(with_finding())
                mutate(data)

                result = self.run_build(data)

                self.assert_rejected(result, f"results.json: {message}")

    def test_rejects_malformed_json(self) -> None:
        self.results.write_text('{"title": "Checkout",', encoding="utf-8")

        result = self.run_build(None)

        self.assert_rejected(result, "JSONDecodeError")

    def test_rejects_a_missing_results_file(self) -> None:
        result = self.run_build(None)

        self.assert_rejected(result, "No such file or directory")


class DeriveTests(unittest.TestCase):
    def test_verdict_label_follows_the_schema_table(self) -> None:
        cases = [
            ("critical confirmed", [make_check("C1")], [make_finding("F1", "critical")], ("Ship blocked", "crit")),
            ("critical flaky", [make_check("C1")], [make_finding("F1", "critical", "flaky")], ("Ship blocked", "crit")),
            (
                "critical pre-existing only",
                [make_check("C1")],
                [make_finding("F1", "critical", "pre-existing")],
                ("Ready with caveats", "minor"),
            ),
            (
                "major beside pre-existing critical",
                [make_check("C1")],
                [make_finding("F1", "critical", "pre-existing"), make_finding("F2", "major")],
                ("Fix before release", "major"),
            ),
            ("minor only", [make_check("C1")], [make_finding("F1", "minor")], ("Ready with caveats", "minor")),
            ("nit only", [make_check("C1")], [make_finding("F1", "nit")], ("Ready with caveats", "minor")),
            ("blocked, no findings", [make_check("C1"), make_check("C2", "blocked")], [], ("Clean, with gaps", "gaps")),
            ("skipped, no findings", [make_check("C1", "skipped")], [], ("Clean, with gaps", "gaps")),
            ("all pass", [make_check("C1"), make_check("C2")], [], ("Clean", "clean")),
            ("partial, no findings", [make_check("C1", "partial")], [], ("Clean", "clean")),
        ]
        for name, checks, findings, expected in cases:
            with self.subTest(name):
                derived = build.derive(make_results(checks=checks, findings=findings))

                self.assertEqual((derived["label"], derived["css"]), expected)

    def test_pass_rate_counts_only_checks_that_ran_and_rounds(self) -> None:
        checks = [make_check("C1"), make_check("C2", "fail"), make_check("C3", "partial"), make_check("C4", "blocked")]

        derived = build.derive(make_results(checks=checks))

        self.assertEqual((derived["total"], derived["ran"], derived["pass_rate"]), (4, 3, "33%"))

    def test_bullet_list_escapes_items_and_falls_back_when_empty(self) -> None:
        self.assertEqual(build.bullet_list(["a<b", "c&d"]), "<ul><li>a&lt;b</li><li>c&amp;d</li></ul>")
        self.assertEqual(build.bullet_list([], "<p>none</p>"), "<p>none</p>")


if __name__ == "__main__":
    unittest.main()
