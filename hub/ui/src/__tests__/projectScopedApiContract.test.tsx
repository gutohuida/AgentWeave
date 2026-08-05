/// <reference types="vite/client" />
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useTasks } from '@/api/tasks'

// Phase 4.3 (local-multi-project-workspace): every project-scoped API hook
// must carry the stable project identifier in both its request path and its
// React Query key (design.md decision 8), so a delayed response or a stale
// invalidation from one project can never touch another project's cache
// slot. client.ts (instance-level HTTP helpers) and setup.ts/projects.ts
// (the instance credential and the project collection itself — neither is
// project-scoped by definition) are deliberately excluded.
//
// Source read via Vite's `?raw` glob import rather than node:fs — this file
// compiles under the browser-targeted app tsconfig (no @types/node), and
// vitest's Vite-powered transform resolves `?raw` imports to plain strings
// in both the test runner and a static `tsc --noEmit` pass.
const API_SOURCES = import.meta.glob('../api/*.ts', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

// modelCatalog.ts: the model/provider/control catalog is static and identical for every
// project (2026-08-04-hub-model-control-and-provisioning design.md), same rationale as
// projects.ts's own exemption below. fsBrowse.ts: directory listing backs choosing a
// project directory *before* a project exists, so it cannot carry a project ID either.
const INSTANCE_LEVEL_FILES = new Set([
  'client.ts',
  'setup.ts',
  'projects.ts',
  'modelCatalog.ts',
  'fsBrowse.ts',
])

function apiFiles(): Array<[name: string, source: string]> {
  return Object.entries(API_SOURCES)
    .map(([modPath, source]): [string, string] => [modPath.split('/').pop() as string, source])
    .filter(([name]) => !INSTANCE_LEVEL_FILES.has(name))
}

/** Every string/template literal passed as the first argument to one of the
 * REST helpers, restricted to ones that look like a Hub API path. */
function extractApiCallPaths(src: string): string[] {
  const callRe = /\b(?:getJson|postJson|patchJson|putJson|fetchWithAuth)(?:<[^>(]*>)?\(\s*(`[^`]*`|'[^']*'|"[^"]*")/g
  const paths: string[] = []
  let match: RegExpExecArray | null
  while ((match = callRe.exec(src))) {
    const literal = match[1]
    if (literal.includes('/api/v1/')) paths.push(literal)
  }
  return paths
}

/** Every `queryKey: [...]` array literal (single-line only — every hook in
 * this codebase writes queryKey as one line; a multi-line key would need a
 * smarter parser, which isn't warranted while that convention holds). */
function extractQueryKeys(src: string): string[] {
  const keyRe = /queryKey:\s*(\[[^\]\n]*\])/g
  const keys: string[] = []
  let match: RegExpExecArray | null
  while ((match = keyRe.exec(src))) keys.push(match[1])
  return keys
}

describe('every project-scoped API hook carries project ID (source contract)', () => {
  const files = apiFiles()

  it('the file list is not accidentally empty (the scan itself is meaningful)', () => {
    expect(files.length).toBeGreaterThan(5)
  })

  for (const [file, src] of files) {
    it(`${file}: every Hub API request path is project-scoped`, () => {
      const apiPaths = extractApiCallPaths(src)
      for (const literal of apiPaths) {
        expect(literal).toMatch(/\/projects\/\$\{projectId\}/)
      }
    })

    it(`${file}: every queryKey starts with ['project', projectId, ...]`, () => {
      const queryKeys = extractQueryKeys(src)
      for (const key of queryKeys) {
        expect(key).toMatch(/^\['project',\s*projectId\b/)
      }
    })
  }
})

// ---------------------------------------------------------------------------
// Behavioral: a delayed response crossing a project switch must not leak
// into the newly-selected project's cache (spec.md scenario "A delayed
// response crosses a switch").
// ---------------------------------------------------------------------------

function makeWrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('a delayed response crossing a project switch stays in its own project cache slot', () => {
  it('project A\'s in-flight response does not populate project B\'s query', async () => {
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
    })

    const resolver: { current: (() => void) | null } = { current: null }
    const fetchMock = (globalThis.fetch = ((url: string) => {
      if (url.includes('/projects/proj-a/')) {
        return new Promise((resolve) => {
          resolver.current = () =>
            resolve({
              ok: true,
              status: 200,
              json: async () => [{ id: 'task-a', title: 'from A' }],
            } as Response)
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => [{ id: 'task-b', title: 'from B' }],
      } as Response)
    }) as typeof fetch)

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = makeWrapper(client)

    // Render while selected project is A — this starts the (deliberately
    // never-resolving-yet) request for project A's tasks.
    renderHook(() => useTasks(), { wrapper })

    // Switch to project B before A's response arrives.
    useConfigStore.getState().setSelectedProject('proj-b')
    const bHook = renderHook(() => useTasks(), { wrapper })
    await waitFor(() =>
      expect(bHook.result.current.data).toEqual([{ id: 'task-b', title: 'from B' }])
    )

    // Now let A's delayed response resolve.
    resolver.current?.()
    await new Promise((r) => setTimeout(r, 0))

    // Project A's cache slot holds A's data; project B's view is unaffected.
    expect(client.getQueryData(['project', 'proj-a', 'tasks'])).toEqual([
      { id: 'task-a', title: 'from A' },
    ])
    expect(bHook.result.current.data).toEqual([{ id: 'task-b', title: 'from B' }])

    void fetchMock
  })
})

// ---------------------------------------------------------------------------
// Behavioral: rapidly switching projects leaves each hook instance reading
// its own project's data, never a stale mix (spec.md's rapid-switch race).
// ---------------------------------------------------------------------------

describe('rapid project switching never blends two projects into one rendered view', () => {
  it('re-rendering with a new selected project fetches under a new query key, not the old one', async () => {
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-1',
      isConfigured: true,
      bootstrapState: 'ready',
    })

    const seen: string[] = []
    globalThis.fetch = ((url: string) => {
      seen.push(url)
      const projectId = url.includes('proj-1') ? 'proj-1' : 'proj-2'
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => [{ id: `task-${projectId}` }],
      } as Response)
    }) as typeof fetch

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = makeWrapper(client)

    const first = renderHook(() => useTasks(), { wrapper })
    await waitFor(() => expect(first.result.current.data).toBeDefined())
    expect(first.result.current.data).toEqual([{ id: 'task-proj-1' }])

    useConfigStore.getState().setSelectedProject('proj-2')
    const second = renderHook(() => useTasks(), { wrapper })
    await waitFor(() => expect(second.result.current.data).toBeDefined())
    expect(second.result.current.data).toEqual([{ id: 'task-proj-2' }])

    // Both project's slots are independently cached — switching back to
    // proj-1 would not need to refetch to get correct (if stale) data.
    expect(client.getQueryData(['project', 'proj-1', 'tasks'])).toEqual([{ id: 'task-proj-1' }])
    expect(client.getQueryData(['project', 'proj-2', 'tasks'])).toEqual([{ id: 'task-proj-2' }])
    expect(seen.some((u) => u.includes('/projects/proj-1/tasks'))).toBe(true)
    expect(seen.some((u) => u.includes('/projects/proj-2/tasks'))).toBe(true)
  })
})
