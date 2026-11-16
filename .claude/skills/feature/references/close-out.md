# Close-out — acting on the action items, and chaining the next run

The action items list (close-out step 8) is what is left for a human to decide. Most of those decisions end in something the lead could do itself in one tool call: merge a PR, delete a branch, start the next run. So the lead lets the human answer by picking options, and then does what they picked. It no longer prints a list and expects someone to type each item back.

## The selection prompt

Once the summary and its `Action items:` block are printed, ask about the items the lead can act on with `AskUserQuestion`.

**What can be offered.** An item can be offered only when the lead can carry it out in this session, with a tool it holds, and the result can be checked afterwards. Examples: merge a PR whose gate passes, open one more review round, delete a leftover branch, edit or delete a comment the run posted, open a PR adding the proposed `CLAUDE.md` line, start or chain the next-step run. An item that only a human can do stays in the printed list and is never an option: anything that needs their own credentials or account (publishing to npm, a secret, a release outside GitHub), a judgement about product direction, or a fix the human said they would make themselves.

**One decision per question, with everything needed to decide it.** The human answers from the dialog alone. They may be on a phone, with the summary scrolled away. They should never need to open the PR to understand the choice. So each action item gets its own single-select question, built like this:

- **The question** states the situation in two to four sentences, then asks. Cover what is blocked and where (PR, job or file, as a link or `owner/repo#N`), why it is blocked (the concrete cause, with names: the file, the rule, the finding), what the obvious fix is and why the lead did not just make it (outside the stage's owned files, needs a decision, against a repo rule). End with the question itself: "How should I fix it?", "Should I merge it?".
- **Each option** is one path forward. The label is a short imperative (`Exempt .refcache`, `Run a 7th review round`). The description says exactly what the lead will do if it is picked: which file, which command, which comment. Then it gives the trade-off or cost in one clause: what is lost, what extra is touched, what stays broken.
- **The option you would pick** goes first, with ` (Recommended)` on its label. Its description says why, if that is not obvious from the trade-off.
- **Always offer a way to leave it**, for example `Leave it for me` or `Leave it red`. Its description says what is left behind and where it is noted, for example "Push nothing; note the blocker on the PR for whoever picks it up."

An example, for a lint job failing on a run's PR:

> **Question:** CI's lint job on owner/repo#1659 is failing because `scripts/check-filenames.mjs` rejects the committed kramdown-rfc cache files (`.refcache/reference.RFC.4648.xml` and others), whose names kramdown-rfc dictates. The clean fix is a one-line exemption for `.refcache/` in `scripts/check-filenames.mjs`, but that file is outside the stage's owned files. How should I fix it?
>
> - **Exempt .refcache (Recommended):** Add `.refcache/` to the exempt roots in `scripts/check-filenames.mjs`, with a comment that kramdown-rfc names these files. One extra file outside the owned list.
> - **Stop committing .refcache:** Gitignore `.refcache/`. `build-spec.sh --check` then needs `--fetch` (network access to bib.ietf.org) in a fresh checkout, so the offline, reproducible build is lost.
> - **Leave it red:** Push nothing; note the blocker on the PR for whoever picks it up.

Write it from what the run already knows: the ledger, the review findings, the escalation reason. Never write "see the PR". If the lead does not know the cause well enough to write the question, it cannot offer a fix either, so the item stays in the printed list.

**Housekeeping** can share one `multiSelect` question, "Which of these should I do now?": deleting leftover branches, editing comments the run posted, archiving a session that refused to archive. These are items with only one way forward and nothing to weigh. Each option's description still names exactly what will be touched (the branch names, the comment links). An unpicked option means "leave it".

**The next-step run** always gets its own question (see below).

**How many.** The tool takes 1–4 questions per call, with 2–4 options each, and adds "Other" by itself. Order the questions by what unblocks the most, and ask them in calls of up to four until every offerable item has been asked. The human is there answering, so a second call costs nothing. Stop at the first call that is dismissed or answered with nothing.

**What a pick authorises.** A pick authorises exactly the action on that option, once, and nothing more. "Merge #1657" is not "merge whatever else is green". A merge picked here still goes through the merge gate (`references/merge-gate.md`): if the gate fails, report why and leave the PR. A pick does not override the repo's rules either. If the repo forbids something, say so and skip it.

**After the answers.** Carry out the picks in the order of the questions. Report each one's result in one line. Then print the action items again with what was done ticked (`- [x]`) and what is left unticked. Post the same list to the tracking issue, so the record matches. Then print `The End`.

If the human dismisses a prompt or answers nothing, act on nothing from that call, ask no further calls, and carry out only what earlier calls picked. Never ask the same item twice. If no item can be offered, skip the prompt.

## Chaining the next run

The next-step `/feature` prompt (close-out step 2) often cannot start yet. For example, the next run needs a package this run changed, and that package is not on npm until someone merges the release PR. Starting it early wastes a whole run. Waiting means someone has to remember to come back. So the next step records its **prerequisites**, and the lead can start it when they are met.

**Writing the prerequisites.** Under the fenced prompt, list each prerequisite as one line the lead can check by machine, with how to check it:

- a PR is merged: `owner/repo#N merged` (`pull_request_read`)
- a release or tag exists: `owner/repo release vX.Y.Z` (`list_releases`, `list_tags`)
- a version is on a registry: `npm: pkg@>=X.Y.Z` (the registry's public metadata, for example `https://registry.npmjs.org/pkg`)
- a file or export is on the default branch: `owner/repo:path contains <text>` (`get_file_contents`)
- CI on the default branch is green: `owner/repo main CI green` (`actions_list`)

"When the API is stable" or "once the team agrees" is not a prerequisite. It is a decision for a human, so it goes in the action items and the next step is not chained.

**The question.** Ask about the next step with these options, leaving out any that do not apply:

- `Start it now`: only if every prerequisite is met already. Start a new cloud session with `create_session`, with the next-step prompt as its prompt. Do not run the next run inside this lead. Its context belongs to this run.
- `Start it when prerequisites are met`: only if at least one prerequisite is unmet and all of them can be checked by machine. Set up the watcher below.
- `Don't start it`: the prompt stays in the closing comment for later.

**The watcher.** Use `create_trigger` with `create_new_session_on_fire: true`, a cron of every 4 hours, and `initiation: "human_request"`. Each firing starts a fresh, small session. That is cheaper than waking this lead with its whole context. The trigger's prompt must stand alone, because the new session knows nothing else. It contains:

1. The prerequisites, each with its check.
2. The next-step `/feature` prompt, verbatim.
3. Its own trigger id and the give-up date: 7 days from now, or whatever the human typed under "Other".
4. These instructions: check every prerequisite. If any is unmet and the give-up date has not passed, end without doing anything. If all are met, start the next run with `create_session`, comment the new session's link on the tracking issue, send a `PushNotification`, and switch the trigger off with `update_trigger` (`enabled: false`). A session a trigger started cannot delete that trigger. If the give-up date has passed, switch the trigger off, comment which prerequisite was still unmet, and send a `PushNotification`.

The chained run stops at its own plan sign-off, like any other `/feature` run. Chaining saves the wait, not the human gate. That is why a chained start is safe to leave alone.

This watcher is the one trigger close-out leaves running on purpose. Cleanup (step 4) deletes the run's check-ins, not this. Name it in the final comment with its trigger id, the give-up date, and how to cancel it (`delete_trigger <id>`). Also add a ticked action item: `Next run chained: starts when {prerequisites} — cancel with delete_trigger <id>`.
