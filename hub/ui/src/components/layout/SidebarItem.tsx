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
  transition: 'background 0.15s, color 0.15s',
  cursor: 'pointer',
  border: 'none',
  textAlign: 'left',
}

const HOVER_BG = 'rgba(255,255,255,0.04)'
const ACTIVE_BG = 'rgba(255,255,255,0.06)'
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
  color: danger ? '#fff' : 'var(--text-2)',
  fontWeight: 600,
})

/**
 * One row in the sidebar nav. Owns its hover state, active indicator,
 * icon, label, and optional badge. Used both for top-level items and
 * sectioned items (and the bottom Settings button) — Sidebar groups them
 * into sections, but the per-row presentation is identical.
 */
export function SidebarItem({ label, icon, active, badge, onClick, testId }: SidebarItemProps) {
  const [hovered, setHovered] = useState(false)

  const isHighlighted = active || hovered
  const style: CSSProperties = {
    ...baseStyle,
    color: isHighlighted ? ACTIVE_COLOR : baseStyle.color,
    background: active ? ACTIVE_BG : hovered ? HOVER_BG : 'transparent',
  }

  return (
    <button
      onClick={onClick}
      className="group"
      style={style}
      data-testid={testId}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span style={activeIndicatorStyle(active)} />
      <Icon name={icon} size={18} />
      <span className="flex-1">{label}</span>
      {badge && (
        <span className="shrink-0" style={badgeStyle(badge.danger)}>
          {badge.count}
        </span>
      )}
    </button>
  )
}
