---
name: plan
description: Write or update implementation plans as .claude/plans/<slug>.plan.md files using the stages frontmatter schema rendered by the plan-preview extension. Use whenever asked to write, draft, produce, revise, or update a plan file — including when presenting a plan from plan mode — instead of emitting the plan as chat text or ad-hoc markdown. This is about authoring the plan *file*; it is not the Plan architect agent or the harness plan mode. In a repo that tracks plans as GitHub issues (it has an open issue labelled `roadmap`), a new plan has its open decisions, queue position and sign-off settled with the user, then is filed with `plan-issues`, `ready` for agents, as the last step. Every plan starts by researching the request in the repo; with `--explore`, it also narrows it down with the user, one question at a time, before drafting.
argument-hint: "<what to build> [--explore]"
---

# Writing plans

Write plans as plan files: `.claude/plans/<slug>.plan.md` — YAML frontmatter, then a Markdown body. This is our own **stages** schema (below), rendered by the plan-preview extension; it is **not** the `.md` **rules** schema in `.claude/rules/`.

A plan is a **checklist of deliverables in the frontmatter** plus **narrative detail in the body**. Small work is a flat `todos` list; larger work is broken into **stages**, each a mini-plan with its own goal, todos, and exit criteria.

A plan without a populated `todos` list (flat, or inside every stage) is incomplete — never hand back a plan with an empty or missing todos array.

## Invocation

Invoke as `/plan <what to build> [--explore]`.

Every plan starts with **research** (below), with or without the flag. Then:

- **Default: plan what was asked.** Take the request as the spec and ask nothing before drafting. Where the request leaves something open, take the reading the research and the request best support and say so in `## Approach`. A choice that only the user can make, and that changes the stages, becomes a `### Decision needed` in its stage. The filing step asks about those in a repo that tracks plans as issues.
- **`--explore`: narrow it down with the user first.** Use this when the request is a direction rather than a spec. It adds the back-and-forth in **Explore mode** below before the plan is drafted, and a review of the draft after.

Ignore `--explore` when no one is there to answer, as in `/feature` issue mode. Plan from the request and say that the flag was ignored.

## Research first

Before drafting any plan, read what bears on the request: the code it touches, the plans in `.claude/plans/` (one may already cover it, or the new one may depend on or collide with it), related open issues, and recent history in the area. For broad reading, spawn an `Explore` agent with `model: "sonnet"` and keep its conclusions, not the files. Scale it to the request: a one-file change needs that file and its callers, not a survey. What the research settles goes into the plan as fact, and a question the repo answers is never put to the user.

## Explore mode

The aim is a plan the user recognises as what they meant, reached with as few questions as possible. Every question costs the user's attention, so the research answers what it can. After **Research first**:

1. **Say what you found.** In a few lines of chat: what exists now, what the request seems to mean against it, and the two or three ways it could reasonably go. This is where the user corrects a wrong premise cheaply.
2. **Ask only what changes the plan.** A question qualifies when its answer changes the stages, the scope or the acceptance criteria. Ask about intent, scope and priorities, which only the user knows; leave the how to the draft. Ask with `AskUserQuestion`, one question at a time, as `decide` does (`decide` → Procedure, step 4): set it up in a line or two of chat, the recommended option first, plus **Discuss first** and **Skip for now**. Each question states the assumption the draft will take if it is skipped. When an answer opens new ground, research it before the next question. Most requests need three questions or fewer. Past about six, stop asking and draft on the assumptions.
3. **Confirm the understanding.** Restate it in chat: the goal, what is in scope, what is out of scope, and how done will be judged. Then ask once with `AskUserQuestion`: **Looks right (Recommended)** or **Change something**. A change goes back to step 2 for that point only. The confirmed statement becomes the plan's `## Context`, `## Out of scope` and `## Verification`.
4. **Draft**, as the rest of this skill says.
5. **Review the draft with fresh eyes.** Spawn one `general-purpose` agent with `model: "sonnet"`, give it the plan file and the confirmed understanding (not your reasoning), and ask it to find what would make the plan fail: a missing stage, a todo with no done-signal, a wrong dependency order, a file the work needs that no todo names, verification that cannot be run, anything that contradicts the confirmed understanding. Fix what has a factual answer yourself. What only the user can decide becomes a `### Decision needed` for the filing step, or, in a repo that does not file plans, one more question here.

If the user dismisses a prompt, stop asking: draft on the assumptions so far, and list them in `## Approach`. The filing step that follows does not ask again about anything settled here.

## Frontmatter — flat (small plans)

```yaml
---
name: <Short title>
overview: <1–2 sentences — what changes and why. The only summary a reader sees before opening the plan.>
todos:
  - id: <kebab-case-slug>       # stable + unique across the file
    content: <one-line actionable pointer — see rules below>
    status: pending             # pending | in_progress | completed | cancelled
---
```

## Frontmatter — staged (larger plans)

Use `stages` when the work has distinct phases that land and verify independently. Each stage is a self-contained mini-plan; the reader can see its goal, its todos, and how it's judged done without opening the body.

```yaml
---
name: <Short title>
overview: <1–2 sentences — what changes and why.>
stages:
  - id: <kebab, unique across the file>
    title: <stage name>
    goal: <one line — what this stage achieves>
    verification: <one line — the exit criteria / how you know it's done>
    status: pending             # optional; otherwise derived from its todos
    todos:
      - id: <kebab, unique across the file>
        content: <verb-first, names the file/symbol — see body>
        status: pending         # pending | in_progress | completed | cancelled
  - id: <next stage…>
    # …
---
```

- **`id`s are unique across the whole file** (stage ids and todo ids alike) — status toggling and progress tracking key off them.
- Order stages, and todos within a stage, **by dependency** (earliest first).
- A stage's `status` is derived from its todos unless set explicitly (use explicit to mark the active/cancelled stage).

## Plans filed as issues

In a repo that tracks plans as GitHub issues (the `plan-issues` skill), a plan may also carry `roadmap`, `spec`, `priority` and `labels` at the top level, and `issue`, `related` and `labels` on a stage. `plan-issues` documents them and writes `issue:` itself. Once a stage has an issue, the issue's open or closed state is its status, so do not keep that stage's `status:` in sync by hand. Write each stage's `## <title>` body section so it stands alone: it becomes the sub-issue's body.

### Filing the plan: the last step

In such a repo, a plan this skill writes is filed as issues before the skill hands back, so the work can be picked up at once. Skip this step when `/feature` is drafting the plan in its Phase 1: a run's plan files nothing until its sign-off, and a run that wants issues uses issue mode.

1. **Does the repo track plans as issues?** Take `owner/repo` from `git remote get-url origin` and look for an open issue labelled `roadmap` (`list_issues`). If there is none, stop here: the plan stays a file.
2. **Settle it with the user, so it goes in `ready`.** The person running `/plan` has repo access and is there now. So the plan is settled here, not left for a separate `/decide` pass. Ask with `AskUserQuestion`, one question at a time, in the way `decide` does (`decide` → Procedure, step 4). Set each one up in a line or two of chat first, then give the options with the recommended one first, plus **Discuss first** and **Skip for now**. Discuss first opens a conversation and then asks the same question again. In order:
   - **Every open decision in the plan:** each stage's `### Decision needed`, and any choice the draft left open. Write each answer into the plan, in the stage's body and its todos, so the decision is part of the spec rather than a comment beside it. A question the user skips stays a `### Decision needed`, and that stage gets `labels: [needs-decision]`.
   - **Where it goes in the queue,** unless the user already said. The options are the end of the queue (the highest `priority:` among the plans in `.claude/plans/` plus 10), next, or a named place ("before WP49"). The answer becomes its `priority:`, set against the other plans'.
   - **Sign-off.** Ask: may agents start it? **Ready (Recommended)** adds `labels: [ready]` to the plan. **Backlog** leaves it unlabelled, for `/decide --backlog` later. Ready is the recommendation once every decision is settled. If a stage is still `needs-decision`, ready still lets agents build the stages that don't wait on it.

   Validate the YAML (below) after writing the answers in. If the user dismisses a prompt, stop asking: file the plan as it stands, as backlog, with every unanswered decision labelled `needs-decision`, so nothing is lost and `/decide` picks it up.
3. **File it.** Run the `plan-issues` skill on this one file (`/plan-issues .claude/plans/<slug>.plan.md`). It matches each stage against the open issues first, files the parent and its stages, places the parent under the `roadmap` issue by priority, and records every number in the plan. The same applies when this skill adds stages to a plan that is already filed (it has `issue:`): `plan-issues` files only what is new, and reopens the parent if it was closed.
4. **Open the PR.** Once the issues are filed and their numbers are recorded in the plan, `plan-issues` commits the plan file, pushes it and opens a pull request that holds only the plan change (`plan-issues` → Procedure, step 7). Running `/plan` is the request for that PR. The issues link to the plan file on the default branch, so they show the old plan, or none, until this PR merges. Do not merge it or wait for CI here: landing it is a separate step for the owner, or `/pr-land`.
5. **Report and finish.** Report the PR link, the parent issue, whether it is `ready` (and any stage still `needs-decision`), the stages it created, the open issues it matched, and where the plan sits in the queue. End by saying that this session is done: the plan is filed, the PR is open, and merging the PR is the only step left. Then stop. Do not start building a stage in the same session.

## Todos — a checklist of deliverables, not the spec

- **Always populate this list.** Every plan has at least one todo; break multi-file or multi-step work into one todo per independently-shippable deliverable.
- **Verb-first and specific.** Name the primary file/symbol touched, e.g. `"Add backup config schema + parser — see Config file format"`, not `"Config handling"`.
- **Independently checkable.** A reader can tell when each is done. If you can't state a done-signal, the todo is too big — split it.
- **Point to the body, don't restate it.** End `content` with `— see <Section>`; the full detail lives in that section and is never duplicated into the todo.
- **Keep `id` stable** once work starts.

## Executing a plan — keep the status live

A plan is not a write-once artifact. While you execute it, the plan file is the live progress tracker, so keep the frontmatter `status` fields in sync with reality:

- Flip a todo to `in_progress` when you start it and to `completed` the moment its work lands — one item at a time, not batched at the end. Use `cancelled` for a todo you drop, with the reason in the body.
- A stage's `status` derives from its todos unless set explicitly; set it explicitly to mark the stage you are actively working (`in_progress`) or one you are skipping (`cancelled`).
- Keep every edited scalar YAML-parseable (see the rules below) — appending a status note to a `content:` value is the most common way to break the render.

This keeps the plan-preview extension showing accurate progress and leaves an honest record if work is paused and resumed.

## Frontmatter is YAML — keep every scalar parseable

The frontmatter between the `---` fences is parsed as YAML. A single malformed scalar makes the **whole plan fail to render** in the Plan Preview extension — and the failure is silent (no error in the file itself). The free-text fields (`overview`, `content`, `goal`, `verification`, stage `title`) are where this breaks, because they hold prose that often contains YAML metacharacters. This bites most often when *appending status notes* to a `content:` value after work lands.

Rules for any unquoted free-text scalar:

- **No `: ` (colon-space) inside the value.** YAML reads it as a nested mapping and errors with `mapping values are not allowed here`. This is the #1 breaker. Reword — use ` — ` (em-dash) or `—` instead of `: ` (e.g. `raw_bind_parameter idiom — fs_uid binds once`, not `raw_bind_parameter idiom: fs_uid binds once`). A colon with **no** following space is fine (`state.rs:1672`, `ratio 3:1`).
- **No leading indicator char.** A value starting with `` ` `` `#` `&` `*` `!` `%` `@` `|` `>` `[` `{` `,` `?` `-` must be quoted or reworded. In particular a leading backtick (```` `foo` returns… ````) breaks parsing — lead with a word instead (``the `foo` accessor returns…``).
- **No unescaped `#` after a space** — YAML treats ` #` as a comment. Reword or quote.
- **If you must keep a metacharacter,** wrap the whole value in single quotes and double any internal single-quote (`content: 'uses ''foo'': bar'`). Prefer rewording over quoting so the file stays visually uniform.

**Before saving any plan, validate the frontmatter parses.** Extract the block between the first two `---` and run it through a YAML parser, e.g.:

```bash
sed -n '/^---$/,/^---$/p' <plan>.plan.md | sed '1d;$d' | python3 -c 'import sys,yaml; yaml.safe_load(sys.stdin); print("YAML OK")'
```

A non-zero exit or anything but `YAML OK` means the plan will not render — fix the offending scalar before handing back the plan.

## Body — concise but concrete

The body is where problem-specific detail lives — keep the *prose* tight, not the *substance*. Prefer short declarative sentences, tables, and code/interface sketches over paragraphs. Every claim should be checkable against a real file, type, or command — no vague hand-waving ("handle edge cases appropriately").

Cut anything a reader can already infer from the codebase (file layout, existing conventions) unless this plan changes it. State only what's new, different, or a real decision.

Soft-wrap prose: one line per paragraph/bullet, no manual hard-wraps — they render as cramped, ragged columns in the plan view (code blocks and tables are exempt). Link every file mention as a clickable path.

Recommended sections, in order — drop any that don't apply (a one-file change can be three short sections). For a staged plan, mirror the stages: one `## <Stage title>` section per stage holding its deliverable-level detail.

1. `## Context` / `## Problem` — what exists now and why the change is needed. A few sentences, not a narrative.
2. `## Approach` — key decisions and their rationale; include only when there's a real choice to justify (naming, algorithm, layout). Skip for mechanical work.
3. One `## <section>` per deliverable (or per stage) — the actual work: what to do, which files, a short code/interface sketch. Every todo traces to one of these.
4. `## Out of scope` — what this deliberately does **not** change. Guards against scope creep.
5. `## Tests` — what to cover; name the existing test files to mirror.
6. `## Verification` — the exact commands to run before it's done (e.g. the scoped unit-test, type-check, and format commands for the packages the plan touches).

Use tables for file→role maps, fenced blocks for interfaces/config, and `mermaid` for non-trivial flows. If a section is trending long, ask whether it's actually two deliverables that should split into two todos (or two stages).
