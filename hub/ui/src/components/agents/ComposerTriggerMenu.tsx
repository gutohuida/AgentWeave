import { Icon } from '@/components/common/Icon'
import type { SpecReference } from '@/lib/specReference'

export interface ComposerTriggerMenuItem {
  value: string
  label: string
  /** A second, dimmer line of identification (a spec's path). */
  detail?: string
  /** The heading this item sits under; items of one group are contiguous. Omitted: no headings. */
  group?: 'Specs' | 'Files'
  /** Set on a spec result: accepting it inserts a box for this document, not text. */
  spec?: SpecReference
}

interface ComposerTriggerMenuProps {
  items: ComposerTriggerMenuItem[]
  /** Why the Specs group has nothing in it yet (loading, or the list could not be read). */
  specsNotice?: string
  activeIndex: number
  onHover: (index: number) => void
  onSelect: (item: ComposerTriggerMenuItem) => void
}

const GROUP_HEADING: React.CSSProperties = {
  padding: '6px 10px 2px',
  fontSize: 10.5,
  fontWeight: 600,
  letterSpacing: '0.04em',
  textTransform: 'uppercase',
  color: 'var(--text-3)',
}

/**
 * Passive overlay driven entirely by the composer's own keydown handling — this
 * component never receives focus itself (see `Composer.tsx`'s keydown wiring), so
 * dismissing it or navigating it never moves focus off the composer's field.
 * `onMouseDown` (not `onClick`) with `preventDefault` on each option so a pointer
 * click doesn't blur the field before the selection is applied.
 *
 * Group headings are not options: the arrow keys move through one flat list, so ArrowDown from
 * the last spec lands on the first file.
 */
export function ComposerTriggerMenu({ items, specsNotice, activeIndex, onHover, onSelect }: ComposerTriggerMenuProps) {
  return (
    <div
      role="listbox"
      aria-label="References"
      data-testid="composer-trigger-menu"
      style={{
        position: 'absolute',
        bottom: '100%',
        left: 0,
        marginBottom: 6,
        minWidth: 240,
        maxWidth: '100%',
        maxHeight: 260,
        overflowY: 'auto',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
        zIndex: 50,
      }}
    >
      {specsNotice && (
        <>
          <div role="presentation" data-testid="composer-menu-group" style={GROUP_HEADING}>
            Specs
          </div>
          <div
            role="status"
            data-testid="composer-specs-notice"
            style={{ padding: '4px 10px 6px', fontSize: 12, color: 'var(--text-3)' }}
          >
            {specsNotice}
          </div>
        </>
      )}
      {items.length === 0 ? (
        <div style={{ padding: '6px 10px', fontSize: 12, color: 'var(--text-3)' }}>No matches</div>
      ) : (
        items.map((item, index) => (
          <div key={item.value} role="presentation">
            {item.group && item.group !== items[index - 1]?.group && (
              <div role="presentation" data-testid="composer-menu-group" style={GROUP_HEADING}>
                {item.group}
              </div>
            )}
            <div
              role="option"
              aria-selected={index === activeIndex}
              data-kind={item.spec ? 'spec' : 'text'}
              data-label={item.label}
              onMouseEnter={() => onHover(index)}
              onMouseDown={(event) => {
                event.preventDefault()
                onSelect(item)
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 10px',
                fontSize: 12,
                color: index === activeIndex ? 'var(--text)' : 'var(--text-2)',
                background: index === activeIndex ? 'var(--surface-3)' : 'transparent',
                cursor: 'pointer',
                fontFamily: item.spec ? undefined : "'JetBrains Mono', monospace",
              }}
            >
              {item.spec && <Icon name="description" size={14} />}
              <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {item.label}
              </span>
              {item.detail && (
                <span
                  style={{
                    marginLeft: 'auto',
                    minWidth: 0,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontSize: 11,
                    color: 'var(--text-3)',
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  {item.detail}
                </span>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  )
}
