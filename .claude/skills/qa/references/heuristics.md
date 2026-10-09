# QA heuristics

What a tester checks that nobody writes down, plus the rubrics the report
depends on. The skill reads this when building the check list in Phase 0 and
again when rating findings in Phase 3.

## Depth

The `--depth` flag decides how much of this file applies.

| Depth | What runs |
| --- | --- |
| `smoke` | Only what the caller asked for, plus the happy path of anything they named. Use when a change is small or time is short. |
| `standard` (default) | The asked-for checks, the **always** rows below for every area touched, and the boundaries of any input involved. |
| `deep` | Everything here that applies, including accessibility, responsive widths, interruption, and concurrency. |

## The sweep

For any web feature, in the order a tester would actually work it. The
**always** rows are the ones that find bugs often enough to be worth the time
at `standard` depth.

| # | Case | Depth | What it catches |
| --- | --- | --- | --- |
| 1 | **Happy path**, exactly as documented | always | The feature does not work at all. Do this first; everything else is wasted if it fails. |
| 2 | **Empty, zero, one, many** — no records, one record, and a list long enough to paginate or scroll | always | Empty states that render a broken shell, pagination off by one, layouts that only ever saw three rows. |
| 3 | **Required fields left blank**, then submitted | always | Validation that never fires, a submit that 500s, an error that appears somewhere nobody looks. |
| 4 | **Invalid and hostile input** — see the data table below | always | Missing escaping, silent truncation, crashes on unicode. |
| 5 | **Cancel and back out** mid-flow, then re-enter | always | Half-written state left behind, a modal that will not reopen, a draft that resurrects. |
| 6 | **Double-submit** — click the primary button twice fast | always | Duplicate records, double charges, a button with no disabled state. |
| 7 | **Refresh mid-flow**, and use the browser back button after a step | always | State kept only in memory, a URL that does not reflect the step, a back button that resubmits. |
| 8 | **Reload after success** — does the change persist? | always | An optimistic UI update that never reached the server. |
| 9 | **The console, the whole time** | always | Uncaught exceptions, React key warnings, failed requests the UI swallows. |
| 10 | **Slow and failing network** — throttle, then block the feature's endpoint | deep | Missing loading states, spinners that never resolve, an error path nobody implemented. |
| 11 | **Permissions** — the same flow as a lower-privileged user, and logged out | deep | Actions visible to users who cannot perform them; a redirect that loses the destination. |
| 12 | **Keyboard only** — tab to every control, operate the feature, `Esc` out of every modal | deep | Focus traps, controls that are `div`s, a modal that does not return focus. |
| 13 | **Responsive** — the narrowest supported width, then a wide one | deep | Overflow, controls off-screen, a table that cannot be scrolled. |
| 14 | **Two tabs at once** on the same record | deep | Lost updates, stale caches, a websocket that does not reconcile. |
| 15 | **Long strings and other locales** — a 300-character name, an RTL string, a non-ASCII one | deep | Truncation that hides meaning, layouts that only fit English. |
| 16 | **Timezone and date edges** where dates are shown | deep | Off-by-one days, UTC rendered as local, "yesterday" computed wrong. |

## Test-design techniques

Use these to turn "test the invite form" into specific checks:

- **Equivalence classes.** Group inputs that should behave identically and test
  one of each, rather than five variations of the same class.
- **Boundaries.** Where a rule has a limit, test just under, exactly at, and
  just over it: 0, 1, max, max+1, and the empty value. Most input bugs live
  here.
- **State transitions.** Draw the states the feature moves through (draft →
  sent → accepted → expired) and test each transition, including the ones that
  should be refused — accepting an expired invite, cancelling a sent one twice.
- **CRUD lifecycle.** Create it, read it back on a fresh load, update it,
  delete it, then confirm it is gone from every list that showed it.
- **Pairwise, for combinations.** With three toggles you do not need eight
  runs; cover every pair of settings and stop.
- **Follow the data.** Where a value is entered in one place and displayed in
  another — a list, an export, an email, an API response — check every
  downstream view, not just the form.

## Exploratory charters

At `standard` and `deep`, spend a few checks without a script. A charter is one
sentence: *explore the invite flow with an expired token to discover how the
app recovers*. Useful tours:

- **The unhappy tour** — refuse, cancel, and fail every step deliberately.
- **The impatient tour** — click before things finish loading; navigate away mid-save.
- **The supplied-data tour** — put the awkward strings below into every field.
- **The variability tour** — change one thing about the environment (zoom to
  200%, a narrow window, a slow network) and re-run the happy path.

Log what you tried even when nothing broke; the report's coverage section is
built from it.

## Data worth trying

| Input | Why |
| --- | --- |
| `''` and `'   '` | Whitespace-only passing a "required" check. |
| `0`, `-1`, `999999999` | Falsy zero treated as absent; no upper bound. |
| 300 characters of text | Truncation, overflow, a column that is `varchar(255)`. |
| `Ünïcödé`, `🎉`, `שלום` | Encoding, width, and RTL handling. |
| `O'Brien`, `a+b@example.com` | Quoting bugs, over-strict email validation. |
| `<b>hi</b>` typed into a text field | Escaping. It should render as literal text, not bold. Do not attempt anything beyond checking that markup is escaped. |
| `../../etc/passwd` as a name | Path handling in anything that becomes a filename. |
| Two spaces mid-word, a trailing space | Trimming that silently changes what the user typed. |

## Severity rubric

Rate on user impact and how likely the path is, never on how hard it looks to
fix. Findings from different areas of one pass have to rank against each other.

- **critical** — data loss or corruption, a security or access-control hole, a
  charge or send that is wrong, or the main path of the feature is unusable
  with no workaround. Ship-blocking.
- **major** — a documented requirement is not met, a common path breaks, or the
  workaround is one a user would not find. Fix before release.
- **minor** — an edge case, a wrong message, a cosmetic break that does not
  stop the task, or a missing loading state. Fix soon.
- **nit** — copy, spacing, inconsistent casing, a preference. Batch it.

Two modifiers that belong in the finding, not the rating: **flaky** (it did not
reproduce every time — say how many of how many) and **pre-existing** (it
happens on the baseline too, so the change under test did not cause it).

## Not findings

Reporting these costs the report its credibility:

- Console noise present in the Phase 1 baseline, unless the feature made it worse.
- Anything the spec or the ticket explicitly decided — say "matches spec" and move on.
- A slow response on a local dev server with no production numbers to compare against.
- Design preferences the caller did not ask about. Rendering that differs from a mock is a finding; taste is not.
- A failure you only saw once and could not reproduce, unless the failure itself is severe — then report it as flaky with both attempts described.
- Anything you did not actually see happen. "Probably also broken on mobile" is a coverage gap, not a finding.
