---
name: async-daily
description: Summarise what you have been working on as an async standup, grouped by pull request — a "done" list of PRs that merged and a "doing" list of PRs still open plus uncommitted local work, written in plain language rather than commit messages. Covers every repo you touched, not just the ones checked out, over the last day by default or any number of days. Use for "/async-daily", "what did I do yesterday", "write my standup", "what have I been working on this week", or when someone needs a status update on their own recent work.
argument-hint: "[days] [--author <login>] [--local-only] [--root <dir>]"
allowed-tools:
  - Read
  - Bash(python3:*)
  - Bash(git log:*)
  - Bash(git status:*)
  - Bash(git remote:*)
  - Bash(gh:*)
  - ToolSearch
  - AskUserQuestion
  - mcp__github__get_me
  - mcp__github__search_pull_requests
---

# async-daily

Turn recent work into the standup you would actually type into Slack: what
landed, what is still in flight, in the words you would use out loud.

**The unit of work is the pull request, not the commit.** A PR is the thing that
got reviewed and merged, it is what a teammate recognises, and it is the only
unit that survives both merge styles. Commits are an implementation detail of
one — five commits chipping away at one PR are never five lines. Nor is it
ever fewer: one PR is exactly one line, however well two of them pair.

Invoke with `/async-daily [days] [flags]`. A bare number is the window in days
(default `1`). On a Monday, reach for `/async-daily 3`.

---

## Phase 1: Resolve whose work this is

The identity that matters is the **GitHub login**, because PR authorship is what
this skill groups by. Take it from `--author`, else `mcp__github__get_me`
(`login`), else the `origin` remote of the current repo.

**Never take the author from `git config user.email`.** In an agent session that
is the *agent's* identity (`noreply@anthropic.com`), so trusting it produces a
standup of the agent's commits. This is the single most likely way to get this
skill wrong.

## Phase 2: Collect

### GitHub is the primary source

Load the tools if needed: ToolSearch
`select:mcp__github__search_pull_requests,mcp__github__get_me`. Then two
searches, with `<since>` as an ISO timestamp (`2026-09-09T00:00:00Z`):

```
author:<login> is:merged merged:>=<since>     → done
author:<login> is:open updated:>=<since>      → doing
```

Ask for `number`, `title`, `repository_url`, `draft`, `created_at`,
`updated_at` only. Page until `total_count` is covered.

Going through GitHub rather than git is not a convenience — it is what makes the
answer correct:

- **It attributes agent work properly.** A PR opened by you whose commits were
  all authored by Claude is *your* PR on GitHub, and invisible to any
  author-matched `git log`.
- **It covers repos that are not checked out.** A day's work routinely spans
  more repos than the workspace has clones, and those would silently vanish.

`gh pr list --author <login> --state merged --json ...` is the fallback if the
MCP tools are unavailable.

### git supplies what GitHub cannot see

```bash
python3 <skill dir>/scripts/collect.py --days <n> --author <substring> [--root <dir>]
```

This is for **local work that is not a PR yet** — unpushed commits and a dirty
working tree. Nothing else in its output is needed when GitHub answered; it also
groups landed commits by PR on its own, which is the offline path when GitHub is
unreachable or `--local-only` was passed.

Its `--author` is a git identity substring, not a login. One short substring
usually covers every address someone commits under.

## Phase 3: Bucket

| Signal | Bucket |
| --- | --- |
| PR merged inside the window | **done** |
| PR open, created inside the window | **doing** |
| PR open, created earlier but updated inside the window | **doing**, only if genuinely worked on |
| Unpushed commits, or a dirty working tree | **doing** |

That third row is the one that needs judgement. `updated:` also fires on CI
runs, bot pushes, and rebases, so a months-old draft can look active. Treat an
older PR as real work only when something corroborates it — commits in the
window, a title matching other work that day. Otherwise leave it out, or sweep
the leftovers into a single closing line (`plus six older drafts still open`)
rather than itemising them.

Never list the same work under both headings.

## Phase 4: Write it

**One PR, one line.** Never fold two PRs into a single line, however neatly they
pair — not a stack, not a PR and its follow-up fix, not the same change rolled
across several packages. Each one was reviewed and merged on its own, and the
person reading wants to be able to find it.

A day is commonly twenty or more PRs, so a day is commonly twenty or more lines.
That is the correct length. Do not trim by merging.

**Order by repo**, and keep each repo's lines together. A flat list of twenty
lines in arbitrary order is what makes a long standup unreadable — not the
length. Within a repo, ascending PR number is fine.

**One number per line**, in the same `(repo #number)` form:

```
made sdk generation byte-identical in the typescript emitter (bane #1340)
```

**Translate the title.** Drop the conventional-commit prefix, the scope, and any
ticket ID. Say the effect, not the mechanism — `precompiled the schema
validator` is what you did, `made the config package load on Cloudflare Workers`
is what it means. Prefer the latter; the PR title usually contains both.

**Name the repo** on every line, so a line still says where the work was when it
is quoted on its own.

**Format.** Lowercase, one item per line, no bullets, no bold. Past tense under
`done:`, present participle under `doing:`. Mark drafts:

```
done:
made sdk generation byte-identical in the typescript emitter (bane #1340)
carried the byte-identical output to the remaining emitters (bane #1354)
added cohere as the first x-fern-* fixture (bane #1315)
fixed the three defects the cohere fixture turned up (bane #1326)
made the config package load on cloudflare workers (bane #1357)
gave the compiler a browser playground (compiler #16)
moved the wasm32 build onto an arena abi (compiler #19)
added a go column to the compiler benchmarks (compiler #24)
dispatched union values in mjst (mjst #342)
repaired the union values that dispatched to the wrong arm (mjst #343)
fixed boolean coercion (mjst #344)
stopped a delete-project test flaking on storage resets (scalar-org #6328)

doing:
giving the config package a write side (bane #1362)
resolving the last three speakeasy import paths (bane #1363, draft)
upgrading knip to v6 so it runs under typescript 7 (scalar-org #6344)
adding an async standup skill (local, not pushed)
```

Omit a section entirely when it is empty rather than printing an empty header.

## Reporting honestly

- **Say nothing you did not verify.** If the window is empty, say so and suggest
  a wider one rather than padding the list.
- **Local work with no PR is still work.** Read the file list and describe it —
  an untracked `skills/async-daily/` is "adding an async standup skill", not
  "one untracked directory".
- **Do not invent progress.** If a PR only renamed things, the line says a
  rename. The value of this is that it can be trusted on a Monday.
