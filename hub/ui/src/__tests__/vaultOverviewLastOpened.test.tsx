import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { VaultEntry } from '@/api/vault'
import { VaultOverview } from '@/components/vault/VaultOverview'

/** VPTSW-6: the "What profiles open" row said "last now ago" for a source opened under a minute
 *  ago, and "last Oct 16 ago" for one opened months ago. It reads the long form now. */

const NOW = new Date('2026-11-24T00:31:08.000Z')

function source(id: string, name: string, lastFetchedAt: string): VaultEntry {
  return {
    id, name, type: 'note', kind: 'source', visibility: 'tracked', created_at: '2026-10-09T15:01:00.000000Z',
    holder: null, available: true, opening: 'Opening line.', fetches: 1, last_fetched_at: lastFetchedAt,
    readers: [{ agent: 'Developer' }],
  } as unknown as VaultEntry
}

function renderOverview(entries: VaultEntry[]) {
  const noop = () => {}
  render(
    <VaultOverview
      entries={entries}
      uses={{ state: 'ready', uses: [] }}
      contradictions={[]}
      reports={[]}
      onOpen={noop}
      onShowKind={noop}
      onShowFacts={noop}
      onShowReview={noop}
      now={NOW}
    />,
  )
  return screen.getByRole('region', { name: 'What profiles open' })
}

describe('What profiles open: when a source was last opened', () => {
  it('says "last opened just now" for a source opened at this moment', () => {
    const section = renderOverview([source('src-aaaaaaaaaaaa', 'Kickoff', NOW.toISOString())])
    const row = within(section).getByRole('button', { name: /Kickoff/ })
    expect(row).toHaveTextContent('last opened just now')
    expect(row).not.toHaveTextContent(/now ago/)
  })

  it('says "last opened 3 days ago" for one opened three days back', () => {
    const section = renderOverview([source('src-aaaaaaaaaaaa', 'Kickoff', '2026-11-21T00:31:08.000Z')])
    expect(within(section).getByRole('button', { name: /Kickoff/ })).toHaveTextContent('last opened 3 days ago')
  })

  it('names the day, without "ago", for one opened months back', () => {
    const section = renderOverview([source('src-aaaaaaaaaaaa', 'Kickoff', '2026-08-01T12:00:00.000Z')])
    const row = within(section).getByRole('button', { name: /Kickoff/ })
    expect(row).toHaveTextContent('last opened Aug 1')
    expect(row).not.toHaveTextContent(/ago/)
  })
})
