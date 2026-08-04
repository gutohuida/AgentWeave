import { describe, expect, it } from 'vitest'
import {
  agentDestination,
  environmentDestination,
  parseDestination,
  projectDestination,
  resolveDestination,
  serializeDestination,
  type WorkspaceDestination,
} from '@/lib/navigation'

describe('phase 5 URL navigation contract', () => {
  describe('serializeDestination / parseDestination round trip', () => {
    it('round-trips a project destination at its default tab', () => {
      const destination = projectDestination('proj-1')
      const search = serializeDestination(destination)
      expect(parseDestination(search)).toEqual(destination)
    })

    it('round-trips a project destination on a non-default tab', () => {
      const destination = projectDestination('proj-1', 'tasks')
      expect(parseDestination(serializeDestination(destination))).toEqual(destination)
    })

    it('round-trips the environment tab with its section', () => {
      const destination = environmentDestination('proj-1', 'runners')
      expect(parseDestination(serializeDestination(destination))).toEqual(destination)
    })

    it('round-trips an agent conversation with no conversation id yet', () => {
      const destination = agentDestination('proj-1', 'claude')
      expect(parseDestination(serializeDestination(destination))).toEqual(destination)
    })

    it('round-trips an agent conversation with a selected AgentWeave conversation id', () => {
      const destination = agentDestination('proj-1', 'claude', 'conv-123')
      expect(parseDestination(serializeDestination(destination))).toEqual(destination)
    })

    it('serializes the zero-project state as an empty query string', () => {
      expect(serializeDestination({ kind: 'zero' })).toBe('')
    })

    it('parses an empty query string as no requested destination', () => {
      expect(parseDestination('')).toBeNull()
      expect(parseDestination('?')).toBeNull()
    })
  })

  describe('parseDestination robustness', () => {
    it('defaults an unknown or missing tab to overview', () => {
      expect(parseDestination('?project=proj-1&tab=bogus')).toEqual(
        projectDestination('proj-1', 'overview'),
      )
      expect(parseDestination('?project=proj-1')).toEqual(projectDestination('proj-1', 'overview'))
    })

    it('defaults an unknown or missing environment section to the first section', () => {
      expect(parseDestination('?project=proj-1&tab=environment&section=bogus')).toEqual(
        environmentDestination('proj-1'),
      )
      expect(parseDestination('?project=proj-1&tab=environment')).toEqual(
        environmentDestination('proj-1'),
      )
    })

    it('treats agent+project as a conversation destination regardless of tab', () => {
      expect(parseDestination('?project=proj-1&agent=claude&tab=tasks')).toEqual(
        agentDestination('proj-1', 'claude'),
      )
    })

    it('never produces a destination keyed by a provider session id', () => {
      const search = serializeDestination(agentDestination('proj-1', 'claude', 'conv-123'))
      const params = new URLSearchParams(search)
      const allowedKeys = new Set(['project', 'tab', 'section', 'agent', 'conversation'])
      for (const key of params.keys()) {
        expect(allowedKeys.has(key)).toBe(true)
      }
      expect(params.has('session_id')).toBe(false)
      expect(params.has('claude_session_id')).toBe(false)
    })
  })

  describe('resolveDestination fallback rules', () => {
    const options = (overrides: Partial<Parameters<typeof resolveDestination>[1]> = {}) => ({
      availableProjectIds: ['proj-1', 'proj-2'],
      lastOpenedProjectId: 'proj-2',
      ...overrides,
    })

    it('keeps a requested destination whose project is registered', () => {
      const requested = projectDestination('proj-1', 'tasks')
      expect(resolveDestination(requested, options())).toEqual(requested)
    })

    it('falls back to the last-opened available project when the requested project is unknown', () => {
      const requested: WorkspaceDestination = projectDestination('proj-missing')
      expect(resolveDestination(requested, options())).toEqual(projectDestination('proj-2'))
    })

    it('falls back to the first available project when there is no last-opened project', () => {
      const requested: WorkspaceDestination = projectDestination('proj-missing')
      expect(
        resolveDestination(requested, options({ lastOpenedProjectId: null })),
      ).toEqual(projectDestination('proj-1'))
    })

    it('falls back to the first available project when the last-opened project is no longer registered', () => {
      const requested: WorkspaceDestination = projectDestination('proj-missing')
      expect(
        resolveDestination(requested, options({ lastOpenedProjectId: 'proj-gone' })),
      ).toEqual(projectDestination('proj-1'))
    })

    it('falls back to the zero-project state when nothing is registered', () => {
      const requested: WorkspaceDestination = projectDestination('proj-missing')
      expect(
        resolveDestination(requested, {
          availableProjectIds: [],
          lastOpenedProjectId: null,
        }),
      ).toEqual({ kind: 'zero' })
    })

    it('resolves a null (unspecified) request the same way as an unknown project', () => {
      expect(resolveDestination(null, options())).toEqual(projectDestination('proj-2'))
      expect(
        resolveDestination(null, { availableProjectIds: [], lastOpenedProjectId: null }),
      ).toEqual({ kind: 'zero' })
    })

    it('trusts a requested conversation destination whose project is registered', () => {
      const requested = agentDestination('proj-1', 'claude', 'conv-1')
      expect(resolveDestination(requested, options())).toEqual(requested)
    })

    it('falls back a conversation destination whose project is unknown', () => {
      const requested = agentDestination('proj-missing', 'claude', 'conv-1')
      expect(resolveDestination(requested, options())).toEqual(projectDestination('proj-2'))
    })

    it('does not validate against the registry while the collection is still loading', () => {
      const requested = projectDestination('proj-not-yet-loaded', 'tasks')
      expect(
        resolveDestination(requested, { availableProjectIds: null, lastOpenedProjectId: null }),
      ).toEqual(requested)
    })

    it('falls back to the last-opened project while loading if no destination was requested', () => {
      expect(
        resolveDestination(null, { availableProjectIds: null, lastOpenedProjectId: 'proj-2' }),
      ).toEqual(projectDestination('proj-2'))
    })
  })
})
