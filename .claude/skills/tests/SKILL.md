---
name: tests
description: Write clear, maintainable Vitest and Playwright tests — precise assertions, consistent naming and structure, minimal mocking, and behavioral coverage — and run them scoped correctly through the repo's task runner. Use when adding or reviewing any .test.ts or .spec.ts file, or when deciding how to run a suite for a package you changed.
---

# Writing tests

Write tests that are clear, maintainable, and thorough. Optimize for readability and reliability. Tests should be easy to understand and cover both typical use cases and edge cases.

## Essentials

- Always scope a run to the package you touched, and go through the repo's task runner from the repository root — never `cd` into a package to run its script directly (see [Running tests](#running-tests)).
- Use Vitest; always import `describe`, `it`, and `expect` explicitly (no globals).
- Name test files `name.test.ts`, placed next to the file under test, with a top-level `describe()` matching the file name.
- Do not start test descriptions with "should" (`it('generates a slug')`, not `it('should generate a slug')`).
- Minimize mocking; prefer refactoring toward pure functions.
- For Vue components, assert behavior — not DOM structure or Tailwind classes.
- Playwright is for limited end-to-end testing only (`/playwright/test/`, `*.spec.ts`); do not run the e2e suites unless explicitly asked.

## Running tests

Two rules hold in every repo:

1. **Scope the run to what you touched.** A whole-repo run is slow, noisy, and
   surfaces unrelated pre-existing failures that hide the one you caused. Reach
   for an unfiltered run only as a deliberate pre-merge sanity check.
2. **Invoke through the repo's task runner from the repository root**, not by
   `cd`-ing into a package and calling its script.

The second rule is the one that bites. Where tests import sibling workspace
packages through their built `dist/`, the task runner is what encodes the build
ordering — bypass it and a run races in-flight builds and can read a
half-written `dist/`. The symptom is badly misleading: type or test failures in
files nobody touched, coming from a stale dependency `dist/`.

Per repo:

| Repo | Unit tests | Type check |
| --- | --- | --- |
| `scalar-org` (turbo) | `pnpm turbo test:unit --filter=<package>` | `pnpm turbo types:check --filter=<package>` |
| `scalar` (vitest) | `pnpm vitest packages/<name> --run` | `pnpm --filter @scalar/<name> types:check` |
| `bane`, `mjst` (bun) | `bun run test` | `bun run types:check` |

In a turbo repo, check `turbo.json` before assuming: only tasks declared under
`tasks` go through turbo. Everything else keeps its plain form
(`pnpm --filter <package> test:e2e`, `pnpm check`, and so on).

## Setup

- Use Vitest for most tests. Vitest is our primary testing framework.
- No globals. Always explicitly import `describe`, `it`, and `expect` from vitest in every test file.
- File naming conventions:
  - Unit/integration test files end with `.test.ts`.
  - Each test file matches the name of the file it tests. Example: if the code is in `custom-function.ts`, the test file should be named `custom-function.test.ts`.
  - The test file is located in the same folder as the file under test. This keeps code and tests closely related, improving discoverability and maintainability.
- Minimize mocking. Only mock when absolutely necessary. Prefer refactoring the code under test to make mocking unnecessary. Aim for simpler, pure functions that are easier to test without mocks.
- Every test file has a top-level `describe()`.
  - The top-level `describe()` matches the file name under test. Example: `describe('custom-function')` for `custom-function.test.ts`.
  - Inside this `describe()`, you can add nested `describe()` blocks if you are testing multiple functions or distinct features.
  - Deeper nesting is fine if it improves clarity.
  - Use `it()` for individual tests.
  - Keep descriptions concise and direct.
  - Do not start with "should".
    - ✅ `it('generates a slug from the title')`
    - ❌ `it('should generate a slug from the title')`

## Testing Vue components

- Do not rely on markup for assertions.
- Avoid testing the exact structure of the DOM unless necessary.
- Do not rely on Tailwind CSS classes in assertions.
- Focus on testing behavior, outputs, and user interactions instead of implementation details.

## Playwright tests

- Use Playwright for limited end-to-end testing.
- Playwright tests live in `/playwright/test/`.
- Files end with `.spec.ts`.
- Be selective. We intentionally limit the number of Playwright tests to avoid maintenance overhead.
- Do not run Playwright suites (`test:e2e`, `test:e2e:ci`, `test:e2e:update`) unless explicitly asked — they are slow and resource-hungry. Verify with the package's scoped unit tests and type check instead (see [Running tests](#running-tests)).

## Visual snapshots

Visual tests are `*.e2e.ts` with baselines committed next to them. Two things about how they render are not visible from the config, and both have been measured:

- **Baselines can be generated on any machine.** Every suite reaches the browser through the pinned `scalarapi/playwright-runner` container over `PW_TEST_CONNECT_WS_ENDPOINT`, so the fonts, freetype, and Chromium are the image's and the host contributes nothing but instruction execution. An arm64 Mac running the amd64 image emulated produces the same bytes as the amd64 CI runner. Harvesting `-actual.png` out of a CI report is a convenience, not a correctness requirement, and a local render is not suspect for being local.
- **`launchOptions` in these configs do nothing.** Connecting to a browser server is not launching one: Playwright's connect path passes only `{ wsEndpoint, headers, exposeNetwork }`, and the container's browser was already started with no arguments. Chromium flags added to a `playwright.config.ts` here are silently dropped — including ones that look load-bearing. If you need a flag to apply, the browser has to be launched rather than connected to, and then local and CI must both do it the same way or their baselines diverge.

Before adding a Chromium flag on the theory that it stabilises rendering, prove it changes anything: pass something unmissable (`--blink-settings=minimumFontSize=30`) and check the screenshot actually moved.

## Style and best practices

- Clarity first. Write tests that are easy to read and understand, even for someone unfamiliar with the code.
- Think like a QA engineer.
  - Cover all important code paths.
  - Test both the happy path and error handling.
  - Add tests for edge cases and potential failure scenarios.
- Comments are welcome when they add value.
  - Use comments to explain why a test exists, not what it is doing.
  - Avoid repeating what the code already makes obvious.

## Example test file structure

```
/src
  /lib
    custom-lib.ts
    custom-lib.test.ts
```

```ts
import { describe, it, expect } from 'vitest'
import { generateSlug } from './custom-function'

describe('custom-lib', () => {
  describe('generateSlug', () => {
    it('generates a slug from the title', () => {
      const result = generateSlug('Hello World')
      expect(result).toBe('hello-world')
    })

    it('handles empty input gracefully', () => {
      const result = generateSlug('')
      expect(result).toBe('')
    })
  })
})
```
