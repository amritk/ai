# Fan-out — one slice, one cloud session, one PR

How the lead turns an accepted plan into parallel workers on Claude Code cloud, and what it does when one of them dies.

## Slicing rules

A slice is a plan **stage**. Get these right in Phase 1 and the rest of the run is mechanical; get them wrong and you will spend the run resolving conflicts between your own workers.

- **One PR's worth of work.** If a stage cannot be reviewed in one sitting, it is two stages.
- **Disjoint ownership.** Every stage's body carries an `**Owns:**` line of file globs. Two stages that run concurrently must not overlap. Shared files (a barrel export, a router table, a lockfile) belong to exactly one slice; the others wait behind a merge-order edge.
- **Independently verifiable.** The stage's `verification` field is a command that passes or fails on its own, against its own branch, with nothing else merged. A stage that can only be verified after a sibling lands is a dependent stage, not a parallel one.
- **Development order vs merge order.** A dependency between stages blocks the *merge*, not necessarily the *work*. Only make a stage wait to start if it genuinely cannot be written against `main` — usually because it consumes an interface the other stage introduces.

`Owns` lives in the stage's body section rather than the frontmatter on purpose: the `plan` skill's stages schema is fixed and the plan-preview extension renders it, so the run's own metadata stays out of it.

## Pre-flight — check the slicing before anyone is spawned

Run this in Phase 1, against the plan file, before the plan is put to the human. Every check is mechanical, it costs seconds, and each one fails hours later as a stuck worker or a conflict between two sessions you started yourself.

1. **Every stage is complete.** A `goal`, a `verification` that is a runnable command and not a description of one, an `Owns:` line, and at least one todo. A stage missing any of them cannot be rendered into a worker prompt.
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

**3. Record the returned session id in the ledger before spawning the next slice.** This is not bookkeeping; it is the only copy. `list_sessions` tag filtering is OAuth-only and errors for in-session callers, so a lead that loses a session id cannot get it back — it can only find the *branch*, and will have to respawn to touch the work again.

**4. Subscribe and arm.** `subscribe_pr_activity` once the PR exists; `send_later` a first check-in ~15 minutes out.

## The worker prompt

Workers wake in an empty container with no memory of the planning conversation. Everything they need goes in the prompt — inline, not by reference, except the plan itself which is also fetchable.

```
You are implementing one stage of an accepted plan. Work only this stage.

Repo: {owner/repo}          Base: {default branch} at {base SHA}
Branch: feature/{slug}/{stage-id}   (already assigned — commit and push here, nothing else)

## Your stage
{stage title}
Goal: {goal}
Owns (do not create or edit files outside these globs): {owns globs}
Verification: {verification command}

Todos:
{the stage's todos, verbatim}

Full plan, for context on how your stage fits with the others:
  git fetch origin feature/{slug}/plan
  git show origin/feature/{slug}/plan:.claude/plans/{slug}.plan.md
Read it. Do not implement anything from another stage — another session owns it
and is working in parallel right now.

## Definition of done
1. The stage's todos are implemented, and nothing outside your Owns globs changed.
2. `{test command}` passes.
3. `{coverage command}` passes with the repo's configured thresholds. 100% coverage
   of the lines you added is the bar. If you cannot reach it, say which lines and why
   in the PR body — do NOT lower a threshold, add an ignore comment, or skip a test.
   Changing coverage configuration is out of scope for this stage, full stop.
4. `{lint command}` and `{typecheck command}` pass.
5. Before you open the PR, run /check-iterate and fix what it confirms. If that
   command is not available in your session, review your own diff against
   {default branch} adversarially yourself and fix what you find — do not skip it.
6. Then run /simplify over the same diff and apply what it returns: reuse what the
   repo already has instead of adding a parallel version of it, drop scaffolding you
   no longer need, and keep each piece at the altitude it belongs at. If that command
   is not available, re-read your diff for the same things. Re-run `{test command}`
   and `{coverage command}` afterwards — a cleanup that breaks a test is not a
   cleanup. This pass never changes behaviour and never widens your Owns globs.
7. Open a PR from your branch to {default branch}. Title: `{stage title}`.
   Body: what changed and why, the verification commands you ran with their results,
   and `Part of #{issue number}` so it links to the run.

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
- You will get review comments as a single batch. Address every one of them in one
  push, then stop. Do not reply to argue; if a finding is wrong, say so in one line
  on that thread and move on.
```

## Concurrency

Default `--max-slices 4`. The cap exists for review throughput, not compute: every open PR is a review loop the lead has to drive on every wake, and a lead juggling ten PRs per wake does each of them badly. Spawn the next slice when one merges or escalates.

## When a worker dies

Cloud workers fail in ways a subagent does not — container reclaimed, turn errored, environment setup broken. Detect it on any wake via `get_session`: `status_bucket: failed` means its last turn errored (plain `status` reads `idle` either way, so check the bucket).

Silence is the harder case, so it is a clock rather than a judgement — an unattended lead that decides "long enough" by feel decides it differently on every wake:

- **No branch 45 minutes after spawn** → treat as failed. A healthy worker has pushed something by then; one that has not is usually a container that never came up.
- **No new commit for 90 minutes** on a row that is `running` or `fixing` → `SendMessage` the worker once, naming what the ledger is waiting for. No commit 90 minutes after that → treat as failed.
- **`status_bucket: failed`** → failed immediately, whatever the clocks say.

Then, by what is on the branch:

- **Branch has commits** → the work is not lost. `SendMessage` the worker to continue (this re-provisions its container; `unarchive_session` first if it was archived). Its context is still the best context that exists for that slice.
- **Branch is empty or absent, first failure** → respawn once, same prompt plus one line naming what failed. Update the ledger's session id to the new session.
- **Second failure** → escalate. Mark the row `escalated`, comment the reason on the tracking issue, and stop spawning for that slice. Two clean failures is a broken slice or a broken environment, and a third session will not discover which.

Workers cannot report back — a cloud session receives messages but has no reply channel to the lead. So never wait for a worker to say it is done, and never send "are you finished?". **Done is observable state**: a branch with commits and an open PR. That is the only completion signal the lead uses.
