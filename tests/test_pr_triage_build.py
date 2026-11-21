"""Tests for the pr-triage page builder (.claude/skills/pr-triage/scripts/build.py)."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import tempfile
import unittest

from tests.helpers import SKILLS, load_script, run_script

BUILD = SKILLS / "pr-triage" / "scripts" / "build.py"
build = load_script(BUILD, "pr_triage_build")

REPORT_DATE = "2026-11-21"
PLACEHOLDER = re.compile(r"__[A-Z_]+__")


def make_pr(number: int, **overrides) -> dict:
    """One assessment in the reviewer-brief shape, opened 5 days and updated 1 day before REPORT_DATE."""
    pr = {
        "number": number,
        "title": f"PR {number}",
        "url": f"https://github.com/acme/widgets/pull/{number}",
        "author": "octo",
        "draft": False,
        "base": "main",
        "created_at": "2026-11-16T10:00:00Z",
        "updated_at": "2026-11-20T10:00:00Z",
        "additions": 10,
        "deletions": 2,
        "changed_files": 1,
        "areas": ["core"],
        "summary": "Does a thing.",
        "ci": "passing",
        "ci_detail": "",
        "mergeable_state": "clean",
        "approvals": 1,
        "changes_requested_by": [],
        "open_threads": 0,
        "reviewer_concerns": [],
        "risk": "Low",
        "risk_reasons": ["Small isolated change with tests."],
        "flags": [],
    }
    pr.update(overrides)
    return pr


def extract_data(page: str) -> list[dict]:
    match = re.search(r"const DATA = (.*);\n", page)
    assert match, "DATA assignment not found in page"
    return json.loads(match.group(1))


def tile_count(page: str, risk: str) -> int:
    match = re.search(rf'data-risk="{risk}" aria-pressed="false"><span class="n">(\d+)</span>', page)
    assert match, f"{risk} tile not found"
    return int(match.group(1))


def signal_count(page: str, quick: str) -> int:
    match = re.search(rf'data-quick="{quick}" aria-pressed="false"><span class="n">(\d+)</span>', page)
    assert match, f"{quick} signal not found"
    return int(match.group(1))


class BuildCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.batches = self.root / "batches"
        self.batches.mkdir()
        self.out = self.root / "out" / "triage.html"

    def write_batch(self, name: str, prs: list[dict]) -> pathlib.Path:
        path = self.batches / name
        path.write_text(json.dumps(prs), encoding="utf-8")
        return path

    def write_highlights(self, highlights: dict) -> pathlib.Path:
        path = self.root / "highlights.json"
        path.write_text(json.dumps(highlights), encoding="utf-8")
        return path

    def run_build(self, *extra: str, repo: str = "acme/widgets", date: str | None = REPORT_DATE):
        args = ["--repo", repo, "--batches", str(self.batches), "--out", str(self.out)]
        if date is not None:
            args += ["--date", date]
        return run_script(BUILD, *args, *extra)

    def build_page(self, *extra: str, **kwargs) -> str:
        result = self.run_build(*extra, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.out.read_text(encoding="utf-8")

    def assert_rejected(self, result, *fragments: str) -> None:
        self.assertNotEqual(result.returncode, 0)
        for fragment in fragments:
            self.assertIn(fragment, result.stderr)
        self.assertFalse(self.out.exists(), "no page should be written on a rejected build")


class RenderTests(BuildCase):
    def test_fills_every_placeholder_and_derives_header_counts(self) -> None:
        self.write_batch("batch1.json", [
            make_pr(1, risk="Critical", ci="failing", ci_detail="unit tests", mergeable_state="dirty"),
            make_pr(2, risk="High", ci="pending"),
            make_pr(3, risk="Medium", ci="failing", ci_detail="lint"),
        ])
        self.write_batch("batch2.json", [
            make_pr(4, risk="Low"),
            make_pr(5, risk="Low", created_at="2026-10-01T00:00:00Z"),
        ])

        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        page = self.out.read_text(encoding="utf-8")

        self.assertEqual(PLACEHOLDER.findall(page), [])
        self.assertIn("<title>widgets PR Triage</title>", page)
        self.assertIn("acme/widgets &middot; open pull requests &middot; 21 Nov 2026", page)
        self.assertIn("Open PR triage: 5 pull requests ready for review", page)
        self.assertEqual(
            {risk: tile_count(page, risk) for risk in ("Critical", "High", "Medium", "Low")},
            {"Critical": 1, "High": 1, "Medium": 1, "Low": 2},
        )
        self.assertIn("<strong>2</strong> with failing CI &middot; <strong>1</strong> with merge conflicts", page)
        self.assertEqual(signal_count(page, "failing"), 2)
        self.assertEqual(signal_count(page, "conflicts"), 1)
        self.assertEqual(signal_count(page, "stale"), 1)
        self.assertIn("<strong>1</strong> open three weeks or longer", page)
        self.assertEqual(
            result.stdout.splitlines()[1:],
            ["  Critical 1, High 1, Medium 1, Low 2", "  failing CI 2, known conflicts 1, stale 1, drafts 0"],
        )

    def test_data_is_ordered_by_risk_then_least_recently_updated(self) -> None:
        self.write_batch("batch1.json", [
            make_pr(1, risk="Low", updated_at="2026-11-19T00:00:00Z"),
            make_pr(2, risk="Critical"),
            make_pr(3, risk="Low", updated_at="2026-11-10T00:00:00Z"),
            make_pr(4, risk="Medium"),
            make_pr(5, risk="High"),
        ])

        data = extract_data(self.build_page())

        self.assertEqual([p["number"] for p in data], [2, 5, 4, 3, 1])

    def test_age_and_idle_days_are_counted_from_the_report_date(self) -> None:
        self.write_batch("batch1.json", [
            make_pr(1, created_at="2026-11-01T23:59:00Z", updated_at="2026-11-18T00:00:00Z"),
        ])

        (pr,) = extract_data(self.build_page())

        self.assertEqual((pr["age_days"], pr["idle_days"]), (20, 3))

    def test_stale_threshold_counts_prs_open_exactly_21_days(self) -> None:
        self.write_batch("batch1.json", [
            make_pr(1, created_at="2026-10-31T00:00:00Z"),
            make_pr(2, created_at="2026-11-01T00:00:00Z"),
        ])

        page = self.build_page()

        self.assertEqual(signal_count(page, "stale"), 1)

    def test_date_option_sets_the_header_and_footer_date(self) -> None:
        self.write_batch("batch1.json", [make_pr(1)])

        page = self.build_page(date="2027-01-05")

        self.assertIn("open pull requests &middot; 5 Jan 2027</p>", page)
        self.assertIn("review threads on 5 Jan 2027.", page)

    def test_default_date_is_today(self) -> None:
        self.write_batch("batch1.json", [make_pr(1)])

        page = self.build_page(date=None)

        self.assertIn(f"open pull requests &middot; {dt.date.today().strftime('%-d %b %Y')}</p>", page)

    def test_creates_the_output_directory_when_missing(self) -> None:
        self.write_batch("batch1.json", [make_pr(1)])
        self.out = self.root / "nested" / "deeper" / "triage.html"

        self.build_page()

        self.assertTrue(self.out.is_file())


class MergeTests(BuildCase):
    def test_same_pr_in_two_batches_appears_once_with_the_later_batch_winning(self) -> None:
        self.write_batch("batch1.json", [make_pr(7, title="old title", risk="High"), make_pr(8)])
        self.write_batch("batch2.json", [make_pr(7, title="new title", risk="Low")])

        page = self.build_page()
        data = extract_data(page)

        self.assertEqual(sorted(p["number"] for p in data), [7, 8])
        self.assertEqual(next(p for p in data if p["number"] == 7)["title"], "new title")
        self.assertIn("Open PR triage: 2 pull requests", page)
        self.assertEqual(tile_count(page, "High"), 0)
        self.assertEqual(tile_count(page, "Low"), 2)

    def test_batches_are_merged_in_file_name_order(self) -> None:
        self.write_batch("batch-b.json", [make_pr(7, title="from b")])
        self.write_batch("batch-a.json", [make_pr(7, title="from a")])

        (pr,) = extract_data(self.build_page())

        self.assertEqual(pr["title"], "from b")

    def test_ignores_json_files_not_named_batch(self) -> None:
        self.write_batch("batch1.json", [make_pr(1)])
        (self.batches / "notes.json").write_text("not json at all", encoding="utf-8")

        data = extract_data(self.build_page())

        self.assertEqual([p["number"] for p in data], [1])


class EscapingTests(BuildCase):
    def test_script_tags_in_pr_text_cannot_close_the_data_script(self) -> None:
        hostile = "</script><script>alert(1)</script>"
        self.write_batch("batch1.json", [make_pr(1, title=hostile, summary=hostile, reviewer_concerns=[hostile])])

        page = self.build_page()

        self.assertEqual(page.count("</script>"), 1, "only the template's own closing tag may appear")
        data_line = re.search(r"const DATA = (.*);\n", page).group(1)
        self.assertNotIn("<", data_line, "every < in the data is escaped as \\u003c")
        (pr,) = extract_data(page)
        self.assertEqual(pr["title"], hostile)
        self.assertEqual(pr["summary"], hostile)

    def test_comment_then_script_in_pr_text_cannot_swallow_the_closing_tag(self) -> None:
        # Regression: only `</` was escaped, and `<!--<script>` left the browser
        # unable to end the data script, so the page rendered no PRs.
        text = "Strip <!--<script> from docs"
        self.write_batch("batch1.json", [make_pr(1, title=text, summary=text)])

        page = self.build_page()

        self.assertNotIn("<!--", page)
        (pr,) = extract_data(page)
        self.assertEqual((pr["title"], pr["summary"]), (text, text))

    def test_placeholder_like_text_in_pr_data_is_shown_as_written(self) -> None:
        # Regression: placeholders were replaced one by one over the whole page,
        # so these failed the build or were rewritten inside the data.
        titles = ["Rename __DATE__ token", "Fix count shown as __TOTAL__", "Move __TITLE__ and __REPO__"]
        prs = [make_pr(n, title=t, summary="See __DRAFT_FILTERS__") for n, t in enumerate(titles, start=1)]
        self.write_batch("batch1.json", prs)

        page = self.build_page("--include-drafts")

        data = extract_data(page)
        self.assertEqual(sorted(p["title"] for p in data), sorted(titles))
        self.assertEqual({p["summary"] for p in data}, {"See __DRAFT_FILTERS__"})

    def test_repo_name_is_escaped_in_the_header(self) -> None:
        self.write_batch("batch1.json", [make_pr(1)])

        page = self.build_page(repo='acme/<b onclick="x">')

        self.assertIn('<p class="eyebrow">acme/&lt;b onclick=&quot;x&quot;&gt; &middot;', page)


class DraftTests(BuildCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_batch("batch1.json", [make_pr(1), make_pr(2, draft=True, flags=["draft"])])

    def test_drafts_are_excluded_by_default(self) -> None:
        page = self.build_page()

        self.assertEqual([p["number"] for p in extract_data(page)], [1])
        self.assertIn("Open PR triage: 1 pull requests", page)
        self.assertNotIn('data-quick="drafts"', page)
        self.assertNotIn('data-quick="ready"', page)
        self.assertIn("Draft PRs are excluded. They estimate", page)

    def test_include_drafts_keeps_drafts_and_adds_draft_filters(self) -> None:
        result = self.run_build("--include-drafts")
        self.assertEqual(result.returncode, 0, result.stderr)
        page = self.out.read_text(encoding="utf-8")

        self.assertEqual(sorted(p["number"] for p in extract_data(page)), [1, 2])
        self.assertIn("Open PR triage: 2 pull requests", page)
        self.assertEqual(signal_count(page, "drafts"), 1)
        self.assertIn('<button data-quick="ready" aria-pressed="false">ready for review only</button>', page)
        self.assertIn("<strong>1</strong> drafts &middot; <strong>", page)
        self.assertIn("Draft PRs are excluded unless the report was built with --include-drafts.", page)
        self.assertEqual(PLACEHOLDER.findall(page), [])
        self.assertIn("drafts 1", result.stdout)

    def test_only_drafts_without_include_drafts_is_rejected(self) -> None:
        self.write_batch("batch1.json", [make_pr(2, draft=True)])

        result = self.run_build()

        self.assert_rejected(result, "no pull requests left to render")


class MergeabilityTests(BuildCase):
    NOTE = "GitHub had not computed mergeability for most branches"

    def test_note_appears_when_most_mergeable_states_are_unknown(self) -> None:
        self.write_batch("batch1.json", [
            make_pr(1, mergeable_state=""),
            make_pr(2, mergeable_state=None),
            make_pr(3, mergeable_state="clean"),
        ])

        page = self.build_page()

        self.assertIn(self.NOTE, page)
        states = {p["number"]: p["mergeable_state"] for p in extract_data(page)}
        self.assertEqual(states, {1: "unknown", 2: "unknown", 3: "clean"})

    def test_note_is_absent_when_exactly_half_are_unknown(self) -> None:
        self.write_batch("batch1.json", [make_pr(1, mergeable_state="unknown"), make_pr(2, mergeable_state="clean")])

        page = self.build_page()

        self.assertNotIn(self.NOTE, page)


class HighlightsTests(BuildCase):
    def setUp(self) -> None:
        super().setUp()
        self.write_batch("batch1.json", [
            make_pr(10, risk="High"),
            make_pr(11),
            make_pr(12),
            make_pr(13, created_at="2026-10-01T00:00:00Z"),
            make_pr(14, created_at="2026-09-01T00:00:00Z"),
            make_pr(15, draft=True),
        ])

    def test_start_here_section_is_omitted_without_highlights(self) -> None:
        page = self.build_page()

        self.assertNotIn('class="start"', page)

    def test_review_with_care_lists_rendered_prs_with_escaped_reasons(self) -> None:
        path = self.write_highlights({
            "review_with_care": [
                {"number": 10, "why": "<script>alert(1)</script> touches auth"},
                {"number": 999, "why": "not in the queue"},
                {"number": 15, "why": "draft, filtered out"},
            ],
        })

        page = self.build_page("--highlights", str(path))

        self.assertIn(
            '<h3>Review with care</h3><ul><li><a href="#pr-10">#10</a> '
            "&lt;script&gt;alert(1)&lt;/script&gt; touches auth</li></ul>",
            page,
        )
        self.assertNotIn("not in the queue", page)
        self.assertNotIn("draft, filtered out", page)

    def test_quick_merges_drop_unknown_numbers_and_escape_the_note(self) -> None:
        path = self.write_highlights({"quick_merges": [11, 12, 999], "quick_merge_note": "Merge #11 <before> #12."})

        page = self.build_page("--highlights", str(path))

        self.assertIn(
            '<h3>Quick merges</h3><p>Low risk, CI green, no open concerns: '
            '<a href="#pr-11">#11</a>, <a href="#pr-12">#12</a>.</p><p>Merge #11 &lt;before&gt; #12.</p>',
            page,
        )
        self.assertNotIn("#pr-999", page)

    def test_stale_prs_are_listed_in_number_order_with_the_default_note(self) -> None:
        path = self.write_highlights({"quick_merges": []})

        page = self.build_page("--highlights", str(path))

        self.assertIn(
            "<h3>Stale and unreviewed</h3><p>2 PRs have been open 21 days or more: "
            '<a href="#pr-13">#13</a>, <a href="#pr-14">#14</a>. Decide to review or close.</p>',
            page,
        )

    def test_stale_note_replaces_the_default_and_is_escaped(self) -> None:
        path = self.write_highlights({"stale_note": "Ping <owners>."})

        page = self.build_page("--highlights", str(path))

        self.assertIn('<a href="#pr-14">#14</a>. Ping &lt;owners&gt;.</p>', page)
        self.assertNotIn("Decide to review or close.", page)


class RejectionTests(BuildCase):
    def test_rejects_unknown_enum_values_naming_the_file_and_pr(self) -> None:
        cases = [
            ({"risk": "Severe"}, "PR 1 has unknown risk 'Severe'"),
            ({"ci": "green"}, "PR 1 has unknown ci state 'green'"),
            ({"mergeable_state": "conflicting"}, "PR 1 has unknown mergeable_state 'conflicting'"),
            ({"url": "javascript:alert(1)"}, "PR 1 url must start with https://github.com/, got 'javascript:alert(1)'"),
            ({"url": None}, "PR 1 url must start with https://github.com/, got None"),
        ]
        for override, message in cases:
            with self.subTest(override=override):
                path = self.write_batch("batch1.json", [make_pr(1, **override)])

                result = self.run_build()

                self.assert_rejected(result, f"{path}: {message}")

    def test_rejects_a_non_integer_pr_number(self) -> None:
        pr = make_pr(1)
        pr["number"] = "1"
        path = self.write_batch("batch1.json", [pr])

        result = self.run_build()

        self.assert_rejected(result, f"{path}: PR number must be an integer, got '1'")

    def test_rejects_a_pr_missing_required_keys(self) -> None:
        pr = make_pr(3)
        del pr["risk"], pr["summary"]
        path = self.write_batch("batch1.json", [make_pr(1), pr])

        result = self.run_build()

        self.assert_rejected(result, f"{path}: PR 3 is missing keys ['risk', 'summary']")

    def test_rejects_an_empty_batches_directory(self) -> None:
        result = self.run_build()

        self.assert_rejected(result, f"no batch*.json files found in {self.batches}")

    def test_rejects_a_malformed_batch_file(self) -> None:
        self.write_batch("batch1.json", [make_pr(1)])
        (self.batches / "batch2.json").write_text('[{"number": 2,', encoding="utf-8")

        result = self.run_build()

        self.assert_rejected(result, "JSONDecodeError")

    def test_rejects_a_malformed_highlights_file(self) -> None:
        self.write_batch("batch1.json", [make_pr(1)])
        path = self.root / "highlights.json"
        path.write_text("{oops", encoding="utf-8")

        result = self.run_build("--highlights", str(path))

        self.assert_rejected(result, "JSONDecodeError")

    def test_rejects_a_bad_date(self) -> None:
        self.write_batch("batch1.json", [make_pr(1)])

        result = self.run_build(date="21/11/2026")

        self.assert_rejected(result, "Invalid isoformat string: '21/11/2026'")


class HelperTests(unittest.TestCase):
    def test_pr_link_points_at_the_pr_anchor(self) -> None:
        self.assertEqual(build.pr_link(42), '<a href="#pr-42">#42</a>')

    def test_render_start_here_is_empty_for_missing_or_empty_highlights(self) -> None:
        prs = [dict(make_pr(1), age_days=30)]

        self.assertEqual(build.render_start_here(None, prs), "")
        self.assertEqual(build.render_start_here({}, prs), "")

    def test_render_start_here_is_empty_when_nothing_applies(self) -> None:
        prs = [dict(make_pr(1), age_days=3)]

        result = build.render_start_here({"review_with_care": [{"number": 2, "why": "x"}], "quick_merges": [3]}, prs)

        self.assertEqual(result, "")

    def test_validate_enums_normalises_missing_mergeable_state_to_unknown(self) -> None:
        pr = make_pr(1, mergeable_state=None)

        build.validate_enums("batch1.json", pr)

        self.assertEqual(pr["mergeable_state"], "unknown")

    def test_enrich_sets_ages_and_sorts_in_place(self) -> None:
        prs = [
            make_pr(1, risk="Low", created_at="2026-11-11T00:00:00Z", updated_at="2026-11-20T00:00:00Z"),
            make_pr(2, risk="High", created_at="2026-11-01T00:00:00Z", updated_at="2026-11-15T00:00:00Z"),
        ]

        build.enrich(prs, dt.date(2026, 11, 21))

        self.assertEqual([(p["number"], p["age_days"], p["idle_days"]) for p in prs], [(2, 20, 6), (1, 10, 1)])


if __name__ == "__main__":
    unittest.main()
