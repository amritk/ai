# The review loop — adversarial, fresh, bounded

One PR, up to `--max-rounds` rounds (default 10), no discussion. Most PRs converge in two.

## What a round is

A round is: **collect → verify → batch → wait**. It happens entirely at one PR head SHA.

**1. Collect.** Spawn `subagent_type: "pr-adversary"` agents — one per shard for a large diff, one for a small one, all in a single message so they run concurrently. Each gets the PR number, the head SHA, the stage's `Owns` globs, the stage's todos, and the round number. They read the diff through `pull_request_read`; they do not need a checkout, which is why review runs as in-process agents rather than cloud sessions.

`pr-adversary` rather than `checker` for one reason: `checker` reviews a local diff against a merge-base, and the lead has no checkout of the worker's branch. Same mandate, different source of truth.

Each round spawns **new** agents. Never continue a previous round's agent with `SendMessage`, and never pass it the previous round's findings. Fresh context is the mechanism that makes the loop adversarial instead of collegial — an agent that remembers arguing about a finding starts negotiating over it.

**2. Verify.** Every collected finding gets an independent refutation pass before it reaches the worker, by the same `subagent_type: "verifier"` agent `/check-iterate` uses — one per group of findings, defaulting to REFUTED unless it can trace the failure itself. The agent already defines its own mandate and output format, so the prompt only supplies the findings:

```
You are verifying findings another reviewer made against PR #{n} at {head SHA}.
For each finding below, independently confirm or refute it — read the cited code
yourself, chase the claimed failure, and default to REFUTED unless the evidence
actually holds up.

{numbered findings: dimension, file:line, evidence quote, claimed failure}

Return, per finding: CONFIRMED or REFUTED, one line of independent evidence
(file:line + quote), and nothing else. No fixes, no plan.
```

This pass is what makes autonomous merge defensible. Without it the worker spends its rounds chasing plausible-sounding findings that no one checked, and the round budget burns on noise.

**3. Batch.** Post the confirmed findings as **one** review — a single COMMENT review with line-anchored comments, submitted once. Then send the worker one message pointing at it. That is the entire communication for the round.

**4. Wait.** The round is over. The lead does not answer the worker, does not clarify, does not review the worker's reply. The next wake that finds a new head SHA starts the next round against it.

## The ledgers that make it converge

Carried in the tracking issue per PR, and consulted before every round:

- **`rejected`** — findings the verification pass refuted, with the refutation. Never re-raised, never re-sent. A collector that finds one again in a later round has it dropped silently during dedupe. Without this ledger the loop cannot terminate: the same false positive resurfaces every round until the budget is gone.
- **`disputed`** — findings the worker pushed back on in one line rather than fixing. Re-verified once by a fresh pass; if the refutation holds, it moves to `rejected`, and if it does not, it becomes an escalation. Never a third opinion.
- **`skipped`** — findings that need a human call. They do not block the round, and they do block the merge.

Deduplicate on `file:line` + root cause, not on wording — two agents describing the same bug differently is the common case.

## Stop rules

- **Converged**: a full round where zero findings survive verification. This is the only clean exit.
- **Stalemate**: a round's confirmed findings are identical to the previous round's — the worker is not actually fixing them. Stop immediately and escalate; the remaining rounds will produce the same output.
- **Budget exhausted**: `--max-rounds` reached with findings open → **escalate, never merge**. A PR that needed ten rounds is a PR a human should look at.
- **Worker unreachable**: findings outstanding and the slice's session is dead → respawn per `fan-out.md`, or escalate on a second failure.

## What the reviewers look for

Beyond the standard three dimensions the `checker` agent covers (security, reliability, consistency), a `feature` review carries four extra obligations, because nothing downstream will catch them:

1. **Scope.** Any file outside the stage's `Owns` globs is a finding. This is how parallel workers stay out of each other's way, and it is invisible to a normal PR review.
2. **Plan fidelity.** The diff must implement the stage's todos — no more, no less. A todo with no corresponding change, or a change no todo accounts for, is a consistency finding.
3. **Gate integrity.** Any edit that weakens verification is a **blocking** finding regardless of severity: lowered coverage thresholds, added coverage ignores, `skip`/`only`/`todo` on tests, loosened lint rules, `@ts-expect-error` added to make types pass, CI workflow edits. A worker under pressure to hit 100% will reach for these, and they are the one class of change that makes every other gate meaningless.
4. **Test quality.** 100% coverage is a floor, not evidence. Assertions that cannot fail, tests that mock the thing under test, and snapshot tests standing in for behavioural ones are findings — coverage is what makes them look adequate.

## Cost

Rounds are not free: each one is a fan-out plus a verification fan-out, per PR, per wake. The round budget is a ceiling, not a target — a converged PR at round 2 is the normal case, and a run that routinely burns eight rounds per PR is telling you the slices are too big or the plan was too vague.
