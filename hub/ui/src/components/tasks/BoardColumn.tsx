import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import '@/styles/board.css'

/** Where a dragged card may land. `idle` while nothing is being dragged. */
export type ColumnDropState = 'idle' | 'available' | 'active' | 'unavailable'

/** The drag-and-drop half of a column, supplied by a board whose cards can move. */
export interface ColumnDropProps {
  state: ColumnDropState
  onDragEnter: React.DragEventHandler<HTMLElement>
  onDragOver: React.DragEventHandler<HTMLElement>
  onDrop: React.DragEventHandler<HTMLElement>
}

/** One lifecycle column. An empty column, or one the operator folded, is a 44px rail with its
 *  label set vertically and its count; clicking the rail opens it. So the columns that hold work
 *  get the width, and the board still shows every stage in order: on today's board five empty
 *  columns took full width while twelve real cards squeezed into a 175px column at the edge.
 *
 *  A folded rail is a drop target too: dragging a card onto it moves the card there (and the
 *  column opens, because it is no longer empty). */
export function BoardColumn({
  id,
  label,
  tone,
  count,
  folded,
  onToggleFold,
  emptyHint,
  drop,
  children,
}: {
  id: string
  label: string
  /** The status colour token, or null for a neutral column (lib/taskStatusColors). */
  tone: string | null
  count: number
  folded: boolean
  onToggleFold: () => void
  /** What an open empty column says. */
  emptyHint?: string
  drop?: ColumnDropProps
  children?: React.ReactNode
}) {
  const style = { '--column-tone': tone ?? 'var(--text-3)' } as React.CSSProperties
  const dropAttrs = drop
    ? { 'data-drop-state': drop.state, onDragEnter: drop.onDragEnter, onDragOver: drop.onDragOver, onDrop: drop.onDrop }
    : {}
  if (folded) {
    return (
      <button
        type="button"
        data-slot="board-rail"
        className="aw-board-rail"
        data-status={id}
        style={style}
        aria-expanded={false}
        aria-label={`${label}, ${count} ${count === 1 ? 'task' : 'tasks'}. Show column`}
        title={count === 0 ? `${label}: nothing here` : `Show ${label}`}
        onClick={onToggleFold}
        {...dropAttrs}
      >
        <span className="aw-board-rail-count" data-empty={count === 0 ? 'true' : 'false'}>
          {count}
        </span>
        <span className="aw-board-rail-label">{label}</span>
      </button>
    )
  }
  return (
    <section className="aw-board-column" data-status={id} aria-labelledby={`col-${id}`} style={style} {...dropAttrs}>
      <header className="aw-board-column-head">
        <span className="aw-board-column-dot" aria-hidden="true" />
        <h3 id={`col-${id}`} className="aw-board-column-label">
          {label}
        </h3>
        <span className="aw-board-column-count">{count}</span>
        <button
          type="button"
          data-slot="icon-button"
          className="aw-icon-button aw-board-fold"
          aria-label={`Fold ${label}`}
          title="Fold column"
          onClick={onToggleFold}
        >
          <Icon name="expand_less" size={13} className="-rotate-90" />
        </button>
      </header>
      <div className="aw-board-column-body">
        {count === 0 ? (
          <p className="aw-board-column-empty" data-testid={`task-column-empty-${id}`}>
            {emptyHint ?? 'Nothing here.'}
          </p>
        ) : (
          children
        )}
      </div>
    </section>
  )
}
