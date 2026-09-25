---
name: typescript
description: Write clear, predictable TypeScript and Vue TypeScript — strong typing, Result-based error handling, ESM conventions, naming, and JSDoc. Use when writing or reviewing any .ts, .tsx, or .vue file, deciding how a fallible function should report failure, or when a change adds types, exports, or public API surface.
---

# Writing TypeScript

Write TypeScript that is clear, predictable, and easy to maintain. The goal is a codebase that is safer, more understandable, and easier to refactor without over-engineering.

## Essentials

- Prefer `type` over `interface`; explicit return types for functions.
- Avoid `any` (use `unknown`), avoid enums (use string literal unions), use `const` over `let`, `satisfies` over `as`, and `readonly` when possible.
- Fallible functions return a `Result<T, E>` (`ok` / `err` constructors) instead of throwing, returning `null`, or ad-hoc `{ data } | { error }` unions. In Scalar repos that type is `@scalar/helpers/types/result`; elsewhere use whatever the repo already has. Types describing an external response keep their real shape.
- Never assign inside `try`/`catch` (`let x; try { x = await fn() } catch { … }`). Chain a `.catch` and early-exit instead: `const x = await fn().catch(() => null); if (!x) { return … }`.
- In an ESM codebase (almost every repo here): use `import.meta.dirname` / `import.meta.filename`, never `__dirname` / `__filename` (enforced by the `noGlobalDirnameFilename` Biome rule).
- In Vue, explicitly type `defineProps`, `defineEmits`, composable return types, `Ref`, and `ComputedRef`.
- Comments explain why, not what; use JSDoc for exported types and functions; avoid contractions.
- Write Vitest tests alongside the source as `name.test.ts`.

## Principles

- Type safety over flexibility.
- Clarity over cleverness.
- Type inference where it makes sense.

## General guidelines

- Prefer `type` over `interface`.
- Explicit return types for functions.
- Avoid `any`. Use `unknown` when the type is unclear.
- Prefer primitive types over complex ones unless necessary.
- Use `readonly` when possible.
- Avoid enums. Use string literal unions instead.
- Always use `const` instead of `let`.
- Use `satisfies` instead of `as`.

## Naming conventions

- Be descriptive.
- Use suffixes appropriately.

## ESM directory and filename

This codebase uses ES Modules. Do not use `__dirname` or `__filename` as they are not available in ESM. Use `import.meta.dirname` and `import.meta.filename` instead:

```typescript
// Bad - CJS globals not available in ESM
const dir = __dirname
const file = __filename

// Bad - Verbose workaround (no longer needed)
import { fileURLToPath } from 'node:url'
import path from 'node:path'
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// Good - Direct ESM support (Node.js 20.11+)
const dir = import.meta.dirname
const file = import.meta.filename
```

The `noGlobalDirnameFilename` Biome lint rule enforces this pattern and provides automatic fixes.

## Fallible functions return `Result`

When a function can fail in expected ways, return the repo's shared `Result<T, E>` type (`@scalar/helpers/types/result` in Scalar repos; otherwise whatever the repo already has, and if it has nothing, a small local `Result` module is preferable to ad-hoc unions) instead of throwing, returning `null`, or inventing an ad-hoc `{ data } | { error }` union. Build values with its `ok` / `err` constructors and narrow on the `ok` discriminant:

```typescript
import { err, ok, type Result } from '@scalar/helpers/types/result'

const loadUser = async (uid: string): Promise<Result<User>> => {
  const user = await findUser(uid)
  if (!user) return err('User not found')
  return ok(user)
}

const result = await loadUser(uid)
if (!result.ok) {
  toast(result.error, 'error')
  return
}
console.log(result.data)
```

The error type defaults to `string`; pass a string-literal union as the second type argument when callers should switch on discriminated codes. In tests, assert with the constructors: `expect(result).toEqual(ok(user))` / `expect(result).toEqual(err('User not found'))`.

Exception: types that describe an external response keep their real shape. A service client that returns its own `APIResponse<T> | APIError` union (an `error: boolean` discriminant, say) is typed with that service's own exported types — do not re-wrap or re-model it as `Result`.

## Prefer promise `.catch` over try/catch assignment

When a throwing async call needs a fallback, do not declare a mutable binding and assign to it inside a `try`/`catch`. Chain `.catch` on the promise so the binding stays `const`, and early-exit on the fallback value:

```typescript
// Bad - let + try/catch just to guard one call
let document: unknown
try {
  document = await bundle(input, { plugins, depth: 0 })
} catch {
  return output.error().title('Invalid input').exit('error')
}

// Good - const + promise catch + early exit
const document = await bundle(input, { plugins, depth: 0 }).catch(() => null)
if (!document) {
  return output.error().title('Invalid input').exit('error')
}
```

`try`/`catch` blocks are for genuinely multi-statement failure domains or when the error object itself is consumed. A single awaited call with a discard-the-error fallback is always the `.catch(() => null)` form.

## Working with Vue + TypeScript

- Explicitly type `defineProps` and `defineEmits`.
- Explicit return types for composables.
- Explicitly type `Ref` and `ComputedRef`.

See the `vue-components` skill for component structure and styling.

## Testing

- Write all tests using Vitest.
- Cover main cases as well as edge cases; try to break the code with the tests.
- Create the test file alongside the file being tested, named `name.test.ts`.

See the `tests` skill for the full testing conventions.

## Great comments for all types

The general rules live in the `comments` skill — in particular, do not narrate the change that produced the code, and do not explain how TypeScript or Vue works. What follows is the TypeScript and JSDoc detail on top of them.

- Use comments to explain why, not what. Most of the time, the code explains what is happening. Comments should clarify why a type or function exists, why you made specific decisions, or why a workaround is necessary.
- Keep comments succinct. Say what is happening in as few words as needed, and stop. Do not narrate every branch, restate the code, or pile on caveats the reader does not need. A tight two lines beats an exhaustive six.
- Write comments that sound human — clear and direct rather than robotic or formal. That is a note on tone, not license to say more.

Good:

```ts
/**
 * We load the user here to make sure we have fresh data when the component mounts.
 * Without this, the user info could be stale.
 */
```

Bad:

```ts
/**
 * Load user.
 */
```

- Avoid contractions in comments. Use "do not" instead of "don't", "it is" instead of "it's", etc. This makes comments easier to read, especially for non-native speakers.
- If you use contractions, make sure they have proper apostrophes. Sometimes contractions can make a comment more approachable. If you choose to use them, use proper punctuation.
- Comment on types when their purpose is not obvious. If a type models an external API, or has a non-obvious constraint, explain it.
- Explain relationships between types when they are not clear.

Example:

```ts
/**
 * Maps UserStatus to a badge color used in the UI.
 * Should stay in sync with the theme color palette.
 */
export type StatusColorMap = {
  active: 'green'
  inactive: 'gray'
}
```

- Document the intent of utility types or generic types.

Example:

```ts
/**
 * Represents a partial object where at least one property is required.
 * Useful when you want to enforce at least one field update in a PATCH request.
 */
export type AtLeastOne<T> = {
  [K in keyof T]: Partial<T> & Pick<T, K>
}[keyof T]
```

- For complex function signatures or composables, describe the behavior and usage.

Example:

```ts
/**
 * Loads the user for the current session and keeps it in sync with the
 * active workspace. The initial fetch runs on mount, so callers only need
 * `loadUser` when they have changed the user server-side.
 */
export function useUser() { ... }
```

- If the type is temporary or will change later, leave a TODO comment.

Example:

```ts
/**
 * TODO: Replace with dynamic permissions from backend when available.
 */
export type Permissions = 'read' | 'write' | 'admin'
```

- Use JSDoc style consistently for types and functions that are exported or public. This improves editor support (tooltips, autocompletion) and helps other developers understand your code faster.

## Example

```ts
/**
 * A user in the system.
 * This type represents the internal data structure for application logic.
 * If you need to expose user data publicly, use `PublicUser`.
 */
export type User = {
  /** Unique identifier for the user (UUID). */
  id: string
  /** The user's full name. */
  name: string
  /** Email address. Must be validated before saving. */
  email: string
  /** ISO date string of when the user signed up. */
  createdAt: string
  /** Whether the user has verified their email. */
  isVerified: boolean
}
```
