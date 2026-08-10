import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SpecDocumentPicker } from '@/components/spec/SpecDocumentPicker'
import { buildInventory, buildPathTree } from '@/components/spec/specNavigation'
import type { SpecListResponse } from '@/api/spec'

/* The picker opens on the specification as it is organised, not on an empty box.
 *
 * The flat ranked list is still what a query produces — the two answer different questions, and
 * which one is showing is decided by whether anything has been typed (operator, 2026-08-10:
 * "show the tree of spec... how each files are organized the folder etc").
 */

const HOME = 'spec/spec.html'
const ROADMAP = 'spec/roadmaps/collaboration.html'
const CHANGE = 'spec/changes/queued-message-delivery/spec.html'
const SECOND = 'spec/changes/agent-handoff/spec.html'
const ARCHIVED = 'spec/changes/archive/2026-07-29-add-agent-stream-kinds/spec.html'

const LIST: SpecListResponse = {
  specs: [
    { path: HOME, title: 'Specification', kind: 'baseline', state: 'filed', parent: null, order: 0 },
    { path: ROADMAP, title: 'Collaboration roadmap', kind: 'roadmap', state: 'filed', parent: null, order: 10 },
    { path: CHANGE, title: 'Queued message delivery', kind: 'change-spec', state: 'filed', parent: ROADMAP, order: 20 },
    { path: SECOND, title: 'Agent handoff', kind: 'change-spec', state: 'filed', parent: ROADMAP, order: 30 },
    { path: ARCHIVED, title: 'Add Agent Stream Kinds', kind: 'change-spec', state: 'filed', parent: ROADMAP, order: 40 },
  ],
  home: HOME,
  manifest: null,
  missing: [{ path: 'spec/changes/gone/spec.html', title: 'Gone Change', kind: 'change-spec', status: 'draft', parent: null, order: 50 }],
  diagnostics: [],
}

const inventory = buildInventory(LIST)

function renderPicker(currentPath: string | null = null) {
  const onSelect = vi.fn()
  const utils = render(
    <SpecDocumentPicker
      open
      onOpenChange={() => {}}
      inventory={inventory}
      onSelect={onSelect}
      currentPath={currentPath}
    />,
  )
  return { ...utils, onSelect }
}

beforeEach(() => cleanup())

describe('buildPathTree — the folder hierarchy', () => {
  it('names a shared directory once, above its children', () => {
    const rows = buildPathTree(inventory.nodes)
    const changes = rows.filter((r) => r.kind === 'directory' && r.path === 'spec/changes')
    expect(changes).toHaveLength(1)
  })

  it('drops the leading spec/ segment, which every path shares', () => {
    const rows = buildPathTree(inventory.nodes)
    expect(rows.some((r) => r.kind === 'directory' && r.label === 'spec')).toBe(false)
    // ...and the depths start at 0 for the first real directory.
    expect(rows.find((r) => r.path === 'spec/changes')?.depth).toBe(0)
    expect(rows.find((r) => r.path === 'spec/changes/agent-handoff')?.depth).toBe(1)
  })

  it('nests a document under every segment of its own path', () => {
    const rows = buildPathTree(inventory.nodes)
    const archived = rows.find((r) => r.path === ARCHIVED)
    // spec/changes/archive/2026-07-29-add-agent-stream-kinds/ — three directories deep.
    expect(archived?.depth).toBe(3)
    for (const dir of ['spec/changes', 'spec/changes/archive', 'spec/changes/archive/2026-07-29-add-agent-stream-kinds']) {
      expect(rows.some((r) => r.kind === 'directory' && r.path === dir)).toBe(true)
    }
  })

  it('includes archived and missing documents — a folder view that hides drift lies', () => {
    const paths = buildPathTree(inventory.nodes).filter((r) => r.kind === 'document').map((r) => r.path)
    expect(paths).toContain(ARCHIVED)
    expect(paths).toContain('spec/changes/gone/spec.html')
  })

  it('is empty for an empty inventory rather than inventing a root', () => {
    expect(buildPathTree([])).toEqual([])
  })
})

describe('the picker browses before it searches', () => {
  it('shows the tree with nothing typed', () => {
    renderPicker()
    const results = within(screen.getByTestId('spec-picker-results'))
    expect(results.getByTestId('spec-picker-directory-spec/changes')).toBeInTheDocument()
    expect(results.getByTestId('spec-picker-directory-spec/roadmaps')).toBeInTheDocument()
    expect(results.getByTestId(`spec-picker-document-${CHANGE}`)).toHaveTextContent('Queued message delivery')
  })

  it('shows the filename beside the title, because spec.html repeats down a column', () => {
    renderPicker()
    expect(screen.getByTestId(`spec-picker-document-${CHANGE}`)).toHaveTextContent('spec.html')
  })

  it('does not print the filename twice when it is also the title', () => {
    // An unfiled document has no manifest title, so its label falls back to the filename. Showing
    // both rendered `a1-probe.html a1-probe.html` on one row.
    const unfiled = buildInventory({
      ...LIST,
      specs: [{ path: 'spec/a1-probe.html', state: 'unindexed' }],
      missing: [],
    })
    cleanup()
    render(
      <SpecDocumentPicker open onOpenChange={() => {}} inventory={unfiled} onSelect={vi.fn()} />,
    )
    const row = screen.getByTestId('spec-picker-document-spec/a1-probe.html')
    expect(row.textContent?.match(/a1-probe\.html/g)).toHaveLength(1)
  })

  it('still shows the archive date rather than the filename for an archived document', () => {
    renderPicker()
    expect(screen.getByTestId(`spec-picker-document-${ARCHIVED}`)).toHaveTextContent('2026-07-29')
  })

  it('marks the document already open', () => {
    renderPicker(CHANGE)
    expect(screen.getByTestId(`spec-picker-document-${CHANGE}`)).toHaveAttribute('aria-current', 'true')
    expect(screen.getByTestId(`spec-picker-document-${SECOND}`)).not.toHaveAttribute('aria-current')
  })

  it('opens a document from the tree', () => {
    const { onSelect } = renderPicker()
    fireEvent.click(screen.getByTestId(`spec-picker-document-${SECOND}`))
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ path: SECOND }))
  })

  it('keeps a missing document visible and unselectable in the tree', () => {
    const { onSelect } = renderPicker()
    const missing = screen.getByTestId('spec-picker-document-spec/changes/gone/spec.html')
    expect(missing).toBeDisabled()
    fireEvent.click(missing)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('replaces the tree with ranked matches as soon as something is typed', async () => {
    const user = userEvent.setup()
    renderPicker()
    await user.type(screen.getByPlaceholderText(/Search by title/), 'handoff')

    expect(screen.queryByTestId('spec-picker-directory-spec/changes')).not.toBeInTheDocument()
    const results = within(screen.getByTestId('spec-picker-results'))
    expect(results.getByText('Agent handoff')).toBeInTheDocument()
    expect(results.queryByText('Queued message delivery')).not.toBeInTheDocument()
  })

  it('comes back to the tree when the query is cleared', async () => {
    const user = userEvent.setup()
    renderPicker()
    const input = screen.getByPlaceholderText(/Search by title/)
    await user.type(input, 'handoff')
    await user.clear(input)

    expect(screen.getByTestId('spec-picker-directory-spec/changes')).toBeInTheDocument()
  })
})
