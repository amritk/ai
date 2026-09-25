---
name: check-iterate
description: Iteratively review and fix the branch's diff against main until consensus
  is reached. Each loop fans the diff against the merge-base with main — the change
  set a PR would show — out across read-only `checker` collectors, has read-only
  `verifier` subagents try to refute every finding, has the primary agent fix the
  confirmed issues with a regression test where one is cheap, and re-checks — ending
  when a loop produces zero confirmed findings (consensus) or after 7 loops. Use when
  asked to "check and fix until clean", "iterate on the branch", or "run
  /check-iterate". Unlike /check, this skill edits files and stages the fixes; it
  still never commits.
argument-hint: "[--max-loops N] [--dimension security|reliability|consistency] [focus notes]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Agent
  - Edit
  - Write
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
---

# check-iterate

A convergence loop on top of the `/check` review: **collect → verify → fix**, repeated until the reviewers and verifiers agree there is nothing actionable left, or the loop cap is hit. Data collection is delegated to read-only `checker` subagents and verification to read-only `verifier` subagents — two agents with opposite mandates, so a finding has to survive both; all fixes are made by the primary agent so there is a single editor and no write conflicts.

Invoke with `/check-iterate [--max-loops N] [--dimension <name>] [focus notes]`.

**Arguments** (from `$ARGUMENTS`):

- `--max-loops N`: override the loop cap (default **7**).
- `--dimension <security|reliability|consistency>`: restrict every loop to one dimension (repeatable). Default is all three.
- Remaining free text is passed to every collector and verifier as extra focus.

**Scope and safety:**

- **Branch scope.** Each loop reviews the branch's current diff against the merge-base with main — branch commits plus working-tree edits, exactly what a PR would contain once committed — so fixes from earlier loops are re-reviewed without committing. If there is no diff against main at the start, stop with: `No changes against main. /check-iterate reviews the branch's diff against main — commit or edit something first, then re-run /check-iterate.`
- **Fixes are scoped to findings.** The primary agent edits only to resolve confirmed findings — no opportunistic refactors, no touching files outside the branch's change set unless a fix genuinely requires it.
- **Edits and stages, never commits.** Fixes land in the working tree and are staged for the user to commit; the loop never commits, so the branch history is untouched.
- Runs in the spirit of `/check --auto`: no AskUserQuestion mid-loop. Findings that cannot be judged from the code alone are skipped and recorded for the final summary instead of blocking the loop.

---

## Phase 0: Preconditions

1. Resolve the diff base exactly as `/check` does: prefer `origin/main` (check with `git rev-parse --verify origin/main`), fall back to `main`, then run `git merge-base <ref> HEAD`. Record the SHA as `<base>`; it stays fixed for the whole run.
2. `git diff --stat <base>` — if empty, stop (message above).
3. `git diff --name-only <base>` — record the changed file list. Untracked files are invisible to the diff; note any in the final summary.
4. Parse `$ARGUMENTS`. Initialize the loop ledger:
   - `loop`: current iteration (1-based).
   - `fixed`: findings fixed so far, per loop.
   - `rejected`: findings refuted by verification or judged not-an-issue — checked every loop so a refuted finding is never re-litigated or re-fixed.
   - `skipped`: findings that need a human judgment call, were UNDECIDED by verification, or whose true fix is out of scope.

---

## The loop (up to the cap, default 7)

### Step 1 — Collect

Run the `/check` collection fan-out exactly as defined in Phases 0–1 of the `check` skill: re-enumerate the diff against `<base>` (it changes as fixes land), shard by cohesion, and spawn one read-only `checker` subagent per shard **in a single message** with the standard adversarial spawn prompt — including the base SHA — plus any `--dimension` restriction and free-text focus. Do not background them.

Merge and deduplicate the reports (same `file:line` + root cause), then drop anything already in `rejected` or `skipped` from a previous loop — a finding that was refuted once does not get a second trial.

**If nothing new survives the merge → consensus. Exit the loop.**

### Step 2 — Verify

Every surviving finding gets an independent adversarial verification before it is trusted. Group the findings by file/area and spawn one read-only `verifier` subagent per group (`subagent_type: "verifier"`, again all in one message, not backgrounded). The `verifier` agent's own system prompt carries the refute-first mandate and the severity rubric; the spawn prompt only supplies the data:

```
Verify these findings another reviewer made against this branch's changes
against main. The diff base (merge-base with main) is {base SHA}.

{numbered findings, each: dimension — title; file:line; evidence quote; claimed
failure; claimed severity}

Return one verdict block per finding in your defined output format. No fixes.
```

Never send findings back to a `checker` to verify — its mandate is to assume the code is broken, which is the opposite of what this step needs.

- **CONFIRMED** findings proceed to the fix step, at the severity the verifier settled on.
- **REFUTED** findings go into `rejected` (with the refutation) and are dropped.
- **UNDECIDED** findings go into `skipped` with the verifier's note on what would settle them.

**If zero findings are confirmed → consensus. Exit the loop.**

### Step 3 — Fix (primary agent)

The primary agent fixes each confirmed finding directly, in rank order (security → reliability → consistency, higher severity first). Follow the repo rules that auto-attach on the touched files. Fix the root cause the finding cites — if the true fix is genuinely out of scope for the branch (e.g. requires an API redesign), put the finding in `skipped` with a one-line reason instead of a cosmetic patch.

**Pin security and reliability fixes with a test.** A confirmed finding is a demonstrated failing input; when the touched package has cheap unit tests, add or extend a test that feeds exactly that input and would have failed before the fix (follow the `tests` skill for placement and naming). Skip it only when there is no unit-test harness to extend or the failure needs infrastructure a unit test cannot stand up — and say so in the ledger. Consistency fixes do not need one.

### Step 4 — Validate and stage the fixes

1. Format the touched files with whatever the repo uses, scoped to those paths — for example `pnpm biome check --write <paths>` (plus `pnpm prettier --write <paths>` for Markdown and YAML) in the pnpm repos, `bun run format` in the Bun repos. Read the root `package.json` scripts if unsure; never hand-format.
2. Run the touched package's unit tests scoped to it (this is also what proves the new regression tests fail-then-pass); on type-heavy changes, run its type check. Invoke both through the repo's task runner from the repository root, so build ordering and caching apply. Skip whole-repo runs. A fix that leaves a test red is not a fix — repair it or move the finding to `skipped` before staging.
3. `git add` exactly the files you edited or created — fixes stay staged for the user to commit, and a newly created file is invisible to `git diff <base>` until it is tracked.
4. Record the loop in the ledger, then continue to the next iteration.

### Convergence guard

If a loop's confirmed findings are **identical** to the previous loop's (same `file:line` + root cause — the fixes are not converging), stop early and report the stalemate rather than burning the remaining loops.

---

## Final summary

Short (< ~12 lines), whatever the exit reason:

```
/check-iterate: {consensus reached after N loops | loop cap (7) hit | stalemate after N loops}

  Loop 1: {X} findings → {Y} confirmed → fixed
  Loop 2: ...
  Fixed: {total} ({S} security, {R} reliability, {C} consistency), {T} pinned with a regression test
  Refuted by verification: {count}
  Needs a human call: {list file:line + one-liner, or "none"}
  {If the cap or a stalemate ended the loop: the findings still open, file:line each}

All fixes are staged; nothing was committed.
```

If the loop cap ended the run with findings still open, suggest `/check` to turn the remainder into a tracked plan file.

---

## Design notes

- **Collectors find, verifiers refute, the primary fixes.** Collection and verification are independent read-only passes by two different agents with opposite system prompts, so a finding must survive an agent trying to break the code *and* an agent trying to break the finding before anyone edits. Consensus = a full loop where nothing survives both.
- **Fixes carry their own proof.** A regression test turns a one-off finding into something the next loop, and every future PR, re-checks for free.
- **The `rejected` ledger is what makes the loop converge.** Without it, a refuted finding resurfaces every loop and the run can never reach a clean exit.
- **The diff base is fixed; the diff is live.** Reviewing merge-base → working tree means each loop sees the previous loop's fixes without a commit, and the scope never silently shrinks to whatever was staged.
- **One editor.** Subagents never edit; only the primary applies fixes, so there are no conflicting writes and every fix is reviewed by the next loop's collectors.
