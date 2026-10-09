---
name: plan
description: Write or update implementation plans as .claude/plans/<slug>.plan.md files using the stages frontmatter schema rendered by the plan-preview extension. Use whenever asked to write, draft, produce, revise, or update a plan file — including when presenting a plan from plan mode — instead of emitting the plan as chat text or ad-hoc markdown. This is about authoring the plan *file*; it is not the Plan architect agent or the harness plan mode.
---

# Writing plans

Write plans as plan files: `.claude/plans/<slug>.plan.md` — YAML frontmatter, then a Markdown body. This is our own **stages** schema (below), rendered by the plan-preview extension; it is **not** the `.md` **rules** schema in `.claude/rules/`.

A plan is a **checklist of deliverables in the frontmatter** plus **narrative detail in the body**. Small work is a flat `todos` list; larger work is broken into **stages**, each a mini-plan with its own goal, todos, and exit criteria.

A plan without a populated `todos` list (flat, or inside every stage) is incomplete — never hand back a plan with an empty or missing todos array.

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
