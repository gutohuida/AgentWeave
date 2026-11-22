import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import { NewConversationIntro } from '@/components/conversation/NewConversationIntro'
import { ProfilesIndex } from '@/components/profiles/ProfilesIndex'
import type { ProfileListItem } from '@/components/profiles/profilesModel'
import { TAB_LABELS, PROJECT_TABS } from '@/lib/navigation'

afterEach(cleanup)

const profile = (name: string, archived = false): ProfileListItem => ({
  name,
  colorIndex: 0,
  charterName: null,
  provider: 'claude',
  providerLabel: 'Claude Code',
  model: 'Sonnet 5.5',
  moreModels: 0,
  status: { kind: 'idle' },
  spendUsd: 1,
  lastActiveAt: null,
  archived,
})

const renderIndex = (items: ProfileListItem[], query = '') =>
  render(<ProfilesIndex items={items} query={query} onQueryChange={() => undefined} onOpen={() => undefined} onNewThread={() => undefined} onAdd={() => undefined} now={new Date()} />)

describe('the Profiles count', () => {
  it('counts only the profiles in play: an archived one has its own group', () => {
    renderIndex([profile('Builder'), profile('Scribe', true)])
    expect(screen.getByText(/working first, then A to Z/)).toHaveTextContent(/^1 profile · working first/)
  })

  it('counts every profile when none is archived', () => {
    renderIndex([profile('Builder'), profile('Checker')])
    expect(screen.getByText(/working first, then A to Z/)).toHaveTextContent(/^2 profiles · working first/)
  })

  it('counts a filter against the profiles in play', () => {
    renderIndex([profile('Builder'), profile('Checker'), profile('Scribe', true)], 'build')
    expect(screen.getByText(/working first, then A to Z/)).toHaveTextContent(/^1 of 2 profiles/)
  })
})

describe('what a new thread says it runs on', () => {
  const agent = { name: 'Builder', status: 'idle', message_count: 0, active_task_count: 0, color_index: 0 } as AgentSummary
  it('names the CLI only: the composer’s chips say the model, effort and permissions', () => {
    render(<NewConversationIntro agent={agent} runnerLabel="Claude Code" starters={[]} onPick={() => undefined} />)
    expect(screen.getByText('Runs on Claude Code')).toBeInTheDocument()
  })
})

describe('the top bar', () => {
  it('calls the thread tab Chapters, and keeps its id', () => {
    expect(TAB_LABELS.thread).toBe('Chapters')
    expect(PROJECT_TABS).toContain('thread')
  })
})
