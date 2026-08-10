import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Icon } from '@/components/common/Icon'

export interface RowMenuItem {
  id: string
  label: string
  onSelect: () => void
  disabled?: boolean
  /** Stated under the label when the item is disabled. An unavailable action says why rather
   *  than disappearing, so the menu's shape does not change between rows. */
  reason?: string
}

interface RowMenuProps {
  /** Accessible name for the trigger — "Actions for <thing>", never a bare "Menu". */
  label: string
  items: RowMenuItem[]
  testId: string
  /** Keep the trigger visible without hovering. Set on the row the operator is looking at. */
  persistent?: boolean
  /**
   * The trigger's glyph. Defaults to the three dots, which is what "actions for this row" looks
   * like everywhere in the app and should stay that.
   *
   * Set it only when a second menu sits beside the first: two identical three-dot buttons in one
   * corner are indistinguishable, and the `aria-label` that tells them apart is invisible to
   * anyone using their eyes.
   */
  icon?: string
}

const ITEM_STYLE: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-start',
  gap: 2,
  width: '100%',
  padding: '6px 10px',
  borderRadius: 'var(--radius-sm)',
  fontSize: 12,
  color: 'var(--text-2)',
  cursor: 'pointer',
  outline: 'none',
}

/**
 * One menu for every row in navigation — agent rows and conversation rows both.
 *
 * Opened from a control that is in layout at rest and revealed by hover *or* keyboard focus
 * (`.row-action`), not by right-click: the operator's call, 2026-08-08 — *"using right click is
 * nice but not everyone will think about it… your instinct to show three dots is good"*. A
 * context menu with no visible affordance is the thing this deliberately is not.
 *
 * Radix handles the rest of the keyboard contract: arrow keys move between items, Escape closes,
 * and focus returns to the trigger on dismiss.
 */
export function RowMenu({
  label,
  items,
  testId,
  persistent = false,
  icon = 'more_horiz',
}: RowMenuProps) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          className="row-action"
          data-persistent={persistent ? 'true' : undefined}
          data-testid={testId}
          aria-label={label}
          title={label}
          // The trigger sits beside a row that navigates; a click here must not also open it.
          onClick={(event) => event.stopPropagation()}
        >
          <Icon name={icon} size={15} />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={4}
          style={{
            minWidth: 200,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: 4,
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
            zIndex: 50,
          }}
        >
          {items.map((item) => (
            <DropdownMenu.Item
              key={item.id}
              data-testid={`${testId}-${item.id}`}
              disabled={item.disabled}
              aria-disabled={item.disabled ? 'true' : undefined}
              style={{ ...ITEM_STYLE, ...(item.disabled ? { opacity: 0.5, cursor: 'not-allowed' } : {}) }}
              onSelect={(event) => {
                if (item.disabled) {
                  event.preventDefault()
                  return
                }
                item.onSelect()
              }}
            >
              <span>{item.label}</span>
              {item.disabled && item.reason && (
                <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{item.reason}</span>
              )}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
