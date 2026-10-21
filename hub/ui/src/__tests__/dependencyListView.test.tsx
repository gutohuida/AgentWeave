import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'

import type { Task } from '@/api/tasks'
import { DependencyListView } from '@/components/tasks/DependencyListView'

/**
 * The Dependencies view (ui-finesse), which replaced the per-document DAG board: one chain per
 * document, in prerequisite order, each row naming what it waits on and what it unblocks. Carried
 * from `DependencyBoardView`/`DependencyBoard`: hand-made tasks have a group of their own that says
 * no document declares their dependencies (F552), the document is named as where structure changes,
 * and a prerequisite declared by another document is named with that document (task 8.7).
 */

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
    created_at: '2026-08-10T09:00:00Z',
    prerequisites: [
      { id: 'first', title: 'Read the config', status: 'approved', spec_document_id: 'doc-a' },
      { id: 'other', title: 'Load plugins', status: 'rejected', spec_document_id: 'doc-b' },
    ],
    dependency_state: 'gated_on_rejected',
  }),
  makeTask({ id: 'first', title: 'Read the config', spec_document_id: 'doc-a', status: 'approved', dependents: [{ id: 'second', title: 'Watch the folder', status: 'pending' }] }),
  makeTask({ id: 'other', title: 'Load plugins', spec_document_id: 'doc-b', status: 'rejected' }),
  makeTask({ id: 'hand', title: 'Tidy the logs', spec_document_id: null }),
]

afterEach(cleanup)

describe('the dependencies view', () => {
  it('groups by document, orders each chain by its prerequisites, and counts what is approved', () => {
    render(<DependencyListView tasks={TASKS} documents={DOCS} onOpenTask={vi.fn()} onOpenDocument={vi.fn()} />)

    const watcher = screen.getByRole('region', { name: 'Watcher' })
    expect(watcher).toHaveTextContent('1 of 2 approved')
    const rows = within(watcher).getAllByRole('button', { name: /Read the config|Watch the folder/ })
    expect(rows[0]).toHaveTextContent('Read the config')
    expect(rows[1]).toHaveTextContent('Watch the folder')
  })

  it('names a prerequisite another document declared, with that document, and says it was rejected', () => {
    render(<DependencyListView tasks={TASKS} documents={DOCS} onOpenTask={vi.fn()} onOpenDocument={vi.fn()} />)

    const row = screen.getByTestId('deps-row-second')
    expect(row).toHaveTextContent('Waits on Load plugins (in Plugins)')
    expect(row).toHaveTextContent('a prerequisite was rejected')
    expect(row).toHaveAttribute('data-dependency-state', 'gated_on_rejected')
  })

  it('gives hand-made tasks their own group, saying no document declares their dependencies', () => {
    render(<DependencyListView tasks={TASKS} documents={DOCS} onOpenTask={vi.fn()} onOpenDocument={vi.fn()} />)

    const hand = screen.getByRole('region', { name: 'Made by hand' })
    expect(hand).toHaveTextContent('no document declares these')
    expect(within(hand).queryByRole('button', { name: /Open document/ })).toBeNull()
  })

  it('says structure is changed in the document, and opens it', () => {
    const onOpenDocument = vi.fn()
    const onOpenTask = vi.fn()
    render(<DependencyListView tasks={TASKS} documents={DOCS} onOpenTask={onOpenTask} onOpenDocument={onOpenDocument} />)

    expect(screen.getByRole('note')).toHaveTextContent('edit the document that declares it')
    fireEvent.click(within(screen.getByRole('region', { name: 'Watcher' })).getByRole('button', { name: /Open document/ }))
    expect(onOpenDocument).toHaveBeenCalledWith('spec/changes/watcher/spec.json')
    fireEvent.click(screen.getByRole('button', { name: /Tidy the logs/ }))
    expect(onOpenTask).toHaveBeenCalledWith('hand')
  })
})
