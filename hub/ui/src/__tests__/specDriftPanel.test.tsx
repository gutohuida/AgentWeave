import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ApiError } from '@/api/client'
import type { DriftCandidate, DriftListResponse } from '@/api/spec'
import { SpecDriftPanel } from '@/components/spec/SpecDriftPanel'

/* `drift-is-scanned-and-answered-on-the-document` (F129): drift detection worked and nothing in the
 * app reached it. Fixtures are in the route's order -- oldest first (F190): a panel that re-sorted, or
 * a fixture reversed, fails 1.7. */

const state = vi.hoisted(() => ({
  drift: { drift: [], unwatched: [] } as DriftListResponse,
  refetched: { drift: [], unwatched: [] } as DriftListResponse,
  totals: { verified: 1 } as Record<string, number>,
  resolveCalls: [] as unknown[],
  resolveError: null as unknown,
  detectCalls: 0,
  raised: [] as string[],
  driftError: null as unknown,
}))

vi.mock('@/api/spec', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/spec')>()
  type Options = { onSuccess?: (value: never) => unknown; onError?: (error: unknown) => void }
  return {
    ...actual,
    useSpecDrift: () => ({
      data: state.drift,
      error: state.driftError,
      refetch: async () => ({ data: state.refetched }),
    }),
    useSpecCoverage: () => ({ data: { totals: state.totals } }),
    useResolveDrift: () => ({
      isPending: false,
      mutate: (args: unknown, options?: Options) => {
        state.resolveCalls.push(args)
        if (state.resolveError) options?.onError?.(state.resolveError)
      },
    }),
    useDetectDrift: () => ({
      isPending: false,
      mutate: (_args: unknown, options?: Options) => {
        state.detectCalls += 1
        options?.onSuccess?.({ raised: state.raised } as never)
      },
    }),
  }
})

function candidate(id: string, identifier: string, created: string): DriftCandidate {
  return {
    id,
    requirement_id: `spreq-${id}`,
    evidence_id: `ev-${id}`,
    state: 'candidate',
    observed: { 'src/ledger.py': { was: 'aaaaaaaaaa', now: 'bbbbbbbbbb' } },
    resolution: null,
    created_at: created,
    requirement: { identifier, document: 'spec/changes/demo/spec.json' },
    evidence: { summary: `checked ${identifier}`, locator: 'src/ledger.py', actor: 'operator', actor_kind: 'operator' },
  }
}

function panel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SpecDriftPanel path="spec/changes/demo/spec.json" />
    </QueryClientProvider>,
  )
}

describe('the drift panel', () => {
  beforeEach(() => {
    cleanup()
    state.drift = { drift: [], unwatched: [] }
    state.refetched = { drift: [], unwatched: [] }
    state.totals = { verified: 1 }
    state.resolveCalls = []
    state.resolveError = null
    state.detectCalls = 0
    state.raised = []
    state.driftError = null
  })

  it('1.7 renders candidates in the route order, each with its paths and evidence', () => {
    state.drift = {
      drift: [candidate('drift-1', 'FR-1', '2026-10-07T10:00:00Z'), candidate('drift-2', 'FR-2', '2026-10-07T11:00:00Z')],
      unwatched: [],
    }
    panel()
    const rows = screen.getAllByTestId(/^spec-drift-row-/)
    expect(rows.map((r) => r.getAttribute('data-testid'))).toEqual(['spec-drift-row-drift-1', 'spec-drift-row-drift-2'])
    expect(rows[0].textContent).toContain('FR-1')
    expect(rows[0].textContent).toContain('src/ledger.py: aaaaaaa → bbbbbbb')
    expect(rows[0].textContent).toContain('checked FR-1')
  })

  it('1.8 each answer sends its enum value and the candidate id; a refusal is shown on the row', () => {
    state.drift = { drift: [candidate('drift-1', 'FR-1', '2026-10-07T10:00:00Z')], unwatched: [] }
    panel()
    fireEvent.click(screen.getByRole('button', { name: 'Spec updated' }))
    fireEvent.click(screen.getByRole('button', { name: 'Code corrected' }))
    state.resolveError = new ApiError(
      409,
      JSON.stringify({ detail: { message: 'this candidate was already answered: no_change_required', code: 'drift_not_open' } }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'No change' }))
    expect(state.resolveCalls).toEqual([
      { id: 'drift-1', resolution: 'specification_updated' },
      { id: 'drift-1', resolution: 'implementation_corrected' },
      { id: 'drift-1', resolution: 'no_change_required' },
    ])
    expect(screen.getByRole('alert').textContent).toContain('already answered')
  })

  it('1.9 Scan says what it found, counting this document against the refetched strip', async () => {
    state.raised = ['drift-new', 'drift-elsewhere']
    state.refetched = { drift: [candidate('drift-new', 'FR-3', '2026-10-07T12:00:00Z')], unwatched: [] }
    panel()
    fireEvent.click(screen.getByTestId('spec-drift-scan'))
    await waitFor(() =>
      expect(screen.getByTestId('spec-drift-scanned').textContent).toBe(
        'Scanned the project: 2 new — 1 on this document',
      ),
    )
    expect(state.detectCalls).toBe(1)
  })

  it('1.10 unwatched evidence is counted, and expanded with its remedy', () => {
    state.drift = {
      drift: [],
      unwatched: [
        {
          evidence_id: 'ev-1',
          requirement: { identifier: 'FR-4', document: 'spec/changes/demo/spec.json' },
          summary: 'ran it',
          actor: 'operator',
          reason: 'names_no_file',
        },
      ],
    }
    panel()
    const section = screen.getByTestId('spec-drift-unwatched')
    expect(section.textContent).toContain('1 piece of accepted evidence here is not watched for drift')
    fireEvent.click(screen.getByRole('button', { name: /not watched for drift/ }))
    expect(section.textContent).toContain('FR-4 · ran it: it names no file or commit in the tree')
  })

  it('a drift read that failed is said, not shown as nothing drifting', () => {
    state.totals = { verified: 0, drifting: 0, stale: 0 }
    state.driftError = new ApiError(500, JSON.stringify({ detail: 'the index could not be read' }))
    panel()
    expect(screen.getByTestId('spec-drift-load-error').textContent).toContain('the index could not be read')
  })

  it('1.11 renders nothing when there is nothing about drift to say', () => {
    state.totals = { verified: 0, drifting: 0, stale: 0 }
    const { container } = panel()
    expect(container.textContent).toBe('')
  })
})
