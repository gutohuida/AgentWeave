import { describe, expect, it } from 'vitest'
import {
  agentDestination,
  agentSettingsBackDestination,
  agentSettingsDestination,
  environmentDestination,
  isAgentSettingsDestination,
  isSectionedDestination,
  parseDestination,
  projectDestination,
  isSpecDocumentPath,
  resolveDestination,
  serializeDestination,
  withDocument,
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

    it('round-trips an agent-settings destination at its default section', () => {
      const destination = agentSettingsDestination('proj-1', 'claude')
      expect(parseDestination(serializeDestination(destination))).toEqual(destination)
    })

    it('round-trips an agent-settings destination on a named section', () => {
      const destination = agentSettingsDestination('proj-1', 'claude', 'interaction')
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

    it('resolves a settings URL to settings, not to the conversation it also looks like', () => {
      // The conversation branch claims any URL carrying an `agent`, so a settings link is only
      // a settings link if `settings` is tested first. Getting this backwards sends every
      // settings link to a chat, which is exactly the shape of bug that survives type-checking.
      const parsed = parseDestination('?project=proj-1&agent=claude&settings=execution')
      expect(isAgentSettingsDestination(parsed as WorkspaceDestination)).toBe(true)
      expect(parsed).toEqual(agentSettingsDestination('proj-1', 'claude', 'execution'))
    })

    it('defaults an unknown settings section to the first section', () => {
      expect(parseDestination('?project=proj-1&agent=claude&settings=bogus')).toEqual(
        agentSettingsDestination('proj-1', 'claude'),
      )
    })

    it('ignores a settings parameter that names no agent', () => {
      // There is no such thing as configuring no agent, so this is not coerced into one.
      expect(parseDestination('?project=proj-1&settings=execution')).toEqual(
        projectDestination('proj-1'),
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

  describe('the agent-settings destination', () => {
    it('back goes to the agent, not to wherever the operator came from', () => {
      // Fixed, like "Back to {project}" — no stored origin. `conversationId: null` is what makes
      // it the agent's most recent, since `resolveConversationSelection` already resolves null
      // that way.
      const back = agentSettingsBackDestination(
        agentSettingsDestination('proj-1', 'claude', 'access'),
      )
      expect(back).toEqual(agentDestination('proj-1', 'claude'))
      expect(back.conversationId).toBeNull()
    })

    it('puts the rail into section mode, as project configuration does', () => {
      expect(isSectionedDestination(agentSettingsDestination('proj-1', 'claude'))).toBe(true)
      expect(isSectionedDestination(environmentDestination('proj-1'))).toBe(true)
      expect(isSectionedDestination(agentDestination('proj-1', 'claude'))).toBe(false)
    })

    it('survives resolution against the registered project collection', () => {
      const requested = agentSettingsDestination('proj-1', 'claude', 'charter')
      expect(
        resolveDestination(requested, {
          availableProjectIds: ['proj-1'],
          lastOpenedProjectId: null,
        }),
      ).toEqual(requested)
    })

    it('falls back when its project is not registered', () => {
      expect(
        resolveDestination(agentSettingsDestination('proj-gone', 'claude'), {
          availableProjectIds: ['proj-1'],
          lastOpenedProjectId: null,
        }),
      ).toEqual(projectDestination('proj-1'))
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

describe('the open document is part of the conversation destination', () => {
  const DOC = 'spec/roadmaps/agentweave-reconstruction.html'

  it('round-trips a conversation with a document open beside it', () => {
    const destination = agentDestination('proj-1', 'claude', 'conv-123', DOC)
    expect(parseDestination(serializeDestination(destination))).toEqual(destination)
  })

  it('carries no document parameter when none is open', () => {
    const destination = agentDestination('proj-1', 'claude', 'conv-123')
    expect(destination.document).toBeNull()
    expect(serializeDestination(destination)).not.toContain('document')
  })

  it('opens, changes, and closes the document without disturbing where the operator is', () => {
    const base = agentDestination('proj-1', 'claude', 'conv-123')
    const opened = withDocument(base, DOC)
    expect(opened).toEqual({ ...base, document: DOC })
    expect(withDocument(opened, 'spec/spec.html').document).toBe('spec/spec.html')
    expect(withDocument(opened, null).document).toBeNull()
  })

  it('rejects a path that is not a legal specification path, resolving to no document', () => {
    // The same contract `validate_spec_path` applies server-side. An illegal value is "no
    // document", never an error page.
    const illegal = [
      '../etc/passwd',
      'spec/../../secret.html',
      'notspec/spec.html',
      'spec/spec.txt',
      'spec/SPEC.html',
      'spec//spec.html',
      'spec/.hidden/spec.html',
      'spec/%2e%2e/spec.html',
      'spec\windows\spec.html',
      '',
    ]
    for (const value of illegal) {
      expect(isSpecDocumentPath(value)).toBe(false)
      expect(parseDestination(`?project=proj-1&agent=claude&document=${encodeURIComponent(value)}`))
        .toMatchObject({ document: null })
    }
    expect(isSpecDocumentPath(DOC)).toBe(true)
  })

  it('never lets an illegal path reach the URL, however the destination was constructed', () => {
    const forged = {
      kind: 'conversation' as const,
      projectId: 'proj-1',
      agent: 'claude',
      conversationId: 'conv-1',
      document: '../../etc/passwd',
    }
    expect(serializeDestination(forged)).not.toContain('document')
  })

  it('keeps the document across a conversation change', () => {
    // The document is what the operator is working on, not a property of the thread they are
    // working on it in.
    const first = agentDestination('proj-1', 'claude', 'conv-1', DOC)
    const second = agentDestination('proj-1', 'claude', 'conv-2', first.document)
    expect(second.document).toBe(DOC)
  })

  it('a resolved conversation destination keeps its document', () => {
    const requested = agentDestination('proj-1', 'claude', 'conv-1', DOC)
    expect(resolveDestination(requested, {
      availableProjectIds: ['proj-1'],
      lastOpenedProjectId: null,
    })).toEqual(requested)
  })
})
