#!/usr/bin/env python3
"""Score /check and /check-iterate against fixture diffs with planted bugs.

Each fixture under evals/fixtures/<case>/ is a tiny repo: `base/` becomes
`main`, `head/` becomes the branch under review, and `case.json` says where the
planted bugs are and which probe scripts prove them. The runner builds a fresh
git repo per run, installs the `.claude/` directory from the ref being tested,
runs the skill headlessly with `claude -p`, and grades what comes back.

Comparing two refs is the point: `--ref main --ref WORKTREE` runs the same
fixtures against the skills as they are on main and as they are in this
checkout, so a change to a skill or agent is kept only if it scores no worse.

Run with:
  python3 evals/run.py --self-test                       # fixtures only, no model calls
  python3 evals/run.py --skill check --ref main --ref WORKTREE --reps 2
  python3 evals/run.py --skill check-iterate --cases off-by-one,clean-slugify
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "evals" / "fixtures"
WORKTREE = "WORKTREE"
# A finding counts as hitting a planted bug when it cites the bug's file within
# this many lines of the bug's line: reviewers cite the start of a function or
# the line after as often as the exact line.
LINE_SLACK = 3
CITATION_RE = re.compile(r"([A-Za-z0-9_./-]+\.py):(\d+)(?:\s*[-–]\s*(\d+))?((?:,\s*\d+)*)")
# Plans cite as `[users.py](users.py):12` or as `[`users.py:12`](../../users.py)`:
# the line sits after the link in one and inside its text in the other, so a
# link is rewritten to `text target` and both forms parse like a bare citation.
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
# The child sees only the fixture repo's own `.claude/`: these would otherwise
# leak this session's linked directories, and with them a second copy of every
# skill under test.
SCRUBBED_ENV = (
    "CLAUDECODE",
    "CLAUDE_ADDITIONAL_DIRECTORIES",
    "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD",
)
# Plain `Bash`, not `Bash(git:*)`: the skills chain git commands with `||` and
# `$(...)`, which a prefix rule does not match, and a denied command makes the
# skill stop with nothing reviewed. Each run gets a throwaway repo to act in.
# Writes into `.claude/` stay denied in this mode whatever the allow rules say,
# so a /check that writes its plan with Write rather than Bash is graded from
# its reply instead (see grade_check).
ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Agent", "Write", "Edit", "Skill", "Bash"]
PROMPTS = {
    # --auto: there is nobody to answer AskUserQuestion in a headless run.
    "check": "/check --auto",
    "check-iterate": "/check-iterate --max-loops {max_loops}",
}


def git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=eval", "-c", "user.email=eval@example.com", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


def load_case(name: str) -> dict:
    case = json.loads((FIXTURES / name / "case.json").read_text())
    case["name"] = name
    head = FIXTURES / name / "head"
    for bug in case["bugs"]:
        for loc in bug["locations"]:
            lines = (head / loc["file"]).read_text().splitlines()
            hits = [i + 1 for i, line in enumerate(lines) if loc["contains"] in line]
            if len(hits) != 1:
                raise SystemExit(f"{name}: '{loc['contains']}' matches {len(hits)} lines of {loc['file']}, need exactly 1")
            loc["line"] = hits[0]
    return case


def copy_tree(src: pathlib.Path, dest: pathlib.Path) -> None:
    for path in src.rglob("*"):
        if path.is_file():
            target = dest / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def extract_claude_dir(ref: str, dest: pathlib.Path) -> pathlib.Path:
    """Materialise the `.claude/` directory a ref carries, once per ref."""
    target = dest / re.sub(r"[^A-Za-z0-9._-]", "_", ref)
    if target.exists():
        return target
    target.mkdir(parents=True)
    if ref == WORKTREE:
        shutil.copytree(ROOT / ".claude", target / ".claude",
                        ignore=shutil.ignore_patterns("plans", "settings.local.json"))
    else:
        archive = subprocess.run(["git", "archive", ref, ".claude"], cwd=ROOT,
                                 check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", str(target)], input=archive, check=True)
    return target


def build_repo(case: dict, dest: pathlib.Path, claude_dir: pathlib.Path | None) -> pathlib.Path:
    """`main` holds base plus the skills, so `.claude/` never shows in the diff under review."""
    repo = dest / case["name"]
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    copy_tree(FIXTURES / case["name"] / "base", repo)
    if claude_dir is not None:
        shutil.copytree(claude_dir / ".claude", repo / ".claude")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "feature")
    for path in repo.iterdir():
        if path.name not in (".git", ".claude"):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    copy_tree(FIXTURES / case["name"] / "head", repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feature")
    return repo


def run_probe(case: dict, probe: str, repo: pathlib.Path) -> bool:
    script = FIXTURES / case["name"] / probe
    result = subprocess.run([sys.executable, str(script)], cwd=repo, capture_output=True, timeout=120)
    return result.returncode == 0


def run_tests(repo: pathlib.Path) -> bool:
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
                            cwd=repo, capture_output=True, timeout=300)
    return result.returncode == 0


def self_test(cases: list[dict]) -> int:
    """Every fixture must be a fair test before any model is asked to pass it."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases:
            repo = build_repo(case, pathlib.Path(tmp), None)
            if not run_tests(repo):
                failures.append(f"{case['name']}: head's own tests fail")
            for bug in case["bugs"]:
                if run_probe(case, bug["probe"], repo):
                    failures.append(f"{case['name']}: probe {bug['probe']} passes on head, so it cannot detect the bug")
            for guard in case["guards"]:
                if not run_probe(case, guard, repo):
                    failures.append(f"{case['name']}: guard {guard} fails on head")
            git(repo, "checkout", "-q", "main")
            if not run_tests(repo):
                failures.append(f"{case['name']}: base's own tests fail")
            print(f"{case['name']}: {len(case['bugs'])} bugs, {len(case['guards'])} guards")
    for failure in failures:
        print(f"error: {failure}", file=sys.stderr)
    return 1 if failures else 0


def parse_findings(plan_text: str) -> list[list[tuple[str, int, int]]]:
    """One entry per finding bullet in the plan body, holding every file:line it cites.

    The plan's frontmatter todos restate the body, and its Notes section is
    coverage gaps rather than findings, so only body bullets outside Notes count.
    """
    body = plan_text.split("\n---", 2)[-1] if plan_text.startswith("---") else plan_text
    findings, section = [], ""
    for line in body.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section.startswith("notes") or not line.lstrip().startswith("- "):
            continue
        cites = []
        for m in CITATION_RE.finditer(LINK_RE.sub(r"\1 \2", line)):
            path = re.sub(r"^(\.\.?/)+", "", m.group(1))
            cites.append((path, int(m.group(2)), int(m.group(3) or m.group(2))))
            # `durations.py:6,12` cites two lines.
            cites += [(path, int(n), int(n)) for n in re.findall(r"\d+", m.group(4))]
        if cites:
            findings.append(cites)
    return findings


def grade_check(case: dict, run_dir: pathlib.Path) -> dict:
    """Grade a /check run from the plan it wrote, or from its final reply when it wrote none.

    A clean review writes no plan by design and says so in its reply; a run
    whose plan write was denied still reported its findings there. Scoring
    either as zero would be wrong, so both are graded from the reply, and the
    denial still marks the run in the summary.
    """
    plan_text = (run_dir / "plan.md").read_text()
    source = "plan"
    if not plan_text.strip():
        plan_text, source = (run_dir / "result.txt").read_text(), "reply"
    findings = parse_findings(plan_text)
    found = [bug["id"] for bug in case["bugs"]
             if any(hits(f, loc) for f in findings for loc in bug["locations"])]
    unmatched = [f for f in findings
                 if not any(hits(f, loc) for bug in case["bugs"] for loc in bug["locations"])]
    return {"findings": len(findings), "found": found, "unmatched": len(unmatched), "graded_from": source}


def hits(cites: list[tuple[str, int, int]], loc: dict) -> bool:
    """Whether a finding cites the bug's file near the bug's line.

    Line proximity is all it checks, so a different finding whose cited range
    covers the bug line also counts: `unmatched` undercounts extra findings.
    """
    return any((path == loc["file"] or path.endswith("/" + loc["file"]))
               and start - LINE_SLACK <= loc["line"] <= end + LINE_SLACK
               for path, start, end in cites)


def read_transcript(path: pathlib.Path) -> tuple[dict, int]:
    """The run's result, and how many subagents the top-level loop spawned.

    A run whose subagents went to the background resumes when each one lands,
    and every resumed turn ends in its own result event. Cost is cumulative
    across them, but duration and turns are per event, so those are summed.
    """
    result, spawns, duration_ms, turns = {}, 0, 0, 0
    for raw in path.read_text().splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            result = event
            duration_ms += event.get("duration_ms") or 0
            turns += event.get("num_turns") or 0
        elif event.get("type") == "assistant" and not event.get("parent_tool_use_id"):
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and block.get("name") in ("Agent", "Task"):
                    spawns += 1
    if result:
        result = {**result, "duration_ms": duration_ms, "num_turns": turns}
    return result, spawns


def run_one(case: dict, ref: str, rep: int, args, claude_dirs: dict, out: pathlib.Path) -> dict:
    run_dir = out / "runs" / f"{case['name']}--{re.sub(r'[^A-Za-z0-9._-]', '_', ref)}--{rep}"
    run_dir.mkdir(parents=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="eval-", dir=out / "work"))
    repo = build_repo(case, work, claude_dirs[ref])
    env = {k: v for k, v in os.environ.items() if k not in SCRUBBED_ENV}
    cmd = [
        "claude", "-p", PROMPTS[args.skill].format(max_loops=args.max_loops),
        "--output-format", "stream-json", "--verbose",
        "--setting-sources", "project",
        "--permission-mode", "dontAsk",
        "--allowedTools", *ALLOWED_TOOLS,
        "--max-budget-usd", str(args.budget_usd),
    ]
    if args.model:
        cmd += ["--model", args.model]
    transcript = run_dir / "transcript.jsonl"
    timed_out = False
    with transcript.open("w") as fh:
        try:
            subprocess.run(cmd, cwd=repo, env=env, stdout=fh, stderr=subprocess.STDOUT,
                           timeout=args.timeout_min * 60)
        except subprocess.TimeoutExpired:
            timed_out = True
    result, spawns = read_transcript(transcript)
    (run_dir / "result.txt").write_text(str(result.get("result", "")))

    record = {
        "case": case["name"], "ref": ref, "rep": rep, "timed_out": timed_out,
        "clean_case": not case["bugs"],
        "cost_usd": result.get("total_cost_usd"), "duration_s": (result.get("duration_ms") or 0) / 1000,
        "turns": result.get("num_turns"), "subagents": spawns,
        "error": result.get("subtype") not in ("success", None) and result.get("subtype"),
        # A denied call usually means the skill gave up rather than reviewed, so
        # a run with denials is flagged rather than scored as a quiet miss.
        "denials": len(result.get("permission_denials") or []),
    }
    if args.skill == "check":
        plans = sorted((repo / ".claude" / "plans").glob("*.plan.md"))
        (run_dir / "plan.md").write_text("\n".join(p.read_text() for p in plans))
        record.update(grade_check(case, run_dir))
    else:
        record.update(
            fixed=[bug["id"] for bug in case["bugs"] if run_probe(case, bug["probe"], repo)],
            guards_broken=[g for g in case["guards"] if not run_probe(case, g, repo)],
            tests_pass=run_tests(repo),
            staged=git(repo, "diff", "--cached", "--name-only").split(),
        )
    (run_dir / "record.json").write_text(json.dumps(record, indent=2))
    if not args.keep_repos:
        shutil.rmtree(work, ignore_errors=True)
    print(f"  {case['name']} @ {ref} #{rep}: " + json.dumps(
        {k: record[k] for k in record if k in ("found", "unmatched", "fixed", "guards_broken", "cost_usd", "subagents")}),
        flush=True)
    return record


def mean(values) -> str:
    values = [v for v in values if v is not None]
    return f"{statistics.mean(values):.2f}" if values else "—"


def summarize(records: list[dict], cases: list[dict], refs: list[str], skill: str, reps: int) -> str:
    lines = [f"# {skill} eval — {len(cases)} cases × {reps} reps", ""]
    total_bugs = sum(len(c["bugs"]) for c in cases)
    if skill == "check":
        lines += ["| ref | bugs found | findings / bug case | unmatched / bug case | findings / clean case | subagents | cost $ | time s |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    else:
        lines += ["| ref | bugs fixed | guards broken | suites red | subagents | cost $ | time s |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
    for ref in refs:
        rs = [r for r in records if r["ref"] == ref]
        if skill == "check":
            found = sum(len(r["found"]) for r in rs)
            lines.append(
                f"| `{ref}` | {found}/{total_bugs * reps} "
                f"| {mean(r['findings'] for r in rs if not r['clean_case'])} "
                f"| {mean(r['unmatched'] for r in rs if not r['clean_case'])} "
                f"| {mean(r['findings'] for r in rs if r['clean_case'])} "
                f"| {mean(r['subagents'] for r in rs)} | {mean(r['cost_usd'] for r in rs)} "
                f"| {mean(r['duration_s'] for r in rs)} |")
        else:
            lines.append(
                f"| `{ref}` | {sum(len(r['fixed']) for r in rs)}/{total_bugs * reps} "
                f"| {sum(len(r['guards_broken']) for r in rs)} | {sum(not r['tests_pass'] for r in rs)} "
                f"| {mean(r['subagents'] for r in rs)} | {mean(r['cost_usd'] for r in rs)} "
                f"| {mean(r['duration_s'] for r in rs)} |")
    # Aggregates hide regressions that cancel out, so show every case per ref.
    key = "found" if skill == "check" else "fixed"
    lines += ["", "## Per case", "", "| case | " + " | ".join(f"`{r}`" for r in refs) + " |",
              "| --- |" + " --- |" * len(refs)]
    for case in cases:
        cells = []
        for ref in refs:
            rs = [r for r in records if r["ref"] == ref and r["case"] == case["name"]]
            if case["bugs"]:
                cell = f"{sum(len(r[key]) for r in rs)}/{len(case['bugs']) * len(rs)} {key}"
            else:
                cell = (f"{mean(r['findings'] for r in rs)} findings" if skill == "check"
                        else f"{sum(len(r['guards_broken']) for r in rs)} guards broken")
            if any(r["timed_out"] or r["error"] or r["denials"] or not r["cost_usd"] for r in rs):
                cell += " ⚠"
            cells.append(cell)
        lines.append(f"| {case['name']} | " + " | ".join(cells) + " |")
    lines += ["", "⚠ = a run timed out, errored, hit a permission denial, or reported no cost; read its transcript under `runs/`."]
    return "\n".join(lines) + "\n"


def regrade(out: pathlib.Path) -> int:
    """Re-score saved runs from their transcripts and plans, so a grader fix costs no re-run.

    /check-iterate's fix verdicts come from probing a repo that no longer
    exists, so for it only the transcript metrics are recomputed.
    """
    records = json.loads((out / "results.json").read_text())
    skill = "check-iterate" if any("fixed" in r for r in records) else "check"
    cases = {name: load_case(name) for name in sorted({r["case"] for r in records})}
    for r in records:
        run_dir = out / "runs" / f"{r['case']}--{re.sub(r'[^A-Za-z0-9._-]', '_', r['ref'])}--{r['rep']}"
        result, spawns = read_transcript(run_dir / "transcript.jsonl")
        r.update(cost_usd=result.get("total_cost_usd"), duration_s=(result.get("duration_ms") or 0) / 1000,
                 turns=result.get("num_turns"), subagents=spawns,
                 denials=len(result.get("permission_denials") or []))
        if skill == "check":
            r.update(grade_check(cases[r["case"]], run_dir))
        (run_dir / "record.json").write_text(json.dumps(r, indent=2))
    (out / "results.json").write_text(json.dumps(records, indent=2))
    refs = list(dict.fromkeys(r["ref"] for r in records))
    reps = max(r["rep"] for r in records)
    summary = summarize(records, list(cases.values()), refs, skill, reps)
    (out / "summary.md").write_text(summary)
    print(summary)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skill", choices=sorted(PROMPTS), default="check")
    parser.add_argument("--ref", action="append", help=f"git ref whose .claude/ to test, or {WORKTREE} (repeatable)")
    parser.add_argument("--cases", help="comma-separated fixture names (default: all)")
    parser.add_argument("--reps", type=int, default=2, help="runs per case per ref (default 2)")
    parser.add_argument("--jobs", type=int, default=4, help="runs in parallel (default 4)")
    parser.add_argument("--model", help="main-loop model (default: Claude Code's default)")
    parser.add_argument("--max-loops", type=int, default=3, help="check-iterate loop cap (default 3)")
    parser.add_argument("--budget-usd", type=float, default=5.0, help="per-run spend ceiling (default 5)")
    parser.add_argument("--timeout-min", type=int, default=30, help="per-run wall clock ceiling (default 30)")
    parser.add_argument("--out", type=pathlib.Path, help="results directory (default evals/results/<timestamp>)")
    parser.add_argument("--keep-repos", action="store_true", help="keep each run's fixture repo for inspection")
    parser.add_argument("--self-test", action="store_true", help="check the fixtures themselves; no model calls")
    parser.add_argument("--regrade", type=pathlib.Path, metavar="RESULTS_DIR",
                        help="re-grade a finished run from its saved transcripts and plans; no model calls")
    args = parser.parse_args()
    if args.regrade:
        return regrade(args.regrade)

    names = args.cases.split(",") if args.cases else sorted(p.name for p in FIXTURES.iterdir() if p.is_dir())
    cases = [load_case(name) for name in names]
    if args.self_test:
        return self_test(cases)

    refs = args.ref or [WORKTREE]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or ROOT / "evals" / "results" / f"{args.skill}-{stamp}"
    (out / "work").mkdir(parents=True, exist_ok=True)
    claude_dirs = {ref: extract_claude_dir(ref, out / "refs") for ref in refs}
    jobs = [(case, ref, rep) for rep in range(1, args.reps + 1) for case in cases for ref in refs]
    print(f"{len(jobs)} runs → {out}", flush=True)

    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_one, case, ref, rep, args, claude_dirs, out) for case, ref, rep in jobs]
        for future in concurrent.futures.as_completed(futures):
            records.append(future.result())
    records.sort(key=lambda r: (r["case"], r["ref"], r["rep"]))
    (out / "results.json").write_text(json.dumps(records, indent=2))
    summary = summarize(records, cases, refs, args.skill, args.reps)
    (out / "summary.md").write_text(summary)
    shutil.rmtree(out / "work", ignore_errors=True)
    print("\n" + summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
