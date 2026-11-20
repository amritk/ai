---
name: plan-issues
description: Turn plan files into GitHub issues — one parent issue per `.claude/plans/<slug>.plan.md`, one sub-issue per open stage, existing issues reused instead of duplicated, every parent hung under one ordered Roadmap issue — and record the issue numbers back into the plans. Use for "/plan-issues", "file these plans as issues", "sync the plans to GitHub", "make issues from the roadmap", after adding a stage to a plan, or to reopen a finished plan with new work. Idempotent; rerunning creates only what is missing.
argument-hint: "[plan paths...] [--dry-run] [--no-root] [--no-match]"
allowed-tools:
  - Read
  - Edit
  - Agent
  - ToolSearch
  - Bash(python3:*)
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git remote:*)
  - Bash(gh api -X GET search/issues:*)
  - mcp__github__issue_read
  - mcp__github__issue_write
  - mcp__github__sub_issue_write
  - mcp__github__list_issues
  - mcp__github__add_issue_comment
  - mcp__github__update_issue_comment
  - mcp__Claude_Code_Remote__get_session
  - mcp__claude-code-remote__get_session
---

# plan-issues

Plans say **what** to build. Issues say **where it stands**. This skill files each plan as issues so agents can claim, track and close the work on GitHub, and writes each issue's number back into its plan, so the next run knows the issue exists.

| Plan file | GitHub |
| --- | --- |
| the plan | a **parent issue**, label `plan` plus the plan's `labels` |
| an open stage (not `completed`/`cancelled`) | a **sub-issue** of the parent, in stage order, with the stage's `labels` |
| a stage's `issue: N` | that existing issue, attached as the sub-issue instead of a new one |
| a stage's `related: [N, ...]` | existing issues attached as sub-issues **of the stage's issue** |
| `priority` | the parent's place under the **Roadmap** issue (lower first) |

## The labels and the state

The labels these issues carry, and how agents claim, checkpoint, hand off and take them over, are the `pickup` skill's. This skill only applies them.

**Issues hold the state.** Once a stage has an issue, its open or closed state is the truth, and the stage's `status:` in the plan is not kept up to date. A PR closes a stage with `Fixes #N`. A `/feature` run closes the parent when its last sub-issue closes.

## Plan fields this skill adds

These are optional fields on top of the `plan` skill's staged schema. The script rejects a plan where they are malformed.

```yaml
roadmap: docs/roadmap/wp49.md   # a human-facing page, linked from the parent
spec: docs/wp49.md              # the design note, linked from the parent
priority: 10                    # Roadmap order; a plan with neither priority nor issue is not filed
labels: [ready]                 # parent: ready | needs-decision | deferred
issue: 1900                     # written by this skill
stages:
  - id: s6-gate
    title: WP49 S6 — ...        # the sub-issue's title: make it self-contained
    issue: 1637                 # an existing issue that IS this stage, or written by this skill
    related: [1402, 1468]       # existing issues this stage's PR also resolves
    labels: [needs-decision]    # needs-decision | deferred
```

Each stage's body section (`## <stage title>`) is copied into its sub-issue, so write it to stand alone. A stage that needs a decision has a `### Decision needed` subsection with the question, the options and a recommendation. `/decide` reads it.

## Procedure

Use `<skill dir>/scripts/plan-issues.py` for everything except the GitHub calls.

1. **Check.** `python3 <skill dir>/scripts/plan-issues.py check [plans...]`. Fix every error before going on. A plan that fails here would file a broken issue.
2. **Match existing issues first.** Skip this step only with `--no-match`. A stage with no `issue` may already be someone's open issue. Filing a new one would leave the old one orphaned and the work counted twice.
   - **Candidates:** every open issue (`list_issues`, state open, fields `number`, `title`, `labels`, paginated), minus:
     - the numbers `python3 <skill dir>/scripts/plan-issues.py used` prints (already in a plan);
     - issues labelled `plan`, `roadmap` or `feature-run`;
     - pull requests.
   - **Judging:** give the candidate list (number, title, labels) and each unfiled stage (its title, goal, todos and `## <title>` section) to one `subagent_type: "general-purpose"` agent with `model: "sonnet"`. It reads the body of every candidate whose title could plausibly fit, and returns for each stage at most one `issue` and any number of `related`, each with one line of evidence:
     - **`issue`**: the candidate asks for exactly this stage's deliverable, so the stage's PR closing it is the right outcome.
     - **`related`**: the candidate reports a symptom the stage fixes, or a part of its work, so the same PR resolves it too.
     - **neither**: anything less. When unsure, leave it out. A wrong match closes someone's issue with a PR that did not address it, which is worse than a duplicate.
     - Each candidate goes to at most one stage across all the plans.
   - **Record:** `issue_read get` each match and drop any whose `parent` is already set. Then write the rest into the plans with `python3 <skill dir>/scripts/plan-issues.py record <file> --stage <id>=<N>` and `--related <id>=<N>[,<N>...]`, before anything is filed. The plan stays the record of what each issue is for.
   - **Dry run:** with `--dry-run`, print the matches with their evidence and record nothing.

   Step 5 then treats a matched stage like any stage with an existing issue: it attaches the issue as a sub-issue, adds the stage's labels, and comments the link, without rewriting the issue's title or body. A stage with no match is the only kind that gets a new issue.
3. **Render.** `python3 <skill dir>/scripts/plan-issues.py render --repo <owner/repo> [plans...] > <scratch>/issues.json`. `owner/repo` comes from `git remote get-url origin`. This JSON is the exact title, body and labels of every issue. Do not write issue text by hand. With `--dry-run`, print a table (plan, parent title, new or existing, stage count, labels) from it and stop.
4. **The Roadmap issue.** Unless `--no-root` is passed, find the open issue labelled `roadmap` with `list_issues`. If none exists, create one titled `Roadmap`, labelled `roadmap`, with a body saying its sub-issues are the plans in pickup order and that reordering them reorders the work.
5. **Execute.** Go through the plans in the rendered order. With more than about 10 issues to write, give this step to one `subagent_type: "general-purpose"` agent with `model: "sonnet"`, passing it the JSON path, these rules and the record command. It returns counts and failures. The writes stay out of the lead's context.
   - **Parent, `issue` null.** First guard against a run that created the issue but died before recording it: `gh api -X GET search/issues -f q='repo:<owner/repo> in:body "plan: <file>"'`. If a match exists, record that number and skip creating. Otherwise create the issue with `issue_write` (`create`, the rendered title, body and labels). Then immediately run `python3 <skill dir>/scripts/plan-issues.py record <file> --parent <N>`. Recording after every write is what makes a rerun safe.
   - **Parent, `issue` set.** Leave the title and body alone. If the parent is closed and the plan has an open stage with no issue, reopen it (`state: open`): new work moves it out of done.
   - **Roadmap order.** Make the parent a sub-issue of the Roadmap issue (`sub_issue_write add`; it takes the parent's `id`, not its number: `issue_write` returns `id` for a create and for an update, and `issue_read` does not return it) unless it already is one. Then place it by priority. Among the parents already under the Roadmap issue, find the last one whose plan has a `priority` no higher than this plan's: the plans give each parent's number, and `issue_read get_sub_issues` on the Roadmap issue gives their ids. Move the new parent after it with `sub_issue_write reprioritize`, or before the first parent if there is none. A parent that was already under the Roadmap issue is never moved, because the owner may have reordered it by hand.
   - **Stage, `issue` null.** Create it with `issue_write` (`create`, the rendered title, body and labels, `parent_issue_number` the parent). Then immediately run `record <file> --stage <id>=<N>`.
   - **Stage, `issue` set.** `issue_read` it for its labels, state and parent. Then `issue_write update` it with the union of its labels and the stage's labels (the update replaces the whole set). That call also returns the issue's `id`, which `sub_issue_write` needs, so make it even when the union adds nothing. Attach it under the parent with `sub_issue_write add`, unless it is already a sub-issue there. If it is attached to another parent, report it and leave it. Post one comment linking the plan stage, opening with `<!-- plan-stage: <file>#<id> -->`, unless such a comment is already there. Never rewrite an existing issue's title or body: someone wrote it, and it may be cited.
   - **Related.** Attach each one under the stage's issue the same way (its `id` from a label-union `issue_write update`), with one linking comment.

Use only the GitHub tools for writes. A label's first use creates it. Two agents that use a new label at the same moment can race, and one write fails; retry it once.
6. **Verify.** Run `render` again. Every plan and every open stage now has an `issue`. For each parent, `issue_read get_sub_issues` lists its stages in plan order. Reorder with `sub_issue_write reprioritize` where they are out of order.
7. **Hand back.** The plan files now carry issue numbers. Commit them under the repo's own rules (branch, PR, commit format). Report what was matched (with the evidence), what was created, what was reused, and what was skipped and why, with links to the Roadmap issue and each parent.

## Adding work later

To add work to a plan, add a stage to the plan file in a PR and run this skill. It looks for an open issue that already is that work, then attaches it or creates the new sub-issue and reopens the parent if it was closed. To retire a stage, close its issue with `not_planned`. Do not delete the stage from the plan: its `issue:` is the record.

## What this skill never does

- It never closes an issue, never edits an existing issue's title or body, and never removes a label it did not add.
- It never files a completed stage as a closed issue. History stays in the plan and the repo.
- It never creates an issue without recording its number before the next write.
