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

**Housekeeping** can share one `multiSelect` question, "Which of these should I do now?": deleting leftover branches, editing comments the run posted, archiving a session that refused to archive, and **Archive this session** (the lead itself), offered when every slice merged and nothing escalated. Archiving the lead ends the conversation, so this pick runs last of all (see **After the answers**). These are items with only one way forward and nothing to weigh. Each option's description still names exactly what will be touched (the branch names, the comment links). An unpicked option means "leave it".

**The next-step run** always gets its own question (see below).

**How many.** The tool takes 1–4 questions per call, with 2–4 options each, and adds "Other" by itself. Order the questions by what unblocks the most, and ask them in calls of up to four until every offerable item has been asked. The human is there answering, so a second call costs nothing. Stop at the first call that is dismissed or answered with nothing.

**Picks that have to wait go to a new session.** By the time of this prompt, close-out step 4 has unsubscribed every PR, deleted the check-ins and archived the workers, so nothing will wake this lead again. A pick the lead can finish now and check right away, it does here: a merge whose gate passes at the current head, deleting a branch, editing a comment, opening the `CLAUDE.md` PR. A pick that has to wait for CI, for a review round, or for a worker to push fixes goes to a fresh session. Start it with `create_session`, with the prompt `/pr-land <owner/repo#N>`, plus `--review` for another review round, and add one sentence on why the PR is open and what was picked. Tick it as `handed to <session link>`. Do not keep this run alive to wait. A handoff gets no standing rules (`fan-out.md`): it carries out a pick the human made, under its own skill, and that pick can include a merge the standing rules forbid. The same goes for a chained next run, which is a new lead.

**What a pick authorises.** A pick authorises exactly the action on that option, once, and nothing more. "Merge #1657" is not "merge whatever else is green". A merge picked here still goes through the merge gate (`references/merge-gate.md`). When a slice escalated on a person's question or hold, its question quotes that text, and picking its merge is the owner's answer to it: log `feedback <id> answered at close-out` before re-reading the gate. A pick whose question did not quote the hold answers nothing. If the gate fails only because CI is still running, hand the PR to `/pr-land` as above. If it fails for any other reason, report why and leave the PR. A pick does not override the repo's rules either. If the repo forbids something, say so and skip it.

**After the answers.** Carry out the picks in the order of the questions. Report each one's result in one line. Then print the action items again with what was done ticked (`- [x]`) and what is left unticked. Post the same list to the tracking issue, so the record matches. Then print `The End`. If **Archive this session** was picked, it is the one pick not carried out in order: list it on the tracking issue as `archiving the lead after this comment`, not ticked, and make `archive_session` on this session (`get_session` with no id gives its id) the very last tool call, after `The End`. If it is refused, say so in one line in chat; the tracking issue is not edited again.

**A picked merge that completes the run.** An escalated run can become complete here: the human picks the merge of the last open PR, and it passes its gate. Check this after carrying out the picks and before printing the list again. If every ledger row is now `merged`, run the static acceptance pass (Phase 7.1) on the criteria still marked `escalated`. Run it only on those. Every other criterion must already be MET from Phase 7. If they are all MET now, the run is complete. Do what close-out step 5 would have done: set the row to `merged`, close the tracking issue, and run the issue-mode parent close-out again (Issue mode step 6). The dynamic pass is not run again, because it would mean waiting and nothing wakes this lead. Say so in the list posted to the tracking issue: `<stage> merged at close-out; its criteria checked statically only`. If any criterion is still PARTIAL or NOT MET, change nothing: the issue stays open. A PR handed to `/pr-land` never comes back to this lead, so a run that finishes that way also stays open. Its tracking issue is the record, and closing it is the human's call.

**When the run is done.** Done means nothing is left to do, so archiving the lead loses nothing. Decide it after the picks, once the list has been posted to the tracking issue. The run is done when all of these hold:

- the tracking issue is closed: every stage merged and every criterion met;
- every action item was carried out, or the human answered it with "leave it". Unpicked options count as "leave it";
- no action item is one only a human can do, and nothing was handed to a `/pr-land` session, because both are still open work;
- no prompt was dismissed while items were still unanswered.

A chained next-run watcher does not count against it, because it is its own scheduled task. An unattended `--next` close-out asks nothing, so it is done only when its list is `Action items: none`. When the run is done, rename the lead with the `✅` prefix (**The lead's title**) before `The End`. If it is not done, the title keeps its final marks and no prefix. **Archive this session** follows the same rule: if it was picked and the run is not done, skip it and say in one line what is still open.

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
3. Its own trigger id and the give-up date: 7 days from now, or whatever the human typed under "Other". `create_trigger` returns the id only after the prompt is stored, so create the trigger first, then use `update_trigger` to replace its prompt with one that includes the id. Without the id, the fired session cannot switch the trigger off.
4. These instructions: check every prerequisite. If any is unmet and the give-up date has not passed, end without doing anything. If all are met, start the next run with `create_session`, comment the new session's link on the tracking issue, send a `PushNotification`, and switch the trigger off with `update_trigger` (`enabled: false`). A session a trigger started cannot delete that trigger. If the give-up date has passed, switch the trigger off, comment which prerequisite was still unmet, and send a `PushNotification`.

The chained run stops at its own plan sign-off, like any other `/feature` run. Chaining saves the wait, not the human gate. That is why a chained start is safe to leave alone.

This watcher is the one trigger close-out leaves running on purpose. Cleanup (step 4) deletes the run's check-ins, not this. Name it in the final comment with its trigger id, the give-up date, and how to cancel it (`delete_trigger <id>`). Also add a ticked action item: `Next run chained: starts when {prerequisites} — cancel with delete_trigger <id>`.
