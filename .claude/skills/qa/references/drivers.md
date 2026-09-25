# Browser drivers

How to connect each backend, which tool does what, and the interaction
discipline that keeps a pass from producing flaky nonsense. The skill picks a
driver in Phase 1; the rules at the bottom apply to all of them.

## 1. Claude in Chrome (preferred)

The Claude in Chrome extension puts Claude Code in the user's own browser —
their cookies, their sessions, their extensions, their rendering. For QA this
is the closest thing to a human tester, and it is the only driver that can
exercise an app the user is already logged into without handling credentials.

**Connect.** The tools appear as `mcp__claude-in-chrome__*` once the session is
started with `claude --chrome`, or `/chrome` is run mid-session. Load them with
ToolSearch before the first check. If they are absent, tell the user to run
`/chrome` (the status panel should show "Status: Enabled" and "Extension:
Installed") rather than silently dropping to another driver — the pass is worth
more in their browser.

**The tools worth knowing**, by job:

| Job | Tool |
| --- | --- |
| Open a URL, go back or forward | `navigate` |
| Open / list / close tabs | `tabs_create_mcp`, `tabs_context_mcp`, `tabs_close_mcp` |
| See the page as a structure to act on | `read_page` |
| Read the visible text | `get_page_text` |
| Locate an element by name or text | `find` |
| Click, type, scroll, screenshot | `computer` |
| Fill fields reliably | `form_input` |
| Console output | `read_console_messages` |
| Requests and responses, including failures | `read_network_requests` |
| Evaluate an expression in the page | `javascript_tool` |
| Change the viewport | `resize_window` |
| Attach a local file to an upload field | `file_upload` |
| Record the flow as a GIF | `gif_creator` |
| Several actions in one round trip | `browser_batch` |

Names can drift between extension versions: `/mcp` → `claude-in-chrome` →
**View tools** lists what this session actually has. Use what is there rather
than assuming this table.

**Things this driver does that others do not.** It pauses and hands back to the
user on a login page or CAPTCHA — let it, never type credentials for them. It
acts in a visible window, so a screenshot is what the user would see. It groups
its tabs, so closing them at the end is polite but not required. Permissions
are per-site and inherited from the extension, so the first action on a new
host may prompt.

**Things to be careful about.** It is a real browser with real sessions: a
destructive action is really destructive, and `file_upload` reads real local
files. A recorded GIF captures everything visible, logged-in account details
included — do not attach one to a report that leaves the team.

## 2. A browser MCP server

Chrome DevTools MCP or Playwright MCP, when the session has one. Same shape,
different names: a snapshot tool instead of `read_page`, `browser_click` /
`click` instead of `computer`, a console tool, a network tool, and usually
network throttling and CPU throttling as well — which makes case 10 of the
sweep cheap. Discover the names with ToolSearch (`browser navigate snapshot
click console`), then apply the same discipline.

These drive a browser profile that is not the user's, so treat auth like the
Playwright case below.

## 3. Local Playwright

Always available in a cloud session: Chromium is preinstalled at
`/opt/pw-browsers/chromium`, `PLAYWRIGHT_BROWSERS_PATH` is already set, and
`playwright install` must not be run. Locally, use the repo's own Playwright if
it has one — a version mismatch with the repo's fixtures is not worth debugging
mid-pass.

Drive it with a script in the scratchpad, never in the repo. One script per
check, or one script that runs the check list and writes a JSON result — either
is fine, as long as each check starts from a fresh context so the preconditions
are real:

```js
// <scratchpad>/qa/<slug>/check.mjs — run with: node check.mjs
import { chromium } from 'playwright'

const browser = await chromium.launch() // headless; the screenshots are the evidence
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } })
const page = await context.newPage()

const consoleErrors = []
page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text()))
page.on('pageerror', (e) => consoleErrors.push(`uncaught: ${e.message}`))
const failedRequests = []
page.on('response', (r) => r.status() >= 400 && failedRequests.push(`${r.status()} ${r.url()}`))

await page.goto(process.env.BASE_URL, { waitUntil: 'networkidle' })
await page.getByRole('button', { name: 'Invite' }).click()
await page.getByLabel('Email').fill('a+b@example.com')
await page.getByRole('button', { name: 'Send invite' }).click()
await page.getByText('Invitation sent').waitFor({ timeout: 5000 }) // the assertion, not a sleep

await page.screenshot({ path: 'shots/C3-after-send.png', fullPage: true })
console.log(JSON.stringify({ consoleErrors, failedRequests }, null, 2))
await browser.close()
```

Locators by role and label are not a style preference here: they are what makes
the check test the thing a user sees rather than a class name that changes next
sprint.

**What this driver cannot do.** No logged-in state — auth-dependent checks need
credentials from the user, or they are `blocked` and the report says so. No
user extensions, no real profile, and a headless renderer that can differ
subtly from a headed one. Say which driver ran in the report so the reader can
weigh a visual finding accordingly.

## Discipline that applies to every driver

- **Read the page before acting on it.** Every click follows a `read_page` or
  snapshot of the current state. Acting on a remembered layout is how a pass
  reports a bug that is really a mis-click.
- **Address elements by accessible name or visible text.** Coordinates and
  brittle CSS paths produce findings that cannot be reproduced by a human.
- **Wait for a condition, never for a duration.** The text that should appear,
  the request that should settle, the row that should vanish. A fixed sleep
  either flakes or wastes the pass's time, usually both.
- **Assert by reading back, not by return value.** A click that "succeeded" says
  nothing about what the app did with it.
- **One check, one state.** Reset between checks — a fresh tab or context, a
  fresh navigation. A cascade of failures caused by leftover state from check 3
  is one finding, not nine.
- **Screenshot at the moment of failure**, before navigating away or retrying.
  The retry is what destroys the evidence.
- **Collect console and network per check**, and diff against the Phase 1
  baseline so pre-existing noise does not become a finding.
- **Prefer the accessible tree to the pixels** when reading state: it is what
  assistive technology sees, so a check that passes against it is a check that
  passes for more users.
