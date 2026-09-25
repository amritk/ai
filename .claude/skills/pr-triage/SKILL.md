---
name: pr-triage
description: Review every open, non-draft pull request in a GitHub repository and publish a triage page that gives each one a plain-language summary, CI and review state, and a Low / Medium / High / Critical risk rating, with a "start here" list of the PRs that most need a careful reviewer. Use whenever someone asks to go through the open PRs, summarise the PR queue, rate or rank PRs by risk, find which PRs are safe to merge or need attention, or wants a PR dashboard or report, even if they do not say "triage" or "risk".
argument-hint: "[owner/repo] [--include-drafts] [extra focus notes]"
allowed-tools:
  - Read
  - Write
  - Glob
  - Agent
  - ToolSearch
  - Artifact
  - mcp__github__list_pull_requests
  - mcp__github__pull_request_read
  - Bash(git remote:*)
  - Bash(mkdir:*)
  - Bash(python3:*)
  - Bash(gh:*)
---

# pr-triage

Turn the open pull-request queue into one page an engineering lead can act on:
every ready-for-review PR summarised, rated for risk, and sorted so the ones
that need a careful reviewer come first and the safe merges are easy to spot.

Reading is fanned out across subagents, one batch of PRs each; this skill
scopes the queue, briefs the reviewers, normalises their ratings, and builds
and publishes the page. Everything is read-only against GitHub: nothing is
posted, approved, or merged.

Invoke with `/pr-triage [owner/repo] [--include-drafts] [focus notes]`.

**Arguments** (from `$ARGUMENTS`):

- `owner/repo`: the repository. Default: the `origin` remote of the current
  checkout (`git remote get-url origin`).
- `--include-drafts`: keep draft PRs. By default drafts are dropped, because
  the page is for deciding what to review and merge, and a draft is neither.
- Remaining free text is passed to every reviewer as extra focus (for example
  "pay attention to anything touching billing").

---

## Phase 0: List the queue

1. Load the GitHub tools: ToolSearch `select:mcp__github__list_pull_requests,mcp__github__pull_request_read`.
   If they are unavailable, `gh pr list --state open --json ...` is the fallback.
2. List open PRs with `state: open`, `perPage: 100`, sorted by `updated`
   descending; page until the list runs out. Ask for the `number`, `title`,
   `draft`, `user`, `head`, `base`, `created_at`, `updated_at` fields only.
3. Drop drafts unless `--include-drafts` was given. If nothing is left, stop
   and say so.
4. Create a working directory in the scratchpad (never in the repo):
   `<scratchpad>/pr-triage/<owner>-<repo>/` with a `batches/` subdirectory.

Report the count to the user in one line before fanning out; a queue of sixty
takes several minutes to read and they should know that is expected.

---

## Phase 1: Fan out to reviewers

Split the PR numbers into batches of about ten, ordered as listed so a batch
tends to share an author or a theme. Spawn one `general-purpose` subagent per batch
in a single message so they run concurrently, `run_in_background: true`.

Each prompt is short; the substance lives in the brief:

```
Read <skill dir>/references/reviewer-brief.md and follow it exactly.
Repository: {owner}/{repo}.
Your PR numbers: {list}.
{if focus notes: "Extra focus from the operator: {focus}."}
Write your output to {work dir}/batches/batch{n}.json
```

Wait for every completion notification. If a batch errors or its file fails
`python3 -m json.tool`, re-spawn that batch once; if it fails again, list its
PR numbers under a **Not reviewed** note in the final summary rather than
silently dropping them.

---

## Phase 2: Normalise the ratings

Reviewers rate independently, so before building the page read every batch
file and check the ratings agree with each other and with the rubric in the
brief. Typical corrections:

- Two PRs with the same shape (say, small tested auth fixes) rated differently.
  Pick the one that matches the rubric's "consequence if wrong" test and adjust
  the other, editing the batch file directly.
- A rating driven by the directory rather than the blast radius: a two-line CI
  workflow tweak is not High just because it lives under `.github`.
- Missing mitigations: if `risk_reasons` only lists dangers and the PR is
  approved and well tested, add that so the reader sees both sides.

Then write `highlights.json` in the work directory. This is the "start here"
box at the top of the page, and it is the most-read part, so choose carefully:

```json
{
  "review_with_care": [
    { "number": 6137, "why": "re-lands the hosting change behind the 27 Aug outage; every hosted site is in the blast radius." }
  ],
  "quick_merges": [6318, 6319],
  "quick_merge_note": "Merge #6323 before #6326; they edit the same file.",
  "stale_note": "Most are from early August with no human review. Decide to review or close."
}
```

- `review_with_care`: four to six PRs where a mistake is expensive, each with
  one sentence saying what makes it so. Prefer concrete consequences over the
  word "risky".
- `quick_merges`: Low-risk PRs with passing CI and no open concerns. Leave out
  anything with changes requested or an unresolved bot finding.
- Both notes are optional; the stale list is derived automatically from PRs
  open 21 days or more.

---

## Phase 3: Build and publish

```
python3 <skill dir>/scripts/build.py \
  --repo {owner}/{repo} \
  --batches {work dir}/batches \
  --highlights {work dir}/highlights.json \
  --out {work dir}/pr-triage.html \
  [--include-drafts]
```

The script merges the batches, drops drafts unless asked, derives the counts
(risk tiles, failing CI, known conflicts, stale), and renders
`assets/template.html`. It exits non-zero on a malformed batch or a leftover
placeholder, so a clean run means the page is complete.

Publish with the Artifact tool (favicon `🔍`, description "Every open PR in
{owner}/{repo} with a summary, CI and review state, and a risk rating"). Where
the Artifact tool is not available, hand the HTML file to the user instead.
Keep the same file path on re-runs in one session so the URL stays stable.

---

## Phase 4: Terminal summary

Keep it under about fifteen lines. Lead with the link, then the counts as a
small table, then the "review with care" picks in one line each, then the
quick merges. Close with the two caveats that always apply: GitHub often has
not computed mergeability, so the conflict count is a lower bound; and a rating
measures blast radius, not quality, so High is a request for a careful
reviewer, not a verdict on the PR.

---

## Design notes

- **Reviewers collect, the orchestrator judges.** Ten PRs is about what one
  agent can read attentively; consistency across sixty comes from the shared
  brief plus the normalising pass, not from one agent reading everything.
- **Drafts are out by default.** The page answers "what should I review or
  merge today", and a draft is by definition not ready for either. The flag
  exists for the occasional "what is everyone working on" view.
- **The page is one file.** Data is embedded as JSON, filtering is client-side,
  and it needs no server, so it can be published as an artifact or attached to
  a message unchanged.
- **Highlights are hand-picked.** A sorted list already exists on the page; the
  "start here" box earns its place by being a judgment, so the orchestrator
  writes it after reading every assessment rather than the script deriving it
  from flags.
