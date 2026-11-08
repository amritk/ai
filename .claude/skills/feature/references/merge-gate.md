# The merge gate

The only thing standing between an autonomous worker and `main`. Every condition here is a fact read from GitHub or a command's exit code — none of them is the lead's assessment.

## The gate

Evaluate **at the PR's current head SHA**, immediately before merging. A gate evaluated before an earlier merge, or before the worker's last push, is stale and must be re-run.

The facts for conditions 3–6 come from one fresh `subagent_type: "run-reconciler"` agent in `gate` mode, given the PR number, the stage's `Owns` globs, the ledger's required-checks line, and the globs `CODEOWNERS` assigns to a team (the lead reads `CODEOWNERS` once in Phase 0; the reconciler has no file-reading tool). It returns one table of facts at the head SHA; the lead applies the conditions. That keeps the gate's raw reads out of the lead's context, and every run reads the gate the same way instead of each lead writing its own prompt for it.

1. **Review converged** — a full round with zero blocking findings surviving verification. Not "the last round was small". Non-blocking findings sent at convergence do not hold the gate.
2. **`skipped` and `disputed` are empty.** Anything awaiting a human call blocks the merge by definition.
3. **CI green on this head.** Every required check concluded `success`. Not "green on the previous commit", not "the failure looks unrelated". A required check that never ran is not green.
4. **GitHub says mergeable.** `pull_request_read` reports `mergeable: true` and a `mergeable_state` that permits merging. Trust GitHub's answer over your own reasoning about conflicts — it knows about protection rules, required reviews, and stale branches that you do not.
5. **Diff is inside the slice.** Files changed ⊆ the stage's `Owns` globs. A PR that grew outside its lane merges into a conflict with a sibling.
6. **No sensitive paths.** If the diff touches any of these, escalate regardless of everything above:
   - `.github/workflows/**`, CI configuration, release or publish scripts
   - coverage, lint, or type-check configuration
   - authentication, authorization, secrets handling, crypto
   - dependency manifests beyond the packages the stage legitimately added
   - anything the repo's CODEOWNERS assigns to a specific team
7. **Merge order satisfied.** Every stage this one depends on is already merged.
8. **`--no-merge` not set.**

All eight, or it does not merge.

## Merging

- Use the repo's configured merge method; prefer squash where the repo squashes. Pass the full 40-character head SHA as the expected head, never a short one: the API rejects short SHAs. Leave branch deletion to the repo's auto-delete setting. Deleting a branch from the session is usually refused as destructive; if it is, do not retry, and list the branch in the close-out comment instead.
- **Never bypass.** No admin merge, no force-merge, no disabling a required check, no dismissing a review to get past protection. If protection blocks the merge, protection is right and the run escalates.
- One at a time, in dependency order. A converged PR merges at its current head, on the CI that ran there, **unless it needs an update** from the default branch first (below). An update costs a merge, a regeneration, a full suite run and a CI cycle, one PR after another. A PR whose files no other PR touched gets nothing for that cost that the acceptance pass (`acceptance.md`) does not already check, against the whole merged result.
- The lead writes the squash commit message at merge from the PR's final state, so the message meets the repo's convention without a review round spent on the PR body.
- If updating a branch produces a conflict, that PR goes back to its worker. The lead does not resolve conflicts in code it did not write.

### When a PR updates before it merges

A PR updates from the default branch before it merges if any of these holds:

1. **GitHub requires it.** `mergeable_state` is `behind` (the repo requires branches to be up to date), or the PR is conflicted (`dirty`). A conflicted PR goes back to its worker whatever its turn.
2. **It depends on a stage that merged after its base.** It has never been tested against the code it consumes, and that is the combination most likely to break.
3. **It changes a generated file and the default branch has moved since its base.** Generated output can depend on files the PR never touched, so it has to be regenerated against the new base.

Otherwise it merges as it is. To update, message the worker to update from the default branch: it merges the new base, regenerates the generated files, runs the full suite and pushes. The gate is then re-evaluated from scratch once CI is green on that head. PRs further back in the order are never updated ahead of their turn.

**A red default branch stops the run's merges.** Before merging a PR that did not update, read CI on the default branch at its current head (`actions_list`). If it is red after one of this run's merges, two PRs that were green apart have broken together. Merge nothing more. Escalate it, naming the merges since the default branch was last green. Updating the remaining PRs would only make them red as well, and the run does not repair code.

## Escalation

Escalating is a normal outcome, not a failure. It means: stop acting on this slice, leave everything exactly as it is, and make the state findable.

1. Mark the ledger row `escalated` with a one-line reason.
2. Comment once on the **PR** — what is blocking, what was tried, what a human needs to decide. Not a transcript.
3. Log it on the tracking issue and leave the issue open.
4. **Tell the human it happened.** `PushNotification` (load it with `ToolSearch`), once per escalation, with the slice, the one-line blocker, and the PR link — an escalation nobody hears about is a run that quietly stopped. The other slices keep going; this is a notification, not a halt. Log that you sent it, so a later wake re-reading the same row does not send it again.
5. Keep the PR open, the branch intact, and the subscription live if the blocker could clear on its own (a flaky required check, a pending human approval). Drop the subscription if it cannot.
6. Carry it into the final summary. An escalation that is only visible on a PR nobody opens did not escalate.

Escalate — do not retry — on: budget exhausted with findings open, stalemate, a second worker failure, a sensitive-path diff, protection requiring a human, or any gate condition you cannot evaluate. "I could not check it" is never "it passed".

## Waiting on people

Where branch protection requires a human approval or a code-owner review, no push can satisfy it and no amount of waking will change it. Say so once — on the PR and in one `PushNotification`, because the run is now blocked on a person who does not know it — keep the PR green and conflict-free, and stop. Do not push to "refresh" the PR — a push can dismiss approvals it already has. Keep the check-ins running so a merge can happen the moment the approval lands, and report it in the summary as waiting on reviewers rather than as work in progress.
