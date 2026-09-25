# The ledger — durable state for an ephemeral lead

On cloud there is no shared filesystem and no long-lived process. The lead session's container is reclaimed on inactivity, its context is compacted, and it resumes hours later on a wake with no reliable memory of what it started. A run that keeps its state in the lead's head loses the run.

So the run's state lives in **one GitHub issue**, and every wake begins by reading it.

## Why an issue

- It outlives every container in the run.
- Workers can read it (`issue_read`) and link their PRs to it, so the graph is navigable from either end.
- A human can open it mid-run and see exactly what is happening without asking, which is the difference between "autonomous" and "opaque".
- It is the handoff artifact when something escalates.

A state file in the repo would need a branch, a push, and a merge to update — three ways to conflict with the workers. The issue has none of that.

## Schema

Title `Feature: <slug>`, label `feature-run`, body:

```markdown
## Run
- repo: {owner/repo}
- base: {default branch} @ {base SHA}
- plan: `feature/{slug}/plan` → `.claude/plans/{slug}.plan.md`
- flags: max-slices {N}, max-rounds {N}, {--no-merge if set}
- verification: test `{cmd}` · coverage `{cmd}` · lint `{cmd}` · types `{cmd}`
- bounds: deadline {ISO timestamp} · no-branch 45m · no-commit 90m · re-runs 1 per check per head

## Acceptance
| # | criterion | static | qa | state |
|---|---|---|---|---|
| 1 | a signed-out visitor hitting /invite/:token sees the accept screen | MET | pass | met |
| 2 | an expired token shows the expiry notice, not a 500 | NOT MET | fail | escalated |

## Slices
| stage | owns | depends on | session | branch | PR | CI | rounds | state |
|---|---|---|---|---|---|---|---|---|
| api-types | `src/types/**` | — | `session_01ABC…` | `feature/foo/api-types` | #41 | green | 2/10 | merged |
| api-client | `src/client/**` | api-types | `session_01DEF…` | `feature/foo/api-client` | #42 | red | 1/10 | fixing |
| ui-panel | `src/ui/panel/**` | api-client | — | — | — | — | — | pending |
| _acceptance_ | — | all | `session_01GHI…` | — | — | — | — | running |

## Log
- 2026-09-15T10:02Z spawned api-types, api-client
- 2026-09-15T10:41Z #41 round 1 — 3 confirmed, sent to worker
- 2026-09-15T11:15Z #41 converged after round 2, merged
```

**States**: `pending` → `running` → `review` → `fixing` → `converged` → `merged`, plus `escalated` and `aborted` as terminal states.

The acceptance pass gets a row of its own so the wake loop stays uniform — it is spawned, reconciled, and read back exactly like a slice, and a lead resuming after a compaction cannot tell it apart from one. It goes `pending` → `running` → `met` or `escalated`, and it has no branch, no PR, and no rounds. Its dependency is every slice.

Keep the log append-only and one line per event. It is the only record of why a run did what it did, and it is what you read first when a run goes wrong.

## The stateless wake protocol

Every wake, without exception, in this order:

1. **Read the issue.** Do not act on anything you remember. If your context still holds the run, treat it as a cache to be validated, not a source.
2. **Reconcile each row against reality.** The ledger is a claim; GitHub is the fact.
   - branch: `list_branches`
   - PR and its `mergeable` / `mergeable_state` / review state: `pull_request_read`
   - CI on the PR's **current head**: `actions_list` / `get_check_run`
   - worker liveness: `get_session` → `status_bucket`
   Write back every row that drifted, and log the drift. Rows drift constantly and that is normal — events get dropped, workers push between wakes.
3. **Act on at most one thing per row**, in the priority order the SKILL gives. One action per row per wake keeps the run legible in the log and stops the lead from stacking a merge on top of a push it has not seen CI for.
4. **Re-arm the next wake before reporting.** A failure while writing a summary must not end the run.

## Idempotency

Every action the lead takes is guarded by a check that it has not already happened:

| action | guard |
|---|---|
| spawn a slice | branch absent **and** no PR from it |
| open the tracking issue | no open issue titled `Feature: <slug>` |
| send a review batch | round number not already logged for that PR head SHA |
| merge | PR still open, and gate re-evaluated at the current head |
| re-arm a wake | no pending trigger for this run (`list_triggers`) |
| re-run a red check | no re-run already logged for that check at that head SHA |
| spawn acceptance | every slice merged or escalated, and no acceptance row already `running` |
| read the acceptance verdict | a comment on the issue opening with `<!-- feature:acceptance -->` |
| notify a human | that escalation not already in the log as notified |

This is what makes a duplicate event harmless and a resumed run indistinguishable from an uninterrupted one. Anchor review rounds to the **head SHA**, not just the round counter — a worker that pushed twice between wakes has changed the thing you reviewed, and a batch written against the old head is noise.

## What never goes in the ledger

Secrets, tokens, raw CI logs, or full diffs. The issue is as visible as the repo. Link to the run and the job; do not paste them.
