#!/usr/bin/env python3
"""Turn plan files into GitHub issues, and record the issue numbers back.

A plan file (`.claude/plans/<slug>.plan.md`, the `plan` skill's staged schema)
becomes one parent issue, and each open stage in it one sub-issue. This script
does the parts that must not vary between runs: it validates the plans, renders
every issue's title, body and labels, and writes the numbers the agent got back
into the frontmatter. It never talks to GitHub itself. The agent running the
`plan-issues` skill does that with its GitHub tools, because a cloud session
has no token a script could use.

    plan-issues.py check  [plans...]
    plan-issues.py render --repo owner/repo [--ref main] [plans...]
    plan-issues.py record <plan> [--parent N] [--stage <id>=N ...]

With no plans named, every `.claude/plans/*.plan.md` under the current
directory that opts in is read: it carries `stages` and a `priority` or an
`issue`. A plan a single `/feature` run wrote for itself carries neither, and
is not filed.

`render` prints one JSON object: `{"plans": [...]}`, ordered by `priority`
(lower first, then file name). Each plan has `file`, `issue`, `labels`,
`priority`, `title`, `body` and `stages`; each stage has `id`, `issue`,
`related`, `labels`, `title` and `body`. Stages whose status is `completed` or
`cancelled` and that have no issue are left out: a plan's history is not
re-filed as closed issues.

`record` edits the frontmatter as text, inserting or replacing one
`issue: N` line, so the rest of the file -- comments, quoting, wrapping --
stays byte for byte as it was.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import posixpath
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the machine
    sys.exit("plan-issues: PyYAML is required (pip install pyyaml)")

PLANS_DIR = pathlib.Path(".claude/plans")
STAGE_LABELS = {"ready", "needs-decision", "deferred"}
PLAN_LABELS = {"ready", "needs-decision", "deferred"}
# Every parent issue carries this, so a lead can list the plans without
# reading every issue in the repo.
PARENT_LABEL = "plan"
DONE = {"completed", "cancelled"}
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# A relative Markdown link target, rewritten to an absolute blob URL in an
# issue body, where relative paths would resolve against the issue's URL.
REL_LINK_RE = re.compile(r"\]\((?!https?:|#|mailto:)([^)\s]+)\)")


class PlanError(Exception):
    pass


def split(path: pathlib.Path) -> tuple[str, str]:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise PlanError(f"{path}: no frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise PlanError(f"{path}: unterminated frontmatter")
    return text[4 : end + 1], text[end + 5 :]


def load(path: pathlib.Path) -> tuple[dict, str]:
    head, body = split(path)
    try:
        data = yaml.safe_load(head)
    except yaml.YAMLError as err:
        raise PlanError(f"{path}: frontmatter is not YAML: {err}") from err
    if not isinstance(data, dict):
        raise PlanError(f"{path}: frontmatter is not a mapping")
    return data, body


def ints(value: object, where: str) -> list[int]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        raise PlanError(f"{where}: must be a list of issue numbers")
    return value


def labels(value: object, allowed: set[str], where: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise PlanError(f"{where}: labels must be a list of strings")
    unknown = [v for v in value if v not in allowed]
    if unknown:
        raise PlanError(f"{where}: unknown label(s) {unknown}; allowed: {sorted(allowed)}")
    return value


def issue_no(value: object, where: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PlanError(f"{where}: issue must be a positive issue number")
    return value


def check(path: pathlib.Path) -> dict:
    """Validate one plan and return it normalised; raise PlanError on any gap."""
    data, body = load(path)
    for key in ("name", "overview", "stages"):
        if not data.get(key):
            raise PlanError(f"{path}: missing `{key}`")
    if not isinstance(data["stages"], list):
        raise PlanError(f"{path}: `stages` must be a list")
    seen: set[str] = set()
    numbers: dict[int, str] = {}
    parent = issue_no(data.get("issue"), f"{path}: issue")
    if parent:
        numbers[parent] = "the plan"
    plan = {
        "file": path.as_posix(),
        "name": str(data["name"]),
        "overview": str(data["overview"]),
        "roadmap": data.get("roadmap"),
        "spec": data.get("spec"),
        "priority": data.get("priority", 100),
        "issue": parent,
        "labels": labels(data.get("labels"), PLAN_LABELS, f"{path}: labels"),
        "body": body,
        "stages": [],
    }
    if not isinstance(plan["priority"], int):
        raise PlanError(f"{path}: priority must be an integer")
    for ref in ("roadmap", "spec"):
        if plan[ref] and not pathlib.Path(plan[ref]).exists():
            raise PlanError(f"{path}: {ref} `{plan[ref]}` does not exist")
    for i, stage in enumerate(data["stages"]):
        where = f"{path}: stage {stage.get('id', i)}"
        for key in ("id", "title", "goal", "verification", "todos"):
            if not stage.get(key):
                raise PlanError(f"{where}: missing `{key}`")
        for sid in [stage["id"], *(t.get("id") for t in stage["todos"])]:
            if not isinstance(sid, str) or not ID_RE.match(sid):
                raise PlanError(f"{where}: id `{sid}` is not kebab-case")
            if sid in seen:
                raise PlanError(f"{where}: id `{sid}` is used twice")
            seen.add(sid)
        number = issue_no(stage.get("issue"), f"{where}: issue")
        related = ints(stage.get("related"), f"{where}: related")
        for n in [number, *related]:
            if n is None:
                continue
            if n in numbers:
                raise PlanError(f"{where}: issue {n} is already used by {numbers[n]}")
            numbers[n] = f"stage {stage['id']}"
        plan["stages"].append(
            {
                "id": stage["id"],
                "title": str(stage["title"]),
                "goal": str(stage["goal"]),
                "verification": str(stage["verification"]),
                "status": stage.get("status", "pending"),
                "issue": number,
                "related": related,
                "labels": labels(stage.get("labels"), STAGE_LABELS, f"{where}: labels"),
                "todos": [str(t.get("content", "")) for t in stage["todos"]],
            }
        )
    return plan


def section(body: str, title: str) -> str:
    """The text under the `## <title>` heading, up to the next `## ` heading."""
    lines = body.splitlines()
    out: list[str] | None = None
    for line in lines:
        if line.startswith("## "):
            if out is not None:
                break
            if line[3:].strip() == title.strip():
                out = []
                continue
        elif out is not None:
            out.append(line)
    return "\n".join(out or []).strip()


def absolute(text: str, plan_file: str, repo: str, ref: str) -> str:
    base = posixpath.dirname(plan_file)

    def fix(match: re.Match[str]) -> str:
        target = match.group(1)
        path, _, anchor = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(base, path))
        url = f"https://github.com/{repo}/blob/{ref}/{resolved}"
        return f"]({url}{'#' + anchor if anchor else ''})"

    return REL_LINK_RE.sub(fix, text)


def render(plan: dict, repo: str, ref: str) -> dict:
    blob = f"https://github.com/{repo}/blob/{ref}"
    links = [f"Plan: [`{plan['file']}`]({blob}/{plan['file']})"]
    if plan["roadmap"]:
        links.append(f"Roadmap page: [`{plan['roadmap']}`]({blob}/{plan['roadmap']})")
    if plan["spec"]:
        links.append(f"Design note: [`{plan['spec']}`]({blob}/{plan['spec']})")
    context = absolute(section(plan["body"], "Context"), plan["file"], repo, ref)
    parent_body = "\n\n".join(
        part
        for part in [
            f"<!-- plan: {plan['file']} -->",
            plan["overview"],
            " · ".join(links),
            context,
            "Each stage is a sub-issue below, one pull request each, in merge order. "
            "The plan file holds the spec; these issues hold the state. "
            "A stage labelled `needs-decision` waits on the owner; `deferred` is wanted but not scheduled.",
        ]
        if part
    )
    stages = []
    for stage in plan["stages"]:
        if stage["status"] in DONE and stage["issue"] is None:
            continue
        detail = absolute(section(plan["body"], stage["title"]), plan["file"], repo, ref)
        todos = "\n".join(f"- {t}" for t in stage["todos"])
        related = ", ".join(f"#{n}" for n in stage["related"])
        body = "\n\n".join(
            part
            for part in [
                f"<!-- plan-stage: {plan['file']}#{stage['id']} -->",
                f"**Goal:** {stage['goal']}",
                f"**Verification:** `{stage['verification']}`",
                f"**Plan:** [`{plan['file']}`]({blob}/{plan['file']}), stage `{stage['id']}`",
                f"**Also resolves:** {related}" if related else "",
                detail,
                f"### Todos\n\n{todos}",
            ]
            if part
        )
        stages.append(
            {
                "id": stage["id"],
                "issue": stage["issue"],
                "related": stage["related"],
                "labels": stage["labels"],
                "title": stage["title"],
                "body": body,
            }
        )
    return {
        "file": plan["file"],
        "issue": plan["issue"],
        "priority": plan["priority"],
        "labels": [PARENT_LABEL, *plan["labels"]],
        "title": plan["name"],
        "body": parent_body,
        "stages": stages,
    }


def record(path: pathlib.Path, parent: int | None, stages: dict[str, int]) -> None:
    head, body = split(path)
    lines = head.splitlines(keepends=True)
    if parent is not None:
        lines = set_issue(lines, None, parent, path)
    for sid, number in stages.items():
        lines = set_issue(lines, sid, number, path)
    path.write_text("---\n" + "".join(lines) + "---\n" + body)
    check(path)


def set_issue(lines: list[str], stage: str | None, number: int, path: pathlib.Path) -> list[str]:
    """Insert or replace `issue: N` at the plan's top level or in one stage."""
    if stage is None:
        for i, line in enumerate(lines):
            if re.match(r"^issue:", line):
                lines[i] = f"issue: {number}\n"
                return lines
        for i, line in enumerate(lines):
            if re.match(r"^stages:", line):
                return [*lines[:i], f"issue: {number}\n", *lines[i:]]
        raise PlanError(f"{path}: no `stages:` key to record the parent before")
    start, indent = None, 0
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)- id:\s*(\S+)\s*$", line)
        if m and m.group(2) == stage:
            start, indent = i, len(m.group(1)) + 2
            break
    if start is None:
        raise PlanError(f"{path}: no stage `{stage}`")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() and len(line) - len(line.lstrip(" ")) < indent:
            end = i
            break
    keys = {
        lines[i].strip().split(":", 1)[0]: i
        for i in range(start + 1, end)
        if len(lines[i]) - len(lines[i].lstrip(" ")) == indent and ":" in lines[i]
    }
    line = " " * indent + f"issue: {number}\n"
    if "issue" in keys:
        lines[keys["issue"]] = line
        return lines
    at = keys.get("todos", end)
    return [*lines[:at], line, *lines[at:]]


def plan_paths(names: list[str]) -> list[pathlib.Path]:
    if names:
        return [pathlib.Path(n) for n in names]
    paths = []
    for p in sorted(PLANS_DIR.glob("*.plan.md")):
        try:
            data, _ = load(p)
        except PlanError:
            # Unparseable: report it only if it looks opted in, so a run's own
            # broken plan does not block filing the roadmap.
            if re.search(r"^(priority|issue):", p.read_text(), re.M):
                paths.append(p)
            continue
        if data.get("stages") and ("priority" in data or "issue" in data):
            paths.append(p)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("plans", nargs="*")
    p_render = sub.add_parser("render")
    p_render.add_argument("--repo", required=True)
    p_render.add_argument("--ref", default="main")
    p_render.add_argument("plans", nargs="*")
    p_record = sub.add_parser("record")
    p_record.add_argument("plan")
    p_record.add_argument("--parent", type=int)
    p_record.add_argument("--stage", action="append", default=[], metavar="ID=N")
    args = parser.parse_args()

    try:
        if args.cmd == "record":
            stages = {}
            for item in args.stage:
                sid, _, n = item.partition("=")
                if not n.isdigit():
                    raise PlanError(f"--stage {item}: expected <id>=<issue number>")
                stages[sid] = int(n)
            record(pathlib.Path(args.plan), args.parent, stages)
            print(f"recorded in {args.plan}")
            return 0
        plans, failures = [], []
        for path in plan_paths(args.plans):
            try:
                plans.append(check(path))
            except PlanError as err:
                failures.append(str(err))
        if failures:
            print("\n".join(failures), file=sys.stderr)
            return 1
        if args.cmd == "check":
            print(f"{len(plans)} plans OK, {sum(len(p['stages']) for p in plans)} stages")
            return 0
        plans.sort(key=lambda p: (p["priority"], p["file"]))
        print(json.dumps({"plans": [render(p, args.repo, args.ref) for p in plans]}, indent=1, ensure_ascii=False))
        return 0
    except PlanError as err:
        print(err, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
