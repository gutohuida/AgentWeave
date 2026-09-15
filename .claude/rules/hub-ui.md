---
paths:
  - "hub/ui/**"
  - "hub/hub/static/ui/**"
---

# Hub UI rules (loaded when a UI file is read)

## The committed bundle reaches the operator's live app

`hub/hub/static/ui` is a committed build artefact, and the operator's `:8000` Hub serves it straight
from this checkout: **a committed UI bundle reaches their live app on their next reload.** After
`cd hub/ui && npm run build`, run `make ui` (or `python scripts/refresh_ui_bundle.py` directly —
`make` is not on PATH in Git Bash on this machine). It copies `dist/` over the bundle, confirms the
copy, and records `hub/hub/static/ui/ui-build-stamp.json`, the fingerprint of the source it was
built from. Commit `hub/ui/src` and `hub/hub/static/ui` together; the stamp is what gives a
byte-identical rebuild something to commit, so `/health` can stop reporting `ui_stale`. Only the
script writes the stamp. `test_ui_staleness.py` still does **not** check this repo's copy;
`test_ui_build_stamp.py` checks the stamp parses, and gates the stricter bundle-matches-source
assertion behind `AW_CHECK_UI_BUNDLE=1`.

## Adding a component

1. Create it in `hub/ui/src/components/{category}/ComponentName.tsx` — TypeScript, functional.
2. Use existing components (Badge, Icon, EmptyState) for consistency; add to a barrel export if
   applicable.
3. Tailwind CSS + CSS variables for theming; React Query for data (`hub/ui/src/api/`), Zustand for
   global state.

## Adding an API hook

```typescript
// hub/ui/src/api/feature.ts
import { useQuery } from '@tanstack/react-query'
import { getJson } from './client'
import { useConfigStore } from '@/store/configStore'

export function useFeature() {
  const { isConfigured } = useConfigStore()
  return useQuery({
    queryKey: ['feature'],
    queryFn: () => getJson('/api/v1/feature'),
    enabled: isConfigured,
  })
}
```

Frontend server-state keys are project-prefixed (see the multi-project boundary in `CLAUDE.md`).

## Real-time updates

SSE via the `useSSE` hook in `hub/ui/src/hooks/useSSE.ts`. Events such as `agent_output`,
`session_synced`, `task_updated`; the frontend invalidates React Query caches on events. A test for
code that consumes a payload uses the order the route actually returns (`CLAUDE.md`, Critical Rules).

## Icons

Use the `Icon` component — it wraps `lucide-react` SVGs. The Material Symbols webfont was removed (it
loaded `display=block` from a CDN and held every icon invisible until the request completed). The
`name` API was kept so call sites did not change. **Do not reintroduce a second icon *font*, and do
not add a third icon source without the operator deciding it.**

**`simple-icons` is a sanctioned exception, decided by the operator 2026-08-19.** lucide
deliberately carries no brand marks, and neither do Heroicons, Phosphor or Tabler. Brand marks live
in `hub/ui/src/components/common/brandMarks.ts` and are reached through the same `Icon` component via
a `brand:<key>` name, so there is still one call surface. These are bundled path strings, so the
webfont failure mode is absent. Tree-shaking is load-bearing: importing 24 marks by name costs
~15 kB gzip, the full 3,453 would be megabytes — never `import * from 'simple-icons'`.

A brand mark is used **only where one is actually published** (PowerShell, Java and C# were
withdrawn upstream over trademark objections, so those keep a generic lucide glyph), and a brand's
own colour is used **only when it clears a contrast floor against both backgrounds** — Markdown,
JSON and Rust are officially `#000000` and were invisible in dark mode for one build. `brandHex`
computes this and returns null to fall back to a palette token.

## Lint

`cd hub/ui && npm run lint`.
