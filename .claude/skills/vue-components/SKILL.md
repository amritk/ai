---
name: vue-components
description: Build Vue 3 components with TypeScript and Tailwind — Composition API structure, typed props and emits, composable logic, accessibility, and maintainable styling. Use when creating or reviewing any .vue single-file component.
---

# Writing Vue components

Write Vue 3 components that are clean, readable, and easy to maintain. Optimize for clarity and simplicity.

## Essentials

- Keep components small and focused; move business logic into composables, utilities, or services.
- Use `<script setup lang="ts">` with strongly typed `defineProps` / `defineEmits`; destructure props.
- Favor computed properties over inline template logic; fail gracefully with sensible defaults.
- Style with Tailwind utility classes; handle responsive and dark mode variants; do not neglect accessibility (semantic HTML, ARIA, focus handling).
- Keep `<script setup>` ordered: imports, props/emits, state/computed/methods, lifecycle hooks.
- For Scalar-branded UI, follow the repo's `scalar-design-system` guidance and its `--scalar-*` tokens.

## Principles

- Keep components small and focused. Each component should do one thing and do it well. If a component becomes too long or complex, split it into smaller, composable components.
  - Watch a Single File Component's length as you build and refactor. Treat a component passing ~600 lines as a strong signal of architectural bloat, not a hard limit to police. When you cross it, refactor: extract business logic into small, tested helper functions, and break complex layouts into smaller, isolated sub-components.
- Minimize logic inside components. Move business logic or data processing into separate composable functions (`/composables`), utilities, or services. This makes the component easier to test and understand.
- Favor computed properties and methods over template logic. Keep templates clean and declarative. Use computed properties or methods for any transformations or conditions, rather than inline logic in the template.
- Fail gracefully. Components should be fault-tolerant. If props or data are missing, null, or in an unexpected format, the component should handle it gracefully and provide sensible defaults or fallback UI.
- Use TypeScript effectively. Strongly type props, emits, and events. Leverage Vue's `defineProps` and `defineEmits` to ensure correct usage. Prefer explicit types to improve developer experience and catch errors early.
- Write testable code. Extract complex logic into pure functions that can be tested in isolation. Keep the component focused on rendering and user interaction.
- Consistent naming and structure.
  - Use clear, descriptive names for components, props, and events.
  - Stick to a consistent file structure (e.g., components, composables, utils).
  - Keep the `<script setup>` section organized: first imports, then props/emits, then state/computed/methods, and finally lifecycle hooks.

## Styling with Tailwind CSS

- Use Tailwind CSS utility classes for all styling. Avoid writing custom CSS unless necessary. Utility classes keep the styles consistent and colocated with the template.
- Keep class lists readable.
  - Break long class lists into multiple lines for readability if needed.
  - Use component-level abstractions when appropriate.
- If multiple components share the same styles, extract them into reusable Vue components or leverage Tailwind's `@apply` in minimal CSS files or scoped styles.
- Handle responsive and dark mode thoughtfully. Use Tailwind's responsive and dark mode variants consistently. Ensure components look good on different screen sizes and in both light/dark themes.
- Accessibility matters. Tailwind will not handle accessibility for you. Make sure you add semantic HTML, ARIA attributes where needed, and focus handling for interactive components.
- When building Scalar-branded UI, follow the repo's `scalar-design-system` guidance so output uses real `--scalar-*` tokens and `@scalar/components` instead of generic defaults.

## Example structure

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useItems } from '@/composables/useItems'

const { initialItems } = defineProps<{
  initialItems?: Item[]
}>()

const { items } = useItems(initialItems ?? [])

/** We do not want to show the card when there is no item. */
const hasItems = computed(() => items.value.length > 0)
</script>

<template>
  <div
    v-if="hasItems"
    class="grid gap-4 md:grid-cols-2">
    <ItemCard
      v-for="item in items"
      :key="item.id"
      :item="item"
      class="rounded-xl bg-white p-4 shadow dark:bg-gray-800" />
  </div>
  <p
    v-else
    class="text-center text-gray-500">
    No items available.
  </p>
</template>
```
