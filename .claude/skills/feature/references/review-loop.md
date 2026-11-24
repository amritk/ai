# The review loop — adversarial, fresh, bounded

One PR, up to `--max-rounds` rounds (default 3, plus one extra round while the blocking findings are still going down — see **Stop rules**), no discussion. Most PRs converge in two. A round is opened only by a blocking finding (see **Blocking and non-blocking**).

## What a round is

A round is: **collect → verify → batch → wait**. It happens entirely at one PR head SHA.

**0. Start on the head, not on CI.** Start a round as soon as a head appears with no round logged for its SHA: when the PR opens, and again when the worker pushes for a batch. Do not wait for CI. Once a PR has converged, a new head does not open a round. That covers a base merge before the PR's turn to merge, and the one push that applies non-blocking findings. The merge gate re-checks those heads. The exception is a push answering feedback — a person's change request or a confirmed bot finding (`merge-gate.md`, **Feedback on the PR**). It is new code no round has seen, so its head gets a **feedback round**: a delta round like any other, given the forwarded items as what the delta was meant to fix. One a bot started counts against `--max-rounds`; one a person started does not, and is logged in the `rounds` cell as `+f` (`ledger.md`). The stalemate rule applies to both. A round and a CI run take about the same wall-clock time, so waiting for green before reviewing makes every cycle twice as long and saves nothing. The worker has to push for a red check anyway, and the round's findings go in that same push. The one head not to review is a conflicted one. It goes back to the worker first (SKILL Phase 4.3), and resolving the conflict changes the code, so a round on it is spent twice.

A red check that comes in while a round on that head is still running waits for the round. The job logs go to the worker in the round's batch message (step 3), so the worker makes one push for both, not one push for the check and another for the findings. Hold it for no longer than that round.

**1. Collect.** Spawn `subagent_type: "pr-adversary"` agents, all in a single message so they run concurrently. Use one agent for a diff under ~400 changed lines. Above that, use one per shard of roughly that size, split along file boundaries. More shards on a small diff add cost without adding coverage, and each extra collector also feeds more findings to the verifier. Each gets the PR number, the head SHA, the stage's `Owns` globs, the stage's todos, the round number, the generated-file globs, and **the path of a diff file the lead wrote once for this head**. The `Owns` globs are pasted verbatim, with every amendment the ledger logs for the stage, into every `pr-adversary` prompt and every gate prompt — never summarised, never abbreviated. A collector checks scope against the list it was given, so a shortened list turns every file it leaves out into a scope finding; one past round-5 collector raised a false one exactly that way.

```
git fetch origin feature/{slug}/{stage-id}
git diff origin/{default branch}...{head SHA} -- . {':(exclude)<glob>' per generated glob} > {scratchpad}/pr-{n}-{short sha}.diff
```

**From round 2 on, also write the round's delta** — what the worker changed since the head the last round reviewed — and give collectors both files:

```
git diff {previous reviewed SHA} {head SHA} -- . {':(exclude)<glob>' per generated glob} > {scratchpad}/pr-{n}-{short sha}.delta.diff
```

Skip the delta, and send the full diff alone, when the worker merged or rebased onto the default branch between the two heads (`git merge-base origin/{default branch} <sha>` differs for the two SHAs): the delta would then carry everyone else's changes too.

The redirect keeps the diff out of the lead's context, and in-process agents share the lead's filesystem, so every collector and verifier reads the same file instead of each fetching the diff again through the API — a past run made 437 `get_file_contents` calls doing that, and the reviewers read generated goldens nobody needed. They still use the GitHub tools for file context outside the diff; they do not need a checkout of their own, which is why review runs as in-process agents rather than cloud sessions.

`pr-adversary` rather than `checker` for one reason: `checker` reviews a local diff against a merge-base, and the lead has no checkout of the worker's branch. Same mandate, different source of truth.

Each round spawns **new** agents. Never continue a previous round's agent with `SendMessage`. Fresh context is the mechanism that makes the loop adversarial instead of collegial — an agent that remembers arguing about a finding starts negotiating over it.

**Round 2 on: start from where the last round ended, not from scratch.** The full diff was reviewed in round 1. A later round's collectors review the **delta**, and get the previous round's confirmed **blocking** findings as what the delta was meant to fix. Non-blocking ones are not passed on: they were sent once and are never re-checked.

```
This is round {n}. The PR's full diff was reviewed in an earlier round; review the
delta file — what the worker pushed since — against the full diff for context.
The worker was asked to fix the findings below. For each, check that the delta
fixes it, that the fix broke nothing around it, and probe the sibling cases of the
same shape. Then review the rest of the delta as usual.

{confirmed blocking findings from the last batch: file:line, one-line title}
```

Never pass refuted or disputed findings, or anything the worker said about them: those are what an agent would start negotiating over, and the `rejected` ledger already drops them. Shard a later round on the delta's size, not the PR's, so most later rounds are a single collector. This is cheaper than re-reviewing the whole PR every round, and it finds more, because attention goes to the code that just changed. A round on the full diff alone (no delta, as above) runs as round 1 does.

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

**3. Batch.** If no confirmed finding is blocking, there is no round to send: the PR has converged, and the non-blocking findings go to the worker once, as below. Otherwise post the confirmed findings, blocking and non-blocking together, as **one** review — a single COMMENT review with line-anchored comments, submitted once. Its body **and every line comment in it** open with `<!-- feature:review -->`: the lead writes as the owner's account, and the marker is how a later wake tells the run's own threads from the owner's (`merge-gate.md`, **Feedback on the PR**). An unmarked line comment would read as the owner's and hold the gate until someone resolved it. Then send the worker one message pointing at it. If CI on the reviewed head has gone red by now, that message also carries the failing checks and their job logs, under the flake policy in SKILL Phase 4.3. A converged round with red CI sends the logs together with the non-blocking findings. That is the entire communication for the round.

If the head moved while the round was running (a conflict fix, say), still post the batch, anchored to the SHA it reviewed. The findings were verified at that SHA, and the worker drops any its push already fixed. Then count the batch as that head's round: do not start another round on the new head until the worker pushes in reply to this batch.

**4. Wait.** The round is over. The lead does not answer the worker, does not clarify, does not review the worker's reply. The next wake that finds a new head SHA starts the next round against it.

## Blocking and non-blocking

Every finding carries a `blocking` verdict from the collector, which the verifier confirms along with the finding.

- **Blocking** — a correctness or soundness bug with a concrete failing input, a security hole, a scope or gate-integrity violation, a todo with no change, a test that cannot fail, a change that weakens a property the default branch pins. These open a round and hold the merge.
- **Non-blocking** — naming, style, comment and doc wording, test additions beyond what pins the change, PR-body or commit-message prose, a performance delta inside its noise band. These never open a round on their own. They ride along with a blocking batch, or go to the worker once at convergence as "apply in one push if cheap, no further review". The next round does not re-check them.

**A collector's rating is not final in either direction, and a downgrade is the one that ships.** A change that weakens a property the default branch pins — a proof, a capability verdict, a `proven: true` in a checked-in report — is blocking even when no test fails. The pinned report is the test, so "no test pins it" is not a reason to downgrade. Before accepting a non-blocking rating on such a change, the lead compares the default branch's pinned report with the PR head's. In one past run a round-4 collector rated a std function losing its panic-freedom proof as non-blocking; the lead upgraded it after that comparison.

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

- **Converged**: a round where zero blocking findings survive verification — round 1 over the full diff, or a later round over the delta from the head the previous round reviewed. Every head since round 1 has to have been covered one way or the other. This is the only clean exit.
- **Stalemate**: a round's confirmed findings are identical to the previous round's — the worker is not actually fixing them. Stop immediately and escalate; the remaining rounds will produce the same output.
- **One extra round while converging**: `--max-rounds` reached with blocking findings open, but the last round confirmed **fewer** blocking findings than the round before it, and that earlier round was round 2 or later (round 1 reviews the whole PR, so comparing a delta round against it would almost always say "fewer") → allow one more round, once per PR. Record each round's blocking count and the extra round in the slice's `rounds` cell (`ledger.md`), so a lead after a compaction applies the rule the same way. A PR that is clearly getting there finishes; a stuck one does not get the extra round.
- **Budget exhausted**: `--max-rounds` reached with blocking findings open and no extra round to give (it was used, or the count did not go down) → **escalate, never merge**. A PR still finding blocking problems after three rounds is usually one that needs a decision the loop cannot make, and a human should look at it.
- **Worker unreachable**: findings outstanding and the slice's session is dead → respawn per `fan-out.md`, or escalate on a second failure.

## What the reviewers look for

Beyond the standard three dimensions the `checker` agent covers (security, reliability, consistency), a `feature` review carries four extra obligations, because nothing downstream will catch them:

1. **Scope.** Any file outside the stage's `Owns` globs is a finding. This is how parallel workers stay out of each other's way, and it is invisible to a normal PR review.
2. **Plan fidelity.** The diff must implement the stage's todos — no more, no less. A todo with no corresponding change, or a change no todo accounts for, is a consistency finding.
3. **Gate integrity.** Any edit that weakens verification is a **blocking** finding regardless of severity: lowered coverage thresholds, added coverage ignores, `skip`/`only`/`todo` on tests, loosened lint rules, `@ts-expect-error` added to make types pass, CI workflow edits, a rule removed or loosened in the repo's agent guidance (`CLAUDE.md`, `AGENTS.md`, `REVIEW.md`, `.claude/rules/`). Reviewers read that guidance from the default branch, never from the PR head, so a PR cannot rewrite the rules it is judged by. A worker under pressure to hit 100% will reach for these, and they are the one class of change that makes every other gate meaningless.
4. **Test quality.** 100% coverage is a floor, not evidence. Assertions that cannot fail, tests that mock the thing under test, and snapshot tests standing in for behavioural ones are findings — coverage is what makes them look adequate.

## Cost

Rounds are not free: each one is a fan-out plus a verification fan-out, and a worker turn that re-reads the worker's whole context several hundred times. The round budget is a ceiling, not a target — a converged PR at round 2 is the normal case, and a run that routinely uses every round is telling you the slices are too big or the plan was too vague. When the same kind of blocking finding recurs across rounds of one PR (a past run found a new soundness hole of the same shape in each of seven rounds), say so in the batch, and tell the worker to probe the siblings of each fix before it pushes, rather than waiting for the next round to find them.
