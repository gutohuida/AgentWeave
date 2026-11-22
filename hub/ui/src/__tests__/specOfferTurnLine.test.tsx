import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import type { TimelineEntry } from '@/api/agentChat'
import type { SpecDocumentOffer } from '@/api/conversationSpec'
import { AgentTimeline, type TurnNote } from '@/components/agents/AgentTimeline'
import { SpecCreatedNote } from '@/components/conversation/SpecCreatedNote'

/** `starting-a-spec-from-a-thread-and-a-spec-page-that-agrees-with-itself`, FR-3 / FR-4 (F1208):
 *  a spec an agent created is offered by one line under the message of the turn that created it.
 *  The entries are in the order the chat route returns them (sorted by timestamp, oldest first,
 *  `agent_chat.py`), and the offers in the order `conversation_document.offers` returns them
 *  (oldest creation first). */

vi.mock('@/components/common/Icon', () => ({
  Icon: ({ name }: { name: string }) => <span data-testid="icon" data-name={name} />,
}))

const agent: AgentSummary = { name: 'Architect', status: 'idle', message_count: 0, active_task_count: 0, runner: 'claude' }

const at = (second: number) => `2026-11-22T10:00:${String(second).padStart(2, '0')}Z`
// Oldest first, as the route returns them.
const ENTRIES: TimelineEntry[] = [
  { id: 'o1', kind: 'operator_input', content: 'first question', timestamp: at(1), delivery_state: 'delivered', run_id: 'run-1' },
  { id: 'a1', kind: 'agent_output', content: 'first answer', timestamp: at(2), delivery_state: 'delivered', run_id: 'run-1' },
  { id: 'o2', kind: 'operator_input', content: 'second question', timestamp: at(3), delivery_state: 'delivered', run_id: 'run-2' },
  { id: 'a2', kind: 'agent_output', content: 'second answer', timestamp: at(4), delivery_state: 'delivered', run_id: 'run-2' },
]

// Oldest creation first, as the offers route returns them.
const OFFERS: SpecDocumentOffer[] = [
  { path: 'spec/changes/shout/spec.json', title: 'Add a shout flag', step: 'requirements', run_id: 'run-1', created_by: 'Architect', created_at: at(2) },
  { path: 'spec/changes/whisper/spec.json', title: 'Add a whisper flag', step: 'intake', run_id: 'run-2', created_by: 'Architect', created_at: at(4) },
]

function notes(offers: SpecDocumentOffer[]): TurnNote[] {
  return offers.map((offer) => ({
    key: offer.path,
    runId: offer.run_id ?? null,
    node: <SpecCreatedNote path={offer.path} title={offer.title} createdBy={offer.created_by} onOpen={() => {}} onDismiss={() => {}} />,
  }))
}

function renderTimeline(entries: TimelineEntry[], offers: SpecDocumentOffer[]) {
  return render(<AgentTimeline agent={agent} entries={entries} roster={[]} runs={{}} isRunning={false} turnNotes={notes(offers)} />)
}

const follows = (a: Node, b: Node) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)

function line(path: string) {
  const found = document.querySelector(`[data-testid=spec-created-note][data-path='${path}']`)
  expect(found, path).not.toBeNull()
  return found as HTMLElement
}

describe('the offer line sits under the turn that created the spec', () => {
  it('draws each line after its own turn and before the next', () => {
    renderTimeline(ENTRIES, OFFERS)
    const shout = line(OFFERS[0].path)
    const whisper = line(OFFERS[1].path)
    expect(follows(screen.getByText('first answer'), shout)).toBe(true)
    expect(follows(shout, screen.getByText('second question'))).toBe(true)
    expect(follows(screen.getByText('second answer'), whisper)).toBe(true)
    expect(screen.getAllByTestId('spec-created-note')).toHaveLength(2)
  })

  it('reads what happened, never the step or "Started"', () => {
    renderTimeline(ENTRIES, OFFERS)
    const shout = line(OFFERS[0].path)
    expect(shout.textContent).toContain('Architect created Add a shout flag')
    expect(shout.textContent).not.toMatch(/Started|Requirements|Intake/)
    expect(within(shout).getByRole('button', { name: /Open Add a shout flag in this thread/ })).toHaveTextContent('Open here')
    expect(within(shout).getByRole('button', { name: /Do not open Add a shout flag here/ })).toBeInTheDocument()
  })

  it('stays under its turn when a later turn arrives', () => {
    const later: TimelineEntry[] = [
      ...ENTRIES,
      { id: 'o3', kind: 'operator_input', content: 'third question', timestamp: at(5), delivery_state: 'delivered', run_id: 'run-3' },
      { id: 'a3', kind: 'agent_output', content: 'third answer', timestamp: at(6), delivery_state: 'delivered', run_id: 'run-3' },
    ]
    renderTimeline(later, OFFERS.slice(0, 1))
    const shout = line(OFFERS[0].path)
    expect(follows(shout, screen.getByText('second question'))).toBe(true)
    expect(follows(shout, screen.getByText('third answer'))).toBe(true)
  })

  it('puts a line whose run is not in the window after the last turn, still in the transcript', () => {
    renderTimeline(ENTRIES, [{ ...OFFERS[0], run_id: 'run-aged-out' }])
    const shout = line(OFFERS[0].path)
    expect(follows(screen.getByText('second answer'), shout)).toBe(true)
    expect(screen.getByTestId('timeline-unplaced-notes')).toContainElement(shout)
  })
})
