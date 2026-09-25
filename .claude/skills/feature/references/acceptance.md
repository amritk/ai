# Acceptance — was the feature built, or just the diff

Every gate before this one reads the diff: the tests pass, coverage holds, the review converged, GitHub says mergeable. None of them has run the software and none of them has looked at what was asked for. A run that stops at the last merge is reporting success on evidence that cannot tell a working feature from a well-tested wrong one.

So the run does not end at the merge. It ends when the thing that was asked for has been checked against what is on the default branch.

## The criteria

Written in **Phase 1**, from the requirements, before any code exists — criteria written afterwards are written to match what got built.

- Numbered, one outcome each, phrased so that something other than reading the diff can settle it: a screen a user reaches, a command that exits zero, an API that answers.
- **Criteria are not the stages' todos.** A todo is work assigned to a worker; a criterion is a result the person who asked would check. Per-PR review already covers plan fidelity (`review-loop.md`), so restating the todos here re-checks the same thing twice and still misses the requirement nobody sliced.
- If a criterion can only be verified by reading code, it is not a criterion yet — restate it as the observable consequence, or drop it.
- Where the run started from a plan slug rather than free text, derive the criteria from the plan's goals and stages and **say in the report that they were derived**, not given. Derived criteria cannot catch a requirement the plan itself missed, and a report that hides that overstates the run.

They live in the tracking issue under `## Acceptance`, one row each, because the lead that evaluates them is not the lead that wrote them.

## Two passes, after the last merge

### 1. Static — does the merged code do what was asked

One fresh in-process `Agent` (`general-purpose`), reading the merged result through the GitHub tools rather than a checkout, the same way `pr-adversary` does. Give it the original requirements verbatim, the numbered criteria, and the merged PR numbers.

```
The following requirements were implemented across PRs {#n, #n, …}, all merged
to {default branch}. For each acceptance criterion below, decide independently
whether the merged code satisfies it. Read the merged files themselves — the PR
descriptions are claims, not evidence.

Requirements, as given:
{original requirements verbatim}

Criteria:
{numbered criteria}

Return, per criterion: MET, PARTIAL, or NOT MET, one line of evidence
(file:line + quote) for the verdict, and nothing else. No fixes, no plan.
Default to NOT MET when you cannot find the evidence — "I could not check it"
is not "it passed".
```

This pass is cheap and it catches the one failure per-PR review is structurally blind to: every stage was faithful to its todos, and the todos as a set did not add up to the feature.

### 2. Dynamic — does it actually run

One cloud session against the merged default branch — the **acceptance session**. It is the only session in the run that is not a slice: no `outcome_branch`, no PR, nothing to push.

| field | value |
|---|---|
| `prompt` | the acceptance prompt below, fully rendered |
| `title` | `feature/<slug>: acceptance` |
| `tags` | `["feature:<slug>", "feature-acceptance"]` |
| `outcome_branch` | omitted — this session writes no code |

```
The feature described below was just merged to {default branch} of {owner/repo}.
Nothing is asked of you except to find out whether it works.

Acceptance criteria:
{numbered criteria}

1. Check out {default branch} at {merge SHA} and install dependencies.
2. Run /qa with those criteria as the checklist, against the app running locally.
   Reproduce every failure before you report it. If /qa is not available in your
   session, drive the feature by hand in a browser and hold yourself to the same
   bar: one check at a time, evidence for every claim.
3. Also run `{test command}` and `{lint command}` on {default branch} as merged.
4. Post ONE comment on issue #{issue number}, beginning with the exact line
   <!-- feature:acceptance --> and containing: a verdict line (SHIP or FAIL), a
   table of criterion → pass/fail → evidence, the QA report link if one was
   published, and what you could not exercise and why.

Do not fix anything. Do not open a PR, a branch, or an issue. If the feature is
broken, the comment saying so precisely is the whole job.
```

The dynamic pass runs as a session rather than in the lead because it needs a checkout, a running app, and a browser — that is a worker's shape, and the lead stays a reader. It reports the way every other worker does: **observable state, not a reply.** Cloud sessions have no channel back to the lead (`fan-out.md`), so the marker line is what makes the verdict findable on a wake hours later, and what tells "spawned, not finished" apart from "never spawned".

**When there is nothing to drive** — no browser-exercisable surface, `/qa` unavailable, or `--no-qa` — the dynamic pass narrows to the plan's verification commands run against the merged branch by the same session, and the report says in as many words that the feature was never exercised by hand. A static-only acceptance must never read as a full one.

## Verdicts

- **Every criterion MET and the QA verdict is SHIP** → the run succeeded. That sentence is worth something now, which is the point of the phase.
- **Anything NOT MET or PARTIAL, or a QA failure** → **escalate** (`merge-gate.md`). File one follow-up issue naming the criterion, the evidence, and the PR that was supposed to satisfy it; link it from the tracking issue; leave the tracking issue open; notify.

Do not revert, do not open a repair slice, do not re-plan. The code is on the default branch and passed every gate that was agreed in advance; whether an unmet criterion is a bug, a misread requirement, or acceptable is the decision a human is owed. An acceptance failure after a clean merge is not a contradiction — the gates prove the diff was sound, acceptance proves whether it was the right diff, and a run that can only ever conclude the first thing is not worth automating.

## What the run learned

Review rounds are the cheapest source of repo conventions nobody wrote down, and they are thrown away at the end of every run.

At close-out, group the run's confirmed and refuted findings by root cause across all slices, and pick out:

- a root cause **confirmed in two or more slices' PRs** — several independent workers made the same mistake, so the repo never told them not to;
- a root cause **refuted three or more times** — the collectors keep flagging something this repo does deliberately, and every round spent on it is budget burnt.

For each, write the `CLAUDE.md` line you would add, verbatim and ready to paste, with the PRs that motivated it, into the close-out comment and the report.

**Propose; never commit.** A run that edits the repo's standing instructions on its own authority has walked around the single human gate this whole skill is built on.
