import { useState, type CSSProperties } from 'react'
import { Icon } from '@/components/common/Icon'

export interface SidebarBadge {
  count: number
  danger: boolean
}

export interface SidebarItemProps {
  label: string
  icon: string
  active: boolean
  badge?: SidebarBadge | null
  onClick: () => void
  testId?: string
  /** Icon-only rail: the label becomes the accessible name and tooltip. */
  compact?: boolean
}

const baseStyle: CSSProperties = {
  position: 'relative',
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  width: '100%',
  padding: '6px 8px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 13,
  fontWeight: 500,
  color: 'var(--text-2)',
  background: 'transparent',
  transition:
    'background-color var(--dur-fast) var(--ease), ' +
    'border-color var(--dur-fast) var(--ease), ' +
    'color var(--dur-fast) var(--ease)',
  cursor: 'pointer',
  // A transparent border is reserved at rest so gaining emphasis on hover
  // colours it in place rather than adding a pixel and nudging the row.
  // Previously `border: none`, which also overrode the global control base.
  border: '1px solid transparent',
  textAlign: 'left',
}

// Theme tokens rather than hardcoded white — the former rgba(255,255,255,…)
// values were invisible against a light background.
const HOVER_BG = 'var(--accent)'
const ACTIVE_BG = 'var(--accent)'
const ACTIVE_BORDER = 'var(--border)'
const ACTIVE_COLOR = 'var(--text)'

const activeIndicatorStyle = (active: boolean): CSSProperties => ({
  content: '""',
  position: 'absolute',
  left: 0,
  top: '50%',
  transform: 'translateY(-50%)',
  width: 2,
  height: active ? 16 : 0,
  background: 'var(--text)',
  borderRadius: '0 2px 2px 0',
  transition: 'height 0.15s',
})

const badgeStyle = (danger: boolean): CSSProperties => ({
  fontSize: 10,
  borderRadius: 9999,
  padding: '1px 5px',
  background: danger ? 'var(--red)' : 'var(--surface-3)',
  color: danger ? 'var(--destructive-fg)' : 'var(--text-2)',
  fontWeight: 600,
})

/**
 * One row in the sidebar nav. Owns its hover state, active indicator,
 * icon, label, and optional badge. Used both for top-level items and
 * sectioned items (and the bottom Settings button) — Sidebar groups them
 * into sections, but the per-row presentation is identical.
 */
export function SidebarItem({
  label,
  icon,
  active,
  badge,
  onClick,
  testId,
  compact = false,
}: SidebarItemProps) {
  const [hovered, setHovered] = useState(false)

  const isHighlighted = active || hovered
  const style: CSSProperties = {
    ...baseStyle,
    color: isHighlighted ? ACTIVE_COLOR : baseStyle.color,
    background: active ? ACTIVE_BG : hovered ? HOVER_BG : 'transparent',
    borderColor: isHighlighted ? ACTIVE_BORDER : 'transparent',
    ...(compact ? { justifyContent: 'center', padding: '6px 0', gap: 0 } : null),
  }

  return (
    <button
      onClick={onClick}
      className="group"
      style={style}
      data-testid={testId}
      title={compact ? label : undefined}
      aria-label={compact ? label : undefined}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span style={activeIndicatorStyle(active)} />
      <Icon name={icon} size={18} />
      {!compact && <span className="flex-1">{label}</span>}
      {badge && (
        <span
          className="shrink-0"
          style={
            compact
              ? {
                  ...badgeStyle(badge.danger),
                  position: 'absolute',
                  top: 2,
                  right: 4,
                  padding: '0 3px',
                  fontSize: 9,
                }
              : badgeStyle(badge.danger)
          }
        >
          {badge.count}
        </span>
      )}
    </button>
  )
}
