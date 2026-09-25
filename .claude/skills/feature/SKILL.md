---
name: feature
description: Drive work from requirements to merged pull requests autonomously on Claude Code cloud — plan it, fan the plan's stages out to one cloud session per PR, review each PR with fresh-context adversarial rounds, merge once the gate passes, and check the merged result against the acceptance criteria before calling it done. Use when asked to "build this feature", "ship this", "run /feature", "build and merge this autonomously", or to take an accepted plan all the way to main without supervision. Spawns sibling cloud sessions and merges PRs, so it always stops for plan acceptance first.
argument-hint: "[requirements | plan slug] [--dry-run] [--max-slices N] [--max-rounds N] [--deadline <duration>] [--no-merge] [--no-qa] [--no-report] [--status <slug>] [--abort <slug>]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
  - PushNotification
  - ToolSearch
  - ListAgents
  - SendMessage
  - Skill
  - mcp__Claude_Code_Remote__create_session
  - mcp__Claude_Code_Remote__get_session
  - mcp__Claude_Code_Remote__list_environments
  - mcp__Claude_Code_Remote__set_session_tags
  - mcp__Claude_Code_Remote__set_session_title
  - mcp__Claude_Code_Remote__interrupt_session
  - mcp__Claude_Code_Remote__archive_session
  - mcp__Claude_Code_Remote__unarchive_session
  - mcp__Claude_Code_Remote__send_later
  - mcp__Claude_Code_Remote__create_trigger
  - mcp__Claude_Code_Remote__list_triggers
  - mcp__Claude_Code_Remote__delete_trigger
  - mcp__Claude_Code_Remote__subscribe_pr_activity
  - mcp__Claude_Code_Remote__unsubscribe_pr_activity
  - mcp__github__issue_read
  - mcp__github__issue_write
  - mcp__github__add_issue_comment
  - mcp__github__list_pull_requests
  - mcp__github__pull_request_read
  - mcp__github__pull_request_review_write
  - mcp__github__add_comment_to_pending_review
  - mcp__github__resolve_review_thread
  - mcp__github__update_pull_request
  - mcp__github__update_pull_request_branch
  - mcp__github__merge_pull_request
  - mcp__github__list_branches
  - mcp__github__get_file_contents
  - mcp__github__get_check_run
  - mcp__github__actions_list
  - mcp__github__actions_get
  - mcp__github__get_job_logs
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git add:*)
  - Bash(git commit:*)
  - Bash(git push:*)
  - Bash(git fetch:*)
  - Bash(git checkout:*)
  - Bash(git rev-parse:*)
  - Bash(git merge-base:*)
  - Bash(git remote:*)
---

# feature

Requirements in, merged PRs out, on **Claude Code cloud**. One lead session plans the work and never writes code; each stage of the plan becomes one sibling cloud session, one branch, one PR; each PR is reviewed by fresh-context adversarial rounds and merged by the lead when the gate passes. Then the run checks whether what merged is what was asked for.

Invoke with `/feature [requirements | plan slug] [flags]`.

**Arguments** (from `$ARGUMENTS`):

- First non-flag token: either a plan slug/path (`.claude/plans/<slug>.plan.md`) to execute, or free-text requirements to plan from. Free text means Phase 1 runs; a slug means it is skipped.
- `--dry-run`: plan, slice, and print the fan-out table — spawn nothing, open nothing, merge nothing.
- `--max-slices N`: concurrent cloud sessions (default **4**).
- `--max-rounds N`: adversarial review rounds per PR (default **10**).
- `--deadline <duration>`: wall-clock ceiling for the whole run (default **8h**). At the deadline the lead stops spawning, finishes the rounds already in flight, escalates whatever has not merged, and closes out. A run with no deadline does not fail, it just never admits it has.
- `--no-merge`: run everything up to the merge gate, then stop with PRs green and report. Acceptance (Phase 7) does not run — nothing merged, so there is nothing to accept — and the report says the criteria were never checked. Use this the first few times against a new repo.
- `--no-qa`: skip the dynamic half of acceptance (Phase 7). The static pass still runs, and the report says the feature was never exercised. Use it for a repo with no runnable surface, not to save time.
- `--no-report`: skip publishing the run through the `session-report` skill at close-out. The tracking issue and the terminal summary are still written.
- `--status <slug>`: read the ledger for an existing run and report; change nothing.
- `--abort <slug>`: stop a run — see **Aborting**.

## What this skill assumes

- **Cloud, not a laptop.** Every worker is a separate session with its own container and its own fresh clone. There is no shared filesystem and no worktree; the lead cannot see a worker's files and a worker cannot see the lead's. Everything that has to cross that boundary crosses through **git and GitHub** — see `references/ledger.md`.
- **The lead does not write code.** It plans, spawns, reviews, merges, and reports. If the lead finds itself editing a source file, the slicing was wrong — respawn the slice instead.
- **Autonomous merge is the default outcome, not a licence.** The only human gate is plan acceptance in Phase 1. Everything after it must be gated by machine-checkable facts, which is what `references/merge-gate.md` exists to enumerate.

---

## Phase 0: Preconditions

Check all of these before touching anything. Any failure stops the run with the specific remedy — do not "proceed anyway" on a partial pass, because every one of these failures surfaces hours later as a stuck worker.

1. **Repo and remote.** `git remote -v` resolves to a GitHub repo in scope. Record `owner/repo`.
2. **Default branch, and who is allowed to merge.** Record the default branch. Branch protection rules are not readable through the tools here, so establish the answer two ways instead: look for a `CODEOWNERS` file and for a required-review convention in `CONTRIBUTING.md`, and **ask the user directly in Phase 1** whether merging this repo requires a human approval. If it does, this run cannot end in an autonomous merge — continue in `--no-merge` mode and say so now, rather than discovering it at the gate after every PR is already green. The first PR's `mergeable_state` from `pull_request_read` confirms it either way; treat a `blocked` state as the authoritative answer and switch to `--no-merge` mid-run if it contradicts what you were told.
3. **Dependencies install themselves.** A worker's container starts from a bare clone, so the repo needs a `SessionStart` hook (`.claude/settings.json`) that installs dependencies. Without one, the coverage gate cannot execute and workers quietly downgrade "100% coverage" to "I believe coverage is fine". No hook → stop with: `No SessionStart hook in this repo — workers start with no dependencies installed and cannot run the coverage gate. Add one, then re-run /feature.` (Claude Code ships a `session-start-hook` skill that writes one; it is not part of this repo, so do not assume it is loaded.)
4. **The verification commands.** Identify the repo's real test, coverage, lint, and typecheck commands from `package.json` / task runner config. Record the exact strings; they go verbatim into every worker prompt and into the merge gate. If no coverage command exists or coverage thresholds are not configured, stop and say so — the coverage gate is a command, never a judgement.
5. **Environment and permissions.** `list_environments` to resolve the environment workers inherit. Note the lead's own permission mode: **workers cannot be more permissive than the lead**, so if the lead is running in a mode that prompts, workers will stall unattended. If the lead cannot pre-approve the worker toolset, stop and say which permission the run needs.
6. **What the workers inherit.** A worker created without an explicit `environment_id` inherits the lead's environment, and with it the same linked repos — so the skills available here are normally available there too. Confirm which of `check-iterate`, `simplify`, `debug`, and the repo's convention skills the workers will actually have, and render the worker prompt accordingly: a prompt that tells a worker to run a slash command it does not have wastes a round. The fallbacks are in `references/fan-out.md`.
7. **No run already in flight.** Search for an open tracking issue for this slug (`Feature: <slug>`, label `feature-run`). If one exists, switch to `--status` behaviour and report instead of starting a duplicate run.
8. **The bounds, as numbers.** Record the run deadline (now + `--deadline`), the worker silence timeouts, and the re-run allowance for a red check — the values are in `references/fan-out.md` and Phase 4. They go in the ledger because they are decisions, and a lead that re-decides "long enough" or "probably a flake" on each wake is not running the same policy twice.
9. **How this run gets accepted.** Establish now how the merged result will be exercised (Phase 7): whether `/qa` is available to a spawned session, whether the feature has a surface a browser can drive, and what URL or command brings the app up. If nothing can exercise it, the run is static-acceptance-only — say so here, not in the closing report.

---

## Phase 1: Plan, and stop for sign-off

Skip if a plan slug was given and its file already exists.

1. Draft the plan with the **`plan` skill**, into `.claude/plans/<slug>.plan.md`. Use the **staged** frontmatter schema — not the flat `todos` form. This is not cosmetic: **one stage = one worker = one branch = one PR**, so the stage boundaries *are* the PR boundaries.
2. Slice for parallelism and against conflict, per `references/fan-out.md`. Every stage needs a `goal`, a `verification` line that is a runnable command, and an `Owns:` line in its body section naming the file globs that stage may touch. Two stages that can run at once must have disjoint `Owns` sets.
3. Order stages by dependency. A stage that must land before another is a **merge-order edge**, recorded in the ledger; it does not have to block that stage's *development*, only its merge.
4. **Pre-flight the slicing** — the mechanical checks in `references/fan-out.md`: every stage complete, every `Owns` glob resolving to real paths, concurrent stages disjoint, every file the todos need owned by exactly one stage, dependency graph acyclic. Fix failures in the plan and re-run it. This costs seconds and it is the only chance to catch a bad slice before four containers are already acting on it.
5. **Write the acceptance criteria** — numbered, observable, derived from the requirements and not from the stages, per `references/acceptance.md`. They are what Phase 7 checks the merged result against. Writing them now, before any code exists, is the point: criteria written at the end get written to match what was built.
6. Present the plan **and the criteria** and **stop**. This is the one human gate in the whole run — use `AskUserQuestion` to take sign-off, an edit, or a cancel. Do not spawn anything until the plan is accepted. The criteria are part of what is being accepted: they are the sentence the run will be judged by, and this is the last moment a human sees them.

With `--dry-run`, print the fan-out table (slice, branch, owns, depends-on, verification command), the pre-flight result, and the criteria — then stop here.

---

## Phase 2: Publish the plan and open the ledger

Workers clone `main` into empty containers, so the plan must exist on the remote before anyone spawns.

1. Commit the plan file and push it to `feature/<slug>/plan`. Do not merge it and do not push to the default branch.
2. Open the tracking issue — title `Feature: <slug>`, label `feature-run` — with the ledger table from `references/ledger.md`, one row per slice, all `pending`. **The issue is the run's only durable state.** The lead's container and context will not survive the run; the issue will.
3. Record in the issue body: `owner/repo`, base SHA, plan branch, the verification commands from Phase 0, the flags in effect, the round/slice budgets, the bounds from Phase 0.8, and the acceptance criteria as their own table.

---

## Phase 3: Fan out

Follow `references/fan-out.md` exactly. In summary:

1. Take the next slices whose merge-order dependencies do not block *development*, up to `--max-slices` concurrent.
2. **Check first, spawn second** — if the slice's branch or PR already exists, the slice is already running or done; reconcile, never double-spawn.
3. `create_session` per slice with the worker prompt template, `outcome_branch` set to `feature/<slug>/<stage-id>`, a distinctive `title`, and tags `feature:<slug>`.
4. Write the returned **session id into the ledger immediately**, before spawning the next one. A session id that is not in the issue is lost — the lead cannot re-discover its own workers later, because `list_sessions` tag filtering is unavailable to in-session callers.
5. `subscribe_pr_activity` for each PR as it appears, and schedule the first self-wake (`send_later`, ~15 min).

---

## Phase 4: The wake loop

Every wake — a PR event, a scheduled check-in, a worker failure notice — runs the same stateless cycle. **Never trust context; re-derive.**

1. **Read the ledger** (`issue_read`). It, not memory, is the state.
2. **Reconcile** every row against reality: does the branch exist, is there a PR, what is its CI state, its review state, its mergeable state, what does `get_session` say about the worker (`status_bucket: failed` means its turn errored). Write back any row whose real state differs.
3. **Act on exactly one thing per row**, in this priority order:
   - Worker `failed`, or silent past one of the timeouts in `references/fan-out.md` → respawn once, escalate on the second failure.
   - PR conflicted → hand it back to the slice's worker to resolve. The lead never resolves conflicts itself and never force-pushes a worker's branch.
   - PR red → hand the failure back to the worker with the job logs. Never skip, disable, or quarantine a test, and never relax a coverage threshold to get green; a diff that edits coverage config is a blocking review finding. "Flake" is a policy, not a hunch: **one** re-run per failing check per head SHA, logged; a check that fails twice at the same head is real and goes to the worker. A check that is red on the base branch too is not this slice's — log it, do not spend the worker's rounds on it, and let the merge gate hold the PR.
   - PR green and un-reviewed, or with a round outstanding → run the next review round (`references/review-loop.md`).
   - PR green and converged → evaluate the merge gate (`references/merge-gate.md`).
4. **Advance the fan-out** — spawn any slice a merge just unblocked, respecting `--max-slices`.
5. **Check the clock.** Past the deadline, stop spawning and stop starting new review rounds: let the rounds already in flight finish, merge whatever passes its gate, escalate every row that is not `merged`, and go to close-out. The deadline bounds the run, not the work already done — it never abandons an open PR without escalating it, and it never merges something to beat the clock.
6. **Re-arm** the next wake and stop. Re-arm *before* reporting, so a failure in reporting cannot end the run.

The loop ends when every slice is merged or escalated, and the acceptance row (Phase 7) has resolved. Then close out.

---

## Phase 5: Review

Per `references/review-loop.md`, with the same two-agent split `/check-iterate` uses: `pr-adversary` collects, `verifier` refutes. The shape, briefly: each round is a **new** `pr-adversary` with no memory of prior rounds, reviewing the PR's current head; every finding it returns has to survive a `verifier` before anything reaches the worker; confirmed findings go over as **one batch per round**, and the round ends there. There is no discussion. A round with zero confirmed findings is convergence; `--max-rounds` exhausted with findings open is an escalation, never a merge.

---

## Phase 6: Merge

Merge in the dependency order recorded in Phase 1, one at a time, re-checking the gate for each PR at its current head — a gate evaluated before an earlier merge is stale. After each merge, `update_pull_request_branch` on every still-open slice PR and let CI re-run; if updating creates a conflict, that PR goes back to its worker.

---

## Phase 7: Acceptance

Per `references/acceptance.md`. Once every slice is merged or escalated, and **before anything is reported as finished**: every gate so far has read the diff, and none of them has run the software or looked at what was asked for.

1. **Static pass.** One fresh `Agent` reads the merged result through the GitHub tools and rules on each acceptance criterion — MET, PARTIAL, or NOT MET, with evidence, defaulting to NOT MET when it cannot find any.
2. **Dynamic pass.** Spawn the acceptance session against the merged default branch; it runs `/qa` with the criteria as its checklist and posts one verdict comment on the tracking issue behind the `<!-- feature:acceptance -->` marker. It is a ledger row like any other, so the wake loop keeps running until it resolves. `--no-qa` skips this half and the report says so.
3. **Verdict.** All criteria met and a SHIP verdict ends the run. Anything else escalates: one follow-up issue naming the criterion and its evidence, linked from the tracking issue, notified. Never revert, never open a repair slice, never re-plan — the code passed every gate agreed in advance, and what an unmet criterion means is a human's call.

Criteria belonging to an escalated slice are marked `escalated` without being checked; do not let an unbuilt stage read as a failed acceptance.

---

## Phase 8: Close out

1. Unless `--no-report` was passed, publish the run through the **`session-report` skill** and put the artifact link on the tracking issue. A `feature` run is the case `session-report` exists for: hours of work across several PRs that nobody watched, where the only alternative record is a log nobody will read. Give it the ledger as its source — what was asked, what each slice changed, what was verified, every finding with its verdict, the acceptance table, and what escalated.
2. **Propose what the run learned.** Group the review findings by root cause across slices: a mistake several workers made independently, or a false positive the collectors kept raising, is a repo convention nobody wrote down. Put the `CLAUDE.md` line you would add — verbatim and ready to paste, with the PRs that motivated it — in the closing comment and the report. Propose it; never commit it (`references/acceptance.md`).
3. Final comment on the tracking issue: the outcome table, what merged, the acceptance result, what escalated and why, the proposed conventions, and the report link.
4. `unsubscribe_pr_activity` for every PR; `delete_trigger` for the run's check-ins; archive the worker sessions, acceptance included.
5. Close the issue only if every slice merged **and** every criterion was met. An escalation leaves it open — that is the handoff.
6. Report to the human (see below), and `PushNotification` the one-line outcome. The run started because nobody wanted to watch it; it ends by telling them how it went.

---

## Aborting

`/feature --abort <slug>`: interrupt and archive every worker session in the ledger, unsubscribe from the PRs, delete the run's triggers, comment the abort reason on the tracking issue, and leave the branches and PRs exactly as they are. **Aborting never closes PRs and never deletes branches** — the work is the user's to keep or discard.

---

## Final summary

Short, whatever the outcome:

```
/feature: {slug} — {N merged | N merged, M escalated | aborted}

  {stage-id}  PR #{n}  {merged | escalated: reason | open: state}
  ...
  Review: {total rounds across PRs}, {findings} confirmed and fixed, {refuted} refuted
  Acceptance: {n/n criteria met} — QA {ship | fail | not run: reason}
  Escalated: {one line each, or "none"}
  Learned: {proposed CLAUDE.md line, or "nothing recurring"}
  Ledger: {issue url}
  Report: {artifact url}
```

---

## Design notes

- **The plan's stages are the unit of everything.** Slice, branch, session, PR, review scope, and merge order all key off the same stage id, so there is exactly one place where "how is this work divided" is decided — in a plan a human accepted.
- **GitHub is the process memory.** On cloud, the lead is as ephemeral as the workers: containers get reclaimed, context gets compacted, wakes arrive hours apart. Any state that lives only in the lead's head is state the run loses. The tracking issue is chosen over a state file for the same reason the plan is pushed rather than kept local — it survives the container, and a human can read it mid-run.
- **Every wake is stateless and idempotent.** The lead re-derives the world on each wake and guards every action on "has this already happened". That is what makes a dropped event, a duplicate event, and a resumed-after-hours session all behave identically.
- **Fresh context is a spawn property, not an instruction.** "No going back and forth" cannot be achieved by telling a reviewer not to argue; it is achieved by the reviewer being a new agent each round that has never seen the previous round. See `references/review-loop.md`.
- **Borrow, do not restate.** The worker's pre-PR verification is `/check-iterate`, its pre-PR quality pass is `/simplify`, a red build is `/debug`, the write-up is `/session-report`, and the review loop uses the same `checker`-and-`verifier` split those skills already established — `pr-adversary` exists only because reviewing a PR through the API at a fixed head SHA is genuinely a different job from reviewing a local diff. Every mechanic this skill restates in its own words is a mechanic that drifts from the skill that owns it.
- **Acceptance is a different question from the gate, asked of a different thing.** The gate asks whether this diff is safe to merge and answers it from the diff. Acceptance asks whether the feature exists and answers it from the merged branch and a running app. A run that only ever asks the first question can merge four impeccable PRs that do not add up to what was requested, and report success — which is the specific way autonomous systems lose people's trust.
- **A bound is a number or the lead re-decides it every wake.** "Long past its spawn", "probably a flake", "this is taking a while" are judgements, and an ephemeral lead making them from a compacted context makes them inconsistently. Deadlines, silence timeouts, and the one re-run per check live in the ledger with everything else the run must not re-invent.
- **The gate is machine-checkable or it is not a gate.** Coverage is a command's exit code, mergeability is GitHub's answer, convergence is a round with zero confirmed findings. Nothing in the merge path is the lead's opinion.
