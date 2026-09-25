#!/usr/bin/env python3
"""Build the QA report page from a pass's results.json.

Validates the file against the schema in references/report-schema.md, derives
the counts and the verdict label, copies the referenced screenshots next to the
output so the page works both published and opened from disk, and renders
assets/template.html into one self-contained HTML file.

Usage:
  build.py --results FILE --out FILE [--shots DIR] [--date YYYY-MM-DD]

Exits non-zero on a malformed result, a missing screenshot, or a placeholder
left unfilled, so a clean run means the page is complete.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
from urllib.parse import urlparse

CHECK_STATUSES = ["pass", "fail", "partial", "blocked", "skipped"]
SEVERITIES = ["critical", "major", "minor", "nit"]
FINDING_STATUSES = {"confirmed", "flaky", "pre-existing"}
CHECK_TYPES = {"specified", "exploratory"}
DRIVERS = {"claude-in-chrome", "browser-mcp", "playwright-local"}
DEPTHS = {"smoke", "standard", "deep"}
ENVS = {"local", "preview", "staging", "production", "other"}
EVIDENCE_KINDS = {"screenshot", "console", "network", "note"}

CHECK_KEYS = {"id", "title", "area", "type", "status", "steps", "expected", "actual"}
FINDING_KEYS = {"id", "title", "severity", "area", "status", "repro", "expected", "actual", "impact"}
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(png|jpg|jpeg|webp|gif)$")

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "template.html")


def fail(message: str) -> None:
    sys.exit(f"results.json: {message}")


def require(obj: dict, keys: set[str], where: str) -> None:
    missing = sorted(keys - set(obj))
    if missing:
        fail(f"{where} is missing {missing}")


def validate(data: dict, shots_dir: str | None) -> None:
    """Reject anything the template would interpolate outside escaped text.

    The file is written by a model after a browser session, so every value the
    page uses as a class name, an href, or an image path is checked against a
    closed set here rather than trusted.
    """
    require(data, {"title", "date", "driver", "depth", "target", "scope", "verdict_note", "checks", "findings"}, "top level")
    if data["driver"] not in DRIVERS:
        fail(f"driver {data['driver']!r} is not one of {sorted(DRIVERS)}")
    if data["depth"] not in DEPTHS:
        fail(f"depth {data['depth']!r} is not one of {sorted(DEPTHS)}")
    try:
        dt.date.fromisoformat(data["date"])
    except (TypeError, ValueError):
        fail(f"date {data['date']!r} is not YYYY-MM-DD")

    target = data["target"]
    require(target, {"url", "env", "build"}, "target")
    if target["env"] not in ENVS:
        fail(f"target.env {target['env']!r} is not one of {sorted(ENVS)}")
    scheme = urlparse(target["url"]).scheme
    if scheme not in {"http", "https"}:
        fail(f"target.url must be http(s), got {target['url']!r}")
    if not str(target["build"]).strip() or str(target["build"]).strip().lower() == "latest":
        fail("target.build must identify the build under test (a commit, version, or deploy), not 'latest'")

    if not data["checks"]:
        fail("no checks; a pass with nothing in it is not a report")
    if not str(data["verdict_note"]).strip():
        fail("verdict_note is empty; the label is derived but the sentence is yours to write")

    check_ids: set[str] = set()
    for check in data["checks"]:
        require(check, CHECK_KEYS, f"check {check.get('id')!r}")
        where = f"check {check['id']!r}"
        if check["id"] in check_ids:
            fail(f"duplicate check id {check['id']!r}")
        check_ids.add(check["id"])
        if check["status"] not in CHECK_STATUSES:
            fail(f"{where} has unknown status {check['status']!r}")
        if check["type"] not in CHECK_TYPES:
            fail(f"{where} has unknown type {check['type']!r}")
        if not isinstance(check["steps"], list) or not check["steps"]:
            fail(f"{where} has no steps")
        if not str(check["actual"]).strip():
            fail(f"{where} has an empty 'actual'; a blocked or skipped check still says why")
        validate_evidence(check.get("evidence", []), where, shots_dir)

    finding_ids: set[str] = set()
    for finding in data["findings"]:
        require(finding, FINDING_KEYS, f"finding {finding.get('id')!r}")
        where = f"finding {finding['id']!r}"
        if finding["id"] in finding_ids:
            fail(f"duplicate finding id {finding['id']!r}")
        finding_ids.add(finding["id"])
        if finding["severity"] not in SEVERITIES:
            fail(f"{where} has unknown severity {finding['severity']!r}")
        if finding["status"] not in FINDING_STATUSES:
            fail(f"{where} has unknown status {finding['status']!r}")
        if not isinstance(finding["repro"], list) or not finding["repro"]:
            fail(f"{where} has no repro steps; an unreproduced failure is not a finding")
        validate_evidence(finding.get("evidence", []), where, shots_dir)
        for check_id in finding.get("checks", []):
            if check_id not in check_ids:
                fail(f"{where} references unknown check {check_id!r}")

    for check in data["checks"]:
        for finding_id in check.get("findings", []):
            if finding_id not in finding_ids:
                fail(f"check {check['id']!r} references unknown finding {finding_id!r}")
        if check["status"] == "fail" and not check.get("findings"):
            fail(f"check {check['id']!r} failed but names no finding; every failure is either a finding or not a failure")


def validate_evidence(items: list, where: str, shots_dir: str | None) -> None:
    for item in items:
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            fail(f"{where} has evidence of unknown kind {kind!r}")
        if kind != "screenshot":
            if not str(item.get("text", "")).strip():
                fail(f"{where} has {kind} evidence with no text")
            continue
        path = item.get("path", "")
        if not SAFE_FILENAME.match(path):
            fail(f"{where} screenshot path {path!r} must be a bare image filename inside the shots directory")
        if shots_dir is None:
            fail(f"{where} references a screenshot but --shots was not given")
        if not os.path.isfile(os.path.join(shots_dir, path)):
            fail(f"{where} references missing screenshot {path!r} in {shots_dir}")


def copy_shots(data: dict, shots_dir: str | None, out_path: str) -> None:
    """Place every referenced screenshot at shots/<name> beside the page.

    The same relative path then works whether the page is published as an
    artifact with its files or opened straight from disk.
    """
    names = {
        item["path"]
        for group in (data["checks"], data["findings"])
        for entry in group
        for item in entry.get("evidence", [])
        if item["kind"] == "screenshot"
    }
    if not names:
        return
    target_dir = os.path.join(os.path.dirname(os.path.abspath(out_path)), "shots")
    os.makedirs(target_dir, exist_ok=True)
    for name in sorted(names):
        source = os.path.join(shots_dir, name)
        destination = os.path.join(target_dir, name)
        if os.path.abspath(source) != os.path.abspath(destination):
            shutil.copyfile(source, destination)


def derive(data: dict) -> dict:
    checks = data["checks"]
    findings = data["findings"]
    counts = {status: sum(1 for c in checks if c["status"] == status) for status in CHECK_STATUSES}
    severities = {level: sum(1 for f in findings if f["severity"] == level) for level in SEVERITIES}
    live = [f for f in findings if f["status"] != "pre-existing"]
    ran = counts["pass"] + counts["fail"] + counts["partial"]

    if any(f["severity"] == "critical" for f in live):
        label, css = "Ship blocked", "crit"
    elif any(f["severity"] == "major" for f in live):
        label, css = "Fix before release", "major"
    elif findings:
        label, css = "Ready with caveats", "minor"
    elif counts["blocked"] or counts["skipped"]:
        label, css = "Clean, with gaps", "gaps"
    else:
        label, css = "Clean", "clean"

    return {
        "counts": counts,
        "severities": severities,
        "total": len(checks),
        "ran": ran,
        "pass_rate": f"{round(100 * counts['pass'] / ran)}%" if ran else "n/a",
        "findings_total": len(findings),
        "label": label,
        "css": css,
    }


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def bullet_list(items: list, empty: str = "") -> str:
    if not items:
        return empty
    return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"


def render_fix_first(data: dict) -> str:
    """The section a reader acts on: everything ship-blocking, in severity order."""
    order = {level: i for i, level in enumerate(SEVERITIES)}
    urgent = sorted(
        (f for f in data["findings"] if f["severity"] in {"critical", "major"}),
        key=lambda f: (order[f["severity"]], f["id"]),
    )
    if not urgent:
        blocked = [c for c in data["checks"] if c["status"] == "blocked"]
        if not blocked:
            return '<div class="fix-first none"><h2>Nothing to fix first</h2><p>No critical or major findings, and every check ran.</p></div>'
        items = "".join(f"<li><b>{esc(c['id'])}</b> {esc(c['title'])} — {esc(c['actual'])}</li>" for c in blocked)
        return f'<div class="fix-first none"><h2>Nothing to fix first</h2><p>No critical or major findings. These checks could not run:</p><ul>{items}</ul></div>'

    rows = "".join(
        f'<li class="sev-{esc(f["severity"])}">'
        f'<a href="#{esc(f["id"])}"><b>{esc(f["id"])}</b> {esc(f["title"])}</a>'
        f'<span class="sev">{esc(f["severity"])}</span>'
        f'<span class="why">{esc(f["impact"])}</span></li>'
        for f in urgent
    )
    return f'<div class="fix-first"><h2>Fix first</h2><ul>{rows}</ul></div>'


def render_panel(title: str, items: list, empty: str) -> str:
    body = bullet_list(items) if items else f"<p class='muted'>{esc(empty)}</p>"
    return f"<section class='panel'><h3>{esc(title)}</h3>{body}</section>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--shots", help="directory holding the screenshots named in the evidence")
    parser.add_argument("--date", help="override the report date (default: the date in results.json)")
    args = parser.parse_args()

    with open(args.results, encoding="utf-8") as handle:
        data = json.load(handle)

    shots_dir = args.shots if args.shots and os.path.isdir(args.shots) else None
    if args.shots and shots_dir is None:
        sys.exit(f"--shots {args.shots} is not a directory")

    validate(data, shots_dir)
    copy_shots(data, shots_dir, args.out)
    derived = derive(data)

    target = data["target"]
    scope = data["scope"]
    baseline = data.get("baseline") or {}
    baseline_items = list(baseline.get("console", []))
    if baseline.get("notes"):
        baseline_items.append(baseline["notes"])

    with open(TEMPLATE, encoding="utf-8") as handle:
        page = handle.read()

    payload = json.dumps(
        {"checks": data["checks"], "findings": data["findings"]},
        ensure_ascii=False,
    ).replace("</", "<\\/")

    substitutions = {
        "__TITLE__": esc(f"{data['title']} QA"),
        "__HEADING__": esc(data["title"]),
        "__DATE__": esc(args.date or data["date"]),
        "__TARGET_URL__": esc(target["url"]),
        "__ENV__": esc(target["env"]),
        "__BUILD__": esc(target["build"]),
        "__BROWSER__": esc(target.get("browser", "unspecified")),
        "__VIEWPORT__": esc(target.get("viewport", "unspecified")),
        "__DRIVER__": esc(data["driver"]),
        "__DEPTH__": esc(data["depth"]),
        "__VERDICT_CLASS__": derived["css"],
        "__VERDICT_LABEL__": esc(derived["label"]),
        "__VERDICT_NOTE__": esc(data["verdict_note"]),
        "__TOTAL__": str(derived["total"]),
        "__PASS_RATE__": esc(derived["pass_rate"]),
        "__FINDINGS_TOTAL__": str(derived["findings_total"]),
        "__ASKED__": esc(scope.get("asked", "")),
        "__IN_SCOPE__": bullet_list(scope.get("in_scope", []), "<p class='muted'>Not recorded.</p>"),
        "__FIX_FIRST__": render_fix_first(data),
        "__BASELINE__": render_panel("Baseline noise", baseline_items, "No baseline recorded."),
        "__GAPS__": render_panel("Not covered", list(scope.get("out_of_scope", [])) + list(data.get("coverage_gaps", [])), "Nothing recorded as out of scope — read that as a gap in itself."),
        "__NOTES__": render_panel("Notes", data.get("notes", []), "None."),
        "__DATA__": payload,
    }
    for status in CHECK_STATUSES:
        substitutions[f"__N_{status.upper()}__"] = str(derived["counts"][status])
    for level in SEVERITIES:
        substitutions[f"__N_{level.upper()}__"] = str(derived["severities"][level])

    for placeholder, value in substitutions.items():
        page = page.replace(placeholder, value)

    leftover = sorted(set(re.findall(r"__[A-Z_]{3,}__", page)))
    if leftover:
        sys.exit(f"template placeholders left unfilled: {leftover}")

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write(page)

    print(
        f"{args.out}: {derived['total']} checks "
        f"({derived['counts']['pass']} pass, {derived['counts']['fail']} fail, "
        f"{derived['counts']['blocked']} blocked), {derived['findings_total']} findings, "
        f"verdict {derived['label']}"
    )


if __name__ == "__main__":
    main()
