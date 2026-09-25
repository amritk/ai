---
name: comments
description: Write comments and JSDoc that explain why rather than what — documenting intent, constraints, and non-obvious decisions without narrating the change that produced them. Use when adding comments or JSDoc, reviewing over- or under-commented code, or writing global CSS where a selector sits far from the markup it serves.
---
# Comments and Documentation

Use comments to explain **why**, not **what**. Most of the time, the code explains what is happening. Comments should clarify why a type or function exists, why a decision was made, or why a workaround is necessary.

Write friendly comments that sound human. Comments should be clear and helpful, not robotic or overly formal.

Keep comments relevant and concise. Say only what the reader needs and stop. Prefer the shortest phrasing that still conveys the why, drop background that does not change how the code is read, and do not pad a comment with restated context, illustrative identifiers, or caveats that the reader will not act on. A tight one or two lines beats a thorough paragraph.

If a workaround needs a paragraph-long comment to sound acceptable, the workaround is probably wrong. Revisit the design before documenting it.

## Source comments

Good comments clarify:

- non-obvious OpenAPI edge cases,
- security-sensitive escaping or path validation,
- external API quirks,
- target language compatibility decisions,
- design tradeoffs,
- temporary workarounds.

Avoid comments that merely label obvious compiler stages or repeat the code.

## Required comments for agent-written code

Agent-authored code must include comments where intent is not obvious. Before finishing a code change, audit the diff for missing comments and fix gaps.

Required:

- Useful JSDoc on every new function an agent adds, including local helpers. Keep it intent-focused; explain why the helper exists or what relationship/fallback it preserves rather than restating the implementation.
- JSDoc on changed exported types, interfaces, functions, classes, enums, and public constants unless the declaration is a narrow re-export or the intent is completely obvious from the name and type.
- A short why-comment before non-trivial control flow, fallback behavior, normalization, escaping, code generation, pagination, streaming, auth, or path-safety logic.
- Comments for generated SDK behavior that affects public API, auth, pagination, streaming, paths, serialization, errors, retries, or runtime options.

Not acceptable:

- Comment-free exported APIs when the declaration introduces public semantics or a new relationship between types.
- Comments that merely restate the code.
- Generated code paths that silently encode business rules without explaining why.

**Good:**

```typescript
/**
 * We preserve the original response media type here because emitters use it to
 * choose a safe fallback when the schema is ambiguous.
 */
```

**Bad:**

```typescript
/** Compile responses. */
```

## Comment guidelines

- Avoid contractions in comments. Use "do not" instead of "don't", "it is" instead of "it's", and similar forms.
- If you use contractions, make sure they have proper apostrophes.
- Comment on types when their purpose is not obvious.
- Explain relationships between types when they are not clear.
- Document utility types or generic types when their intent is non-obvious.
- Use JSDoc for every new function an agent adds, and for exported types and public functions when the intent is not immediately obvious.
- Keep short JSDoc comments on one line when the whole comment fits comfortably, such as `/** Context required to build generated code samples for one SDK target. */`.
- Leave TODO comments only for genuinely temporary solutions and include enough context to remove them later.

## Generated code comments

Generated SDK comments are part of the user-facing SDK experience.

- Escape all spec-derived comments before emitting them.
- Do not emit raw Markdown/HTML into language doc comments unless it is sanitized for the target language.
- Preserve useful OpenAPI descriptions, summaries, deprecation notes, examples, and parameter docs when they improve SDK usability.
- Avoid emitting huge repeated descriptions when they make generated code hard to read.
- Do not emit misleading comments when schema fallback types are lossy or incomplete.
- If generated comments mention auth, pagination, streaming, or runtime behavior, source that information from config/IR rather than target heuristics.
- Keep generated comments deterministic so fixture snapshots and audits stay stable.

## Examples

Document non-obvious type relationships:

```typescript
/**
 * Maps each public resource method back to the OpenAPI operation that produced it.
 * Audits use this to detect generated endpoints that drift from the compiled IR.
 */
export type OperationManifestEntry = {
  readonly operationId: string;
  readonly methodName: string;
};
```

Explain security constraints:

```typescript
/**
 * Spec-derived names are sanitized before path validation so malicious operation
 * IDs cannot escape the output directory through generated file names.
 */
```

Explain compatibility choices:

```typescript
/**
 * We keep this helper Promise-based because the generated Node.js runtime must
 * support streaming responses without assuming a browser-only body type.
 */
```
