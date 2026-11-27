---
name: pr-merge
description: Ship this session's work in one command — commit and push the branch, open a pull request for it (or reuse the open one), review it, fix red CI and merge conflicts on it, drive it to merged with /pr-land, then archive this session. Use for "/pr-merge", "open a PR, review and merge, then archive", "ship it and close the session", "PR this and merge it", or whenever the work in this session is done and should go to main with no more typing.
argument-hint: "[pr number | url] [--no-review] [--keep]"
---

# pr-merge

The short way to say "open a PR, review it, fix its CI and conflicts, merge it, archive this session". This skill only gets the work into an open PR; everything after that is `/pr-land`, so the merge rules live in one place. A red check or a conflict with the default branch does not stop the run: `pr-land` fixes it on this session's branch, then merges once its merge gate passes. A check that is red on the default branch too, or a person's hold or open thread, still stops it.

Invoke with `/pr-merge` on the branch that holds the work, or `/pr-merge <pr>` for a PR that is already open.

- `--no-review`: skip the review before merging.
- `--keep`: keep this session after the merge instead of archiving it.

## 1. Get the work into an open PR

Skip to step 2 when a PR was given.

1. **House rules.** Read the repo's `CLAUDE.md`. Its commit, branch, and attribution rules apply to everything below.
2. **Branch.** Resolve `owner/repo` and the default branch from `origin`. On the default branch, create the branch this session was told to develop on (or a descriptive one) and move the work there. Never push to the default branch.
3. **Commit.** If `git status` shows uncommitted work, commit it in the repo's commit format. Commit only this session's work. Never commit secrets or local settings (`.env`, credentials, `.claude/settings.local.json`); leave them out and say so.
4. **Push** with `git push -u origin <branch>`. If the push is rejected because the remote has commits you lack, merge them in (`git fetch origin <branch> && git merge --no-edit FETCH_HEAD`) and push again. Never force-push.
5. **Find or open the PR.** An open PR from this branch is the PR. Otherwise open one against the default branch. Before writing the body, look for `pull_request_template.md` or `.github/PULL_REQUEST_TEMPLATE/` and fill in its headings from the diff; skip any section that asks for secrets or internal hosts. Write the title and summary from the diff against the base, not from the session's history. A branch whose PR already merged gets a new PR, not the old one.

If nothing differs from the default branch, there is nothing to ship: say so and stop.

## 2. Land it

Invoke the `pr-land` skill with `<pr> --review --archive`, dropping `--review` for `--no-review` and `--archive` for `--keep`. Pass along what the user asked the review to look for, if anything. From here `pr-land` handles the review, fixing red CI and merge conflicts, feedback, the merge gate, the merge, and the archive. Do not duplicate any of it here.

The user typing `/pr-merge` is the request to archive that `pr-land --archive` needs, so archive this session once the PR merges, even inside a longer conversation. If the PR does not merge, `pr-land` keeps the session and reports why.
