---
name: qa
description: Run a QA pass on a web feature in a real browser — drive it through Claude in Chrome (or a Playwright fallback), execute the checks the caller asked for plus the ones a tester would add, reproduce every failure before reporting it, and publish a linked QA report artifact with a verdict, findings, evidence, and what was not covered. Use for "/qa", "QA this feature", "test this in the browser", "check that these things still work", "smoke test the app", "does this flow work", "verify this before I ship", or when handed a feature description, a checklist, a PR, or a staging URL to exercise by hand.
argument-hint: "[feature, checklist, or checklist file] [--url <base url>] [--driver chrome|playwright|auto] [--depth smoke|standard|deep] [--no-publish]"
allowed-tools:
  - Read
  - Write
  - Grep
  - Glob
  - ToolSearch
  - Artifact
  - mcp__claude-in-chrome
  - Bash(git rev-parse:*)
  - Bash(git log:*)
  - Bash(git status:*)
  - Bash(git diff:*)
  - Bash(mkdir:*)
  - Bash(python3:*)
  - Bash(node:*)
  - Bash(npx playwright:*)
---

# qa

Test a feature the way a tester would: in a real browser, against a running
app, one check at a time, with evidence for every claim — then hand back one
page that says whether it is shippable.

Invoke with `/qa <what to test> [--url ...] [--driver ...] [--depth ...] [--no-publish]`.

**Arguments** (from `$ARGUMENTS`):

- Free text or a file path: the feature to exercise, or the list of things to
  check. A path to a Markdown or text file is read and every line item becomes
  a check. "the new invite flow" is enough; so is a numbered list of twelve
  assertions. A PR number or branch name scopes the pass to what it changed.
- `--url <base url>`: where the app is running. Default: a `localhost` dev
  server if one is already up, otherwise ask.
- `--driver chrome|playwright|auto`: which browser backend. Default `auto`
  (see Phase 1).
- `--depth smoke|standard|deep`: how far past the asked-for checks to go.
  `smoke` runs only what was asked; `standard` (default) adds the
  neighbouring cases from `references/heuristics.md` that a tester would not
  skip; `deep` works the full sweep including accessibility, responsive, and
  interruption cases.
- `--no-publish`: write the HTML report and hand it over instead of publishing.

**Three rules that hold throughout.**

- **A check is not done until the page proves it.** The assertion is read back
  off the rendered page — text, DOM state, URL, console, network — never
  inferred from the fact that a click returned successfully.
- **A finding is not real until it reproduces.** Every failure is re-run from a
  clean state before it reaches the report, and is labelled with what happened
  on the second run.
- **Evidence or it did not happen.** Every failed or partial check carries a
  screenshot plus whatever console and network output explains it.

---

## Phase 0: Scope, and get permission to touch the target

Before opening a browser, write down what is being tested and where.

1. **Resolve the target.** Base URL, environment (local, preview, staging,
   production), and build identity — a commit SHA from the checkout, a version
   string in the UI, or a deploy URL. The report is worthless without it.
2. **Confirm the environment is safe to exercise.** State the URL back to the
   user and say what the pass will do to it. If it is production, or anything
   with real customer data, get an explicit go-ahead first and drop every
   destructive check (delete, cancel, send, pay, invite) unless the user keeps
   it. Never create test data in production on your own initiative.
3. **Get credentials the checks need**, or note which checks are blocked
   without them. Ask once, together with anything else you need. With Claude in
   Chrome you usually need none — the browser is already signed in — and when a
   login page or CAPTCHA does appear, hand it back to the user rather than
   typing credentials yourself.
4. **Build the check list.** Each check gets an id (`C1`, `C2`, …), an area, a
   precondition, the steps, and the observable expected result. Sources, in
   order: what the user asked for, the acceptance criteria of the feature or
   PR, the code the branch changed (`git diff --name-only` against the
   merge-base — a changed component nobody listed is still in scope), and the
   neighbouring cases from `references/heuristics.md` at the chosen depth.
   Mark each check `specified` (asked for) or `exploratory` (added here), so
   the report can show both what was requested and what was volunteered.
5. Write it to `<scratchpad>/qa/<slug>/checks.md` and show the user the count
   and the areas in two or three lines before starting. A pass of forty checks
   takes a while; they should know.

If the app is not running and it is a local checkout, start it the way the
repo documents (the `run` skill, if the session has it) rather than guessing a
command.

## Phase 1: Pick a driver and connect

Prefer the caller's real browser; fall back rather than stopping. Full
mechanics for each backend are in `references/drivers.md`.

1. **Claude in Chrome** (`--driver chrome`, and what `auto` tries first). Load
   the tools with ToolSearch (`mcp__claude-in-chrome` — `navigate`,
   `read_page`, `get_page_text`, `find`, `form_input`, `computer`,
   `read_console_messages`, `read_network_requests`, `javascript_tool`,
   `tabs_create_mcp`, `resize_window`). If they are absent, `/chrome` connects
   the extension; say so and let the user run it. This is the driver to want:
   it is the user's own browser, with their sessions, their extensions, and
   their real rendering.
2. **A browser MCP server** — Chrome DevTools MCP or Playwright MCP, if the
   session has one. Same discipline, different tool names.
3. **Local Playwright** (`--driver playwright`). A headed-if-possible Chromium
   driven by a script in the scratchpad. Always available in a cloud session,
   where Chromium is preinstalled. No logged-in state, so auth-dependent checks
   need credentials or get marked blocked.

Say which driver you got, in one line, before the first check — it changes how
the results should be read, and it goes in the report.

Then **take a baseline** in the browser: open the base URL, confirm it loads,
record the viewport, and read the console and network panels *before* running
any check. Pre-existing console noise recorded now is noise; the same message
discovered mid-check would be reported as a finding. Note the build identity
visible in the UI.

## Phase 2: Run the checks

One check at a time, in the same shape every time:

1. **Arrange.** Put the app in the precondition state, from a known starting
   point. Never inherit state from the previous check silently — if a check
   depends on what the last one created, say so in its precondition.
2. **Act.** Read the page first (`read_page` / a snapshot), then act on an
   element you have actually seen. Address elements by their accessible name or
   visible text, not by a coordinate or a guessed CSS path.
3. **Wait for the observable condition**, not a fixed delay: the text that
   should appear, the row count that should change, the request that should
   settle. A `sleep` in a QA script is a flaky check being written on purpose.
4. **Assert against the page.** Re-read text, DOM state, URL, and — where the
   check is about data — the network response. Then classify: `pass`, `fail`,
   `partial` (works, but not as specified), `blocked` (could not run), or
   `skipped` (out of scope for this depth, or dropped in Phase 0).
5. **Capture.** A screenshot for every fail and partial, and for any pass whose
   verdict is visual. Pull console messages and failed requests for the check's
   window. Save shots to `<scratchpad>/qa/<slug>/shots/` with the check id in
   the filename.
6. **Leave the app clean.** Undo what the check created when the app allows it;
   record what could not be cleaned up under notes.

Along the way, watch the things nobody lists but everybody notices: an
uncaught exception in the console, a 4xx/5xx the UI swallows, a request fired
twice, a layout that breaks at the current width, a control that cannot be
reached with the keyboard. Each is a finding in its own right — log it against
the check that surfaced it and keep going.

**Stop early only for a blocker**: the app will not load, auth is broken, or a
check destroyed state the rest depend on. Report what ran, what did not, and
why — a partial pass reported honestly is useful; a pass that pretended the
blocker away is not.

## Phase 3: Triage before you report

Raw failures are not findings yet. For each one:

1. **Reproduce it** from a clean state — new tab, fresh navigation. Label it
   `confirmed` (failed both times), `flaky` (failed once), or drop it if it was
   your own driving error. A flaky finding stays in the report, labelled: a
   test that fails one time in two is itself a defect.
2. **Minimise it.** Cut the repro to the shortest path that still fails, and
   say which step first goes wrong. Check whether it is specific to the state
   you were in, the viewport, or the account.
3. **Decide what it is**: a defect, behaviour that matches the spec but is
   worth flagging, or an environment problem (bad data, dev-only config,
   a service that is down). Do not report an environment problem as a bug;
   report it as a coverage gap with the check marked `blocked`.
4. **Rate it** with the severity rubric in `references/heuristics.md`
   (`critical` / `major` / `minor` / `nit`), on user impact and how likely the
   path is — not on how hard it looks to fix.
5. **Point at the code** when the repo is checked out: grep for the message,
   the component, or the endpoint and give `file:line`. A finding a developer
   can open beats one they have to hunt for. Say it is a lead, not a diagnosis
   — the root cause is `/debug`'s job, not this skill's.
6. **De-duplicate.** Five checks tripping over one broken endpoint are one
   finding with five affected checks, not five findings.

## Phase 4: Report

1. Write `<scratchpad>/qa/<slug>/results.json` in the schema in
   `references/report-schema.md`. Everything the page shows lives there:
   target, driver, scope, every check with its status, every finding with its
   repro and evidence, the coverage gaps, and your one-sentence verdict note.
2. Build the page:

   ```
   python3 <skill dir>/scripts/build.py \
     --results <work dir>/results.json \
     --shots <work dir>/shots \
     --out <work dir>/qa-report.html
   ```

   The script validates the schema, derives the counts and the verdict label,
   copies the referenced screenshots next to the output, and renders
   `assets/template.html`. It exits non-zero on a malformed result or a missing
   screenshot, so a clean run means the page is complete.
3. Publish with the Artifact tool (favicon `🧪`, description "QA pass on
   {feature} against {env}: {n} checks, {n} findings, verdict {label}"),
   passing the copied `shots/` files so the evidence renders. Keep the same
   file path on re-runs in one session so the URL stays stable. With
   `--no-publish`, or where the Artifact tool is genuinely absent, hand over
   the HTML file and say so.
4. **Terminal summary**, under ten lines: the verdict, the link, the counts,
   then the critical and major findings one line each, then what was not
   covered. The page is the report; do not restate it.

Never file issues, comment on a PR, or push a fix from this skill. It tests
and reports; acting on the findings is the caller's call — and fixing one is
`/debug`'s job, with the repro this pass produced.

---

## Design notes

- **The browser is one mutable resource, so there is no fan-out.** Other
  skills here parallelise across subagents; a QA pass cannot, because two
  agents sharing one browser session corrupt each other's preconditions. Depth
  comes from the heuristics, not from more agents.
- **Reproduce before reporting.** The expensive failure mode of an automated QA
  pass is a confident bug report that was really a mis-click. Phase 3 is the
  equivalent of the `verifier` agent in the check loop: a finding has to
  survive a second, independent attempt.
- **The baseline exists to protect the developer.** Without it, every
  pre-existing console warning in a busy app becomes a finding, and the report
  loses the reader on page one.
- **Blocked is a first-class result.** A check that could not run is not a
  pass and not a failure; hiding it behind either is how a QA report starts
  lying. The page counts them separately and the summary names them.
- **The report claims coverage, not absence of bugs.** Every page ends with
  what was not tested, because "no findings" from a pass that never opened
  mobile width means something quite different from "no findings" after the
  full sweep.
