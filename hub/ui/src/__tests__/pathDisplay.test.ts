import { describe, expect, it } from 'vitest'
import { elidePathSegments } from '@/lib/pathDisplay'

describe('elidePathSegments', () => {
  it('elides the middle of a long Windows path, keeping the drive and the last three segments', () => {
    const segments = elidePathSegments('C:\\Users\\huida\\Documents\\projects\\AgentWeave\\testbed\\two-codex-agents\\workspace')
    expect(segments).toEqual(['C:\\', '…', 'testbed', 'two-codex-agents', 'workspace'])
  })

  it('elides the middle of a long POSIX path, keeping the root and the last three segments', () => {
    const segments = elidePathSegments('/home/huida/projects/agentweave/testbed/two-codex-agents/workspace')
    expect(segments).toEqual(['/home', '…', 'testbed', 'two-codex-agents', 'workspace'])
  })

  it('shows every segment of a short path without eliding', () => {
    expect(elidePathSegments('C:\\Users\\workspace')).toEqual(['C:\\', 'Users', 'workspace'])
    expect(elidePathSegments('/home/workspace')).toEqual(['/home', 'workspace'])
  })

  it('returns an empty list for an empty path', () => {
    expect(elidePathSegments('')).toEqual([])
  })
})
