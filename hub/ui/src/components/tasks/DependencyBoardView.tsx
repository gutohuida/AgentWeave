import { useState } from 'react'
import { useTaskBoards } from '@/api/tasks'
import { EmptyState } from '@/components/common/EmptyState'
import { DependencyBoard } from './DependencyBoard'

interface DependencyBoardViewProps {
  onOpenRequirement?: (documentPath: string, anchor: string) => void
}

/**
 * Task 8.5: the document picker (design D9) — one board per document, plus the standing "no
 * document" board for hand-made tasks — wrapping `DependencyBoard` so task 8.11's view toggle has
 * one component to mount rather than reassembling picker-plus-board itself.
 *
 * `useTaskBoards()` already sorts documents first, "no document" last (`hub/hub/api/v1/tasks.py`);
 * this defaults to the first entry in that order rather than always the "no document" board, since
 * a project's dependency-declaring documents are what this view exists to show.
 */
export function DependencyBoardView({ onOpenRequirement }: DependencyBoardViewProps) {
  const { data, isLoading } = useTaskBoards()
  const boards = data?.boards ?? []
  // `undefined` means "no explicit choice yet — use the default"; distinct from `null`, which is
  // itself a valid explicit choice (the "no document" board).
  const [manualSelection, setManualSelection] = useState<string | null | undefined>(undefined)
  const selectedId = manualSelection !== undefined ? manualSelection : boards[0]?.spec_document_id ?? null

  // Task 8.10: this board draws structure, it never writes it (design D5, "the document is the
  // only writer of edges") — there is no add/remove-edge affordance anywhere in this component or
  // `DependencyBoard` for that reason, not by omission. The one place an operator might reasonably
  // look for one is right here, above the board, so it says where structure actually comes from
  // rather than leaving the absence to be discovered by trying. The "no document" board gets its
  // own wording: a hand-made task belongs to no document, so nothing can ever declare its edges
  // (D5's own stated consequence), not merely "edit elsewhere."
  const structureHint =
    selectedId === null
      ? 'Hand-made tasks belong to no document, so they can never have a dependency.'
      : 'Dependencies are set in the document — edit its depends_on field to change them.'

  if (isLoading) {
    return <div className="p-6" style={{ color: 'var(--text-3)' }}>Loading boards…</div>
  }

  if (boards.length === 0) {
    return (
      <div className="p-6">
        <EmptyState
          icon="task_alt"
          title="No tasks yet"
          description="Tasks a specification document declares, and hand-made tasks with none, appear here once they exist."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div
        data-testid="dependency-board-picker"
        className="flex flex-wrap items-center gap-1.5 p-3"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        {boards.map((board) => {
          const isSelected = board.spec_document_id === selectedId
          const label = board.spec_document_id === null ? 'No document' : board.title || 'Untitled'
          return (
            <button
              key={board.spec_document_id ?? '__none__'}
              type="button"
              data-testid={`dependency-board-picker-${board.spec_document_id ?? 'none'}`}
              aria-pressed={isSelected}
              onClick={() => setManualSelection(board.spec_document_id)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium"
              style={{
                background: isSelected ? 'var(--surface-3)' : 'transparent',
                border: `1px solid ${isSelected ? 'var(--border-hi)' : 'var(--border)'}`,
                color: isSelected ? 'var(--text)' : 'var(--text-2)',
              }}
            >
              {label}
              {/* Outstanding-over-total: design D9's "choosing a board and seeing what remains
                  are one act", so the count rides on the picker itself, not a separate fetch
                  after selecting. */}
              <span style={{ color: 'var(--text-3)', fontVariantNumeric: 'tabular-nums' }}>
                {board.outstanding}/{board.total}
              </span>
            </button>
          )
        })}
      </div>
      <p
        data-testid="dependency-board-structure-hint"
        className="px-3 pt-2 text-xs"
        style={{ color: 'var(--text-3)' }}
      >
        {structureHint}
      </p>
      <div className="flex-1 overflow-hidden">
        <DependencyBoard specDocumentId={selectedId} onOpenRequirement={onOpenRequirement} />
      </div>
    </div>
  )
}
