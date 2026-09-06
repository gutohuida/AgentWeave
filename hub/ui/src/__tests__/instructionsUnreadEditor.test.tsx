import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { UserEvent } from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

// Partial mock: `readableApiError` stays REAL. The failure blocks under test render the sentence it
// derives from an `ApiError` body, so stubbing it would turn every "states why" assertion into a
// test of the stub. Only the two transport helpers are replaced, and `putJson` is the instrument
// that carries this change's requirement — the guard asserted here is "no PUT is issued", never
// "the button has a `disabled` attribute", because a markup assertion passes against a page that
// renders the error *and* the textarea.
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, getJson: vi.fn(), putJson: vi.fn() }
})

import { ApiError, getJson, putJson } from '@/api/client'
import { InstructionsPage } from '@/components/instructions/InstructionsPage'

const ALPHA = 'proj-alpha'
const BETA = 'proj-beta'
const pathFor = (projectId: string) => `/api/v1/projects/${projectId}/project/instructions`
const STORED = 'ALPHA PROJECT RULES\nNever force-push.\n'

/** A stand-in for the row the Hub stores, so a PUT is observable as a write and not only as a call. */
let stored: Record<string, string>

function apiError(status: number, detail: string) {
  return new ApiError(status, JSON.stringify({ detail }))
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <InstructionsPage />
    </QueryClientProvider>
  )
  return client
}

/**
 * Do everything the screen offers: type into every text box, then press every button.
 *
 * The requirement is about what an operator can *cause*, so the test may not pick out the control
 * it expects to be gone — it has to exercise whatever is actually there. Against the pre-change
 * page this finds the empty textarea and the live Save beside it; against the fixed page it finds
 * Retry, or nothing at all.
 */
async function interactWithEverything(user: UserEvent) {
  for (const box of screen.queryAllByRole('textbox')) {
    await user.clear(box)
    await user.type(box, 'typed into an editor that never read anything')
  }
  for (const button of screen.queryAllByRole('button')) {
    await user.click(button)
  }
}

describe('an unread instructions editor cannot overwrite what it never read (F271)', () => {
  beforeEach(() => {
    // Call history first: these two are module-factory `vi.fn()`s, which the shared setup's
    // `restoreAllMocks` does not empty — without this, "no PUT was issued" would silently be an
    // assertion about every test that ran before this one.
    vi.clearAllMocks()
    stored = { [ALPHA]: STORED, [BETA]: 'BETA RULES\n' }
    vi.mocked(getJson).mockImplementation(async (path: string) => {
      const projectId = path.split('/')[4]
      return { content: stored[projectId] ?? '' }
    })
    vi.mocked(putJson).mockImplementation(async (path: string, body?: unknown) => {
      const projectId = path.split('/')[4]
      const content = (body as { content: string }).content
      stored[projectId] = content
      return { content }
    })
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: ALPHA,
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  // 2.1
  it('renders no editor and an announced failure when the read fails', async () => {
    vi.mocked(getJson).mockRejectedValue(apiError(503, 'instructions store unavailable'))
    renderPage()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/could not be loaded/i)
    expect(alert).toHaveTextContent('instructions store unavailable')
    expect(alert).toHaveTextContent(/nothing stored has been changed/i)
    expect(screen.queryAllByRole('textbox')).toHaveLength(0)
  })

  // 2.2 — the assertion that carries the requirement.
  it('issues no PUT from any interaction after the read has failed', async () => {
    const user = userEvent.setup()
    vi.mocked(getJson).mockRejectedValue(apiError(503, 'instructions store unavailable'))
    const client = renderPage()
    // Wait on the query settling, NOT on the failure block appearing. Gating this on the alert
    // would make it a second copy of 2.1 — and against a page that renders no alert it would fail
    // for that reason instead of for the write it is here to catch.
    await waitFor(() =>
      expect(client.getQueryState(['project', ALPHA, 'instructions'])?.status).toBe('error')
    )

    await interactWithEverything(user)

    expect(putJson).not.toHaveBeenCalled()
    expect(stored[ALPHA]).toBe(STORED)
  })

  // 2.3 — R2: the in-flight route, which opens on every visit and needs no failure at all.
  it('issues no PUT from any interaction while the read is still in flight', async () => {
    const user = userEvent.setup()
    vi.mocked(getJson).mockImplementation(() => new Promise<{ content: string }>(() => {}))
    renderPage()
    // The skeleton is the observable proof this is the not-yet-answered state, not the failed one.
    expect(await screen.findByLabelText('Loading instructions')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()

    await interactWithEverything(user)

    expect(putJson).not.toHaveBeenCalled()
    expect(stored[ALPHA]).toBe(STORED)
  })

  // 2.4
  it('retries the read and presents the pre-filled editor once it succeeds', async () => {
    const user = userEvent.setup()
    vi.mocked(getJson).mockRejectedValueOnce(apiError(503, 'instructions store unavailable'))
    renderPage()
    await screen.findByRole('alert')

    await user.click(screen.getByRole('button', { name: /retry/i }))

    const box = await screen.findByRole('textbox')
    expect(box).toHaveValue(STORED)
    expect(getJson).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  // 2.5 — the `data`-first ordering, in the other direction: a background refetch failure must not
  // take a loaded editor away from an operator mid-edit.
  it('keeps a loaded editor and its edits when a background refetch fails', async () => {
    const user = userEvent.setup()
    const client = renderPage()
    const box = await screen.findByRole('textbox')
    expect(box).toHaveValue(STORED)

    await user.clear(box)
    await user.type(box, 'half-finished edit')

    vi.mocked(getJson).mockRejectedValue(apiError(503, 'the Hub went away mid-edit'))
    await act(async () => {
      await client.refetchQueries({ queryKey: ['project', ALPHA, 'instructions'] })
    })
    // The scenario has to be shown to have happened: without this, a refetch that quietly did not
    // fail would leave every assertion below true for the wrong reason.
    expect(client.getQueryState(['project', ALPHA, 'instructions'])?.status).toBe('error')
    expect(client.getQueryData(['project', ALPHA, 'instructions'])).toEqual({ content: STORED })

    // Keep typing. This is not decoration: React Query only notifies on the result fields a render
    // actually read, and a `data`-first branch never reads `isError` while data is present — so the
    // failed refetch alone re-renders nothing, and an ordering that *would* discard the editor
    // stays invisible until something else re-renders. Typing is what an operator is doing anyway.
    await user.type(screen.getByRole('textbox'), ', continued')

    expect(screen.getByRole('textbox')).toHaveValue('half-finished edit, continued')
    expect(screen.queryByText(/could not be loaded/i)).toBeNull()
    expect(screen.getByRole('button', { name: /^save$/i })).toBeEnabled()
  })

  // 2.6 — closed by CONSTRUCTION rather than by a guard: `data` is per query key
  // (`['project', projectId, 'instructions']`), so the newly selected project's key has no data of
  // its own and the editor branch cannot be reached holding the previous project's text.
  it('shows no editor holding the previous project content when the new project fails to load', async () => {
    const client = renderPage()
    expect(await screen.findByRole('textbox')).toHaveValue(STORED)

    vi.mocked(getJson).mockRejectedValue(apiError(503, 'beta is unreadable'))
    act(() => {
      useConfigStore.setState({ selectedProjectId: BETA })
    })

    // Again settle-then-assert, so the load-bearing claim — no editor carrying alpha's text on
    // beta's page — is what fails if it is untrue, rather than the absence of an alert.
    await waitFor(() =>
      expect(client.getQueryState(['project', BETA, 'instructions'])?.status).toBe('error')
    )
    expect(screen.queryAllByRole('textbox')).toHaveLength(0)
    expect(screen.queryByDisplayValue(STORED)).toBeNull()
    expect(client.getQueryData(['project', BETA, 'instructions'])).toBeUndefined()
    expect(await screen.findByRole('alert')).toHaveTextContent('beta is unreadable')
  })

  // 2.7 — the success path is unchanged. Expected to pass against the pre-change page as well; that
  // is exactly what makes it evidence the fix took nothing away.
  it('still loads, edits, saves and confirms on the success path', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await screen.findByRole('textbox')
    expect(box).toHaveValue(STORED)

    await user.clear(box)
    await user.type(box, 'deliberately rewritten')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    await waitFor(() => expect(putJson).toHaveBeenCalledTimes(1))
    expect(putJson).toHaveBeenCalledWith(pathFor(ALPHA), { content: 'deliberately rewritten' })
    expect(stored[ALPHA]).toBe('deliberately rewritten')
    expect(await screen.findByRole('status')).toHaveTextContent(/saved/i)
  })

  // 2.8 — R3: a shipped requirement (*Saving reports its outcome*) the page breached before this
  // change, not a new one.
  it('states the failure in the section when a save is rejected', async () => {
    const user = userEvent.setup()
    vi.mocked(putJson).mockRejectedValue(apiError(500, 'instructions store is read-only'))
    renderPage()
    const box = await screen.findByRole('textbox')

    await user.clear(box)
    await user.type(box, 'this will be refused')
    await user.click(screen.getByRole('button', { name: /^save$/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/were not saved/i)
    expect(alert).toHaveTextContent('instructions store is read-only')
    expect(screen.getByRole('textbox')).toHaveValue('this will be refused')
    expect(screen.queryByRole('status')).toBeNull()
  })
})
