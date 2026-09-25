---
name: debug
description: Find and fix the root cause of a bug, failing test, or flaky test by reproducing it first, localising it with evidence, testing one hypothesis at a time, and pinning the fix with a regression test. Use when asked to "fix this bug", "why does X fail", "this test is failing", "CI is red on my branch", "debug this", or "this is flaky", and whenever a fix is about to be written for a failure nobody has reproduced yet.
argument-hint: "[failing command, test name, error text, or issue link] [--no-fix]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Bash(git log:*)
  - Bash(git diff:*)
  - Bash(git blame:*)
  - Bash(git bisect:*)
  - Bash(git status:*)
  - Bash(git show:*)
  - Bash(pnpm test:unit:*)
  - Bash(pnpm types:check:*)
  - Bash(pnpm turbo:*)
  - Bash(pnpm vitest:*)
  - Bash(bun run:*)
  - Bash(bunx:*)
  - Bash(npm run:*)
  - Bash(npx:*)
---

# debug

Turn "it is broken" into a fixed, tested, explained defect. The order is the point: **reproduce, localise, hypothesise, fix, prove**. Skipping to the fix is how a symptom gets patched while the cause ships.

Invoke with `/debug [what is failing] [--no-fix]`. `--no-fix` stops after the root cause is found and reported — for when the caller wants the diagnosis and will decide the fix.

**Two rules that hold throughout:**

- **No fix without a reproduction.** If you cannot make it fail on demand, you cannot know you fixed it. The reproduction is the first deliverable and the last check.
- **One variable at a time.** Change one thing, predict the outcome before running, run, compare. A fix that came from changing three things at once is a guess that happened to work.

---

## Phase 1: Reproduce

1. Pin down the observable failure in one sentence: the command or action, the input, the expected result, the actual result (quote the error text verbatim).
2. Make it fail on demand, cheapest form first: a scoped unit test run through the repo's task runner, a single command, a script in the scratchpad. Prefer turning it into a **failing test next to the code** (per the `tests` skill) — that test becomes the regression test in Phase 5 for free.
3. If it will not reproduce: say so, then narrow the difference between where it fails and where it does not (environment, data, timing, version, order). Do not start editing code on the theory that it is "probably" X.

Record the exact reproduction command; every later phase runs it again.

## Phase 2: Localise

Find the smallest piece of code that has to be wrong, using evidence rather than intuition:

- **Read the stack trace bottom-up** and open the first frame in code the repo owns, not the first frame in a dependency.
- **Ask what changed.** `git log --oneline -- <path>` on the files in the trace; if a known-good commit exists, `git bisect` with the reproduction command is faster than reading. `git blame` the failing line to find the commit and its intent.
- **Bisect the input** when the code is stable and the data is new: halve the input until the smallest failing case is found.
- **Trace the value.** Follow the wrong value backwards from where it is observed to where it is produced; add temporary logging at the midpoint rather than reading everything. Remove every temporary log before finishing.
- **Read the tests that should have caught it.** Either there are none (note it), or one exists and does not exercise this input (note why).

Stop when you can name the function and the line where correct behaviour becomes incorrect.

## Phase 3: Hypothesise and test

State the cause as a falsifiable sentence: *"`parseRange` returns `[0, 0]` for an empty string because `split` yields `['']` and `Number('')` is `0`."* Then test it directly — a one-line script, a REPL call, a targeted assertion — **before** touching the fix. A hypothesis that survives one direct test is a cause; one that needs a second explanation is not.

If the first hypothesis fails, form the next one from what the failed test showed. Keep a short ledger of what was ruled out and how; it goes in the report so nobody repeats it.

## Phase 4: Fix the cause

- Fix the line that is wrong, not the caller that trips over it. A guard added at the call site while the producer still emits garbage is a symptom patch.
- **Look for siblings.** Grep for the same pattern elsewhere in the repo — the same helper misused, the same assumption copied. Fix them in the same change when they are the same bug; list them for the caller when they are not.
- Keep the diff to the defect. No opportunistic refactors, no reformatting neighbouring code, no new abstractions "while here". Follow the repo's conventions and the `typescript` / `comments` skills on the lines you do touch.
- A comment on the fix explains *why* the case matters (the input that broke), not what the patch does.

## Phase 5: Prove it

1. Run the reproduction from Phase 1: it must pass now. Then make it fail once more by reverting the fix (or reasoning precisely about why it cannot), so the test is known to detect the defect.
2. Keep the reproduction as a regression test next to the code, named for the behaviour, not the ticket.
3. Run the touched package's scoped unit tests and type check through the repo's task runner from the repository root. Skip whole-repo runs and e2e suites unless the failure was only ever visible there.
4. Remove temporary logging, scratch files, and any `.only` / `.skip` left from narrowing.

## Flaky tests

A test that passes on re-run is not fixed; it is a bug with a low reproduction rate. Reproduce by running it in a loop (`--repeat`, a shell `for`, or the runner's retry flag turned *off*) until it fails, then debug the failure like any other. The usual causes are shared mutable state between tests, real time or real network in a unit test, unawaited promises, and order dependence. The fix is in the test or the code under test — **never** a retry, a longer timeout, a `skip`, or a quarantine list.

## Never

- Fix a failure you have not reproduced.
- Skip, disable, quarantine, or loosen a test to get green.
- Catch and ignore an error to make a symptom disappear.
- Widen a type to `any` / `unknown` to silence the compiler on the failing path.
- Leave debugging output, `.only`, or a hard-coded test input in the change.

## Report

Short, whatever the outcome:

```
/debug: {one-line failure}

  Cause: {file:line} — {the falsifiable sentence from Phase 3}
  Fix: {file:line} — {one line}; siblings: {list or "none found"}
  Regression test: {path::test name}
  Ruled out: {one line per hypothesis, or "none"}
  Verified: {the scoped commands that pass}
```

With `--no-fix`, stop after the Cause line and add what the fix would involve and where.

---

## Design notes

- **Reproduction is a deliverable, not a step.** It is what makes the fix checkable, what becomes the regression test, and what stops a "fix" from being a coincidence.
- **Hypotheses are tested before fixes are written** because a fix is the most expensive way to test a theory, and the one most likely to leave debris behind when the theory is wrong.
- **Flaky tests get the same treatment** because every other treatment (retries, timeouts, skips) trades a known signal for an unknown bug.
