#!/usr/bin/env python3
"""Assemble the PR triage page from reviewer batch files.

Reads every `batch*.json` in the batches directory (each an array of PR
assessments in the shape described in references/reviewer-brief.md), merges and
de-duplicates them, derives the summary counts, and renders assets/template.html
into a single self-contained HTML file.

Usage:
  build.py --repo owner/name --batches DIR --out FILE
           [--highlights FILE] [--date YYYY-MM-DD] [--include-drafts]

The highlights file is optional JSON written by the orchestrator after reading
the merged assessments:
  {
    "review_with_care": [{"number": 6137, "why": "..."}, ...],
    "quick_merges": [6318, 6319, ...],
    "quick_merge_note": "Merge #6323 before #6326; they edit the same file.",
    "stale_note": "..."
  }
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import html
import json
import os
import sys

RISK_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
CI_STATES = {"passing", "failing", "pending", "none"}
MERGEABLE_STATES = {"clean", "dirty", "blocked", "unstable", "unknown", "behind", "draft", "has_hooks"}
PR_URL_PREFIX = "https://github.com/"
STALE_AFTER_DAYS = 21
REQUIRED_KEYS = {
    "number", "title", "url", "author", "draft", "base", "created_at", "updated_at",
    "additions", "deletions", "changed_files", "areas", "summary", "ci", "ci_detail",
    "mergeable_state", "approvals", "changes_requested_by", "open_threads",
    "reviewer_concerns", "risk", "risk_reasons", "flags",
}


def load_batches(batches_dir: str) -> list[dict]:
    prs: dict[int, dict] = {}
    files = sorted(glob.glob(os.path.join(batches_dir, "batch*.json")))
    if not files:
        sys.exit(f"no batch*.json files found in {batches_dir}")
    for path in files:
        with open(path, encoding="utf-8") as fh:
            for pr in json.load(fh):
                missing = REQUIRED_KEYS - set(pr)
                if missing:
                    sys.exit(f"{path}: PR {pr.get('number')} is missing keys {sorted(missing)}")
                validate_enums(path, pr)
                prs[pr["number"]] = pr
    return list(prs.values())


def validate_enums(path: str, pr: dict) -> None:
    """Reject values the template interpolates into class names or hrefs.

    Reviewer output is produced by a language model reading third-party PRs, so
    every field the page uses outside escaped text content is checked against a
    closed set here rather than trusted from the brief alone.
    """
    number = pr.get("number")
    if pr["risk"] not in RISK_ORDER:
        sys.exit(f"{path}: PR {number} has unknown risk {pr['risk']!r}")
    if pr["ci"] not in CI_STATES:
        sys.exit(f"{path}: PR {number} has unknown ci state {pr['ci']!r}")
    if not pr["mergeable_state"]:
        pr["mergeable_state"] = "unknown"
    if pr["mergeable_state"] not in MERGEABLE_STATES:
        sys.exit(f"{path}: PR {number} has unknown mergeable_state {pr['mergeable_state']!r}")
    if not isinstance(pr["url"], str) or not pr["url"].startswith(PR_URL_PREFIX):
        sys.exit(f"{path}: PR {number} url must start with {PR_URL_PREFIX}, got {pr['url']!r}")
    if not isinstance(pr["number"], int):
        sys.exit(f"{path}: PR number must be an integer, got {pr['number']!r}")


def enrich(prs: list[dict], today: dt.date) -> None:
    for pr in prs:
        created = dt.date.fromisoformat(pr["created_at"][:10])
        updated = dt.date.fromisoformat(pr["updated_at"][:10])
        pr["age_days"] = (today - created).days
        pr["idle_days"] = (today - updated).days
    prs.sort(key=lambda p: (RISK_ORDER[p["risk"]], p["updated_at"]))


def pr_link(number: int) -> str:
    return f'<a href="#pr-{number}">#{number}</a>'


def render_start_here(highlights: dict | None, prs: list[dict]) -> str:
    if not highlights:
        return ""
    by_number = {p["number"]: p for p in prs}
    care = [h for h in highlights.get("review_with_care", []) if h.get("number") in by_number]
    quick = [n for n in highlights.get("quick_merges", []) if n in by_number]
    stale = [p["number"] for p in prs if p["age_days"] >= STALE_AFTER_DAYS]

    left = ""
    if care:
        items = "".join(f"<li>{pr_link(h['number'])} {html.escape(h.get('why', ''))}</li>" for h in care)
        left = f"<div><h3>Review with care</h3><ul>{items}</ul></div>"

    right_parts = []
    if quick:
        right_parts.append(
            "<h3>Quick merges</h3><p>Low risk, CI green, no open concerns: "
            + ", ".join(pr_link(n) for n in quick) + ".</p>"
        )
        if highlights.get("quick_merge_note"):
            right_parts.append(f"<p>{html.escape(highlights['quick_merge_note'])}</p>")
    if stale:
        note = highlights.get("stale_note") or "Decide to review or close."
        right_parts.append(
            f"<h3>Stale and unreviewed</h3><p>{len(stale)} PRs have been open {STALE_AFTER_DAYS} days or more: "
            + ", ".join(pr_link(n) for n in sorted(stale)) + f". {html.escape(note)}</p>"
        )
    right = f"<div>{''.join(right_parts)}</div>" if right_parts else ""
    if not left and not right:
        return ""
    return f'  <section class="start">\n    {left}\n    {right}\n  </section>'


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="owner/name, shown in the page header")
    ap.add_argument("--batches", required=True, help="directory containing batch*.json")
    ap.add_argument("--out", required=True, help="output HTML path")
    ap.add_argument("--highlights", help="optional highlights JSON (see module docstring)")
    ap.add_argument("--date", help="report date, YYYY-MM-DD (default: today)")
    ap.add_argument("--include-drafts", action="store_true", help="keep draft PRs and show the draft filters")
    args = ap.parse_args()

    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    prs = load_batches(args.batches)
    if not args.include_drafts:
        prs = [p for p in prs if not p["draft"]]
    if not prs:
        sys.exit("no pull requests left to render")
    enrich(prs, today)

    highlights = None
    if args.highlights:
        with open(args.highlights, encoding="utf-8") as fh:
            highlights = json.load(fh)

    counts = {k: sum(1 for p in prs if p["risk"] == k) for k in RISK_ORDER}
    failing = sum(1 for p in prs if p["ci"] == "failing")
    drafts = sum(1 for p in prs if p["draft"])
    stale = sum(1 for p in prs if p["age_days"] >= STALE_AFTER_DAYS)
    conflicts = sum(1 for p in prs if p.get("mergeable_state") == "dirty")
    unknown_mergeability = sum(1 for p in prs if p.get("mergeable_state") in (None, "", "unknown"))

    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "template.html")
    with open(template_path, encoding="utf-8") as fh:
        page = fh.read()

    draft_filters = ""
    draft_meta = ""
    draft_note = ""
    if args.include_drafts:
        draft_filters = (
            f'    <button data-quick="drafts" aria-pressed="false"><span class="n">{drafts}</span> drafts</button>\n'
            '    <button data-quick="ready" aria-pressed="false">ready for review only</button>\n'
        )
        draft_meta = f"<strong>{drafts}</strong> drafts &middot; "
        draft_note = " unless the report was built with --include-drafts"
    mergeability_note = (
        " GitHub had not computed mergeability for most branches at read time, so the merge-conflict count is a lower bound."
        if unknown_mergeability > len(prs) / 2 else ""
    )

    replacements = {
        "__TITLE__": f"{args.repo.split('/')[-1]} PR Triage",
        "__REPO__": html.escape(args.repo),
        "__DATE__": today.strftime("%-d %b %Y"),
        "__DATA__": json.dumps(prs, ensure_ascii=False).replace("</", "<\\/"),
        "__TOTAL__": str(len(prs)),
        "__CRIT__": str(counts["Critical"]),
        "__HIGH__": str(counts["High"]),
        "__MED__": str(counts["Medium"]),
        "__LOW__": str(counts["Low"]),
        "__FAILING__": str(failing),
        "__STALE__": str(stale),
        "__CONFLICTS__": str(conflicts),
        "__DRAFTS_META__": draft_meta,
        "__DRAFT_FILTERS__": draft_filters,
        "__DRAFT_NOTE__": draft_note,
        "__MERGEABILITY_NOTE__": mergeability_note,
        "__START_HERE__": render_start_here(highlights, prs),
    }
    for key, value in replacements.items():
        page = page.replace(key, value)

    leftover = [k for k in replacements if k in page]
    if leftover:
        sys.exit(f"unreplaced placeholders: {leftover}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)

    print(f"{len(prs)} PRs -> {args.out}")
    print("  " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"  failing CI {failing}, known conflicts {conflicts}, stale {stale}, drafts {drafts}")


if __name__ == "__main__":
    main()
