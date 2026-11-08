---
name: perf
description: Make something measurably faster, or prove it cannot be made faster cheaply — name the metric and the hardware the result is judged on, take an interleaved same-machine baseline with a noise band, profile before changing code, keep output identical to the baseline, and end in a PR or a "no change, here is the data" page. Use for "/perf", "make X faster", "can we save any performance on…", "optimise the hot path", "profile this", "benchmark ours against theirs", "why is theirs so fast", "did we get faster?", or whenever a speed claim is about to rest on a single run.
argument-hint: "[what to speed up, or the benchmark to beat] [--target <hardware>] [--no-fix]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
  - Skill
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git show:*)
  - Bash(git stash:*)
  - Bash(git worktree:*)
  - Bash(nproc:*)
  - Bash(uname:*)
  - Bash(lscpu:*)
---

# perf

Turn "make it faster" into a number someone else can reproduce. The order is the point: **frame, baseline, profile, change, measure, ship or say no**. Skipping to the change is how a session spends hours on an optimisation that is inside the noise, on the wrong chip, or quietly wrong.

Invoke with `/perf [target] [--target <hardware>] [--no-fix]`. `--no-fix` stops after the profile and the explanation — for "why is X slow" and "why is theirs so fast".

**Three rules that hold throughout:**

- **No claim from one run.** A result is a median over interleaved runs with its spread beside it. A gain inside the noise band is "no change", whatever the median says.
- **The hardware is part of the result.** A speed-up measured on a 4-core ARM container is a fact about that container. If the result is judged elsewhere, say so on every number until it has been measured there.
- **Faster and wrong is wrong.** Every candidate is checked against the baseline's output before its timing counts.

---

## Phase 1: Frame

Write these down before running anything, and put them at the top of whatever this ends in:

1. **The metric**: throughput, p50/p99 latency, CPU per request, ns/op, peak memory. One primary metric; others are guards.
2. **The workload**: the benchmark, the input sizes, the concurrency. Use the repo's own benchmark (package scripts, a `bench/` directory, Make or task-runner targets, a CI benchmark job) when there is one. Write a new harness only when there is none, and keep it beside the code it measures.
3. **The judging hardware**: where the number counts — a CI runner, a published leaderboard's box, production. Record this container's `uname -m`, `nproc`, and CPU model next to it. If they differ, every number from here is *indicative* until measured on the judging hardware, and the report says so.
4. **The comparison**, when the bar is someone else's code: fetch it from its upstream and record the SHA and date. A fork's stale default branch is not the competitor. Past sessions compared against a fork's weeks-old `main` and reported numbers the user had to correct.
5. **The bar**: what counts as a win (for example "p99 down by more than the noise band") and what would be a regression on the guards.

## Phase 2: Baseline

1. **Build both sides as separate artifacts** — base and candidate in separate worktrees or output directories, so a run never measures a half-rebuilt binary.
2. **Capture the correctness oracle**: the baseline's output on the workload (responses, hashes, files), saved outside the repo. Every candidate's output is diffed against it.
3. **Interleave**: A B A B …, at least 5 pairs, in one job on one machine, nothing else heavy running. Interleaving spreads drift (thermal, caches, noisy neighbours) evenly over both sides; running all of A then all of B does not.
4. **Measure the noise**: run A against A the same way. The spread of A-vs-A is the noise band. A container with a wide band needs more pairs, not a bolder claim.
5. Run long benchmarks once in the background with output to a file and end the turn; you are woken when it exits. No `sleep` or `until` loops.

Record: median, spread (min–max or IQR), n, and the noise band, per side.

## Phase 3: Profile before changing anything

Find out where the time goes before deciding what to change. Use the profiler the stack has — `perf`, `pprof`, `--cpu-prof`, `py-spy`, callgrind, a flame graph from whichever exists — on the workload from Phase 1. Name the top frames with their share of time.

Form one hypothesis from the profile: "X is 40% of CPU because it allocates per request". An optimisation that is not aimed at something the profile shows is a guess.

With `--no-fix`, stop here and report the profile, the hypothesis, and what a change would be expected to buy.

## Phase 4: Change and measure, one thing at a time

1. Make one change aimed at the hypothesis.
2. Run the tests and diff against the oracle. A mismatch ends that change — never accept a speed-up that changes output, skips validation, or weakens a guarantee.
3. Measure it against the baseline exactly as in Phase 2.
4. Keep it only if the primary metric moved outside the noise band in the right direction and no guard regressed outside its band. Otherwise revert it and record that it was tried.
5. Re-profile. The next hypothesis comes from the new profile, not the old one.

Do not tune the benchmark instead of the code: changing the workload, the input sizes, or the measurement mid-session invalidates the baseline.

## Phase 5: Measure where it counts

If the judging hardware is reachable — a CI benchmark job, a runner of the right architecture, a box the user names — run the final A/B there. If it is not, the result stays labelled *indicative, measured on <this container>*, and the PR or page says what would confirm it.

## Phase 6: Ship, or say no

Every session ends in one of two visible outcomes. A session that measured, found nothing, and stopped silently leaves the user asking "did we do anything?".

- **A win** → a PR. The body carries a table — metric, baseline median ± spread, candidate median ± spread, n, noise band, hardware — the exact commands to reproduce it, the correctness evidence (oracle diff clean, tests green), and the changes that were tried and reverted.
- **No win** → no PR, and a page through the `session-report` skill: what was measured, the profile, what was tried with each result, and why nothing shipped. "No change, here is the data" is a finished result.

## Summary

```
/perf: {target} — {N% faster on <metric> | no change | indicative only}

  Metric:    {metric}  baseline {median ± spread}  →  candidate {median ± spread}  (n={n}, noise ±{band})
  Hardware:  {measured on} {— judged on <target>: confirmed | not yet measured}
  Correct:   oracle {clean | differs}, tests {green | red}
  Kept:      {changes, one line each}
  Reverted:  {changes tried inside the noise, one line each}
  Result:    {PR url | report url}
```
