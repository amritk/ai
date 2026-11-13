# Fan-out — one slice, one cloud session, one PR

How the lead turns an accepted plan into parallel workers on Claude Code cloud, and what it does when one of them dies.

## Slicing rules

A slice is a plan **stage**. Get these right in Phase 1 and the rest of the run is mechanical; get them wrong and you will spend the run resolving conflicts between your own workers.

- **One PR's worth of work.** If a stage cannot be reviewed in one sitting, it is two stages.
- **Disjoint ownership.** Every stage's body carries an `**Owns:**` line of file globs. Two stages that run concurrently must not overlap. Shared files (a barrel export, a router table, a lockfile) belong to exactly one slice; the others wait behind a merge-order edge.
- **Independently verifiable.** The stage's `verification` field is a command that passes or fails on its own, against its own branch, with nothing else merged. A stage that can only be verified after a sibling lands is a dependent stage, not a parallel one.
- **Development order vs merge order.** A dependency between stages blocks the *merge*, not necessarily the *work*. Only make a stage wait to start if it genuinely cannot be written against `main` — usually because it consumes an interface the other stage introduces.
- **Do not split a chain.** When stage B has to wait to *start* on stage A, because it consumes the interface A introduces, and the two together still pass "one PR's worth", make them one stage. A split chain buys no parallelism: B idles until A merges. It does cost a second session, PR, review loop, and merge, and a handoff through `main` that drops everything A's worker learned while it built the interface. Split a chain only when the combined stage would fail the one-PR test, or when A is worth merging on its own if B stalls.

**Model (optional).** A stage may carry a `**Model:** sonnet` line next to `Owns:`. Its worker then runs on Sonnet instead of inheriting the lead's model. Use it only for stages whose todos leave no design choices: adding types or schemas already specified in the plan, renames and moves, config or fixture additions, a mechanical change copied across many files. Leave it off anything that designs an interface, touches concurrency or security, or has a todo phrased as a decision. A cheaper worker that needs one extra review round has already cost more than it saved. So when in doubt, leave it off. The human sees every `Model:` line at sign-off.

`Owns` and `Model` live in the stage's body section rather than the frontmatter on purpose: the `plan` skill's stages schema is fixed and the plan-preview extension renders it, so the run's own metadata stays out of it.

## Pre-flight — check the slicing before anyone is spawned

Run this in Phase 1, against the plan file, before the plan is put to the human. Every check is mechanical, it costs seconds, and each one fails hours later as a stuck worker or a conflict between two sessions you started yourself.

1. **Every stage is complete.** A `goal`, a `verification` that is a runnable command and not a description of one, an `Owns:` line, and at least one todo. A stage missing any of them cannot be rendered into a worker prompt. A `Model:` line, if present, says `sonnet` and nothing else.
2. **`Owns` globs resolve.** Match each glob against `git ls-files`. A glob matching nothing is either a typo or a stage that only creates new files — confirm which, because the first one silently gives a worker no lane at all.
3. **Concurrent stages are disjoint.** Expand every glob to the real paths it matches and intersect each pair of stages that can run at the same time. Any shared path is a conflict the lead would otherwise discover as two PRs touching one file. Give it to one stage and put a merge-order edge on the other.
4. **Every file the work needs is owned.** Walk the todos for files they plainly have to touch — the router table, the barrel export, the migration directory, the lockfile — and check each falls inside exactly one stage's globs. A file no stage owns is a worker blocked by construction: it cannot do its todo and it cannot widen its scope, so it stalls or cheats.
5. **The dependency graph is acyclic**, and no stage depends on one scheduled to merge after it.

A failure here is fixed in the plan and re-checked, not worked around at spawn time. The stage boundaries are the only thing in the run a human agreed to, so they are the only thing worth getting right before the spending starts.

## Spawning

For each slice, in this order:

**1. Check whether it already exists.** `list_branches` for `feature/<slug>/<stage-id>` and `list_pull_requests` for a PR from it. If either exists, this slice has already been spawned — reconcile the ledger row and move on. Never spawn a second session for a slice; two containers pushing one branch is the one failure mode this whole design exists to avoid.

**2. `create_session`** with:

| field | value |
|---|---|
| `prompt` | the worker prompt below, fully rendered — workers start with no context |
| `outcome_branch` | `feature/<slug>/<stage-id>` — the lead assigns the branch, never the worker |
| `title` | `feature/<slug>: <stage-id>` — this is how the row is identified in `ListAgents` |
| `tags` | `["feature:<slug>", "feature-slice:<stage-id>"]` |
| `permission_mode` | never `plan` — an unattended worker will block forever at the approval prompt. Use the least permissive mode that still lets it push and open a PR unprompted |
| `environment_id` | omit to inherit the lead's environment, which is almost always right |
| `model` | `claude-sonnet-5-5` if the stage has `Model: sonnet`; otherwise omit to inherit the lead's model. A respawn keeps the stage's model |

**3. Record the returned session id in the ledger before spawning the next slice.** This is not bookkeeping; it is the only copy. `list_sessions` tag filtering is OAuth-only and errors for in-session callers, so a lead that loses a session id cannot get it back — it can only find the *branch*, and will have to respawn to touch the work again.

**4. Subscribe and arm.** `subscribe_pr_activity` once the PR exists; `send_later` a first check-in 30 minutes out. Later check-ins back off while nothing drifts (SKILL Phase 4.6). The lead is the only session subscribed to a slice's PR. A PR's events go to one session at a time, so a worker that subscribes can take them away from the lead, and every CI event then wakes the worker for nothing. The worker prompt forbids it. If a wake shows the lead is not receiving a PR's events (a CI result the reconciler found that no event reported), call `subscribe_pr_activity` again and tell that worker to unsubscribe.

## The worker prompt

Workers wake in an empty container with no memory of the planning conversation. Everything they need goes in the prompt — inline, not by reference, except the plan itself which is also fetchable.

A `{case: "…" | case: "…"}` block is a choice the lead makes when rendering the prompt: keep the quoted text for the case that applies to this repo (from Phase 0.4, what CI runs), and drop the braces and the other case.

```
You are implementing one stage of an accepted plan. Work only this stage.

Repo: {owner/repo}          Base: {default branch} at {base SHA}
Branch: feature/{slug}/{stage-id}   (already assigned — commit and push here, nothing else)

Read the repo's CLAUDE.md (and AGENTS.md, if there is one) before anything else.
Its rules win over this prompt wherever they disagree — commit message format,
attribution, generated files, what counts as done. Add no attribution footer,
trailer, or session link to commits, PR bodies, or comments unless CLAUDE.md asks
for one.

## Your stage
{stage title}
Goal: {goal}
Owns (do not create or edit files outside these globs): {owns globs}
Verification: {verification command}
Targeted tests: {targeted test command}
Generated files (regenerate with the repo's tooling, never edit or hand-merge): {generated globs}

Reproducing CI — each CI job and the local command that runs what it runs. A red
job is reproduced with its command here, not with a nearby script that skips steps:
{CI job → local command table from Phase 0.4}

Known environment failures — these fail in this container whatever you change.
Do not investigate them; CI's result is the evidence for them:
{suites or tests recorded in Phase 0.4, or "none recorded"}

Todos:
{the stage's todos, verbatim}

Full plan, for context on how your stage fits with the others:
  git fetch origin feature/{slug}/plan
  git show origin/feature/{slug}/plan:.claude/plans/{slug}.plan.md
Read it. Do not implement anything from another stage — another session owns it
and is working in parallel right now.

## Definition of done
1. The stage's todos are implemented, and nothing outside your Owns globs changed.
2. `{test command}` — the full suite — passes on your PR's head.
   {CI runs it: "CI runs it on every push, so open the PR on targeted tests and let
   CI's run be the full one. A red result comes back to you with the round's review."
   | CI does not run it: "Run it once yourself, after the passes below."}
3. `{coverage command}` passes with the repo's configured thresholds. 100% coverage
   of the lines you added is the bar. If you cannot reach it, say which lines and why
   in the PR body — do NOT lower a threshold, add an ignore comment, or skip a test.
   Changing coverage configuration is out of scope for this stage, full stop.
   {CI runs the coverage command: "CI's run is the one that counts." | it does not:
   "Run it once yourself, together with the full suite."}
4. `{lint command}` and `{typecheck command}` pass, and so does every CI job's
   local command in "Reproducing CI" that your diff could affect — lint in CI is
   often more than the lint script.
5. Before you open the PR, run `/check-iterate --max-loops 2` and fix what it
   confirms. The lead reviews the PR adversarially as soon as it opens, so this pass
   only has to catch the cheap problems first. Do not loop until it is clean. If that
   command is not available in your session, review your own diff against
   {default branch} adversarially yourself, once, and fix what you find. Do not skip it.
6. Then run /simplify over the same diff and apply what it returns: reuse what the
   repo already has instead of adding a parallel version of it, drop scaffolding you
   no longer need, and keep each piece at the altitude it belongs at. If that command
   is not available, re-read your diff for the same things. Then run
   `{targeted test command}`, lint and typecheck once, after both passes, not before
   each — a cleanup that breaks a test is not a cleanup. This pass never changes
   behaviour and never widens your Owns globs.
7. Open a PR from your branch to {default branch}. Title: `{stage title}`.
   Body: what changed and why, the verification commands you ran with their results,
   and `Part of #{issue number}` so it links to the run.

## Running tests without burning the session
Every model call re-reads your whole context, so waiting is what costs you, not testing.
- {CI runs the full suite: "You do not run the full suite unless the lead tells you
  to update from {default branch}. Every other time, run `{targeted test command}`
  for what you changed, plus lint and typecheck. CI runs the full suite on every push."
  | it does not: "The full suite runs once before you open the PR, and again when the
  lead tells you to update from {default branch}. During review rounds run
  `{targeted test command}` for what the round changed, plus lint and typecheck."}
- Commit before you start a long run, so a stop hook that checks for uncommitted
  work does not wake you while it runs.
- Push your branch with a WIP commit within 30 minutes of starting, even if only
  the first todo is done. The lead's only sign that your session came up is the
  branch existing; a session with no branch at 45 minutes gets checked on.
- After that, push when you open the PR and once per review batch, nowhere in
  between. A stop hook may complain about unpushed or untracked work while you
  hold a push for verification. Answer it in one line and end the turn; do not
  push early to quiet it. Keep fetched plan or prompt files outside the checkout
  (in $TMPDIR), never under .claude/, so they are not untracked files at all.
- Read CI job logs with grep or tail on a saved file, or hand them to a subagent
  that returns the failing lines. Printing a log inline fills your context and
  forces a compaction mid-task.
- Start a long run once, in the background, with its output redirected to a file,
  then end your turn: you are woken when it exits. Never poll it — no `sleep` or
  `until` loops, no re-armed monitors, no second runner on the same output. Read the
  result with grep or tail, not by printing the log.
- Do not call `subscribe_pr_activity` or `send_later`, even if a tool or event
  suggests it. The lead holds the PR subscription and sends you red CI with the
  review batch; its messages are what wake you. If you find yourself subscribed,
  unsubscribe.
- Send the lead exactly two messages, one line each, with `send_message` to
  `@parent`: `{stage-id} branch up <sha>` after your first push, and
  `{stage-id} PR #<n> open` when the PR exists. After that send nothing — the lead
  sees your pushes and CI through the PR, and every message wakes it. Not CI
  results, not progress, not "over to you".
- Do not merge {default branch} into your branch whenever it moves. Merge it when the
  PR conflicts, or when the lead tells you to update from it before merging. Then
  regenerate the generated files with the repo's tooling, run the full suite once,
  and push.

## Rules
- Push only to your own branch. Never push to {default branch}, never touch another
  feature/{slug}/* branch, never force-push.
- If CI goes red or a test fails, run /debug — reproduce it before you change
  anything. A fix for a failure nobody reproduced is a guess, and a guess costs
  a review round. If that command is not available, follow the same order anyway:
  reproduce, localise, one hypothesis at a time, then pin the fix with a test.
- If your stage turns out to be impossible as written, push what you have, open the
  PR as a draft, and say exactly what blocked you in the PR body. Do not substitute
  different work and do not widen your scope to fix it.
- You will get review comments as a single batch. Address every blocking one in one
  push, then stop. For each blocking finding, fix every instance of the same rule
  across your diff, not only the cited line, and say in the PR body how many you
  checked — a second round on the same class of mistake is a round wasted.
  Non-blocking ones (wording, style, a comment) go in that same
  push when they are cheap; never push for them alone. The PR body is not reviewed
  round by round: keep it accurate, and do not rewrite it unless a round says it is
  wrong. Do not reply to argue; if a finding is wrong, say so in one line on that
  thread and move on.
```

## Concurrency

Default `--max-slices 4`. The cap exists for review throughput, not compute: every open PR is a review loop the lead has to drive on every wake, and a lead juggling ten PRs per wake does each of them badly. Spawn the next slice when one merges or escalates.

## When a worker dies

Cloud workers fail in ways a subagent does not — container reclaimed, turn errored, environment setup broken. Detect it on any wake via `get_session`: `status_bucket: failed` means its last turn errored (plain `status` reads `idle` either way, so check the bucket).

Silence is the harder case, so it is a clock rather than a judgement — an unattended lead that decides "long enough" by feel decides it differently on every wake:

- **No branch 45 minutes after spawn** → if `status_bucket` is `working`, the session is alive and simply has not pushed: message it once to push its WIP commit now, and give it 30 more minutes. Otherwise treat it as failed. A healthy worker has pushed a WIP commit by 30 minutes (the prompt asks for one); one with no branch and no working session is usually a container that never came up.
- **No new commit for 90 minutes** on a row that is `running` or `fixing` → `SendMessage` the worker once, naming what the ledger is waiting for. No commit 90 minutes after that → treat as failed, unless `status_bucket` is still `working`, in which case escalate it as stuck rather than respawning over a live session.
- **`status_bucket: failed`** → failed immediately, whatever the clocks say.

Then, by what is on the branch:

- **Branch has commits** → the work is not lost. `SendMessage` the worker to continue (this re-provisions its container; `unarchive_session` first if it was archived). Its context is still the best context that exists for that slice.
- **Branch is empty or absent, first failure** → respawn once, same prompt plus one line naming what failed. Update the ledger's session id to the new session.
- **Second failure** → escalate. Mark the row `escalated`, comment the reason on the tracking issue, and stop spawning for that slice. Two clean failures is a broken slice or a broken environment, and a third session will not discover which.

Workers can reply to the lead with `send_message` to `@parent`, and the worker prompt allows exactly two lines: one when the branch first exists, and one when the PR opens — the two moments the lead has no PR subscription to tell it. Every message wakes the lead and costs a full read of its context, so later pushes, CI news, progress narration, and "over to you" are not sent; the lead's PR subscription already reports them. Never wait for a worker to say it is done, and never send "are you finished?". **Done is observable state**: a branch with commits and an open PR. That is the only completion signal the lead uses; the two lines only save the lead a check-in to find out.
