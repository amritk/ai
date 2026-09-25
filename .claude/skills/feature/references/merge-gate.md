# The merge gate

The only thing standing between an autonomous worker and `main`. Every condition here is a fact read from GitHub or a command's exit code — none of them is the lead's assessment.

## The gate

Evaluate **at the PR's current head SHA**, immediately before merging. A gate evaluated before an earlier merge, or before the worker's last push, is stale and must be re-run.

1. **Review converged** — a full round with zero findings surviving verification. Not "the last round was small".
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

- Use the repo's configured merge method; prefer squash where the repo squashes. Delete the branch after merge.
- **Never bypass.** No admin merge, no force-merge, no disabling a required check, no dismissing a review to get past protection. If protection blocks the merge, protection is right and the run escalates.
- One at a time, in dependency order. After each merge: `update_pull_request_branch` on every still-open slice PR, let CI re-run against the new base, and re-evaluate their gates from scratch. A PR that was green ten minutes ago is not green now — it has a new base.
- If updating a branch produces a conflict, that PR goes back to its worker. The lead does not resolve conflicts in code it did not write.

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
