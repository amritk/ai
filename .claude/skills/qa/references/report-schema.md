# results.json

The one file the report is built from. `scripts/build.py` validates it, derives
every count and the verdict label, and renders the page — so anything the
reader should see has to be in here, and anything in here has to be something
that actually happened.

```json
{
  "title": "Team invite flow",
  "date": "2026-09-15",
  "driver": "claude-in-chrome",
  "depth": "standard",
  "target": {
    "url": "https://staging.example.com",
    "env": "staging",
    "build": "a1b2c3d (deploy 2026-09-15 09:12 UTC)",
    "viewport": "1280x800",
    "browser": "Chrome 141, user profile"
  },
  "scope": {
    "asked": "Check the new invite flow before Thursday's release.",
    "in_scope": ["Sending an invite", "Accepting one", "Resend and revoke"],
    "out_of_scope": ["Billing side effects — no test card on staging"]
  },
  "verdict_note": "The flow works end to end, but a revoked invite is still acceptable, which is an access-control problem.",
  "baseline": {
    "console": ["[vite] connected — dev server noise, present before the pass"],
    "notes": "Two pre-existing 404s for /favicon.ico on every page."
  },
  "checks": [
    {
      "id": "C1",
      "title": "Send an invite to a new email address",
      "area": "invite",
      "type": "specified",
      "status": "pass",
      "steps": ["Open /team", "Click Invite", "Enter a+b@example.com", "Send"],
      "expected": "Row appears in Pending with the address and a Revoke action.",
      "actual": "Row appeared; POST /api/invites returned 201.",
      "findings": [],
      "evidence": [{ "kind": "screenshot", "path": "C1-pending-row.png", "caption": "Pending row after send" }]
    },
    {
      "id": "C7",
      "title": "Accept an invite that was revoked first",
      "area": "invite",
      "type": "exploratory",
      "status": "fail",
      "steps": ["Send an invite", "Revoke it from the Pending list", "Open the invite link from the email"],
      "expected": "The link is refused with a message saying the invite is no longer valid.",
      "actual": "The account was created and joined the team.",
      "findings": ["F1"],
      "evidence": [{ "kind": "screenshot", "path": "C7-joined-after-revoke.png", "caption": "Member list after accepting a revoked invite" }]
    }
  ],
  "findings": [
    {
      "id": "F1",
      "title": "A revoked invite can still be accepted",
      "severity": "critical",
      "area": "invite",
      "status": "confirmed",
      "repro": ["Send an invite", "Revoke it", "Open the invite link", "Set a password and continue"],
      "expected": "Refused: the invite is no longer valid.",
      "actual": "The account is created and appears in the member list with the invited role.",
      "impact": "Anyone who ever held an invite link keeps access after it is revoked, including former staff.",
      "console": ["POST /api/invites/accept 200"],
      "network": ["POST /api/invites/accept → 200, body { \"ok\": true }"],
      "code_lead": "src/server/invites/accept.ts:41 — the handler checks expiry but not revoked_at",
      "checks": ["C7"],
      "evidence": [{ "kind": "screenshot", "path": "C7-joined-after-revoke.png", "caption": "Joined after revoke" }]
    }
  ],
  "coverage_gaps": [
    "Mobile widths — not run at standard depth.",
    "Billing side effects of accepting an invite — no test card on staging."
  ],
  "notes": [
    "Left two test accounts on staging: qa+c7@example.com and qa+c8@example.com.",
    "Throttled-network cases skipped: the driver has no throttling."
  ]
}
```

## Fields

**Top level.** `title` — the feature, not the document; it becomes the page's
heading and, with `QA` appended, the artifact's name. Then `date` (`YYYY-MM-DD`), `driver`
(`claude-in-chrome` | `browser-mcp` | `playwright-local`), `depth` (`smoke` |
`standard` | `deep`), `target`, `scope`, `verdict_note`, `checks`, `findings`.
`baseline`, `coverage_gaps`, and `notes` are optional but the page is better
with them, and an empty `coverage_gaps` is a claim you have to be able to
defend.

**`target`.** `url`, `env` (`local` | `preview` | `staging` | `production` |
`other`), `build`, `viewport`, `browser`. `build` is what makes the report
re-checkable later; never leave it as "latest".

**`verdict_note`.** One sentence, written by the skill, not derived. The label
above it (`Ship blocked`, `Fix before release`, …) comes from the counts; this
is the judgment the counts cannot make.

**`checks[]`.** `id` (`C<n>`, unique), `title`, `area`, `type` (`specified` if
the caller asked for it, `exploratory` if the pass added it), `status`
(`pass` | `fail` | `partial` | `blocked` | `skipped`), `steps[]`, `expected`,
`actual`, `findings[]` (finding ids), `evidence[]`. A `blocked` or `skipped`
check still needs `actual` — it says why it did not run.

**`findings[]`.** `id` (`F<n>`, unique), `title`, `severity` (`critical` |
`major` | `minor` | `nit`), `area`, `status` (`confirmed` | `flaky` |
`pre-existing`), `repro[]`, `expected`, `actual`, `impact`, `checks[]` (the
check ids that hit it). Optional: `console[]`, `network[]`, `code_lead`,
`evidence[]`. A `flaky` finding says how often in `actual` ("failed on 2 of 3
attempts"); a `pre-existing` one reproduced on the baseline build too.

**`evidence[]`.** `kind` (`screenshot` | `console` | `network` | `note`), plus
`path` for a screenshot — a bare filename inside the shots directory, no
directories and no `..` — or `text` for the rest. `caption` is optional and
worth writing.

## What the build script derives

Do not put these in the file; they are computed, and a stale hand-written copy
is how a report starts contradicting itself: check counts by status, finding
counts by severity, the pass rate, the areas list, and the verdict label:

| Label | When |
| --- | --- |
| `Ship blocked` | any `critical` finding that is not `pre-existing` |
| `Fix before release` | any `major` finding that is not `pre-existing` |
| `Ready with caveats` | only `minor` / `nit` findings, or only pre-existing ones |
| `Clean, with gaps` | no findings, but some checks `blocked` or `skipped` |
| `Clean` | no findings and every check ran |
