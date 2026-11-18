import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MarkdownMessage } from '@/components/agents/MarkdownMessage'
import { formatSpecReference } from '@/lib/specReference'
import { specTabId, usePanelTabsStore } from '@/store/panelTabsStore'
import { useConfigStore } from '@/store/configStore'

// The documents in the order the documents route returns them (insertion order, oldest first).
const documents = vi.hoisted(() => ({
  list: [
    { id: 'spdoc-000000000001', title: 'Other spec', path: 'spec/changes/o/spec.json', updated_at: '2026-11-10T10:00:00+00:00' },
    { id: 'spdoc-000000000002', title: 'Renamed title', path: 'spec/changes/r/spec.json', updated_at: '2026-11-18T10:00:00+00:00' },
  ] as { id: string; title: string; path: string; updated_at: string }[],
  loaded: true,
}))

vi.mock('@/api/spec', () => ({
  useSpecDocuments: () => ({ data: documents.loaded ? { documents: documents.list } : undefined }),
}))

const live = formatSpecReference({ id: 'spdoc-000000000002', title: 'Old title' })
const gone = formatSpecReference({ id: 'spdoc-0000000000ff', title: 'Vanished spec' })

beforeEach(() => {
  documents.loaded = true
  useConfigStore.setState({ selectedProjectId: 'proj-1' })
  usePanelTabsStore.setState({ projects: {} } as never)
})

describe('a spec reference in the operator’s sent message', () => {
  it('shows the current title, keeps the send-time title as the tooltip, and opens the spec', () => {
    render(<MarkdownMessage specReferences content={`The spec ${live} has issues`} />)
    const box = screen.getByRole('button', { name: 'Open spec Renamed title' })
    expect(box).toHaveTextContent('Renamed title')
    expect(box).toHaveAttribute('title', 'Old title')
    fireEvent.click(box)
    expect(usePanelTabsStore.getState().projects['proj-1']?.activeTabId).toBe(specTabId('spdoc-000000000002'))
  })

  it('shows a missing document muted, marked no longer available, and opens nothing', () => {
    render(<MarkdownMessage specReferences content={`see ${gone}`} />)
    const box = screen.getByTestId('timeline-spec-box')
    expect(box.tagName).not.toBe('BUTTON')
    expect(box).toHaveAttribute('data-state', 'missing')
    expect(box).toHaveTextContent('Vanished spec')
    expect(box).toHaveTextContent('no longer available')
    fireEvent.click(box)
    expect(usePanelTabsStore.getState().projects['proj-1']).toBeUndefined()
  })

  it('does not call a document missing before the list has loaded', () => {
    documents.loaded = false
    render(<MarkdownMessage specReferences content={gone} />)
    expect(screen.getByTestId('timeline-spec-box')).toHaveAttribute('data-state', 'current')
  })

  it('leaves the same text a plain link when the message is not the operator’s', () => {
    render(<MarkdownMessage content={live} />)
    expect(screen.queryByTestId('timeline-spec-box')).toBeNull()
  })
})
