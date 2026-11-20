---
name: pickup
description: Pick up, work, hand off or take over one GitHub issue in a repo that tracks its plans as issues (filed by `plan-issues`) — what the labels mean, which issue to take, how to claim it, the one status comment, when to push, how a PR closes it, how to ask the owner, how to stop, and how another agent takes over. Use for "pick up #123", "pick up WP50", "what can I work on next", "take over #123", "continue where the last session stopped", or before working any issue labelled `plan`, `ready` or `in-progress`.
argument-hint: "[#issue | next]"
allowed-tools:
  - Read
  - Grep
  - Glob
  - ToolSearch
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(git log:*)
  - Bash(git fetch:*)
  - Bash(git checkout:*)
  - Bash(git add:*)
  - Bash(git commit:*)
  - Bash(git push:*)
  - Bash(git show:*)
  - mcp__github__list_issues
  - mcp__github__issue_read
  - mcp__github__issue_write
  - mcp__github__add_issue_comment
  - mcp__github__update_issue_comment
  - mcp__Claude_Code_Remote__get_session
---

# pickup

How one agent works one issue so that nobody does the work twice, the issue always says where the work stands, and any session can die without losing it. The issues come from `plan-issues`: a **parent issue** per plan, labelled `plan`, whose `<!-- plan: <path> -->` marker names its plan file, and a **sub-issue** per stage, one pull request each, in merge order. The plan file holds the spec and the issues hold the state. The repo's own agent guide (`AGENTS.md`, `CLAUDE.md`) may add to this — what else to update when a plan finishes, for example — and wins where it is stricter.

To build a whole parent, with a session per stage, a review loop and merges, use `/feature #<parent>` or `/feature --next`; it follows these rules for the parent and its stages. This skill is for one stage worked in one session.

## The labels

Agents read these, so their meaning is fixed:

| Label | On | Meaning |
| --- | --- | --- |
| `roadmap` | the one Roadmap issue | its sub-issues are every plan, in the order work is picked up |
| `plan` | every parent | a plan file backs this issue; its `<!-- plan: path -->` marker names the file |
| `ready` | a parent | the owner signed off: a `/feature` lead may pick it up without asking |
| `needs-decision` | a parent or stage | waits on the owner; `/decide` asks them. No agent builds it |
| `deferred` | a parent or stage | wanted, not scheduled. No agent builds it |
| `in-progress` | a parent or stage | an agent or a `/feature` run has claimed it |

A parent with none of `ready`, `needs-decision` and `deferred` is backlog. It is planned but not yet signed off, and `/decide` offers it for sign-off. A stage with neither `needs-decision` nor `deferred` may be built once its parent is `ready`.


## Which issue

- **Named** (`/pickup #123`): take it if it is open, its parent is `ready`, and it carries none of `needs-decision`, `deferred` or `in-progress`. A claim older than the takeover rule below allows may be taken over instead. Otherwise say why not and stop.
- **Next** (`/pickup next`, or "what can I work on"): walk the open issue labelled `roadmap`, whose sub-issues are the parents in pickup order. In the first `ready` parent that is not `in-progress`, take the first open stage that carries none of the three labels. In a repo with no `roadmap` issue, use the open parents labelled `plan` and `ready`, lowest `priority:` in their plan file first.

## Working it

1. **Claim** it (below) before writing any code.
2. **Read** the stage's `## <title>` section of the plan file, the design-note section it links, and every comment on the issue. An owner's answer recorded by `/decide` opens with `<!-- decision -->` and binds the work, even where the plan says otherwise. A stage's own sub-issues are issues its PR also resolves.
3. **Build** on a branch, following the repo's rules for commits, tests and generated files. Checkpoint as below.
4. **Open the PR** with `Fixes #<stage issue>` in its body, and one `Fixes #<n>` line for each open sub-issue of the stage, so the merge closes them. Keep those lines if the body is rewritten. A squash merge that drops them leaves the issue open: whoever merges confirms it closed, and closes it (`completed`) if not.
5. **When a parent's last stage closes**, close the parent (`completed`) and drop its `in-progress` and `ready`. Do whatever the repo's guide adds for a finished plan.
6. **A question only the owner can answer**: label the issue `needs-decision` and post the decision request in the shape the `decide` skill gives. Remove `in-progress`, and go on with work that does not wait on it.
7. **New work** for a plan is a stage added to its plan file in a PR, then `plan-issues`, which files the sub-issue and reopens the parent if it was closed.

## Claim, checkpoints, hand-off and takeover

Any session can die: a container is reclaimed, a context runs out, a run is aborted. So whoever works an issue leaves it in a state that another agent can pick up, and does that at a few fixed moments rather than on a timer, because every write costs a call and every comment notifies people.

- **Claim.** Add `in-progress` to the issue, and post **one** status comment opening with `<!-- status -->`. It names the session (its link), the branch, and the next step. There is one status comment per issue. Later updates **edit** it (`update_issue_comment`) instead of adding comments.

  ```markdown
  <!-- status -->
  **State:** claimed | building | PR open | blocked | stopped | taken over
  **Where:** the stage (and, on a parent, which stages are done, open or running), and the todo in hand
  **Branch:** `branch-name` @ `short sha` of the last push · **PR:** #N or none
  **Session:** link · **Updated:** YYYY-MM-DD HH:MM UTC
  **Next step:** one sentence a stranger could act on
  ```
- **Checkpoint: push, then edit the status.** Commit and push the branch when a todo is finished and builds, before a long run (a full suite, a benchmark), and before the session stops for any reason. A push to a branch with no PR runs no CI and wakes no one, so these pushes cost almost nothing. Once a PR is open, push only when there is something for CI or a reviewer to see, because each push reruns CI. Edit the status comment only when the next step changes: a todo done, blocked, the PR opened. Do not edit it for progress inside a todo. At most one edit an hour is the target.
- **Stopping unfinished.** Push, then edit the status to say where it stopped, what is half done, and the exact next step. Then remove `in-progress`. An agent that can see its context or time running out does this first, before trying to finish.
- **Blocked on the owner.** Edit the status, add `needs-decision`, post the decision request (`decide` skill), and remove `in-progress`.
- **Takeover.** An issue labelled `in-progress` is stale when its status comment and its branch's last push are both more than 24 hours old, and the session it names is not working (`get_session`, where available). Any agent may then take it over. It edits the status comment to name itself and the takeover, starts from the pushed branch (never from scratch when a branch exists), and follows the status comment's next step. A parent claimed by `/feature` is taken over through its tracking issue instead (`feature` → Issue mode).

