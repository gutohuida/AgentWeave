export interface ComposerTriggerMenuItem {
  value: string
  label: string
}

interface ComposerTriggerMenuProps {
  items: ComposerTriggerMenuItem[]
  activeIndex: number
  onHover: (index: number) => void
  onSelect: (item: ComposerTriggerMenuItem) => void
}

/**
 * Passive overlay driven entirely by the composer's own keydown handling — this
 * component never receives focus itself (see `Composer.tsx`'s keydown wiring), so
 * dismissing it or navigating it never moves focus off the composer's textarea.
 * `onMouseDown` (not `onClick`) with `preventDefault` on each option so a pointer
 * click doesn't blur the textarea before the selection is applied.
 */
export function ComposerTriggerMenu({ items, activeIndex, onHover, onSelect }: ComposerTriggerMenuProps) {
  return (
    <div
      role="listbox"
      style={{
        position: 'absolute',
        bottom: '100%',
        left: 0,
        marginBottom: 6,
        minWidth: 240,
        maxHeight: 220,
        overflowY: 'auto',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
        zIndex: 50,
      }}
    >
      {items.length === 0 ? (
        <div style={{ padding: '6px 10px', fontSize: 12, color: 'var(--text-3)' }}>No matches</div>
      ) : (
        items.map((item, index) => (
          <div
            key={item.value}
            role="option"
            aria-selected={index === activeIndex}
            onMouseEnter={() => onHover(index)}
            onMouseDown={(event) => {
              event.preventDefault()
              onSelect(item)
            }}
            style={{
              padding: '6px 10px',
              fontSize: 12,
              color: index === activeIndex ? 'var(--text)' : 'var(--text-2)',
              background: index === activeIndex ? 'var(--surface-3)' : 'transparent',
              cursor: 'pointer',
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {item.label}
          </div>
        ))
      )}
    </div>
  )
}
