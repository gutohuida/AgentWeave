/**
 * `apiErrorCode` reads the same structured `detail.code` that `readableApiError` reduces to a
 * sentence — but a caller that offers a *remedy* (ProjectManagerModal's "register as new") needs
 * to match on the code, not the prose. These tests hold that contract against the same response
 * shapes taskIntegration.test.ts already covers for `readableApiError`, since the two functions
 * parse the same `ApiError.message` and must agree on what counts as "no code here".
 */
import { describe, expect, it } from 'vitest'

import { ApiError, apiErrorCode } from '@/api/client'

function refusal(detail: unknown): ApiError {
  return new ApiError(409, JSON.stringify({ detail }))
}

describe('apiErrorCode', () => {
  it('returns null for a plain string detail', () => {
    expect(apiErrorCode(refusal('Cannot move a task from A to B.'))).toBeNull()
  })

  it('reads the code out of an object-shaped detail', () => {
    const detail = {
      code: 'project_identity_conflict',
      message: 'This folder is already bound to a different AgentWeave database.',
    }
    expect(apiErrorCode(refusal(detail))).toBe('project_identity_conflict')
  })

  it('returns null for a Pydantic validation-error array', () => {
    const detail = [{ type: 'value_error', loc: ['body', 'path'], msg: 'Value error, required' }]
    expect(apiErrorCode(refusal(detail))).toBeNull()
  })

  it('returns null when the object detail carries no code', () => {
    expect(apiErrorCode(refusal({ message: 'no code here' }))).toBeNull()
  })

  it('returns null when the code is not a string', () => {
    expect(apiErrorCode(refusal({ code: 42 }))).toBeNull()
  })

  it('returns null for unparseable error text', () => {
    expect(apiErrorCode(new ApiError(500, 'Internal Server Error'))).toBeNull()
  })

  it('returns null for a non-ApiError value', () => {
    expect(apiErrorCode(new Error('network down'))).toBeNull()
  })

  it('returns null when there is no error at all', () => {
    expect(apiErrorCode(null)).toBeNull()
  })
})
