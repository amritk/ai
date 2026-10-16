# The review loop — adversarial, fresh, bounded

One PR, up to `--max-rounds` rounds (default 4), no discussion. Most PRs converge in two. A round is opened only by a blocking finding (see **Blocking and non-blocking**).

## What a round is

A round is: **collect → verify → batch → wait**. It happens entirely at one PR head SHA.

**0. Only on a reviewable head.** Start a round only when the PR's current head is green and not conflicted. A red or conflicted head goes back to the worker first (SKILL Phase 4.3), and its next push changes the code anyway. A round spent on it is spent twice.

**1. Collect.** Spawn `subagent_type: "pr-adversary"` agents, all in a single message so they run concurrently. Use one agent for a diff under ~400 changed lines. Above that, use one per shard of roughly that size, split along file boundaries. More shards on a small diff add cost without adding coverage, and each extra collector also feeds more findings to the verifier. Each gets the PR number, the head SHA, the stage's `Owns` globs, the stage's todos, the round number, the generated-file globs, and **the path of a diff file the lead wrote once for this head**:

```
git fetch origin feature/{slug}/{stage-id}
git diff origin/{default branch}...{head SHA} -- . {':(exclude)<glob>' per generated glob} > {scratchpad}/pr-{n}-{short sha}.diff
```

The redirect keeps the diff out of the lead's context, and in-process agents share the lead's filesystem, so every collector and verifier reads the same file instead of each fetching the diff again through the API — a past run made 437 `get_file_contents` calls doing that, and the reviewers read generated goldens nobody needed. They still use the GitHub tools for file context outside the diff; they do not need a checkout of their own, which is why review runs as in-process agents rather than cloud sessions.

`pr-adversary` rather than `checker` for one reason: `checker` reviews a local diff against a merge-base, and the lead has no checkout of the worker's branch. Same mandate, different source of truth.

Each round spawns **new** agents. Never continue a previous round's agent with `SendMessage`, and never pass it the previous round's findings. Fresh context is the mechanism that makes the loop adversarial instead of collegial — an agent that remembers arguing about a finding starts negotiating over it.

**Dedupe before verifying.** Merge the collectors' findings on `file:line` + root cause, then drop any that match the PR's `rejected` ledger. Only what is left goes to a verifier. A known false positive costs nothing to drop here and a full verification to drop later.

**2. Verify.** Every remaining finding gets an independent refutation pass before it reaches the worker, by the same `subagent_type: "verifier"` agent `/check-iterate` uses — one per group of findings, defaulting to REFUTED unless it can trace the failure itself. The agent already defines its own mandate and output format, so the prompt only supplies the findings:

```
You are verifying findings another reviewer made against PR #{n} at {head SHA}.
For each finding below, independently confirm or refute it — read the cited code
yourself, chase the claimed failure, and default to REFUTED unless the evidence
actually holds up.

{numbered findings: dimension, file:line, evidence quote, claimed failure, blocking}

Return, per finding: CONFIRMED or REFUTED, one line of independent evidence
(file:line + quote), and for a confirmed finding whether it is blocking — a
concrete correctness, soundness, security, scope or gate failure — or
non-blocking. Nothing else. No fixes, no plan.
```

This pass is what makes autonomous merge defensible. Without it the worker spends its rounds chasing plausible-sounding findings that no one checked, and the round budget burns on noise.

**3. Batch.** If no confirmed finding is blocking, there is no round to send: the PR has converged, and the non-blocking findings go to the worker once, as below. Otherwise post the confirmed findings, blocking and non-blocking together, as **one** review — a single COMMENT review with line-anchored comments, submitted once. Then send the worker one message pointing at it. That is the entire communication for the round.

**4. Wait.** The round is over. The lead does not answer the worker, does not clarify, does not review the worker's reply. The next wake that finds a new head SHA starts the next round against it.

## Blocking and non-blocking

Every finding carries a `blocking` verdict from the collector, which the verifier confirms along with the finding.

- **Blocking** — a correctness or soundness bug with a concrete failing input, a security hole, a scope or gate-integrity violation, a todo with no change, a test that cannot fail. These open a round and hold the merge.
- **Non-blocking** — naming, style, comment and doc wording, test additions beyond what pins the change, PR-body or commit-message prose, a performance delta inside its noise band. These never open a round on their own. They ride along with a blocking batch, or go to the worker once at convergence as "apply in one push if cheap, no further review". The next round does not re-check them.

Two kinds of finding cost past runs whole rounds and get a fixed policy here instead:

- **The PR body and the squash message are the lead's.** The lead writes the final commit message when it merges, so prose in the body is not something to send back to the worker round after round. A body that is factually wrong is a single non-blocking finding.
- **Performance is measured once.** When the repo cares about a hot path, the worker measures it once, against the base and against a byte-identical copy of the base for the noise band. A delta inside the band is accepted. A delta outside it is one blocking finding with the numbers. A delta that is outside on one run and inside on the next is the lead's call at the gate, not another round.

## The ledgers that make it converge

Carried in the tracking issue per PR, and consulted before every round:

- **`rejected`** — findings the verification pass refuted, with the refutation. Never re-raised, never re-sent, never re-verified. A collector that finds one again in a later round has it dropped silently during dedupe, before the verify step. Without this ledger the loop cannot terminate: the same false positive resurfaces every round until the budget is gone.
- **`disputed`** — findings the worker pushed back on in one line rather than fixing. Re-verified once by a fresh pass; if the refutation holds, it moves to `rejected`, and if it does not, it becomes an escalation. Never a third opinion.
- **`skipped`** — findings that need a human call. They do not block the round, and they do block the merge.

Deduplicate on `file:line` + root cause, not on wording — two agents describing the same bug differently is the common case.

## Stop rules

- **Converged**: a full round where zero blocking findings survive verification. This is the only clean exit.
- **Stalemate**: a round's confirmed findings are identical to the previous round's — the worker is not actually fixing them. Stop immediately and escalate; the remaining rounds will produce the same output.
- **Budget exhausted**: `--max-rounds` reached with blocking findings open → **escalate, never merge**. A PR still finding blocking problems after four rounds is a PR a human should look at.
- **Worker unreachable**: findings outstanding and the slice's session is dead → respawn per `fan-out.md`, or escalate on a second failure.

## What the reviewers look for

Beyond the standard three dimensions the `checker` agent covers (security, reliability, consistency), a `feature` review carries four extra obligations, because nothing downstream will catch them:

1. **Scope.** Any file outside the stage's `Owns` globs is a finding. This is how parallel workers stay out of each other's way, and it is invisible to a normal PR review.
2. **Plan fidelity.** The diff must implement the stage's todos — no more, no less. A todo with no corresponding change, or a change no todo accounts for, is a consistency finding.
3. **Gate integrity.** Any edit that weakens verification is a **blocking** finding regardless of severity: lowered coverage thresholds, added coverage ignores, `skip`/`only`/`todo` on tests, loosened lint rules, `@ts-expect-error` added to make types pass, CI workflow edits. A worker under pressure to hit 100% will reach for these, and they are the one class of change that makes every other gate meaningless.
4. **Test quality.** 100% coverage is a floor, not evidence. Assertions that cannot fail, tests that mock the thing under test, and snapshot tests standing in for behavioural ones are findings — coverage is what makes them look adequate.

## Cost

Rounds are not free: each one is a fan-out plus a verification fan-out, and a worker turn that re-reads the worker's whole context several hundred times. The round budget is a ceiling, not a target — a converged PR at round 2 is the normal case, and a run that routinely uses every round is telling you the slices are too big or the plan was too vague. When the same kind of blocking finding recurs across rounds of one PR (a past run found a new soundness hole of the same shape in each of seven rounds), say so in the batch, and tell the worker to probe the siblings of each fix before it pushes, rather than waiting for the next round to find them.
