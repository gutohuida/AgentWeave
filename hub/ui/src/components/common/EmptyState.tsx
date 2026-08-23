import type { ReactNode } from 'react'
import { Icon } from './Icon'

/**
 * Why an empty surface is empty is not one question but two, and the operator needs them told
 * apart: "nothing exists here yet" is a claim about the data, and it is simply false when a filter
 * is applied. This component used to make that claim unconditionally — a filtered board with
 * matching tasks hidden still read "No tasks yet" — which is the defect the `filtered` variant
 * exists to fix. Loading is deliberately *not* a variant here: a shape-matched `.skeleton` belongs
 * in its place, not a dressed empty state (IDENTITY.md, "Loading states").
 */
interface EmptyStateProps {
  icon: string   // Icon name — see the map in ./Icon.tsx
  title: string
  description?: string
  /** `filtered` recedes: a filter miss is a normal, self-inflicted state, not an absence worth the
   *  same emphasis as a genuinely empty project. */
  variant?: 'empty' | 'filtered'
  /** The one thing worth doing from here — "Clear filter" on a miss, "New task" on a real empty.
   *  Callers pass a `Button`; this only places it. */
  action?: ReactNode
}

export function EmptyState({ icon, title, description, variant = 'empty', action }: EmptyStateProps) {
  const filtered = variant === 'filtered'
  return (
    <div
      className="flex flex-col items-center justify-center px-6 text-center"
      data-variant={variant}
      // A filter miss sits inside a populated surface the operator is actively working, so it does
      // not get the full-height treatment a genuinely empty one does.
      style={{ paddingTop: filtered ? 28 : 48, paddingBottom: filtered ? 28 : 48 }}
    >
      <div
        className="mb-4 flex items-center justify-center"
        style={{
          width: filtered ? 40 : 52,
          height: filtered ? 40 : 52,
          borderRadius: 'var(--radius-lg)',
          background: 'var(--surface-2)',
          border: '1px solid var(--border-region)',
        }}
      >
        <Icon name={icon} size={filtered ? 19 : 25} style={{ color: 'var(--text-3)' }} />
      </div>
      <p
        className={filtered ? 'text-xs font-semibold' : 'text-sm font-semibold'}
        style={{ color: filtered ? 'var(--text-2)' : 'var(--text)' }}
      >
        {title}
      </p>
      {description && (
        <p className="mt-1.5 max-w-sm text-xs leading-5" style={{ color: 'var(--text-3)' }}>
          {description}
        </p>
      )}
      {action && <div className="mt-3.5">{action}</div>}
    </div>
  )
}
