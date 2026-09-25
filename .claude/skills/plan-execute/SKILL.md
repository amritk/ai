---
name: plan-execute
description: Execute a repo plan file end-to-end, run the plan's own verification
  commands, stage the result, then run the check-iterate convergence loop on the
  branch's diff against main — review by read-only `checker` subagents, refutation
  by `verifier` subagents, fixes by the primary agent — until a loop comes back
  clean (consensus) or 7 loops, then publishes a linked run report through the
  `session-report` skill. Use when asked to "execute the plan", "run
  /plan-execute", or "implement the plan and check it". Stages everything; never
  commits.
argument-hint: "[plan slug or path] [--max-loops N] [--dimension security|reliability|consistency] [--no-report] [focus notes]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Agent
  - Edit
  - Write
  - AskUserQuestion
  - Bash(git diff:*)
  - Bash(git status:*)
  - Bash(git add:*)
  - Bash(git rev-parse:*)
  - Bash(git merge-base:*)
  - Bash(pnpm check:*)
  - Bash(pnpm biome:*)
  - Bash(pnpm prettier:*)
  - Bash(pnpm test:unit:*)
  - Bash(pnpm types:check:*)
  - Bash(pnpm turbo:*)
  - Bash(pnpm vitest:*)
  - Bash(bun run:*)
  - Bash(bunx:*)
  - Bash(npm run:*)
  - Bash(npx:*)
  - Skill
---

# plan-execute

Execute a `.claude/plans/<slug>.plan.md` plan with the primary agent, stage the work, then drive the same **collect → verify → fix** convergence loop that `/check-iterate` uses, until the reviewers agree the branch's diff against main is clean or the loop cap is hit. When the plan is complete, publish one page that records the whole run — the plan's todo status, the verification results, every finding with its verdict and fix, and what is left for a human — so the person who did not watch it, or the PR reviewer, gets the full picture instead of a twelve-line terminal summary.

Invoke with `/plan-execute [plan slug or path] [--max-loops N] [--dimension <name>] [focus notes]`.

**Arguments** (from `$ARGUMENTS`):

- First non-flag token: the plan — a path, or a slug resolved to `.claude/plans/<slug>.plan.md`.
- `--max-loops N`: check-loop cap (default **7**).
- `--dimension` and trailing free text: passed through to the check loop.
- `--no-report`: skip Phase 5 (the `session-report` skill). The terminal summary is still printed.

---

## Phase 0: Resolve the plan

1. If a plan was given, read it. Otherwise list `.claude/plans/*.plan.md`: if exactly one has `pending`/`in_progress` todos, use it; if several qualify, pick via one AskUserQuestion; if none, stop with `No plan with open todos found — write one first (plan skill), or pass a path.`
2. Validate the frontmatter parses (todos/stages schema per the `plan` skill). If it doesn't, stop and say what's malformed rather than guessing.
3. Note the working-tree state (`git status`). Pre-existing staged or dirty files that the plan doesn't own stay untouched — but the check loop reviews the branch's whole diff against main, so they (and earlier branch commits) are in its scope; call out findings that land outside the plan's work in the final summary.

## Phase 1: Execute the plan (primary agent)

Work the todos in order, and keep the plan file live as the `plan` skill requires: set each item's `status` to `in_progress` when you start it and `completed` the moment it lands (or `cancelled` with a reason if dropped) — never batch the updates at the end. Follow the rules that auto-attach on the files you touch. If a todo turns out to be impossible as written, mark it `cancelled` with a one-line reason and continue; don't silently substitute different work.

A todo is `completed` when its done-signal holds, not when its code is typed. If the plan's `## Tests` section names coverage for the todo, write it as part of the todo. For a staged plan, check the stage's `verification` line before moving to the next stage — a stage whose exit criteria fail is `in_progress`, whatever its todos say.

## Phase 1b: Run the plan's verification

Before staging, run every command the plan's `## Verification` section lists (scoped tests, type checks, format checks), through the repo's task runner from the repository root. If the plan has no such section, run the touched packages' scoped unit tests and type check instead. A failure here is yours to fix now, as part of the todo that caused it — do not hand a red verification to the check loop and hope the collectors notice. Record the commands and their results in one line each for the final summary.

## Phase 2: Stage

1. Format the touched files with whatever the repo uses, scoped to those paths — for example `pnpm biome check --write <paths>` (plus `pnpm prettier --write <paths>` for Markdown and YAML) in the pnpm repos, `bun run format` in the Bun repos. Read the root `package.json` scripts if unsure; never hand-format.
2. `git add` the files the plan execution created or changed — including the updated plan file — and nothing else.
3. If nothing changed (the plan was already done), skip the loop and say so.

## Phase 3: Check loop

Run the loop from the `check-iterate` skill, exactly as written there — resolve the merge-base with main, collect via `checker` fan-out over the diff against it, verify by `verifier` refutation, fix confirmed findings with the primary agent (pinning security and reliability fixes with a regression test), stage the fixes — up to `--max-loops` (default 7) or until a loop confirms zero findings (consensus). The first review counts as loop 1. Keep the `rejected`/`skipped` ledgers as that skill defines so the loop converges.

One addition to the collector focus in every loop: include a pointer to the plan file so reviewers can flag work that **diverges from what the plan promised** (a todo marked `completed` whose change isn't in the diff, or staged changes no todo accounts for) as a consistency finding.

## Phase 4: Terminal summary

Short (< ~12 lines):

```
/plan-execute: {plan path}

  Todos: {X} completed, {Y} cancelled ({reasons in one line each, if any})
  Verification: {each command from the plan — pass/fail}
  Check loop: {consensus after N loops | loop cap hit | stalemate} — {total} findings fixed
  Needs a human call: {file:line one-liners, or "none"}
  {If loops ended with findings open: list them}

All work is staged; nothing was committed.
Run report: {artifact URL, or the HTML path when the Artifact tool is unavailable}
```

## Phase 5: Publish the run report

Runs once the plan is complete — every todo `completed` or `cancelled` and the check loop exited — unless `--no-report` was passed. Invoke the `session-report` skill with `--for <plan path>` and the plan name as the title. It reads the plan's todos and verification results, the check-loop ledgers this run kept, and the staged diff, writes one page, and publishes it as a Claude artifact with a link; when the branch has a pull request it leaves the link there as one comment. Put the URL on the last line of the terminal summary.

---

## Design notes

- **One skill owns the loop.** The convergence mechanics live only in `check-iterate`; this skill adds plan resolution, execution, and staging in front of it, so the two commands can't drift apart.
- **The plan file is part of the review surface.** Staging the plan file and pointing collectors at it turns "does the diff match the plan" into a checkable consistency dimension instead of an honor system.
- **The report is the `session-report` skill's page, published at the end of the plan.** One skill owns the format, so a plan run and a hand-written `/session-report` produce the same page; and it publishes once per run, not per loop or per merge, at the moment the lead already owns.
