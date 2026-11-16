import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'

import type { Task } from '@/api/tasks'
import { DependencyMapView } from '@/components/tasks/DependencyMapView'

beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

function makeTask(overrides: Partial<Task>): Task {
  return {
    id: 't',
    project_id: 'p',
    title: 'T',
    status: 'pending',
    priority: 'medium',
    created_at: '2026-08-10T10:00:00Z',
    updated: '2026-08-10T10:00:00Z',
    divergence_policy: 'surface',
    has_open_divergence: false,
    ...overrides,
  }
}

const DOCS = [
  { id: 'doc-a', title: 'Watcher', path: 'spec/changes/watcher/spec.json' },
  { id: 'doc-b', title: 'Plugins', path: 'spec/changes/plugins/spec.json' },
]

const TASKS: Task[] = [
  makeTask({
    id: 'second',
    title: 'Watch the folder',
    spec_document_id: 'doc-a',
    prerequisites: [
      { id: 'first', title: 'Read the config', status: 'approved', spec_document_id: 'doc-a' },
      { id: 'other', title: 'Load plugins', status: 'rejected', spec_document_id: 'doc-b' },
    ],
  }),
  makeTask({ id: 'first', title: 'Read the config', spec_document_id: 'doc-a', status: 'approved' }),
  makeTask({ id: 'other', title: 'Load plugins', spec_document_id: 'doc-b', status: 'rejected' }),
  makeTask({ id: 'hand', title: 'Tidy the logs', spec_document_id: null }),
]

afterEach(cleanup)

const show = (onOpenTask = vi.fn(), onOpenDocument = vi.fn()) =>
  render(<DependencyMapView tasks={TASKS} documents={DOCS} onOpenTask={onOpenTask} onOpenDocument={onOpenDocument} />)

describe('the dependency map', () => {
  it('draws one map per document plus Made by hand, counting what is approved', () => {
    show()
    expect(screen.getByRole('region', { name: 'Watcher' })).toHaveTextContent('1 of 2 approved')
    expect(screen.getByRole('region', { name: 'Plugins' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Made by hand' })).toHaveTextContent('no document declares these')
  })

  it('opens a task by its id when its node is clicked', () => {
    const onOpenTask = vi.fn()
    show(onOpenTask)
    fireEvent.click(within(screen.getByRole('region', { name: 'Made by hand' })).getByRole('button', { name: /Tidy the logs/ }))
    expect(onOpenTask).toHaveBeenCalledWith('hand')
  })

  it("draws another document's prerequisite as a disabled node naming its document", () => {
    show()
    const node = within(screen.getByRole('region', { name: 'Watcher' })).getByTitle('Load plugins, in Plugins')
    expect(node).toBeDisabled()
    expect(node).toHaveTextContent('in Plugins')
  })

  it('opens the document that declares the dependencies', () => {
    const onOpenDocument = vi.fn()
    show(vi.fn(), onOpenDocument)
    fireEvent.click(within(screen.getByRole('region', { name: 'Watcher' })).getByRole('button', { name: /Open document/ }))
    expect(onOpenDocument).toHaveBeenCalledWith('spec/changes/watcher/spec.json')
  })
})
