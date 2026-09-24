import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { renderHook } from '@testing-library/react'
import { agentDestination, projectDestination } from '@/lib/navigation'
import { useWorkspaceNavigation } from '@/hooks/useWorkspaceNavigation'

function setSearch(search: string) {
  window.history.pushState(null, '', search || '/')
}

describe('phase 5 useWorkspaceNavigation', () => {
  beforeEach(() => {
    setSearch('/')
  })

  afterEach(() => {
    setSearch('/')
  })

  it('restores the destination encoded in the URL on mount', () => {
    setSearch('?project=proj-1&tab=tasks')
    const { result } = renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: ['proj-1'], lastOpenedProjectId: 'proj-1' }),
    )
    expect(result.current.destination).toEqual(projectDestination('proj-1', 'tasks'))
  })

  it('mounts a direct agent conversation URL straight into the conversation destination', () => {
    setSearch('?project=proj-1&agent=claude&conversation=conv-9')
    const { result } = renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: ['proj-1'], lastOpenedProjectId: 'proj-1' }),
    )
    expect(result.current.destination).toEqual(agentDestination('proj-1', 'claude', 'conv-9'))
  })

  it('falls back to the last-opened project and rewrites the URL when the requested project is unknown', () => {
    setSearch('?project=proj-missing')
    const { result } = renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: ['proj-1', 'proj-2'], lastOpenedProjectId: 'proj-2' }),
    )
    expect(result.current.destination).toEqual(projectDestination('proj-2'))
    expect(window.location.search).toBe('?project=proj-2&tab=overview')
  })

  it('does not fall back while the project collection is still loading', () => {
    setSearch('?project=proj-not-yet-loaded&tab=jobs')
    type Props = { availableProjectIds: string[] | null; lastOpenedProjectId: string | null }
    const initialProps: Props = { availableProjectIds: null, lastOpenedProjectId: null }
    const { result, rerender } = renderHook(
      (props: Props) => useWorkspaceNavigation(props),
      { initialProps },
    )
    expect(result.current.destination).toEqual(projectDestination('proj-not-yet-loaded', 'jobs'))

    // The collection finishes loading and turns out not to contain that project.
    act(() => {
      rerender({ availableProjectIds: ['proj-1'], lastOpenedProjectId: 'proj-1' })
    })
    expect(result.current.destination).toEqual(projectDestination('proj-1'))
  })

  it('navigate() pushes a new history entry and updates the destination', () => {
    setSearch('?project=proj-1&tab=overview')
    const { result } = renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: ['proj-1'], lastOpenedProjectId: 'proj-1' }),
    )
    act(() => {
      result.current.navigate(projectDestination('proj-1', 'tasks'))
    })
    expect(result.current.destination).toEqual(projectDestination('proj-1', 'tasks'))
    expect(window.location.search).toBe('?project=proj-1&tab=tasks')
  })

  it('restores the prior destination when the browser goes back across projects', () => {
    setSearch('?project=proj-1&tab=overview')
    const { result } = renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: ['proj-1', 'proj-2'], lastOpenedProjectId: 'proj-1' }),
    )
    act(() => {
      result.current.navigate(projectDestination('proj-2'))
    })
    expect(result.current.destination).toEqual(projectDestination('proj-2'))

    // Simulate the browser restoring the previous URL and firing popstate,
    // exactly as it does on a real Back press.
    act(() => {
      window.history.pushState(null, '', '?project=proj-1&tab=overview')
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
    expect(result.current.destination).toEqual(projectDestination('proj-1'))
  })

  it('never writes a provider session identifier into the URL', () => {
    setSearch('?project=proj-1&tab=overview')
    const { result } = renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: ['proj-1'], lastOpenedProjectId: 'proj-1' }),
    )
    act(() => {
      result.current.navigate(agentDestination('proj-1', 'claude', 'conv-1'))
    })
    const params = new URLSearchParams(window.location.search)
    const allowedKeys = new Set(['project', 'tab', 'section', 'agent', 'conversation'])
    for (const key of params.keys()) {
      expect(allowedKeys.has(key)).toBe(true)
    }
  })

  it('resolves to the zero-project state and clears the URL when nothing is registered', () => {
    setSearch('?project=proj-missing')
    const { result } = renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: [], lastOpenedProjectId: null }),
    )
    expect(result.current.destination).toEqual({ kind: 'zero' })
    expect(window.location.search).toBe('')
  })

  it('canonicalises an unknown deep-link pathname to the root (F20)', () => {
    // A URL shape nothing here parses — no `?project=` at all, so `window.location.search` is
    // empty and the app falls back to the last-opened project — but the pathname itself is what
    // the old `target !== currentSearch()` comparison never looked at, so it survived untouched.
    window.history.pushState(null, '', '/projects/proj-1/tasks')
    const { result } = renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: ['proj-1'], lastOpenedProjectId: 'proj-1' }),
    )
    expect(result.current.destination).toEqual(projectDestination('proj-1'))
    expect(window.location.pathname).toBe('/')
    expect(window.location.search).toBe('?project=proj-1&tab=overview')
  })

  it('still canonicalises the pathname when the search half already matches the resolved destination', () => {
    // The half of the old comparison that DID hold: with the query already canonical, only the
    // pathname disagreed, so `target !== currentSearch()` was false and nothing ran.
    window.history.pushState(null, '', '/projects/proj-1/tasks?project=proj-1&tab=overview')
    renderHook(() =>
      useWorkspaceNavigation({ availableProjectIds: ['proj-1'], lastOpenedProjectId: 'proj-1' }),
    )
    expect(window.location.pathname).toBe('/')
    expect(window.location.search).toBe('?project=proj-1&tab=overview')
  })
})
