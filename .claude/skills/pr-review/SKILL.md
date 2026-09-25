---
name: pr-review
description: Review a GitHub pull request in this repo by number, or the current branch before a PR exists, running a custom review prompt against the real diff and context. Use when asked to "review PR 123", "/pr-review 123", "look at PR 123 for <something>", when a PR number or URL is pasted with a review instruction attached, or to self-review a branch before opening a PR (`/pr-review --branch`). Posts findings as line-anchored comments on a COMMENT review; `--dry-run` and `--branch` report in chat instead.
argument-hint: "<pr-number|pr-url|--branch [base-ref]> [custom review prompt] [--dry-run] [--prompt <file>]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(gh pr view:*)
  - Bash(gh pr diff:*)
  - Bash(gh pr list:*)
  - Bash(gh api:*)
  - Bash(git remote:*)
  - Bash(git fetch:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git merge-base:*)
  - Bash(git rev-parse:*)
  - Bash(git status:*)
  - mcp__github__pull_request_read
  - mcp__github__get_file_contents
  - mcp__github__pull_request_review_write
  - mcp__github__add_comment_to_pending_review
  - ToolSearch
  - AskUserQuestion
---

# pr-review

Review one change in a GitHub repository against a **custom prompt**. The repository defaults to the
`origin` remote of the current checkout (`git remote get-url origin`). The PR number — or `--branch`, for
work that has no PR yet — selects what gets reviewed; the prompt decides what "review" means for this
run — bugs, a single subsystem, a migration check, a naming pass, whatever the caller asked for.

Invoke with `/pr-review <pr-number> [custom review prompt]` for an open PR, or
`/pr-review --branch [custom review prompt]` to review the current branch against `main` before
opening one.

Two modes, same review:

| Mode | Trigger | Reviews | Findings go to |
| --- | --- | --- | --- |
| **PR mode** | a PR number or URL | the open PR's diff and context | posted on the PR as a `COMMENT` review (`--dry-run` → chat) |
| **Branch mode** | `--branch [base-ref]` | the current branch's diff against its base, committed and uncommitted | chat only — there is nothing to post to |

Branch mode is the self-review to run **before opening a PR**: it catches the findings the skill
would otherwise post on your own PR minutes later, while they are still cheap to fix and before a
human is looking. It covers the whole PR-to-be — the branch's commits plus whatever is still
uncommitted in the working tree. When there is no branch yet, because the work is sitting uncommitted
on `main` itself, `/code-review` is the tool for that diff.

---

## Phase 0: Resolve the arguments

From `$ARGUMENTS`:

- **First token** — the PR. Accept a bare number (`4821`), a `#`-prefixed number (`#4821`), or a
  full URL (`https://github.com/<owner>/<repo>/pull/4821`). Anything else is not a PR reference.
- **`--branch [base-ref]`** — branch mode: review the checked-out branch instead of an open PR.
  The optional next token is the base to diff against; it defaults to `origin/main`. Treat a token
  as the base only when it looks like a ref (`main`, `origin/main`, `release/1.x`, a SHA); otherwise
  it is the start of the custom prompt. Resolve a bare branch name to its remote-tracking ref —
  `main` means `origin/main` — because local branches in this repo go stale silently and diffing
  against one reviews everything merged since it was last pulled. Use a SHA or an explicit
  `refs/heads/...` as given.
- **`--dry-run`** — report findings in chat and write nothing to GitHub. Absent, the review is
  posted (see Phase 4). Branch mode is always chat-only, so the flag is redundant there.
- **`--prompt <file>`** — read the custom prompt from a file instead of the command line.
- **Remaining free text** — the custom prompt.

If neither a PR reference nor `--branch` was given, stop and ask which to review; do not guess from
recent branches. If both were given, ask which one the caller meant rather than picking — reviewing
the branch when they asked for the PR posts nothing, and the reverse posts to a PR they did not name.
If no custom prompt was given (no free text and no `--prompt`), use `default-prompt.md` next to this
file.

The custom prompt is an **instruction to follow**, not a document to summarize. It governs the
review: what counts as a finding, how findings are worded, and where they are posted. Where it
conflicts with the defaults below, the prompt wins — the phases here exist to load the right context
and carry out what the prompt asks for.

## Phase 1: Load the change

### PR mode

Prefer `gh` when it is on `PATH`; fall back to the GitHub MCP tools (`mcp__github__pull_request_read`
with methods `get`, `get_diff`, `get_files`, `get_review_comments`) when it is not — remote sessions
have the MCP server but no `gh`.

```sh
gh pr view <n> --json number,title,body,author,state,isDraft,baseRefName,headRefName,files,commits
gh pr diff <n>
```

Collect, at minimum: title and description, author, base and head refs, the changed-file list, the
full diff, and any existing review comments (so the review does not repeat what a human already
said).

**Bot gate.** If the author is a bot — `github-actions`, `scalar-sdk-repo-sync`, any `[bot]`
account, or a login the caller names as automation — stop. Post nothing, and say which bot opened it.
These PRs are machine-generated (dependency bumps, spec syncs); reviewing them wastes a run and puts
noise on a PR no human will read. Review one only if the caller explicitly asks for that PR anyway.

**Stack context.** If the PR is part of a stack — its base is another open PR rather than `main`, or
the description links to sibling PRs — read the description of every PR in the stack before
reviewing. Half a stack reads as broken: a function this PR adds with no caller usually gets its
caller in the next PR up, and reporting that as dead code is a false positive.

For a large diff, do not review it from the patch alone. Fetch the head commit and read the changed
files in full, because regressions usually live in what the hunk does not show — a branch a few
lines above, the field the patch consumes, the fixture or snapshot the change should have updated:

```sh
git fetch origin pull/<n>/head:pr-<n>
git diff $(git merge-base origin/main pr-<n>)...pr-<n>
```

If the PR cannot be fetched (wrong number, no access, closed repo), stop and say so plainly rather
than reviewing a partial picture.

### Branch mode

There is no PR to read, so build the same picture from git. Fetch the base first, and diff against
the remote-tracking ref rather than the local branch of the same name — `git fetch origin main`
moves `origin/main` and leaves local `main` where it was, so a merge base taken from local `main`
can be weeks old and drag every commit merged since into the diff:

```sh
BASE=origin/main                         # --branch <ref>; a bare name resolves to origin/<name>
git fetch origin main                    # fetch the branch behind $BASE, not necessarily main
MB=$(git merge-base "$BASE" HEAD)
git diff --stat "$MB"                    # sanity-check the size before reading the full diff
git diff "$MB"                           # committed + staged + unstaged, the PR-to-be
git log --oneline "$MB"..HEAD
```

If `git diff --stat "$MB"` reports far more files than the branch touched, the base is wrong — check
it resolved to a remote-tracking ref before reviewing what it produced.

Two-dot `git diff` against the merge base, not `...HEAD`, because the point of a pre-PR review is to
catch work that is not committed yet. It still misses untracked files, so list them with
`git status --porcelain` and read any that are part of the change — a new emitter file nobody has
`git add`ed is exactly the kind of thing that ships broken.

Collect: the changed-file list, the full diff, the branch's commit subjects (they stand in for the
PR description), and the base ref. The bot gate and stack context do not apply — the caller is
reviewing their own uncommitted work, and there is no author or base PR to check.

Stop and say so, rather than reviewing nothing, when `HEAD` is the base branch itself or the diff
against the merge base is empty. If the branch is behind a base that has moved, review it anyway and
say which base commit the review was against.

## Phase 2: Ground the review in this repo

Before judging anything, read the guides that own the touched area — the custom prompt says what to
look for, the repo's own agent guidance says what "correct" means *here*. A rule this repo has
already settled is not a finding.

Find that guidance in the order it exists:

1. The root `AGENTS.md` / `CLAUDE.md` — always read it; it usually carries a table routing each
   area to a deeper guide.
2. The nested guide for the touched directory — `.agents/<topic>.md`, `.claude/rules/<topic>.md`,
   or a per-package `AGENTS.md` beside the changed files. Follow the routing table from step 1
   rather than guessing filenames.
3. Neighbouring code, when nothing is written down: the conventions the surrounding files already
   follow are the standard.

A finding that contradicts one of these guides is wrong until proven otherwise — check the guide
before reporting it.

## Phase 3: Execute the custom prompt

Run the prompt against the diff and the files you read. Per finding, hold to three bars:

1. **Provable from the code in front of you.** Name the file and line, and describe a concrete
   input or call path that reaches the bad behavior. "This looks fragile" is not a finding.
2. **Caused by this change.** Pre-existing problems the diff merely touches are out of scope unless
   the custom prompt asked for them.
3. **Worth the author's time.** Style nits the repo's formatter would fix, or opinions the repo
   has already settled in its agent guides, get dropped.

Verify before reporting. Grep for the other call sites, read the function being called, check
whether the fixture snapshot actually covers the case. Delete anything that does not survive.

When the change affects generated output, the strongest check available is running it — regenerate a
fixture and look at the real emitted files rather than reasoning about the emitter in the abstract.
Verification is for your own confidence; it does not go in the report unless the prompt asks for it.

## Phase 4: Deliver the review

**Branch mode reports in chat and writes nothing to GitHub** — there is no PR to comment on, and
this skill never opens one to have somewhere to post. A prompt that says to comment on the code
(`default-prompt.md` does) is overridden on that point only; read its "this PR" as "this diff" and
keep everything else it asks for, including the risk score. Give each finding as
`file:line` + defect + failure scenario + severity so the caller can fix it before pushing. Say
plainly when nothing survived verification, and hold to the output discipline at the end of this
phase; the numbered posting steps in between are PR mode only.

For PR mode, deliver findings the way the prompt asks. For the default prompt that means posting to
GitHub:

1. Open a pending review — `mcp__github__pull_request_review_write` with `create`.
2. Attach each finding that maps to a changed line as a line-anchored comment on the diff —
   `mcp__github__add_comment_to_pending_review`.
3. Put anything that cannot be anchored (cross-file contracts, a missing test, the risk score) in
   the review body rather than dropping it.
4. Submit with `submit_pending` as **`COMMENT`**. Never `APPROVE` or `REQUEST_CHANGES` — those are
   the human reviewer's call, and an automated approval is worse than no review.

Without the MCP tools, the same three steps go through `gh api` against
`/repos/<owner>/<repo>/pulls/<n>/reviews` with a `comments` array (`path` + `line` + `body`) and
`"event": "COMMENT"` — one call, same result.

Every posted body ends with the attribution footer:

```
---
_Generated by [Claude Code](https://claude.ai/code)_
```

Post nothing when nothing survived verification; say so in chat instead. An empty review is noise on
someone's PR. Likewise, do not re-post a finding an existing review comment already raised.

With `--dry-run`, skip all of the above and print the same findings in chat.

Output discipline, every path: findings only. No summary of what the PR does, no praise, no
narration of how you reviewed it, no speculative "might be worth checking" items. Each comment is
short enough to read at a glance — defect, failure scenario, severity.

---

## Design notes

- **The prompt is the variable, the PR is the argument.** Baking one fixed checklist in would make
  this a duplicate of `/code-review`; taking the prompt as input is what makes it reusable for
  one-off passes ("check only that the Python emitter change is fixture-safe"). `default-prompt.md`
  is the standing adversarial review, swapped out per run rather than edited.
- **Posting is the default, `COMMENT` is the ceiling.** The review is worth little if it lands in a
  chat log the author never sees, so it posts; capping it at `COMMENT` keeps the merge decision with
  a human. `--dry-run` exists for trying a new prompt without spending a real review on it.
- **Branch mode exists so the review happens before the PR, not after it.** The findings are the
  same either way; posting them on your own PR just means a human saw the defect first. It stays
  chat-only and never opens a PR, because a mode meant to run before the PR exists must not be the
  thing that creates one.
- **Bots and stacks are gates, not prompt text.** Both decide whether the review should run at all
  and what context it needs, so they sit in Phase 1 where they still apply when a caller supplies
  their own prompt.
