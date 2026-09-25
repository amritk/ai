#!/usr/bin/env python3
"""Collect one person's recent work across every repo in a workspace, by PR.

Emits JSON on stdout: per repo, the pull requests they landed inside the window,
any commits that belong to no PR, and whatever is still local (unpushed commits
and a dirty working tree). Deciding what any of it *means* is the skill's job --
this only gathers facts.

Both merge styles are handled, because a workspace usually contains both:
squash-merged repos put the PR number in the commit subject (`... (#1354)`),
while merge-commit repos put it on the merge (`Merge pull request #344 from ...`)
and carry the real commits underneath it.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# Field and record separators that cannot occur in a commit message.
FS = "\x1f"
RS = "\x1e"

# Identities that mean "a coding agent committed this", not a person. Work done
# through an agent is still the user's work, but it cannot be told apart from a
# teammate's agent commits by email alone, so it is counted separately and the
# skill decides.
AGENT_EMAILS = {
    "noreply@anthropic.com",
    "noreply@openai.com",
    "bot@cursor.com",
}

BOT_PATTERN = re.compile(r"\[bot\]|^(github-actions|dependabot|renovate)", re.I)
SQUASH_PR_RE = re.compile(r"\s*\(#(\d+)\)\s*$")
MERGE_PR_RE = re.compile(r"^Merge pull request #(\d+) from (\S+)")
CO_AUTHOR_RE = re.compile(r"^co-authored-by:.*$", re.I | re.M)
# Release automation: real commits, but nobody stands up and reports them.
RELEASE_RE = re.compile(r"^(chore: )?(release|version packages)\b", re.I)


def git(repo: pathlib.Path, *args: str) -> str:
    """Run a git command in `repo`, returning stdout ('' if the command fails).

    Failures are swallowed deliberately: a repo with no upstream, no commits, or
    a detached HEAD should degrade to less information, never abort the run.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
        )
    except (subprocess.SubprocessError, OSError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def is_repo(path: pathlib.Path) -> bool:
    return (path / ".git").exists()


def discover(explicit: list[str], root: str | None) -> list[pathlib.Path]:
    """Resolve which repos to scan: explicit paths, or every repo under `root`."""
    if explicit:
        return [pathlib.Path(p).resolve() for p in explicit if is_repo(pathlib.Path(p))]

    base = pathlib.Path(root).resolve() if root else pathlib.Path.cwd().resolve()
    if not base.is_dir():
        return []
    if not root and is_repo(base):
        # Started inside a repo: scan it and its siblings, so a workspace of
        # checkouts side by side is covered without naming each one.
        base = base.parent
    found = [c.resolve() for c in sorted(base.iterdir()) if c.is_dir() and is_repo(c)]
    return found or ([base.resolve()] if is_repo(base) else [])


def remote_slug(repo: pathlib.Path) -> str:
    """`owner/repo` for the origin remote, so the skill can query GitHub."""
    url = git(repo, "remote", "get-url", "origin").strip()
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return match.group(1) if match else ""


def matches(commit: dict, patterns: list[str]) -> bool:
    """True when the commit's author, committer, or co-author matches an identity.

    Substring, case-insensitive, against both email and name, so `jane` matches
    `jane@example.com` and `Jane Doe` alike. Only `Co-authored-by:` trailers
    are read from the body -- scanning the whole message would claim any commit
    that merely mentions the name in prose.
    """
    haystack = " ".join(
        [
            commit["author_email"],
            commit["author_name"],
            commit["committer_email"],
            *CO_AUTHOR_RE.findall(commit["body"]),
        ]
    ).lower()
    return any(p.lower() in haystack for p in patterns)


def parse_log(raw: str) -> list[dict]:
    """Parse the delimited `git log --name-only` stream into commit records."""
    commits = []
    for chunk in raw.split(RS):
        if not chunk.strip():
            continue
        parts = chunk.split(FS)
        if len(parts) < 8:
            continue
        sha, date, ae, an, ce, subject, body, files_blob = parts[:8]
        # The format emits a trailing separator after %b, so the file list is its
        # own field. Splitting on a blank line instead would cut a multi-paragraph
        # commit message in half and read the rest of it as filenames.
        commits.append(
            {
                "sha": sha.strip(),
                "date": date.strip(),
                "author_email": ae.strip(),
                "author_name": an.strip(),
                "committer_email": ce.strip(),
                "subject": subject.strip(),
                "body": body.strip(),
                "files": [f for f in files_blob.splitlines() if f.strip()],
            }
        )
    return commits


def pull_requests(repo: pathlib.Path, since: str) -> tuple[dict[str, int], dict[int, dict]]:
    """Map commits to the PR that landed them, across both merge styles.

    Returns (sha -> pr number, pr number -> {title, date}). A squash-merged PR
    maps its single commit; a merge-commit PR maps every commit it brought in,
    which is why the merge's second parent has to be walked.
    """
    sha_to_pr: dict[str, int] = {}
    prs: dict[int, dict] = {}

    fmt = FS.join(["%H", "%aI", "%P", "%s", "%b"]) + FS
    raw = git(repo, "log", "--all", "--merges", f"--since={since}", f"--format={RS}{fmt}")
    for chunk in raw.split(RS):
        parts = chunk.split(FS)
        if len(parts) < 5:
            continue
        sha, date, parents, subject, body = (p.strip() for p in parts[:5])
        match = MERGE_PR_RE.match(subject)
        if not match:
            continue
        number = int(match.group(1))
        # The merge commit's body is where GitHub puts the PR title.
        prs[number] = {"number": number, "title": body.splitlines()[0].strip() if body else match.group(2), "date": date}
        parent_list = parents.split()
        if len(parent_list) >= 2:
            for merged_sha in git(repo, "log", f"{parent_list[0]}..{parent_list[1]}", "--format=%H").split():
                sha_to_pr[merged_sha] = number

    return sha_to_pr, prs


def collect_repo(repo: pathlib.Path, since: str, patterns: list[str]) -> dict:
    fmt = FS.join(["%H", "%aI", "%ae", "%an", "%ce", "%s", "%b"]) + FS
    raw = git(repo, "log", "--all", "--no-merges", f"--since={since}", f"--format={RS}{fmt}", "--name-only")

    sha_to_pr, merge_prs = pull_requests(repo, since)

    seen: set[str] = set()
    mine: list[dict] = []
    agent = 0
    others = 0

    for commit in parse_log(raw):
        if commit["sha"] in seen:
            continue
        seen.add(commit["sha"])
        if BOT_PATTERN.search(commit["author_email"]) or BOT_PATTERN.search(commit["author_name"]):
            continue
        if RELEASE_RE.match(commit["subject"]):
            continue
        if matches(commit, patterns):
            mine.append(commit)
        elif commit["author_email"] in AGENT_EMAILS:
            agent += 1
        else:
            others += 1

    # A commit is landed when it is reachable from a remote ref. Computing the
    # reachable set once beats asking per commit.
    landed = set(git(repo, "log", "--remotes", "--no-merges", f"--since={since}", "--format=%H").split())

    grouped: dict[int, dict] = {}
    loose: list[dict] = []
    unpushed: list[dict] = []

    for commit in mine:
        if commit["sha"] not in landed:
            unpushed.append({"subject": commit["subject"], "files": commit["files"]})
            continue

        number = sha_to_pr.get(commit["sha"])
        title = commit["subject"]
        squash = SQUASH_PR_RE.search(commit["subject"])
        if number is None and squash:
            number = int(squash.group(1))
            title = SQUASH_PR_RE.sub("", commit["subject"])

        if number is None:
            loose.append({"subject": commit["subject"], "date": commit["date"], "files": commit["files"]})
            continue

        entry = grouped.setdefault(
            number,
            {
                "number": number,
                "title": merge_prs.get(number, {}).get("title") or title,
                "date": commit["date"],
                "commits": [],
                "files": set(),
            },
        )
        entry["commits"].append(commit["subject"])
        entry["files"].update(commit["files"])
        entry["date"] = max(entry["date"], commit["date"])

    prs = sorted(grouped.values(), key=lambda p: p["date"], reverse=True)
    for entry in prs:
        entry["files"] = sorted(entry["files"])[:40]

    status = git(repo, "status", "--porcelain")
    staged, unstaged, untracked = [], [], []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        index, worktree, path = line[0], line[1], line[3:].strip()
        if index == "?":
            untracked.append(path)
            continue
        if index != " ":
            staged.append(path)
        if worktree != " ":
            unstaged.append(path)

    return {
        "name": repo.name,
        "path": str(repo),
        "remote": remote_slug(repo),
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "prs": prs,
        "loose_commits": sorted(loose, key=lambda c: c["date"], reverse=True),
        "local": {
            "unpushed": unpushed,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
        },
        "agent_commits": agent,
        "other_commits": others,
    }


def has_work(repo: dict) -> bool:
    return bool(repo["prs"] or repo["loose_commits"] or any(repo["local"].values()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=float, default=1, help="how far back to look (default 1)")
    parser.add_argument("--since", help="explicit git date, overrides --days")
    parser.add_argument("--author", action="append", default=[], help="identity substring, repeatable")
    parser.add_argument("--repo", action="append", default=[], help="repo path, repeatable")
    parser.add_argument("--root", help="directory of repos to scan")
    args = parser.parse_args()

    patterns = args.author or [p for p in os.environ.get("ASYNC_DAILY_AUTHORS", "").split(",") if p.strip()]
    if not patterns:
        print(
            "error: no author identity given. Pass --author <substring> (repeatable) or set "
            "ASYNC_DAILY_AUTHORS. Do not rely on `git config user.email` -- in an agent session "
            "it is the agent's identity, not yours.",
            file=sys.stderr,
        )
        return 2

    since = args.since or (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    repos = discover(args.repo, args.root)
    if not repos:
        print("error: no git repositories found to scan", file=sys.stderr)
        return 2

    scanned = [collect_repo(r, since, patterns) for r in repos]
    active = [r for r in scanned if has_work(r)]

    json.dump(
        {
            "since": since,
            "days": args.days,
            "authors": patterns,
            "repos_scanned": [r["name"] for r in scanned],
            "remotes": [r["remote"] for r in scanned if r["remote"]],
            "repos": active,
            "totals": {
                "prs": sum(len(r["prs"]) for r in active),
                "loose_commits": sum(len(r["loose_commits"]) for r in active),
                "agent_commits": sum(r["agent_commits"] for r in scanned),
            },
        },
        sys.stdout,
        indent=2,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
