import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConversationSpecOffers } from '@/components/conversation/ConversationSpecOffers'
import { NextSliceOfferNotice } from '@/components/spec/NextSliceOfferNotice'
import { useAnswerSpecDocumentOffer, useConversationSpecDocuments } from '@/api/conversationSpec'

/** `every-spec-entry-point-leads-into-the-journey`, FR-7 / FR-8 / FR-9, and the Draft notice (FR-1):
 *  the notice for a change document an agent created in a conversation, answered against a Hub
 *  that records the answer, and Draft's link into the drafting conversation. */

vi.mock('@/store/configStore', () => ({
  useConfigStore: Object.assign(
    () => ({ isConfigured: true, selectedProjectId: 'proj-1' }),
    { getState: () => ({ isConfigured: true, selectedProjectId: 'proj-1' }) },
  ),
}))

// The Hub's side: offers derived per conversation, answers recorded and so surviving a reload.
const NEW = { path: 'spec/changes/new/spec.json', title: 'A new change', step: 'intake', created_by: 'claude', created_at: null }
let answered: Record<string, string>
let held: string | null
const calls: Array<{ method: string; url: string; body?: unknown }> = []

beforeEach(() => {
  cleanup()
  answered = {}
  held = null
  calls.length = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response
      const method = init?.method ?? 'GET'
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ method, url, body })
      if (url.includes('/agents')) return json([])
      if (url.endsWith('/spec-documents/answer')) {
        answered[body.path] = body.answer
        if (body.answer === 'open') held = body.path
        return json({ path: body.path, answer: body.answer, attached: held ? { path: held, title: 't', phase: 'exploring', step: 'intake' } : null })
      }
      if (url.endsWith('/spec-documents')) {
        return json({
          attached: held ? { path: held, title: 't', phase: 'exploring', step: 'intake' } : null,
          offers: [NEW].filter((o) => !answered[o.path] && o.path !== held),
        })
      }
      return json({})
    }),
  )
})

function Wired({ onOpen }: { onOpen?: (path: string) => void }) {
  const read = useConversationSpecDocuments('proj-1', 'conv-1')
  const answer = useAnswerSpecDocumentOffer('proj-1', 'conv-1')
  return (
    <ConversationSpecOffers
      offers={read.data?.offers ?? []}
      busy={answer.isPending}
      onAnswer={(path, a) => answer.mutate({ path, answer: a }, { onSuccess: () => (a === 'open' ? onOpen?.(path) : undefined) })}
    />
  )
}

const mount = (ui: React.ReactElement) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>)

describe('the notice for a document an agent created', () => {
  it('names the document with Open and Not now', async () => {
    mount(<Wired />)
    const offer = await screen.findByTestId('conversation-spec-offer')
    expect(offer.getAttribute('data-path')).toBe(NEW.path)
    expect(within(offer).getByText('A new change')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Open A new change' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Not now' })).toBeTruthy()
  })

  it('renders nothing with no offers, and says a failed read', () => {
    const { container } = render(<ConversationSpecOffers offers={[]} onAnswer={() => {}} />)
    expect(container.innerHTML).toBe('')
    cleanup()
    render(<ConversationSpecOffers offers={[]} onAnswer={() => {}} readError="the Hub did not answer." />)
    expect(screen.getByTestId('conversation-spec-offer-error').textContent).toContain('the Hub did not answer.')
  })

  it('Not now hides it, opens nothing, and stays gone after a reload', async () => {
    const onOpen = vi.fn()
    const first = mount(<Wired onOpen={onOpen} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Not now' }))
    await waitFor(() => expect(screen.queryByTestId('conversation-spec-offer')).toBeNull())
    expect(calls.find((c) => c.url.endsWith('/answer'))?.body).toEqual({ path: NEW.path, answer: 'not_now' })
    expect(onOpen).not.toHaveBeenCalled()
    expect(held).toBeNull()
    // A reload: nothing cached, the Hub's record is all there is.
    first.unmount()
    mount(<Wired onOpen={onOpen} />)
    await waitFor(() => expect(calls.filter((c) => c.url.endsWith('/spec-documents')).length).toBeGreaterThan(1))
    expect(screen.queryByTestId('conversation-spec-offer')).toBeNull()
    expect(held).toBeNull()
  })

  it('Open answers open, opens the document, and removes the notice', async () => {
    const onOpen = vi.fn()
    mount(<Wired onOpen={onOpen} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Open A new change' }))
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith(NEW.path))
    expect(held).toBe(NEW.path)
    await waitFor(() => expect(screen.queryByTestId('conversation-spec-offer')).toBeNull())
  })
})

describe('Draft from the spec page notice', () => {
  it('links the drafting conversation, opened with the slice document, once taken', async () => {
    vi.resetModules()
    const offers = {
      offers: [{
        document: 'spec/changes/one/spec.json', document_id: 'd1', title: 'One', roadmap: 'spec/changes/plan/spec.json',
        roadmap_title: 'Plan', approved_slice: { key: 's1' }, next_slice: { key: 's2', title: 'Two' }, agent: 'claude',
        conversation_id: null, requested: false, tasks: [],
      }],
    }
    ;(globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(async (url: string, init?: RequestInit) => {
      const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as unknown as Response
      if (url.endsWith('/next-slice-offers')) return json(offers.offers.length ? offers : { offers: [] })
      if (url.endsWith('/next-slice/take') && init?.method === 'POST') {
        offers.offers = []
        return json({ state: 'queued', agent: 'claude', conversation_id: 'conv-9', entry_id: 'e1', document: 'spec/changes/two/spec.json' })
      }
      return json([])
    })
    mount(<NextSliceOfferNotice path="spec/changes/one/spec.json" />)
    await userEvent.click(await screen.findByRole('button', { name: 'Draft' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Open the conversation' }))
    expect(window.location.pathname + window.location.search + window.location.hash).toContain('conv-9')
    expect(decodeURIComponent(window.location.href)).toContain('spec/changes/two/spec.json')
  })
})
