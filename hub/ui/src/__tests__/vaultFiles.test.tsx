import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { VaultPage } from '@/components/vault/VaultPage'
import { useConfigStore } from '@/store/configStore'

/** `images-and-pdfs-are-vault-sources-too`, requirement wiki-inline (task images-pdfs-tab-impl). The
 *  routes are stubbed at `fetch`; the file route answers real `Response` bodies, so the blob the
 *  page shows is the one the hooks built from them. */

// Newest first, the order `GET /vault/map` returns. A text source has media_type text/plain.
const PDF = {
  id: 'src-pdfpdfpdfpdf', name: 'Refund policy', type: 'document', kind: 'source', media_type: 'application/pdf',
  visibility: 'tracked', created_at: '2026-10-12T10:02:00.000000Z', holder: null, available: true,
  opening: 'Page 1. Refunds up to 450 euros need no manager approval.',
}
const IMAGE = {
  id: 'src-imgimgimgimg', name: 'Shipping screenshot', type: 'example', kind: 'source', media_type: 'image/png',
  visibility: 'tracked', created_at: '2026-10-12T10:01:00.000000Z', holder: null, available: true,
  opening: 'Free shipping threshold: 75 euros',
}
const TEXT = {
  id: 'src-txttxttxttx', name: 'Acme kickoff', type: 'transcript', kind: 'source', media_type: 'text/plain',
  visibility: 'tracked', created_at: '2026-10-12T10:00:00.000000Z', holder: null, available: true,
  opening: 'Kickoff meeting with Acme Retail.',
}
const SETTINGS = {
  private_location: null,
  effective_private_location: 'C:/Users/me/.agentweave/hub/vaults/proj-a',
  default_visibility: 'tracked',
}

type Routed = { status: number; body: unknown; type?: string }
type Route = (url: string, init?: RequestInit) => Routed | undefined
let vault: Route
const calls: Array<{ url: string; method: string; init?: RequestInit }> = []

// A file answers its bytes with their type. Not a jsdom Blob: it has no stream(), and Node 20's
// Response refuses one (CI ui-test, run 38228757844) where Node 24 stringifies it.
function respond({ status, body, type }: Routed) {
  if (type) return Promise.resolve(new Response(body as string, { status, headers: { 'Content-Type': type } }))
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function page(entry: object, content: string | null, note: string | null = null): Routed {
  return { status: 200, body: { ...entry, content, next_offset: null, note } }
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  calls.length = 0
  useConfigStore.setState({ apiKey: 'aw_live_test', hubUrl: 'http://hub', isConfigured: true, selectedProjectId: 'proj-a' })
  vault = (url) => {
    if (url.endsWith('/vault/map')) return { status: 200, body: { entries: [PDF, IMAGE, TEXT] } }
    if (url.endsWith('/vault/settings')) return { status: 200, body: SETTINGS }
    if (url.includes('/vault/entries/src-pdfpdfpdfpdf')) return page(PDF, 'Page 1\nRefunds up to 450 euros need no manager approval.\n')
    if (url.includes('/vault/entries/src-imgimgimgimg')) return page(IMAGE, 'Free shipping threshold: 75 euros\n')
    if (url.includes('/vault/entries/src-txttxttxttx')) return page(TEXT, 'Kickoff meeting with Acme Retail.\n')
    if (url.endsWith('/vault/sources/src-pdfpdfpdfpdf/file')) {
      return { status: 200, body: '%PDF-1.4', type: 'application/pdf' }
    }
    if (url.endsWith('/vault/sources/src-imgimgimgimg/file')) {
      return { status: 200, body: '\x89PNG', type: 'image/png' }
    }
    return undefined
  }
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? 'GET', init })
    return respond(vault(url, init) ?? { status: 404, body: { detail: 'Not Found' } })
  }))
  let made = 0
  // jsdom has no object URLs.
  Object.assign(URL, {
    createObjectURL: vi.fn(() => `blob:http://hub/file-${++made}`),
    revokeObjectURL: vi.fn(),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  Reflect.deleteProperty(URL, 'createObjectURL')
  Reflect.deleteProperty(URL, 'revokeObjectURL')
})

describe('the Vault tab, image and PDF sources', () => {
  it('marks image and PDF entries in the list and leaves a text entry unmarked', async () => {
    render(<VaultPage />, { wrapper })
    const pdf = await screen.findByTestId('vault-entry-src-pdfpdfpdfpdf')
    expect(pdf).toHaveTextContent('PDF')
    expect(screen.getByTestId('vault-entry-src-imgimgimgimg')).toHaveTextContent('image')
    const text = screen.getByTestId('vault-entry-src-txttxttxttx')
    expect(text).not.toHaveTextContent('PDF')
    expect(text).not.toHaveTextContent('image')
  })

  it('does not say a tracked file with no text yet is held on another machine (F591)', async () => {
    const unread = { ...PDF, available: false, opening: null }
    const heldElsewhere = { ...TEXT, id: 'src-privprivpriv', visibility: 'private', holder: 'colleague-pc', available: false, opening: null }
    const base = vault
    vault = (url, init) =>
      url.endsWith('/vault/map') ? { status: 200, body: { entries: [unread, heldElsewhere] } } : base(url, init)
    render(<VaultPage />, { wrapper })
    const row = await screen.findByTestId('vault-entry-src-pdfpdfpdfpdf')
    expect(row).not.toHaveTextContent('Held on')
    expect(row).toHaveTextContent('No text yet')
    // A private entry whose text is on another machine still says so.
    expect(screen.getByTestId('vault-entry-src-privprivpriv')).toHaveTextContent('Held on colleague-pc')
  })

  it('offers Distil and the preview for a tracked file with no text yet (F616)', async () => {
    const unread = { ...PDF, available: false, opening: null }
    const base = vault
    vault = (url, init) =>
      url.endsWith('/vault/map')
        ? { status: 200, body: { entries: [unread] } }
        : url.includes('/vault/entries/src-pdfpdfpdfpdf')
          ? page(unread, null, 'This PDF has not been read yet.')
          : base(url, init)
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-pdfpdfpdfpdf'))
    expect(await screen.findByTestId('vault-distil')).toBeEnabled()
    expect(await screen.findByTestId('vault-file-pdf')).toBeInTheDocument()
  })

  it('shows a PDF in an embedded viewer from a blob URL, above its transcription', async () => {
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-pdfpdfpdfpdf'))
    const viewer = await screen.findByTestId('vault-file-pdf')
    expect(viewer.getAttribute('src') ?? viewer.getAttribute('data')).toMatch(/^blob:/)
    expect(screen.queryByTestId('vault-file-image')).toBeNull()
    const text = await screen.findByTestId('vault-entry-text')
    expect(text).toHaveTextContent('Refunds up to 450 euros')
    // Above: the viewer comes first in the document.
    expect(viewer.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // It was fetched with the key, from the file route.
    const fetched = calls.find((call) => call.url.endsWith('/vault/sources/src-pdfpdfpdfpdf/file'))
    expect(fetched?.url).toBe('http://hub/api/v1/projects/proj-a/vault/sources/src-pdfpdfpdfpdf/file')
    expect((fetched?.init?.headers as Record<string, string>).Authorization).toBe('Bearer aw_live_test')
  })

  it('shows an image as an img from a blob URL', async () => {
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-imgimgimgimg'))
    const image = await screen.findByTestId('vault-file-image')
    expect(image.tagName).toBe('IMG')
    expect(image.getAttribute('src')).toMatch(/^blob:/)
    expect(screen.queryByTestId('vault-file-pdf')).toBeNull()
  })

  it('asks for no file when the source is text', async () => {
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-txttxttxttx'))
    await screen.findByTestId('vault-entry-text')
    expect(screen.queryByTestId('vault-file-pdf')).toBeNull()
    expect(screen.queryByTestId('vault-file-image')).toBeNull()
    expect(calls.some((call) => call.url.endsWith('/file'))).toBe(false)
  })

  it('shows the transcription alone, with no error, when the file route answers 404', async () => {
    const routed = vault
    vault = (url, init) =>
      url.endsWith('/vault/sources/src-pdfpdfpdfpdf/file') ? { status: 404, body: { detail: 'Not Found' } } : routed(url, init)
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-pdfpdfpdfpdf'))
    expect(await screen.findByTestId('vault-entry-text')).toHaveTextContent('Refunds up to 450 euros')
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/file'))).toBe(true))
    expect(screen.queryByTestId('vault-file-pdf')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows the not-read-yet note in place of the transcription, with the file above it', async () => {
    const routed = vault
    vault = (url, init) =>
      url.includes('/vault/entries/src-imgimgimgimg')
        ? page(IMAGE, null, 'This image has not been read yet. Its text appears once the manager has transcribed it.')
        : routed(url, init)
    render(<VaultPage />, { wrapper })
    fireEvent.click(await screen.findByTestId('vault-entry-src-imgimgimgimg'))
    expect(await screen.findByText(/has not been read yet/)).toBeInTheDocument()
    expect(await screen.findByTestId('vault-file-image')).toBeInTheDocument()
    expect(screen.queryByTestId('vault-entry-text')).toBeNull()
  })

  it('sends a chosen PDF as the raw body to /vault/files with its fields in the query', async () => {
    const routed = vault
    vault = (url, init) =>
      url.includes('/vault/files') && init?.method === 'POST'
        ? { status: 201, body: { ...PDF, id: 'src-newnewnewnew', name: 'Contract' } }
        : routed(url, init)
    render(<VaultPage />, { wrapper })
    await screen.findByTestId('vault-entry-src-pdfpdfpdfpdf')
    fireEvent.click(screen.getByTestId('vault-upload-open'))
    const file = new File(['%PDF-1.4 body'], 'Contract.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByTestId('vault-upload-file'), { target: { files: [file] } })
    expect(await screen.findByTestId('vault-upload-name')).toHaveValue('Contract')
    expect(screen.getByTestId('vault-upload-type')).toHaveValue('document')
    fireEvent.change(screen.getByTestId('vault-upload-dated'), { target: { value: '2026-10-01' } })
    fireEvent.click(screen.getByTestId('vault-upload-submit'))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    const sent = calls.find((call) => call.method === 'POST')!
    expect(sent.url).toBe(
      'http://hub/api/v1/projects/proj-a/vault/files?name=Contract&type=document&visibility=tracked&dated=2026-10-01',
    )
    expect(sent.init?.body).toBe(file)
    expect((sent.init?.headers as Record<string, string>)['Content-Type']).toBe('application/pdf')
    expect((sent.init?.headers as Record<string, string>).Authorization).toBe('Bearer aw_live_test')
  })

  it('reads a chosen text file into the text box as before, and sends it to /vault/sources', async () => {
    render(<VaultPage />, { wrapper })
    await screen.findByTestId('vault-entry-src-pdfpdfpdfpdf')
    fireEvent.click(screen.getByTestId('vault-upload-open'))
    const file = new File(['Dana: 450.'], 'notes.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByTestId('vault-upload-file'), { target: { files: [file] } })
    await waitFor(() => expect(screen.getByTestId('vault-upload-content')).toHaveValue('Dana: 450.'))
    expect(screen.getByTestId('vault-upload-type')).toHaveValue('transcript')
  })

  it("shows the Hub's reason when it refuses the file", async () => {
    const routed = vault
    vault = (url, init) =>
      url.includes('/vault/files') && init?.method === 'POST'
        ? { status: 413, body: { detail: 'A file source is at most 10 MiB.' } }
        : routed(url, init)
    render(<VaultPage />, { wrapper })
    await screen.findByTestId('vault-entry-src-pdfpdfpdfpdf')
    fireEvent.click(screen.getByTestId('vault-upload-open'))
    fireEvent.change(screen.getByTestId('vault-upload-file'), {
      target: { files: [new File(['%PDF-1.4'], 'Big.pdf', { type: 'application/pdf' })] },
    })
    fireEvent.click(await screen.findByTestId('vault-upload-submit'))
    expect(await screen.findByRole('alert')).toHaveTextContent('at most 10 MiB')
  })
})
