# Close-out — acting on the action items, and chaining the next run

The action items list (close-out step 8) is what is left for a human to decide. Most of those decisions end in something the lead could do itself in one tool call: merge a PR, delete a branch, start the next run. So the lead lets the human answer by picking options, and then does what they picked. It no longer prints a list and expects someone to type each item back.

## The selection prompt

Once the summary and its `Action items:` block are printed, call `AskUserQuestion` once, with the items the lead can act on.

**What can be offered.** An item can be offered only when the lead can carry it out in this session, with a tool it holds, and the result can be checked afterwards. Examples: merge a PR whose gate passes, open one more review round, delete a leftover branch, edit or delete a comment the run posted, open a PR adding the proposed `CLAUDE.md` line, start or chain the next-step run. An item that only a human can do stays in the printed list and is never an option: anything that needs their own credentials or account (publishing to npm, a secret, a release outside GitHub), a judgement about product direction, or a fix the human said they would make themselves.

**How the questions are built.** The tool takes 1–4 questions with 2–4 options each, and adds "Other" by itself.

- An item with more than one way forward gets its own single-select question, with one option per path. Example: "PR #1657 is blocked on three sentences after six review rounds" → `Run a 7th review round` / `Merge as it is` / `Leave it for me`.
- Do-it-or-not items go in one `multiSelect` question, "Which of these should I do now?", one option each. An unpicked option means "leave it".
- The next-step run always gets its own question (see below).
- Order the questions by what unblocks the most. If more than four questions or options are needed, offer the ones that unblock the most. The rest stay in the printed list, and the prompt's last question says how many were left out.

Each question must stand on its own. The human may see only the dialog, not the summary above it, so name the PR or branch and say what the option will do. Label the option you would choose `(Recommended)` and put it first.

**What a pick authorises.** A pick authorises exactly the action on that option, once, and nothing more. "Merge #1657" is not "merge whatever else is green". A merge picked here still goes through the merge gate (`references/merge-gate.md`): if the gate fails, report why and leave the PR. A pick does not override the repo's rules either. If the repo forbids something, say so and skip it.

**After the answers.** Carry out the picks in the order of the questions. Report each one's result in one line. Then print the action items again with what was done ticked (`- [x]`) and what is left unticked. Post the same list to the tracking issue, so the record matches. Then print `The End`.

If the human dismisses the prompt, answers nothing, or every pick is "leave it", act on nothing and print `The End` after the unchanged list. Do not ask a second time. If no item can be offered, skip the prompt.

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
