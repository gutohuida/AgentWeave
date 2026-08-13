import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { useConfigStore } from '@/store/configStore'

/* Following the open document when the agent renames it.
 *
 * A document's identity in this frontend is its path — the query key, the URL and the panel's prop
 * all hold it — so the one operation that changes a path has to reach the screen showing it. The
 * failure this guards is quiet: the operator goes on looking at a panel whose document has moved,
 * and the next fetch 404s.
 */

type SseHandler = (event: { type: string; data: unknown }) => void

let handlers: SseHandler[] = []

vi.mock('@/hooks/useSSE', () => ({
  useSSE: (handler: SseHandler) => {
    handlers.push(handler)
  },
  onSseReconnect: () => () => {},
  getBufferedEvents: () => [],
  cancelReconnect: () => {},
  __resetSSEStateForTest: () => {},
}))

import { useSpecDocumentRename } from '@/api/spec'

const PLACEHOLDER = 'spec/changes/amber-griffin/spec.html'
const NAMED = 'spec/changes/houseplant-watering-tracker/spec.html'

function Harness({ open, onMoved }: { open: string | null; onMoved: (path: string) => void }) {
  useSpecDocumentRename(open, onMoved)
  return null
}

function emit(data: Record<string, unknown>, type = 'spec_updated') {
  handlers.forEach((handler) => handler({ type, data }))
}

describe('following a renamed document', () => {
  beforeEach(() => {
    cleanup()
    handlers = []
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it('moves the open document to the path the rename produced', () => {
    const onMoved = vi.fn()
    render(<Harness open={PLACEHOLDER} onMoved={onMoved} />)

    emit({ project_id: 'proj-a', path: NAMED, previous_path: PLACEHOLDER })

    expect(onMoved).toHaveBeenCalledWith(NAMED)
  })

  it('leaves a different open document alone', () => {
    const onMoved = vi.fn()
    render(<Harness open="spec/changes/something-else/spec.html" onMoved={onMoved} />)

    emit({ project_id: 'proj-a', path: NAMED, previous_path: PLACEHOLDER })

    expect(onMoved).not.toHaveBeenCalled()
  })

  it('ignores an ordinary content update, which carries no previous path', () => {
    const onMoved = vi.fn()
    render(<Harness open={PLACEHOLDER} onMoved={onMoved} />)

    emit({ project_id: 'proj-a', path: PLACEHOLDER, phase: 'exploring' })

    expect(onMoved).not.toHaveBeenCalled()
  })

  it('ignores another project', () => {
    const onMoved = vi.fn()
    render(<Harness open={PLACEHOLDER} onMoved={onMoved} />)

    emit({ project_id: 'proj-other', path: NAMED, previous_path: PLACEHOLDER })

    expect(onMoved).not.toHaveBeenCalled()
  })

  it('does nothing when no document is open', () => {
    const onMoved = vi.fn()
    render(<Harness open={null} onMoved={onMoved} />)

    emit({ project_id: 'proj-a', path: NAMED, previous_path: PLACEHOLDER })

    expect(onMoved).not.toHaveBeenCalled()
  })
})
