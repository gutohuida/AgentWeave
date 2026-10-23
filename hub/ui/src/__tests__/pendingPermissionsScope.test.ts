import { describe, expect, it } from 'vitest'
import type { PermissionRequest } from '@/api/permissions'
import { openPermissionRequestsFor } from '@/lib/pendingPermissions'

function request(overrides: Partial<PermissionRequest> = {}): PermissionRequest {
  return {
    id: 'perm-1',
    agent: 'alpha',
    run_id: 'run-1',
    conversation_id: 'conv-asking',
    tool_name: 'archive_job',
    tool_use_id: 'toolu_1',
    tool_input: {},
    status: 'pending',
    dismissed: false,
    created_at: new Date().toISOString(),
    decided_at: null,
    decided_by: null,
    ...overrides,
  }
}

// F928: a card belongs to the conversation whose run asked, not to every conversation of the agent.
describe('openPermissionRequestsFor, scoped to a conversation', () => {
  it('shows a request in the conversation whose run asked', () => {
    expect(openPermissionRequestsFor([request()], 'alpha', 'conv-asking')).toHaveLength(1)
  })

  it('does not show it in another conversation of the same agent', () => {
    expect(openPermissionRequestsFor([request()], 'alpha', 'conv-review')).toHaveLength(0)
  })

  it('does not show it with no conversation open', () => {
    expect(openPermissionRequestsFor([request()], 'alpha', null)).toHaveLength(0)
  })

  it('shows a request with no conversation wherever the agent is open', () => {
    const loose = request({ conversation_id: null })
    expect(openPermissionRequestsFor([loose], 'alpha', 'conv-review')).toHaveLength(1)
    // A Hub older than the field leaves it absent; that reads the same.
    const older = request()
    delete older.conversation_id
    expect(openPermissionRequestsFor([older], 'alpha', 'conv-review')).toHaveLength(1)
  })

  it('without a conversation argument keeps the agent-wide reading', () => {
    expect(openPermissionRequestsFor([request()], 'alpha')).toHaveLength(1)
  })
})
