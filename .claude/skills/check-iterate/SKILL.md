---
name: check-iterate
description: Iteratively review and fix the branch's diff against main until consensus
  is reached. Each loop fans the diff against the merge-base with main — the change
  set a PR would show — out across read-only `checker` collectors, has read-only
  `verifier` subagents try to refute every finding, has the primary agent fix the
  confirmed issues with a regression test where one is cheap, and re-checks — ending
  when a loop produces zero confirmed findings (consensus) or after 3 loops (one more
  when the last loop confirmed fewer findings than the one before). Use when
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

- `--max-loops N`: override the loop cap (default **3**). One extra loop is allowed past it when the findings are still going down (see **Loop cap**).
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
   - `fixed_files`: the files the previous loop's fixes touched, with the findings each fix resolved. Empty before loop 1.
   - `confirmed`: how many findings each loop confirmed, for the extra-loop rule.
5. **Cheap checks before any reviewer.** Run the touched packages' lint and type check (and their scoped unit tests when they finish in well under a minute) through the repo's task runner, the same commands Step 4 uses. A collector that reports what a linter would have caught has spent tokens on a check that costs none; a red test it rediscovers is a whole verify round for nothing. Fix what fails in the branch's changed files, format, and stage the fix before loop 1. This is the one edit allowed outside a confirmed finding, and it is limited to what the tool reported. A failure that cannot be fixed within the branch's scope goes under `skipped` with the tool's message, and the run goes on.

---

## The loop (up to the cap, default 3)

### Step 1 — Collect

Run the `/check` collection fan-out exactly as defined in Phases 0–1 of the `check` skill: re-enumerate the diff against `<base>` (it changes as fixes land), shard by cohesion, and spawn one read-only `checker` subagent per shard **in a single message** with the standard adversarial spawn prompt — including the base SHA — plus any `--dimension` restriction and free-text focus. Do not background them.

Always spawn, even for a single shard: `/check`'s inline single-shard path does not apply here. From loop 2 on, the diff contains fixes this agent wrote, and that is exactly the case where `/check` spawns too — the collector has to be a fresh context that never saw the fixes being written.

**Loop 2 on: review what changed, not everything again.** Loop 1 reviewed the whole diff. A later loop shards only `fixed_files` — the files the previous loop's fixes touched — and each collector is told it is reviewing fixes, with this added to its spawn prompt:

```
This is loop {n}. The rest of the branch was reviewed in loop {n-1}; review the
hunks in these files, which the last loop's fixes changed. Each fix below was
meant to resolve the finding next to it: check that it does, that it broke
nothing around it, and probe the sibling cases of the same shape (the other
callers, the other branches of the same switch, the neighbouring inputs).

{fixed file → the finding each fix resolved: title and file:line}
```

The collector is still a fresh agent that never saw the fixes written and never saw a refuted finding, so it has nothing to negotiate over; it only starts from where the last loop ended instead of from scratch. That is cheaper, and the attention goes where the code just changed. The trade is that a bug loop 1 missed in a file no fix touched is not looked for again. Fall back to the whole diff when a fix touched more than half of the branch's changed files, or when the previous loop's fixes changed a signature other changed files call.

**A loop that landed no fix ends the run.** If every finding a loop confirmed ended in `skipped`, `fixed_files` is empty and the next loop would have nothing to review. Do not start it, and do not call it consensus: the run ends as `stopped, K findings need a human`. A fix abandoned on its way to `skipped` (it left a test red, say) is undone before the finding moves there, so no half-made edit stays in the diff unreviewed.

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
2. Run the touched package's unit tests scoped to it (this is also what proves the new regression tests fail-then-pass); on type-heavy changes, run its type check. Invoke both through the repo's task runner from the repository root, so build ordering and caching apply. Skip whole-repo runs. A fix that leaves a test red is not a fix — repair it, or undo its edits and move the finding to `skipped` before staging.
3. `git add` exactly the files you edited or created — fixes stay staged for the user to commit, and a newly created file is invisible to `git diff <base>` until it is tracked.
4. Record the loop in the ledger — including `fixed_files`, which the next loop's collectors are scoped to — then continue to the next iteration.

### Loop cap

The cap is 3 loops. A run that is still confirming findings after three is usually one where the fix needs a decision the loop cannot make, and every loop past that is a full collect-and-verify fan-out spent on it. The baseline in `evals/README.md` was measured at `--max-loops 3` (17 of 18 planted bugs fixed), before later loops were scoped to the fixes; re-run the eval to compare after changing either. A one-rep run with scoped loops fixed 9 of 9.

**One extra loop when it is converging.** At the cap with findings still open, run one more loop only if the last loop confirmed **fewer** findings than the loop before it, and that earlier loop was itself loop 2 or later. Loop 1 reviews the whole diff and later loops review only the fixes, so comparing against loop 1 would almost always say "fewer". In practice the extra loop exists only for caps of 3 or more; with `--max-loops 1` or `2` (the `feature` worker brief uses 2) the cap is exact. Grant it at most once per run, and record it in the ledger. A loop that confirmed the same number or more stops at the cap.

### Convergence guard

If a loop's confirmed findings are **identical** to the previous loop's (same `file:line` + root cause — the fixes are not converging), stop early and report the stalemate rather than burning the remaining loops.

### When the cap ends the run

Nothing is lost: every fix made so far stays staged, and every finding still open is listed in the summary with its `file:line`, so a human picks up exactly where the loop stopped. Re-running `/check-iterate` starts a fresh budget, and `/check` turns the remainder into a plan file.

---

## Final summary

Short, whatever the exit reason — the template below and nothing more:

```
/check-iterate: {consensus reached after N loops | loop cap ({max loops}) hit | stalemate after N loops | stopped after N loops, K need a human}

  Loop 1: {X} findings → {Y} confirmed → fixed
  Loop 2: ...
  Fixed: {total} ({S} security, {R} reliability, {C} consistency), {T} pinned with a regression test
  Refuted by verification: {count}
  Needs a human call: {list file:line + one-liner, or "none"}
  {If the cap or a stalemate ended the loop: the findings still open, file:line each}
  {If a kind of finding was confirmed two or more times at different places: "Make it a rule:" and the lint rule, hook, or CLAUDE.md line that would catch it, verbatim and ready to paste}

All fixes are staged; nothing was committed.
Commit trailer: Verified: check-iterate ({consensus after N loops | cap hit, K open | stalemate, K open | stopped, K open})
```

The trailer line is for the user's commit message, so the history records how each commit was checked and an unchecked one can be found by searching for its absence. Leave it off when the repo's `CLAUDE.md` forbids commit trailers.

A finding that recurs is a convention the repo has not written down. A rule that catches it runs for free on every future change; a reviewer catching it again costs a loop. Propose one only when it can be checked from the diff alone, and propose nothing when the repeats are coincidence.

If the loop cap ended the run with findings still open, suggest `/check` to turn the remainder into a tracked plan file.

---

## Design notes

- **Collectors find, verifiers refute, the primary fixes.** Collection and verification are independent read-only passes by two different agents with opposite system prompts, so a finding must survive an agent trying to break the code *and* an agent trying to break the finding before anyone edits. Consensus = a loop where nothing survives both: loop 1 over the whole diff, or a later loop over everything the previous loop's fixes changed.
- **Fixes carry their own proof.** A regression test turns a one-off finding into something the next loop, and every future PR, re-checks for free.
- **The `rejected` ledger is what makes the loop converge.** Without it, a refuted finding resurfaces every loop and the run can never reach a clean exit.
- **Later loops start where the last one ended.** Each collector is fresh, so the loop stays adversarial, but from loop 2 on it reviews the fixes and their siblings instead of re-reading the whole branch.
- **The diff base is fixed; the diff is live.** Reviewing merge-base → working tree means each loop sees the previous loop's fixes without a commit, and the scope never silently shrinks to whatever was staged.
- **One editor.** Subagents never edit; only the primary applies fixes, so there are no conflicting writes and every fix is reviewed by the next loop's collectors.
