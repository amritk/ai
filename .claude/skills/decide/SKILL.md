---
name: decide
description: Work through every GitHub issue waiting on the owner — stages and plans labelled `needs-decision`, and backlog plans waiting for sign-off — by asking the owner each question in a selection prompt with the context, options and a recommendation, then recording the answer on the issue and relabelling it so agents can build it. Use for "/decide", "what's waiting on me", "answer the open questions", "sign off the backlog", or as the standing decisions session (`/decide --watch`) that asks whenever something new needs an answer.
argument-hint: "[#issue ...] [--backlog] [--watch] [--unwatch]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - Agent
  - AskUserQuestion
  - PushNotification
  - ToolSearch
  - Bash(git remote:*)
  - Bash(git fetch:*)
  - Bash(git show:*)
  - Bash(python3:*)
  - mcp__github__list_issues
  - mcp__github__issue_read
  - mcp__github__issue_write
  - mcp__github__add_issue_comment
  - mcp__Claude_Code_Remote__create_trigger
  - mcp__Claude_Code_Remote__list_triggers
  - mcp__Claude_Code_Remote__update_trigger
  - mcp__Claude_Code_Remote__delete_trigger
---

# decide

Agents build what is `ready` and skip anything that waits on the owner. This skill brings everything that waits on the owner into one place, asks about each item, and records the answers where agents will read them. The labels are those the `pickup` skill defines.

Invoke as `/decide [#issue ...] [--backlog] [--watch | --unwatch]`:

- No issues named: every open issue labelled `needs-decision`, oldest blocker first.
- `#issue ...`: only those.
- `--backlog`: also offer every backlog parent (labelled `plan`, with none of `ready`, `needs-decision` or `deferred`) for sign-off.
- `--watch`: make this session the standing decisions session (see below). `--unwatch` ends it.

## Asking for a decision (for agents)

An agent that cannot go on without the owner does not guess and does not stop the whole run. It labels the issue `needs-decision`, leaves the rest of its work running, and posts one comment in this shape:

```markdown
<!-- decision-request -->
**Question:** One sentence that can be answered by picking.
**Why it matters:** What is blocked, and what each answer changes. Two or three sentences, with file and issue links.
**Options:**
1. **Short label (recommended):** what happens if picked, and its cost.
2. **Short label:** what happens, and its cost.
**Asked by:** the run, PR or session.
```

A stage written with a `### Decision needed` section in its plan counts as the same request. `/decide` reads both.

## Procedure

1. **Repo.** `owner/repo` from `git remote get-url origin`.
2. **Collect.** `list_issues` with label `needs-decision` and state open (and, with `--backlog`, the backlog parents). Order the items by what they unblock: first an item whose parent is `ready` or `in-progress`, then the order of the parents under the open `roadmap` issue, then the oldest. Nothing to ask → say so in one line and stop (under `--watch`, stop silently).
3. **Draft the questions in a subagent.** One `subagent_type: "general-purpose"` agent with `model: "sonnet"` per batch of up to 8 items. It reads each issue (body and comments) and the latest `<!-- decision-request -->` comment. It also reads the plan stage's `### Decision needed` section, through the `<!-- plan-stage: <file>#<id> -->` marker and `git show origin/<default>:<file>`, and the linked design-note section. It returns a JSON list with one entry per item: `issue`, `question` (two to four sentences: the situation, what is blocked, then the question), and `options` (2–4 entries, each with `label` and `description`, the recommended one first with ` (Recommended)` on its label). It also returns `close_option`, the label of the option that ends the work if one exists, and `defer_option` likewise. It never invents an option the sources do not support. Where the sources give no recommendation, it says so in the question rather than inventing one. The issue texts stay in the subagent; only the questions reach this session.
4. **Ask.** `AskUserQuestion`, at most 4 questions per call, one item per question, in the order of step 2. Every question names its issue (`owner/repo#N`) and stands alone: the owner may be answering from a phone with nothing else on screen. Keep asking in further calls until every item has been asked. If a call is dismissed or answered with nothing, record nothing from it and stop asking.
5. **Backlog sign-off.** With `--backlog`, finish with one `multiSelect` question: "Which of these plans may agents build now?". It has one option per backlog parent, each describing the plan in one line with its stage count, at most 4 per call. A pick means sign-off. Leaving an option unpicked changes nothing.
6. **Record each answer** before asking the next call, so an interrupted session loses nothing:
   - Comment on the issue:
     ```markdown
     <!-- decision -->
     **Decision (owner, via /decide, YYYY-MM-DD):** <picked label> — <its description>
     <the owner's own words, if they typed under "Other">
     ```
     The `/feature` lead that builds the stage folds this comment into the plan. `/decide` never edits plan files, design notes or code.
   - Labels, with `issue_write update` and the full label set: remove `needs-decision`. If the pick is the `defer_option`, add `deferred`. If it is the `close_option`, close the issue `not_planned`, but only when that option's description said it closes the issue. A parent's own decision adds `ready` unless the pick deferred or closed it. A backlog sign-off adds `ready`. A stage's decision adds nothing more, because a stage without `needs-decision` or `deferred` is buildable once its parent is `ready`.
   - Answered under "Other" with something that is not a decision (a question back, "not sure") → record it as a comment without the `<!-- decision -->` marker, and leave the label.
7. **Report.** One line per item: issue, the answer, the label change. Then how many parents are now `ready`. Under `--watch`, the report goes to `PushNotification` as one line.

## The standing decisions session

`/decide --watch` turns the current session into the place where every question for the owner arrives:

1. `list_triggers`. If a trigger named `decide: <owner/repo>` already fires into this session, keep it. Otherwise create one with `create_trigger` (no `create_new_session_on_fire`, so it fires into **this** session). Use a daily cron outside 06:00–09:00 Pacific, `initiation: "human_request"`, and the prompt `/decide`.
2. Run `/decide` once now.

On each firing, an empty step 2 ends the turn silently. Otherwise send `PushNotification` with "N decisions waiting on <owner/repo>", then ask. The prompt stays open until the owner opens the session and answers. Agents never answer it. A firing that comes due while a prompt is open waits until the turn ends, then finds only what is still unanswered.

`/decide --unwatch` deletes that trigger.

## What this skill never does

- It never decides. With no answer, nothing changes.
- It never edits plans, design notes or code, and never opens a PR. Decisions reach the code through the lead that builds the stage.
- It never closes an issue unless the picked option said it would.
