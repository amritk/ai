---
name: pr-land
description: Take an open pull request all the way to merged — optionally review it first, then watch it, fix red CI and conflicts on it, and merge on green at the exact head that was verified. Use for "merge it when it's green", "review this PR then merge it", "fix the conflicts and get this merged", "land #123", "get these merged", or right after opening a PR that should go to main without being watched. One PR, or a short list in order; planned multi-PR work from requirements is /feature.
argument-hint: "<pr number | url> [more PRs…] [--review] [--no-merge]"
---

# pr-land

A PR is done when it is on the default branch, not when it is green. This skill drives one PR there: watch it, repair what breaks on it, merge it on facts read at its current head, and say what happened. It is the per-PR half of `/feature`, for work that was not planned as a run.

Invoke with `/pr-land <pr> [more…] [--review] [--no-merge]`.

- `--review`: review the PR before driving it (`pr-review`); also implied by "review this then merge it".
- `--no-merge`: drive it to green and mergeable, then stop and report.

---

## Phase 0: Preconditions

1. **Repo and PR.** Resolve `owner/repo` from `origin`. Read the PR: open, not draft, base branch, head branch, full head SHA, author.
2. **Whose branch.** Fixes are pushed only to a branch the user owns or asked you to drive. On someone else's PR, this skill watches, reports, and merges if asked — it does not push. Never rewrite history on any branch, never force-push.
3. **Who may merge.** If `mergeable_state` is `blocked` because a human approval or code-owner review is required, no push will change that: say so once, drive the PR to green, and stop in `--no-merge` behaviour.
4. **House rules.** Read the repo's `CLAUDE.md`. Its commit message format and attribution rules apply to every commit, comment, and merge message this skill writes.
5. **How to reproduce CI.** Read `.github/workflows/` for the PR's jobs and note the local command that runs what each job runs, so a red job is reproduced with the same steps the first time.

## Phase 1: Review, if asked

Run `pr-review <n>` with only the review part of the user's ask — what to look for, never "then merge it" — or with its default prompt. The merge stays here. Where `pr-review` is not available, review the diff against its base adversarially yourself, once. On the user's own PR, fix every blocking finding before driving to merge. On someone else's, the review is the deliverable: post it and stop unless told to merge regardless.

## Phase 2: Watch without polling

`subscribe_pr_activity` for the PR (load it with `ToolSearch`) and schedule **one** safety-net check-in with `send_later`, 60 minutes out. Then end the turn. PR events wake the session; the check-in only catches a CI run that never reports. Never wait with `sleep` or a polling loop. At most one check-in is pending at a time.

## Phase 3: On every wake

1. **Drop what does not concern the current head.** An event for a head that has since been superseded, or the echo of your own push or comment, ends the wake in one line.
2. **Red CI at the head** → read the failing job's log by saving it and grepping for the failure, not by printing it. Reproduce it locally with that job's command, fix it in the order `/debug` uses (reproduce, localise, one hypothesis, pin with a test), push once. Never skip, disable, or quarantine a test, and never relax a threshold.
   - **Flake policy**: one re-run per failing check per head SHA. If the session cannot re-run jobs, ask the user once to click re-run, and say which check. A check that fails twice at one head is real.
   - **Red on the default branch too**: it is not this PR's failure. Report it and do not fix it here unless asked; wait for the default branch to go green, then update.
3. **Conflict or behind** → merge the default branch in, resolve, regenerate any generated files with the repo's tooling (never hand-merge them), run the tests the conflict touched, push.
4. **Green** → evaluate the gate.

Re-arm the check-in only while the PR is not yet merged.

## Phase 4: The gate

All of these, read fresh at the PR's **current head SHA** immediately before merging:

1. Every required check concluded `success`. Missing, pending, skipped, or cancelled is not success. If the repo reports more than pass/fail (shard summaries, skip counts, "degraded" lines), read them: a shard that skipped what it should have run is not green.
2. `mergeable` is true and `mergeable_state` permits merging.
3. No unresolved blocking review comment, and no requested-changes review.
4. The head is the SHA you verified — if it moved, start the gate again.
5. `--no-merge` is not set.

These are facts, not judgements: "the failure looks unrelated" is not condition 1. It is the same gate `/feature` uses ([merge gate](../feature/references/merge-gate.md)), minus the conditions that only exist in a planned run.

## Phase 5: Merge

- The repo's merge method (squash where the repo squashes), with the **full 40-character head SHA** as the expected head.
- Write the merge message from the PR's final state, in the repo's commit convention.
- Never admin-merge, bypass protection, disable a check, or dismiss a review. If protection blocks the merge, protection is right: report it.
- Leave branch deletion to the repo's auto-delete setting.

With several PRs, land them one at a time in the order given (or dependency order). After each merge the default branch has moved: re-evaluate the next PR's gate from scratch, and update it only if GitHub requires it or it conflicts.

## Phase 6: Close

`unsubscribe_pr_activity`, delete the pending check-in, and report:

```
/pr-land: #{n} {merged as <sha> | green, not merged: <reason> | blocked: <reason>}
  Fixed on the way: {one line each, or "nothing"}
  Re-runs: {check @ sha, or "none"}
```
