import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import { ApiError } from '@/api/client'
import type { ReindexResult, SpecListResponse } from '@/api/spec'
import { SpecDocumentBrowser } from '@/components/spec/SpecDocumentBrowser'
import { SpecCorpusStrip } from '@/components/spec/SpecCorpusStrip'
import { SpecPlaceUnder } from '@/components/spec/SpecPlaceUnder'
import { buildInventory } from '@/components/spec/specNavigation'

/* `the-corpus-is-indexed-arranged-and-adopted-from-the-app` (F206): reindex, adopt one, adopt all and
 * arrange had no caller in the app. Each mutation is mocked to answer what the route answers, in the
 * order the route builds it (`build_index` appends the home diagnostic before `index_home_required`). */

type Answer = { ok?: unknown; error?: unknown }

const state = vi.hoisted(() => ({
  calls: { reindex: [] as unknown[], adoptAll: 0, adopt: [] as unknown[], arrange: [] as unknown[] },
  answers: { reindex: [] as Answer[], adoptAll: [] as Answer[], adopt: [] as Answer[], arrange: [] as Answer[] },
}))

vi.mock('@/api/spec', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/api/spec')>()
  type Options = { onSuccess?: (value: unknown) => void; onError?: (error: unknown) => void }
  const hook = (name: 'reindex' | 'adoptAll' | 'adopt' | 'arrange') => () => ({
    isPending: false,
    mutate: (args: unknown, options?: Options) => {
      if (name === 'adoptAll') state.calls.adoptAll += 1
      else state.calls[name].push(args)
      const next = state.answers[name].shift()
      if (next?.error) options?.onError?.(next.error)
      else options?.onSuccess?.(next?.ok)
    },
  })
  return {
    ...real,
    useReindexSpec: hook('reindex'),
    useAdoptSpecCorpus: hook('adoptAll'),
    useAdoptSpecDocument: hook('adopt'),
    useArrangeSpecDocument: hook('arrange'),
  }
})

function list(overrides: Partial<SpecListResponse> = {}): SpecListResponse {
  return {
    specs: [
      { path: 'spec/home.html', title: 'Home', state: 'filed', document_id: 'spdoc-1', parent: null },
      { path: 'spec/area.html', title: 'Area', state: 'filed', document_id: 'spdoc-2', parent: 'spec/home.html' },
      { path: 'spec/other.html', title: 'Other', state: 'filed', document_id: 'spdoc-3', parent: null },
      { path: 'spec/loose.html', state: 'unfiled', document_id: null },
      { path: 'spec/stray.html', state: 'unfiled', document_id: null },
    ],
    home: 'spec/home.html',
    manifest: { state: 'valid', version: 1 },
    missing: [{ path: 'spec/gone.html', title: 'Gone', kind: 'capability', status: 'current', parent: null, order: 0 }],
    diagnostics: [],
    ...overrides,
  }
}

function reindexAnswer(overrides: Partial<ReindexResult['index']> & { skipped?: ReindexResult['corpus']['skipped'] } = {}): ReindexResult {
  const { skipped = [], ...index } = overrides
  return {
    documents: {
      'spec/home.html': { created: ['FR-1', 'FR-2'], reworded: ['FR-3'], retired: [], restored: [], unchanged: [] },
      'spec/area.html': { created: ['FR-1'], reworded: [], retired: ['FR-4'], restored: [], unchanged: [] },
      'spec/loose.html': null,
    },
    index: { written: null, diagnostics: [], ...index },
    corpus: { rerendered: ['spec/area.html'], skipped },
  }
}

function refusal(status: number, detail: unknown) {
  return new ApiError(status, JSON.stringify({ detail }))
}

function strip(specList = list()) {
  return render(<SpecCorpusStrip specList={specList} />)
}

describe('the corpus strip', () => {
  beforeEach(() => {
    cleanup()
    state.calls = { reindex: [], adoptAll: 0, adopt: [], arrange: [] }
    state.answers = { reindex: [], adoptAll: [], adopt: [], arrange: [] }
  })

  it('1.3 says when there is no usable index, and names the home when there is', () => {
    strip(list({ manifest: { state: 'absent', version: null }, home: null }))
    expect(screen.getByTestId('spec-corpus-index').textContent).toMatch(/No usable index/)
    expect(screen.getByTestId('spec-corpus-rebuild')).toBeTruthy()
    cleanup()

    strip()
    expect(screen.getByTestId('spec-corpus-index').textContent).toBe('Index: home is Home')
  })

  it('1.4 asks for the home only when the Hub asks, and sends the choice', () => {
    state.answers.reindex.push({
      ok: reindexAnswer({
        diagnostics: [
          { code: 'home_ambiguous', path: null },
          { code: 'index_home_required', path: 'spec/index.json' },
        ],
      }),
    })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-rebuild'))
    expect(state.calls.reindex).toEqual([{}])

    fireEvent.change(screen.getByTestId('spec-corpus-home-select'), { target: { value: 'spec/area.html' } })
    fireEvent.click(screen.getByTestId('spec-corpus-home-confirm'))
    expect(state.calls.reindex).toEqual([{}, { home: 'spec/area.html' }])
  })

  it('1.4 keys on index_home_required, not on its position', () => {
    state.answers.reindex.push({ ok: reindexAnswer({ diagnostics: [{ code: 'index_home_required' }] }) })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-rebuild'))
    expect(screen.getByTestId('spec-corpus-home-question')).toBeTruthy()
  })

  it('1.5 summarises a written index, its totals and each skip', () => {
    state.answers.reindex.push({
      ok: reindexAnswer({
        written: { path: 'spec/index.json', documents: 3, home: 'spec/home.html' },
        skipped: [{ path: 'spec/other.html', reason: 'write_failed', message: 'No space left on device' }],
      }),
    })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-rebuild'))
    const summary = screen.getByTestId('spec-corpus-summary').textContent ?? ''
    expect(summary).toContain('Indexed 3 documents')
    expect(summary).toContain('created 3')
    expect(summary).toContain('reworded 1')
    expect(summary).toContain('retired 1')
    expect(summary).toContain('re-rendered 1')
    expect(summary).toContain('Skipped spec/other.html: write_failed (No space left on device)')
  })

  it('1.10 offers only tracked documents as the home, and says when there is nothing to index', () => {
    state.answers.reindex.push({ ok: reindexAnswer({ diagnostics: [{ code: 'index_home_required' }] }) })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-rebuild'))
    const options = within(screen.getByTestId('spec-corpus-home-select'))
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value)
    expect(options).toEqual(['', 'spec/home.html', 'spec/area.html', 'spec/other.html'])
    cleanup()

    state.answers.reindex.push({ ok: reindexAnswer() })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-rebuild'))
    expect(screen.getByTestId('spec-corpus-nothing').textContent).toMatch(/Nothing to index/)
  })

  it('1.15 says why the index could not be written, and offers the rebuild again', () => {
    state.answers.reindex.push({
      ok: reindexAnswer({
        diagnostics: [
          { code: 'index_write_failed', path: 'spec/index.json', actual: 'No space left on device' },
        ],
      }),
    })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-rebuild'))
    expect(screen.getByTestId('spec-corpus-write-failed').textContent).toContain(
      'The index could not be written: No space left on device. The requirements were rebuilt.',
    )
    expect(screen.queryByTestId('spec-corpus-nothing')).toBeNull()
    expect(screen.queryByTestId('spec-corpus-home-question')).toBeNull()
    expect(screen.getByTestId('spec-corpus-rebuild')).toBeTruthy()
  })

  it('1.7 adopts all, and lists each skip with its reason and every diagnostic', () => {
    state.answers.adoptAll.push({
      ok: {
        documents: {
          'spec/loose.html': { adopted: true, path: 'spec/loose.html' },
          'spec/stray.html': { adopted: false, path: 'spec/stray.html', code: 'payload_absent', message: 'no payload block' },
        },
        adopted: ['spec/loose.html'],
        skipped: ['spec/stray.html'],
        diagnostics: [{ code: 'discovery_truncated', path: 'spec/' }],
      },
    })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-adopt-all'))
    expect(screen.getByTestId('spec-corpus-adopt-all').textContent).toBe('Adopt all 2')
    expect(state.calls.adoptAll).toBe(1)
    const result = screen.getByTestId('spec-corpus-adopt-result').textContent ?? ''
    expect(result).toContain('spec/stray.html: no payload block')
    expect(result).toContain('discovery_truncated — spec/')
  })

  it('counts documents already tracked and agreeing, and lists only the rest', () => {
    state.answers.adoptAll.push({
      ok: {
        documents: {
          'spec/a.html': { adopted: false, path: 'spec/a.html', code: 'document_exists', message: 'already tracked', differences: [] },
          'spec/b.html': {
            adopted: false,
            path: 'spec/b.html',
            code: 'document_exists',
            message: 'already tracked, and it disagrees',
            differences: [{ field: 'title', file: 'B', row: 'Bee' }],
          },
          'spec/c.html': { adopted: false, path: 'spec/c.html', code: 'payload_absent', message: 'no payload block' },
        },
        adopted: [],
        skipped: ['spec/a.html', 'spec/b.html', 'spec/c.html'],
        diagnostics: [],
      },
    })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-adopt-all'))
    const text = screen.getByTestId('spec-corpus-adopt-result').textContent ?? ''
    expect(text).toContain('Adopted 0; 1 already tracked; skipped 2.')
    expect(text).not.toContain('spec/a.html')
    expect(text).toContain('spec/b.html: already tracked, and it disagrees')
    expect(text).toContain('spec/c.html: no payload block')
  })

  it('a rebuild after adopting clears "rebuild the index to file them"', () => {
    state.answers.adoptAll.push({
      ok: { documents: {}, adopted: ['spec/loose.html'], skipped: [], diagnostics: [] },
    })
    state.answers.reindex.push({
      ok: reindexAnswer({ written: { path: 'spec/index.json', documents: 4, home: 'spec/home.html' } }),
    })
    strip()
    fireEvent.click(screen.getByTestId('spec-corpus-adopt-all'))
    expect(screen.getByTestId('spec-corpus-adopt-result').textContent).toContain('Rebuild the index')
    fireEvent.click(screen.getByTestId('spec-corpus-rebuild'))
    expect(screen.queryByTestId('spec-corpus-adopt-result')).toBeNull()
    expect(screen.getByTestId('spec-corpus-summary')).toBeTruthy()
  })
})

describe('Adopt beside an untracked document', () => {
  beforeEach(() => {
    cleanup()
    state.calls = { reindex: [], adoptAll: 0, adopt: [], arrange: [] }
    state.answers = { reindex: [], adoptAll: [], adopt: [], arrange: [] }
  })

  function browser(specList = list()) {
    return render(
      <SpecDocumentBrowser inventory={buildInventory(specList)} onSelect={vi.fn()} specList={specList} />,
    )
  }

  it('1.6 shows Adopt on untracked rows only, sends the path, and shows a refusal with its differences', () => {
    state.answers.adopt.push({
      error: refusal(409, {
        message: 'a record already exists for this path',
        path: 'spec/loose.html',
        code: 'document_exists',
        differences: [{ field: 'title', file: 'Loose', row: 'Old title' }],
      }),
    })
    browser()
    expect(screen.queryByTestId('spec-adopt-spec/home.html')).toBeNull()
    expect(screen.queryByTestId('spec-adopt-spec/gone.html')).toBeNull()
    const adopt = screen.getByTestId('spec-adopt-spec/loose.html')

    fireEvent.click(within(adopt).getByRole('button', { name: 'Adopt' }))
    expect(state.calls.adopt).toEqual([{ path: 'spec/loose.html' }])
    const alert = within(adopt).getByRole('alert').textContent ?? ''
    expect(alert).toContain('a record already exists for this path')
    expect(alert).toContain('title: file Loose vs record Old title')
  })

  it('1.11 after an adopt, the strip says a rebuild files it, with Rebuild as the primary action', () => {
    state.answers.adopt.push({ ok: { path: 'spec/loose.html' } })
    browser()
    expect(screen.queryByTestId('spec-corpus-adopted-note')).toBeNull()
    fireEvent.click(within(screen.getByTestId('spec-adopt-spec/loose.html')).getByRole('button'))
    expect(screen.getByTestId('spec-corpus-adopted-note').textContent).toBe(
      'Adopted documents are filed in the index on the next rebuild.',
    )
    expect(screen.getByTestId('spec-corpus-rebuild').className).toContain('primary')
  })
})

describe('Place under…', () => {
  beforeEach(() => {
    cleanup()
    state.calls = { reindex: [], adoptAll: 0, adopt: [], arrange: [] }
    state.answers = { reindex: [], adoptAll: [], adopt: [], arrange: [] }
  })

  function place(path = 'spec/area.html', parent: string | null = 'spec/home.html') {
    render(<SpecPlaceUnder path={path} parent={parent} specList={list()} />)
    fireEvent.click(screen.getByTestId('spec-place-under'))
  }

  it('1.8 lists the filed documents minus this one, preselects the parent, and sends the choice', () => {
    state.answers.arrange.push({ ok: { path: 'spec/area.html', parent: 'spec/other.html' } })
    place()
    const select = screen.getByTestId('spec-place-under-select') as HTMLSelectElement
    const values = within(select).getAllByRole('option').map((o) => (o as HTMLOptionElement).value)
    expect(values).toEqual(['__none__', 'spec/home.html', 'spec/other.html'])
    expect(select.value).toBe('spec/home.html')

    fireEvent.change(select, { target: { value: 'spec/other.html' } })
    fireEvent.click(screen.getByTestId('spec-place-under-confirm'))
    expect(state.calls.arrange).toEqual([{ path: 'spec/area.html', parent: 'spec/other.html' }])
  })

  it('1.8 No parent sends null', () => {
    state.answers.arrange.push({ ok: {} })
    place()
    fireEvent.change(screen.getByTestId('spec-place-under-select'), { target: { value: '__none__' } })
    fireEvent.click(screen.getByTestId('spec-place-under-confirm'))
    expect(state.calls.arrange).toEqual([{ path: 'spec/area.html', parent: null }])
  })

  it('1.9 a 409 shows the message and offers the rebuild; a 422 lists its diagnostics', () => {
    state.answers.arrange.push({
      error: refusal(409, { message: 'no usable index to arrange (absent)', diagnostics: [] }),
    })
    place()
    fireEvent.click(screen.getByTestId('spec-place-under-confirm'))
    expect(screen.getByTestId('spec-place-under-refusal').textContent).toContain(
      'no usable index to arrange (absent)',
    )
    expect(screen.getByTestId('spec-corpus-rebuild')).toBeTruthy()
    cleanup()

    state.answers.arrange.push({
      error: refusal(422, {
        message: 'this placement is not allowed',
        diagnostics: [{ code: 'parent_cycle', path: 'spec/home.html' }],
      }),
    })
    place('spec/home.html', null)
    fireEvent.change(screen.getByTestId('spec-place-under-select'), { target: { value: 'spec/area.html' } })
    fireEvent.click(screen.getByTestId('spec-place-under-confirm'))
    const text = screen.getByTestId('spec-place-under-refusal').textContent ?? ''
    expect(text).toContain('this placement is not allowed')
    expect(text).toContain('parent_cycle — spec/home.html')
    expect(screen.queryByTestId('spec-corpus-rebuild')).toBeNull()
  })
})
