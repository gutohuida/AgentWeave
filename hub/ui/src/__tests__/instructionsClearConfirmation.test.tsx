import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useConfigStore } from '@/store/configStore'

// Partial mock, exactly as the sibling F271 file does it: `readableApiError` stays REAL, and the
// two transport helpers are replaced because `putJson` is this change's instrument. Every guard
// below is asserted as "no PUT was issued" and against a stand-in stored row — never as a
// `disabled` attribute on Save. A markup assertion passes against a page that shows the dialog
// *and* fires the write, which is the one failure this change exists to prevent.
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, getJson: vi.fn(), putJson: vi.fn() }
})

import { ApiError, getJson, putJson } from '@/api/client'
import { InstructionsPage } from '@/components/instructions/InstructionsPage'

const ALPHA = 'proj-alpha'
const PROJECT_NAME = 'Alpha'
const pathFor = (projectId: string) => `/api/v1/projects/${projectId}/project/instructions`
const KEY = ['project', ALPHA, 'instructions']
/** Two lines and a trailing newline — the shape a text editor actually leaves behind. */
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

/** The loaded editor, with its stored text already in it. */
async function loadedEditor() {
  const box = await screen.findByRole('textbox')
  await waitFor(() => expect(box).toHaveValue(stored[ALPHA]))
  return box
}

const saveButton = () => screen.getByRole('button', { name: /^save$/i })
const confirmButton = () => screen.getByRole('button', { name: /clear instructions/i })

describe('clearing stored instructions asks first, and asking writes nothing', () => {
  beforeEach(() => {
    // Call history first: these are module-factory `vi.fn()`s, which `restoreAllMocks` does not
    // empty. Without this, "no PUT was issued" would be an assertion about the preceding test.
    vi.clearAllMocks()
    stored = { [ALPHA]: STORED }
    vi.mocked(getJson).mockImplementation((async (path: string) => {
      // The real `useProjects` is left in place rather than stubbed: naming the project in the
      // dialog is task 1.2, and a stubbed hook would assert the stub instead of the lookup.
      if (path === '/api/v1/projects') return [{ id: ALPHA, name: PROJECT_NAME }]
      const projectId = path.split('/')[4]
      return { content: stored[projectId] ?? '' }
    }) as unknown as typeof getJson)
    vi.mocked(putJson).mockImplementation((async (path: string, body?: unknown) => {
      const projectId = path.split('/')[4]
      const content = (body as { content: string }).content
      stored[projectId] = content
      return { content }
    }) as unknown as typeof putJson)
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: ALPHA,
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  // 4.1 — the assertion that carries the requirement. The dialog being on screen is half of it;
  // the write not having happened is the half that matters.
  it('asks, and issues no PUT, when an emptied editor is saved over stored instructions', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await loadedEditor()

    await user.clear(box)
    await user.click(saveButton())

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    // What it states, per 1.2: which project, how much is lost, and that nothing keeps a copy.
    expect(dialog).toHaveTextContent(`Clear the instructions for “${PROJECT_NAME}”?`)
    expect(dialog).toHaveTextContent(/replaces 2 lines of stored instructions with nothing/)
    expect(dialog).toHaveTextContent(/AgentWeave keeps no copy/)
    expect(dialog).toHaveTextContent(/no history and no undo/)

    expect(putJson).not.toHaveBeenCalled()
    expect(stored[ALPHA]).toBe(STORED)
  })

  // 4.2
  it('writes nothing on Cancel, and leaves the editor as the operator typed it', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await loadedEditor()

    await user.clear(box)
    await user.click(saveButton())
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: /^cancel$/i }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(putJson).not.toHaveBeenCalled()
    expect(stored[ALPHA]).toBe(STORED)
    // Not restored under them: the operator emptied it deliberately (`design.md` D4).
    expect(screen.getByRole('textbox')).toHaveValue('')
  })

  // 4.3 — and the acknowledgement is a 2000 ms flash (`InstructionsPage.tsx:46-52`), so this
  // asserts inside that window. An observer that arrives late reports a correct page as broken.
  it('writes exactly one empty PUT on Confirm and acknowledges it like any other save', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await loadedEditor()

    await user.clear(box)
    await user.click(saveButton())
    await screen.findByRole('dialog')
    await user.click(confirmButton())

    await waitFor(() => expect(putJson).toHaveBeenCalledTimes(1))
    expect(putJson).toHaveBeenCalledWith(pathFor(ALPHA), { content: '' })
    expect(stored[ALPHA]).toBe('')
    expect(await screen.findByRole('status')).toHaveTextContent(/saved/i)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  // 4.4 — the case `content === ''` would miss, and the one the trim exists for.
  it('asks when the editor holds only whitespace over stored instructions', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await loadedEditor()

    await user.clear(box)
    await user.type(box, '  {enter} ')
    // Asserted, not assumed: the rest of this test is about these four characters.
    expect(box).toHaveValue('  \n ')
    await user.click(saveButton())

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(putJson).not.toHaveBeenCalled()
    expect(stored[ALPHA]).toBe(STORED)
  })

  // 4.4, second half — the predicate trims only to DECIDE. What is written is byte-for-byte what
  // was typed, as it is for every other save.
  it('writes the whitespace back untrimmed once it is confirmed', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await loadedEditor()

    await user.clear(box)
    await user.type(box, '  {enter} ')
    await user.click(saveButton())
    await screen.findByRole('dialog')
    await user.click(confirmButton())

    await waitFor(() => expect(putJson).toHaveBeenCalledTimes(1))
    expect(putJson).toHaveBeenCalledWith(pathFor(ALPHA), { content: '  \n ' })
    expect(stored[ALPHA]).toBe('  \n ')
  })

  // 4.5 — unchanged behaviour, and therefore expected to pass either side of the gate. That is
  // what makes it evidence the change took nothing away.
  it('does not ask for an ordinary non-empty save', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await loadedEditor()

    await user.clear(box)
    await user.type(box, 'deliberately rewritten')
    await user.click(saveButton())

    await waitFor(() => expect(putJson).toHaveBeenCalledTimes(1))
    expect(putJson).toHaveBeenCalledWith(pathFor(ALPHA), { content: 'deliberately rewritten' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  // 4.6 — the confirmation is about loss, and there is none.
  it('does not ask when the stored instructions are already empty', async () => {
    const user = userEvent.setup()
    stored = { [ALPHA]: '' }
    renderPage()
    const box = await loadedEditor()
    expect(box).toHaveValue('')

    await user.click(saveButton())

    await waitFor(() => expect(putJson).toHaveBeenCalledTimes(1))
    expect(putJson).toHaveBeenCalledWith(pathFor(ALPHA), { content: '' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  // 4.6, second half — the stored side is trimmed too. This is the assertion a predicate testing
  // `data.content !== ''` would fail, and until this change that half lived only in prose.
  it('does not ask when the stored instructions are only whitespace', async () => {
    const user = userEvent.setup()
    stored = { [ALPHA]: '   \n  \n' }
    renderPage()
    const box = await loadedEditor()

    await user.clear(box)
    await user.click(saveButton())

    await waitFor(() => expect(putJson).toHaveBeenCalledTimes(1))
    expect(putJson).toHaveBeenCalledWith(pathFor(ALPHA), { content: '' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  // 4.7 — the baseline is the last successful `data`, which is what ties this change to F271's
  // `data`-first ordering. An implementation deriving it from a live read would fail here.
  it('still asks after a failing background refetch, measured against what was read', async () => {
    const user = userEvent.setup()
    const client = renderPage()
    const box = await loadedEditor()

    vi.mocked(getJson).mockRejectedValue(apiError(503, 'the Hub went away mid-edit'))
    await act(async () => {
      await client.refetchQueries({ queryKey: KEY })
    })
    // The scenario has to be shown to have happened, or every assertion below is true for the
    // wrong reason.
    expect(client.getQueryState(KEY)?.status).toBe('error')
    expect(client.getQueryData(KEY)).toEqual({ content: STORED })

    await user.clear(box)
    await user.click(saveButton())

    const dialog = await screen.findByRole('dialog')
    // Measured against the content that was read, not against nothing: the count proves which.
    expect(dialog).toHaveTextContent(/replaces 2 lines of stored instructions with nothing/)
    expect(putJson).not.toHaveBeenCalled()
    expect(stored[ALPHA]).toBe(STORED)
  })

  // 4.8
  it('closes on Escape and writes nothing', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await loadedEditor()

    await user.clear(box)
    await user.click(saveButton())
    await screen.findByRole('dialog')
    await user.keyboard('{Escape}')

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(putJson).not.toHaveBeenCalled()
    expect(stored[ALPHA]).toBe(STORED)
  })
})

/**
 * The dialog's own arithmetic and its dismissal target, driven through the page rather than by
 * mounting the component directly — the count is only meaningful as a statement about the text
 * that was actually read.
 *
 * Deliberately absent: `useDialogFocus`'s Tab cycle and its focus restoration. Those are §5.4,
 * assigned to the browser drive because jsdom cannot prove them, and a green jsdom assertion about
 * focus would be exactly the kind of evidence this change exists to stop trusting.
 */
describe('what the confirmation states about the text it would discard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    stored = { [ALPHA]: STORED }
    vi.mocked(getJson).mockImplementation((async (path: string) => {
      if (path === '/api/v1/projects') return [{ id: ALPHA, name: PROJECT_NAME }]
      const projectId = path.split('/')[4]
      return { content: stored[projectId] ?? '' }
    }) as unknown as typeof getJson)
    vi.mocked(putJson).mockImplementation((async () => ({ content: '' })) as unknown as typeof putJson)
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: ALPHA,
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  async function openDialog() {
    const user = userEvent.setup()
    renderPage()
    const box = await loadedEditor()
    await user.clear(box)
    await user.click(saveButton())
    return { user, dialog: await screen.findByRole('dialog') }
  }

  it('says "1 line" in the singular for a one-line file', async () => {
    stored = { [ALPHA]: 'Never force-push.' }
    const { dialog } = await openDialog()
    expect(dialog).toHaveTextContent(/replaces 1 line of stored instructions/)
  })

  // A file that ends in a newline is not one line longer than the same file without it.
  it('does not count a trailing newline as an extra line', async () => {
    stored = { [ALPHA]: 'Never force-push.\n' }
    const { dialog } = await openDialog()
    expect(dialog).toHaveTextContent(/replaces 1 line of stored instructions/)
  })

  it('counts three lines as three, trailing blank lines and all', async () => {
    stored = { [ALPHA]: 'one\ntwo\nthree\n\n\n' }
    const { dialog } = await openDialog()
    expect(dialog).toHaveTextContent(/replaces 3 lines of stored instructions/)
  })

  // The scrim click is guarded on its target so a select-drag that starts on the heading and ends
  // outside the panel does not dismiss the dialog under the operator.
  it('stays open when the click lands inside the panel', async () => {
    const { user, dialog } = await openDialog()

    await user.click(screen.getByText(/Clear the instructions for/))

    expect(dialog).toBeInTheDocument()
    expect(putJson).not.toHaveBeenCalled()
  })

  it('cancels when the click lands on the scrim itself', async () => {
    const { user, dialog } = await openDialog()

    await user.click(dialog)

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(putJson).not.toHaveBeenCalled()
  })
})
