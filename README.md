# ai

Shared Claude Code skills, collected from across my repos so they live in one
place instead of being copied between them.

## Using them

Link this repo into a session alongside whatever you are actually working on.
Claude Code loads a linked repo's `.claude/skills/`, so everything below becomes
available as `/<skill-name>` without any install step or per-repo config.

That is the whole setup — the layout here exists to be discovered:

```
.claude/skills/<name>/SKILL.md    # one directory per skill
.claude/agents/<name>.md          # subagents the workflow skills fan out to
```

### Watch for name collisions

Several of these skills still exist in the repo they came from. Link this repo
next to `scalar-org` and you have two `check` skills, two `plan` skills, and so
on; link it next to `scalar` and `typescript`, `tests`, `vue-components`,
`mock-server`, `openapi-glossary`, and `scalar-docs` all double up. Only one
copy of a given name wins, and which one is not worth guessing at.

So this is most useful linked next to a repo that does *not* already carry
these — `mjst`, or anything new. To get the clean version everywhere, the
duplicates eventually have to come out of the source repos; nothing here
requires that first.

### There is deliberately no CLAUDE.md

A linked repo's `CLAUDE.md` loads too, and this one has no business telling
another repo how to build. Keeping it absent means linking this repo adds
skills and nothing else.

## Skills

**Workflow**

| Skill | What it does |
| --- | --- |
| `check` | Fans the branch's diff against main out to read-only `checker` subagents that try to break it, then reduces the findings to a plan. |
| `check-iterate` | Runs that as a loop — `checker` collects, `verifier` refutes, the primary agent fixes and pins each fix with a regression test — until a pass comes back clean or seven loops. |
| `plan` | Writes plan files in the `.claude/plans/<slug>.plan.md` stages schema. |
| `plan-execute` | Executes a plan file, runs the plan's own verification commands, drives the check loop over the result, then publishes the run through `session-report`. |
| `feature` | Takes requirements to merged PRs on Claude Code cloud — plans the work, gives each stage its own cloud session, branch, and PR, reviews each PR with fresh-context adversarial rounds, and merges when the gate passes. Stops once, for plan acceptance. |
| `session-report` | Publishes what the session did as a linked Claude artifact: what was asked, what changed, what was verified, every finding with its verdict and fix, and what needs a human. Leaves the link on the PR when there is one. |
| `pr-review` | Reviews one PR (or the current branch, with `--branch`) against a prompt you supply. Posts line-anchored comments, capped at a `COMMENT` review. |
| `pr-triage` | Reads the whole open PR queue and publishes one page rating every PR Low → Critical, with a "start here" list. |
| `async-daily` | Writes an async standup grouped by pull request — what merged, what is still open, plus local work that is not a PR yet. Covers every repo you touched, not just the ones checked out. |
| `debug` | Reproduce, localise, hypothesise, fix, prove: root-causes a bug or flaky test and leaves a regression test behind. `--no-fix` stops at the diagnosis. |
| `qa` | Runs a QA pass on a feature in a real browser — Claude in Chrome where the session has it, a Playwright fallback where it does not — reproduces every failure before reporting it, and publishes a report with a verdict, findings, evidence, and what was not covered. |

`check`, `check-iterate`, and `plan-execute` stage their work; none of them commit.
`debug` edits but never stages or commits. `async-daily`, `session-report`, and `qa` are read-only in the repo; `session-report` publishes an artifact and may comment its link on the branch's PR, and `qa` publishes one too. `qa` is the only skill here that touches something outside the repo — a running app — so it confirms the target with you before it starts and refuses destructive checks against production.
`feature` is the exception to all of it — it commits, pushes, opens PRs, and merges
them, which is why it is the only skill here that stops for an explicit human
approval before it does anything.

**Agents**

| Agent | Role |
| --- | --- |
| `checker` | Read-only collector. Assumes the branch's diff is broken and hunts for evidence: a concrete input, a caller that did not adapt, a test that would still pass if the code were wrong. Grounds itself in the repo's own agent guidance first so a settled convention is never a finding. |
| `pr-adversary` | Read-only reviewer for one `feature` review round. Same mandate as `checker`, but it reads a pull request's diff through the GitHub API at a fixed head SHA rather than a local checkout, and it also polices the things only a fan-out run can get wrong: files outside the slice's lane, drift from the plan, and edits that weaken the very gates the run merges on. |
| `verifier` | Read-only refuter. Takes another reviewer's findings and defaults to `REFUTED`, confirming only what it can trace itself. The two agents have opposite mandates on purpose: a finding has to survive both before anyone edits. |

All three run on Sonnet at medium effort, since collection is wide and parallel and the judgment calls stay with the orchestrator.

**Conventions**

| Skill | What it covers |
| --- | --- |
| `typescript` | Typing, `Result`-based error handling, ESM conventions, naming, JSDoc. |
| `tests` | Vitest and Playwright practice, and running suites scoped through the repo's task runner. |
| `comments` | Why-not-what comments, JSDoc, and the global-CSS exception. |
| `vue-components` | Composition API structure, typed props and emits, Tailwind, accessibility. |
| `openapi-glossary` | Consistent OpenAPI terminology. |
| `mock-server` | `@scalar/mock-server` — `x-handler`, `x-seed`, auth, Docker. |
| `scalar-docs` | Writing and updating `scalar.config.json`. |

## Where these came from

`check`, `check-iterate`, `plan`, `plan-execute`, `checker`, `vue-components`
from `scalar-org`; `pr-review` and `comments` from `bane`; `pr-triage` from a
closed `scalar-org` PR; `openapi-glossary`, `mock-server`, `scalar-docs` from
`scalar`. `async-daily`, `debug`, `qa`, `session-report`, `feature`, and the `verifier` and `pr-adversary` agents were written here. `typescript` and `tests` existed in four divergent copies across the
repos — the richest of each was taken and the repo-specific commands
generalised.

Repo-specific paths, package names, and task-runner commands are either removed
or stated with the condition under which they apply. `pr-review` resolves the
repository from `origin` rather than assuming one, and reads whatever agent
guidance the repo has instead of a fixed list of files.

## What is deliberately not here

Skills that only work inside one repo stay there: `dashboard-playground`
(scalar-org), `onboard-client` (bane), and `cloud-agents-starter` (scalar) are
each tied to a specific layout, fixture set, or toolchain. Bane's `report` was
one of these; `session-report` is a rewrite that depends only on git and the
Artifact tool — and is renamed so linking this repo next to bane does not put
two different `report` skills in one session. The bar
for adding something here is that it would work unchanged in a repo that has
never seen it.

## Adding a skill

1. `.claude/skills/<name>/SKILL.md`, with any references and scripts beside it.
2. Write the `description` for triggering — what it does *and* when to reach
   for it, in the words someone would actually use.
3. Strip repo-specific paths, package names, and commands, or state the
   condition under which they apply.
4. `python3 scripts/validate.py`.

The validator checks each skill's frontmatter `name` matches its directory, that
it has a description within Claude Code's listing limit, that every
`<skill dir>/…` pointer and relative Markdown link resolves, that no Cursor
`mdc:` links survived the move, that `allowed-tools` names the subagent tool as
`Agent` (there is no `Task` alias, so a `Task` entry pre-approves nothing), that
every `subagent_type` a skill spawns has an agent file, and that no bundled file
sits there unreferenced. Agents get the same treatment against the fields the
sub-agent docs define (`model`, `effort`, `color`).

## Adding an agent

1. `.claude/agents/<name>.md` with `name`, `description`, `tools`, and a model.
2. Give it one mandate and state it in the first paragraph. `checker` assumes the
   code is broken; `verifier` assumes the finding is. An agent that hedges
   between two stances does neither job well.
3. Define its output format in the file, so the skill that spawns it can parse
   the result without restating the schema in every prompt.
4. `python3 scripts/validate.py`.
