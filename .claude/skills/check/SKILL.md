---
name: check
description: Adversarially review the branch's diff against main — the change set a
  PR would show — for security, reliability, and consistency, then produce a reduced,
  actionable plan. Enumerates the diff against the merge-base with main (uncommitted
  edits included), fans it out across read-only `checker` subagents that try to break
  the change and collect evidence-backed findings, and synthesizes those into a plan
  of just the items worth acting on. Use when asked to "check the branch", "review
  the diff against main", "run /check", or before opening or updating a PR.
argument-hint: "[--auto] [--dimension security|reliability|consistency] [extra focus notes]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
  - Write
  - Bash(git diff:*)
  - Bash(git status:*)
  - Bash(git rev-parse:*)
  - Bash(git merge-base:*)
  # Write + sed/python3 are needed by Phase 3: the plan file must be written to
  # .claude/plans/ and its YAML frontmatter validated per the plan skill.
  - Bash(sed:*)
  - Bash(python3:*)
---

# check

Adversarial review of the branch's **diff against main** — the change set a PR from this branch would show — across three dimensions: **security**, **reliability**, **consistency** — ending in a short, actionable plan. Data collection fans out to read-only `checker` subagents (the `checker` agent); this skill scopes the diff, spawns the collectors, and synthesizes their findings.

**The mandate is adversarial, not descriptive.** Assume the change is broken until the code proves otherwise. Hunt for the input that breaks it, the case the author missed, the invariant the diff quietly violates. A clean report must be *earned* — "looks fine" is not a finding, it is an unfinished search.

Invoke with `/check [--auto] [--dimension <name>] [focus notes]`.

**Arguments** (from `$ARGUMENTS`):

- `--auto`: skip clarification. Record ambiguous findings under a **Needs confirmation** heading instead of asking. Default is **interactive** — genuinely ambiguous items go through AskUserQuestion before the plan is finalized.
- `--dimension <security|reliability|consistency>`: restrict to one dimension (repeatable). Default is all three.
- Remaining free text is passed to every `checker` as extra focus.

**Branch scope, read-only.** Reviews everything the branch changes relative to main: the diff from the merge-base with main to the working tree, so branch commits and uncommitted edits to tracked files are all in scope — exactly what the PR will contain once the work is committed. If there is no diff against main, stop and say so. This skill and its subagents only read: never edit, stage, or commit. The output is a plan; applying it is a separate, user-initiated step.

---

## Phase 0: Scope the branch diff

1. Resolve the diff base: prefer `origin/main` (check with `git rev-parse --verify origin/main`), falling back to `main`, then run `git merge-base <ref> HEAD`. The resulting SHA is `<base>` — use it in every diff command and pass it verbatim to every `checker`. (No fetch — the review runs against local refs.)
2. `git diff --stat <base>` — if empty, stop with: `No changes against main. /check reviews the branch's diff against main — commit or edit something first, then re-run /check.` If HEAD is main itself, note that the review covers only local edits.
3. `git diff --name-only <base>` — enumerate the changed files. Untracked files never appear in the diff: list any (from `git status`) in the plan's **Notes** as un-reviewed instead of silently skipping them.
4. From the `--stat`, note total files and +N/-M per file for sharding.

Parse `$ARGUMENTS`: `--auto`, any `--dimension` values (default all three), trailing free-text focus.

---

## Phase 1: Fan out to `checker` collectors

Split the changed files into shards and spawn one `checker` subagent per shard with the `Agent` tool, **all in a single message** so they run concurrently. Each is read-only, scoped to the branch diff, and returns evidence-backed findings — no fixes, no plan.

**Sharding** — by cohesion, not raw count:

- ≤ 6 files or one tightly-coupled change → a single `checker` over the whole diff.
- Otherwise, keep coupled files together (a service and its tests, a route and its schema, a Vue component and its composable). Aim for 3–6 files per shard, ~6 shards max; a 500+ line file can be its own shard.
- A shard may read files outside its set for context, but do not add unrelated files without reason.

**Spawn** with `subagent_type: "checker"`, `description: "check shard <n>: <short summary>"`:

```
Adversarially review this branch's changes against main to these files ONLY —
assume they are broken and try to prove it:
{shard file list, one per line}

The diff base (merge-base with main) is {base SHA}.

{if --dimension was passed: "Restrict to these dimensions: {list}."}
{if free-text focus was given: "Extra focus from the operator: {focus}."}

Follow your standard operating constraints: read hunks with
`git diff {base SHA} -- <path>`, read surrounding context only as needed to judge
a hunk, cite file:line with the exact offending code, and return the structured
report in your defined output format. No fixes, no plan — raw findings only.
```

Do **not** background these (`run_in_background: false`); you need each report back this turn. If a spawn returns `status: "async_launched"`, recover from completion notifications or re-spawn synchronously in a smaller batch — do not poll transcripts. If a shard errors or returns nothing parseable, re-spawn once; if it fails again, record the un-reviewed files in the plan's **Notes** so gaps are never silent.

---

## Phase 2: Synthesize the findings

Merge every report, then reduce:

1. **Deduplicate** findings sharing a `file:line` and root cause, even across shards.
2. **Spot-check the evidence.** Open the cited line for every high-severity finding and for any finding whose quoted code you cannot place in the diff; drop the ones where the quote does not match the file. `/check` has no verification pass (that is `/check-iterate`), so this is the only filter between a collector's claim and a todo.
3. **Drop the non-actionable** — informational observations with no change to make. Keep genuine **nitpicks** (naming, small drift).
4. **Rank**: security → reliability → consistency, higher severity first within each.
5. **Resolve ambiguity.**
   - Interactive (default): gather the findings you cannot judge from the code alone and present them in **one** AskUserQuestion call (one question each, options roughly `Fix it` / `Leave it` / `Not an issue`). Fold answers in; drop what the user leaves.
   - `--auto`: list each under a **Needs confirmation** heading with a one-line "unclear because …".

---

## Phase 3: Write the plan

Write a repo plan file via the `plan` skill — `.claude/plans/<slug>.plan.md` with the stages/todos frontmatter, **not** a Cursor `.mdc`. Default slug `check-<short-topic>`. Load the `plan` skill for the schema and YAML rules, and validate the frontmatter parses.

- Each surviving finding is one **todo** — verb-first, cites `file:line`, ends `— see <Dimension>`, starts `status: pending`. Use flat `todos` for a small review; one `stage` per dimension when it is large.
- One `## Security` / `## Reliability` / `## Consistency` body section, each finding as ``- `path:line` — <problem>. Fix: <suggested change>.`` Omit an empty dimension.
- Add `## Needs confirmation` for open items and `## Notes` for coverage gaps.

If the review is clean, say so in the terminal rather than forcing a plan file (write a one-todo "passed all three dimensions" plan only if the user wants a record).

---

## Phase 4: Terminal summary

Short (< ~10 lines): counts per dimension, the single most important item, the plan path. Point at the file; do not restate the plan.

```
/check complete: {S} security, {R} reliability, {C} consistency items across {F} changed files.

  Top: {highest-priority item, file:line}
  {N} items need confirmation.  (omit if none)

Wrote .claude/plans/{slug}.plan.md
```

---

## Design notes

- **`checker` is the data layer; this skill is synthesis.** Collection stays read-only and parallel; the one judgment call — what is worth doing — stays with the orchestrator that saw every shard.
- **Adversarial by design.** Neutral "describe the diff" review misses the bug that only shows on the input nobody tried. The stance is baked into both the spawn prompt and the `checker` agent.
- **Branch-scoped** keeps `/check` a pre-PR gate: it reviews exactly the change set the PR will show, committed or not, instead of whatever happens to be staged.
- **Output is a normal `.claude/plans/*.plan.md`**, so a `/check` result is executed and status-tracked like any other plan.
