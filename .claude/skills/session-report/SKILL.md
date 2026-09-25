---
name: session-report
description: Publish what was done in this session as a linked Claude artifact — a run report the person who was not watching, or the PR reviewer, can read once: what was asked, what changed, what was verified, what was found and fixed, and what still needs a human. Use for "/session-report", "write up what you did", "publish a report", "send me a summary I can share", when handing work over, and at the end of /plan-execute and /feature. Reads the session's own record and git; never invents progress.
argument-hint: "[title] [--for <plan path | pr number | branch>] [--no-publish]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Write
  - Artifact
  - ToolSearch
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git remote:*)
  - Bash(git rev-parse:*)
  - Bash(git merge-base:*)
  - Bash(gh pr view:*)
  - Bash(gh pr list:*)
  - mcp__github__list_pull_requests
  - mcp__github__add_issue_comment
---

# session-report

Turn the work this session did into one page with a link. The reader was not here: they are picking the work up, reviewing it, or deciding whether it is done. The page has to let them do that without the transcript.

Invoke with `/session-report [title] [--for <what>] [--no-publish]`.

**Arguments** (from `$ARGUMENTS`):

- Free text: the report's title. Default: the plan name, the PR title, or the branch name, in that order of availability.
- `--for <plan path | pr number | branch>`: what the report is about, when it is not obvious from the session. A plan path pulls in the plan's todos and verification; a PR number pulls in its title and links; a branch sets the diff scope.
- `--no-publish`: write the HTML file and hand it over instead of publishing. The default is to publish; a report nobody can link to is a transcript.

**Facts only.** Every line on the page is something the reader can check against the branch, the plan file, or a command's output. Write from the ledgers, plan statuses, test output, and `git` — not from memory of what you meant to do. If something was not verified, the page says so. If nothing changed, the page says that too, rather than being padded.

---

## Phase 1: Gather

Collect what exists; skip what does not.

1. **Scope.** `git rev-parse --abbrev-ref HEAD`, the `origin` remote as `owner/repo`, and the merge-base with `origin/main` (fall back to `main`). `git diff --numstat <base>` over the working tree is the change set; `git status --porcelain` adds untracked files. If HEAD is main and the tree is clean, the report is about something other than code (a review, a triage, a debugging diagnosis) and the diff sections are left out.
2. **The ask.** What the user asked for, in one or two sentences, in their words where possible.
3. **The plan**, when one was executed (`--for` a plan path, or the plan `/plan-execute` ran): every todo with its final status, grouped by stage with the stage goal; the reason beside each cancelled todo; the commands from its `## Verification` section with their results.
4. **The review loop**, when `/check-iterate` or `/plan-execute` ran: the ledger, one row per loop (found, confirmed, refuted, undecided, fixed, regression tests added), and every finding that reached verification with title, `file:line`, dimension, severity, the verifier's verdict, the collector's claim, and either the refutation or the fix in one sentence plus the regression test as `path::name`.
5. **Verification outside a plan**: any test, type-check, lint, or build command run this session and how it came out, including the ones that failed and were fixed.
6. **Open items**: the `skipped` ledger, findings still open when a loop ended, questions the user has not answered, anything you could not verify — each with `file:line` where it applies and what would settle it.
7. **Links**: the repo (`https://github.com/<owner>/<repo>`), the branch (`.../compare/main...<branch>`), and the pull request if one exists for the branch (`gh pr view --json url,title,number`, or `mcp__github__list_pull_requests` with `head`; load it with ToolSearch). Only link what you derived; never guess a URL.

## Phase 2: Write the page

Load the `artifact-design` skill and follow it. This is a utilitarian document: real typographic hierarchy, a palette, considered spacing, no hero. Light and dark themes, phone width.

Sections, in this order, leaving out any that are empty:

1. **Header** — the title, the repo and branch (linked), the base SHA, the date, and the outcome in one phrase: consensus after N loops, loop cap hit, plan complete with N cancelled, diagnosis only, and so on.
2. **At a glance** — a short row of numbers: todos completed of total, verification passed of total, loops, confirmed findings fixed of confirmed, files changed, items needing a human. Numbers only; detail lives below.
3. **What was asked** — the ask, and any scope decision made along the way (what was deliberately left out and why).
4. **Plan** — the todo checklist by stage, with cancellation reasons.
5. **Verification** — command, result, one-line note.
6. **Check loop** — the ledger table, then the findings grouped by loop. Refuted findings stay on the page, visually quieter: they are the evidence the loop did its job.
7. **Needs a human call** — the section the reader acts on; make it stand out.
8. **Files changed** — one row per path with additions and deletions.
9. **Notes** — coverage gaps, untracked files, commands that could not run, anything a reviewer should know before reading the diff.

No praise, no narrative of how the session went, no "might be worth checking". A reader should be able to stop after the header and the at-a-glance row and know whether to open the diff.

Write the file to the scratchpad, never into the repo.

## Phase 3: Publish

Publish with the Artifact tool: favicon `📋`, description "Run report for {title} on {branch}: what changed, what was verified, findings and fixes, and what needs a human." Keep the same file path when re-running in one session so the URL is stable.

The report is a Claude artifact with a link, not a file: this phase is not done until the tool has returned a URL. Only where the Artifact tool is genuinely absent from the session, or `--no-publish` was passed, hand the HTML file to the user and say so.

When the branch has a pull request, add one comment on it with the link so reviewers find the report where they are looking, ending with the attribution footer:

```
---
_Generated by [Claude Code](https://claude.ai/code)_
```

Do not comment on a PR you did not open or drive unless the user asked for the link to go there.

## Phase 4: Terminal line

One line: the URL, and the at-a-glance numbers after it. The page is the report; do not restate it in chat.

---

## Design notes

- **A prompt, not a pipeline.** The lead already holds every fact the page needs, so it writes the page directly; a schema and a build script would only add a second place for the format to drift.
- **Publishing is the deliverable.** The point is a link someone else can open. Writing the file and stopping is the failure mode this skill exists to prevent.
- **Refuted findings stay.** A report that shows only what was fixed cannot be told apart from one where nothing was checked. The ledger is the proof of work.
- **One skill owns the format.** `/plan-execute` and `/feature` end by invoking this skill rather than describing their own report, so a plan run, an autonomous feature run, and a hand-written `/session-report` produce the same page.
