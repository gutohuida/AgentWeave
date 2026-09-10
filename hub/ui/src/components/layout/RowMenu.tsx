import { useRef } from 'react'
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
  /** Choosing this item opens a control that will take the keyboard for itself — a field asking
   *  what a block is waiting for, say. The menu then stands aside instead of pulling focus back
   *  to the trigger as it closes, which would take the keyboard straight back off the control
   *  that just asked for an answer. `onSelect` also runs *as the menu goes* rather than while it
   *  is still open, because the open menu traps focus; see `pendingSelect` below. Leave it unset
   *  for an action that fires and leaves nothing on screen: those must keep returning focus to
   *  the trigger, and must keep firing immediately. */
  takesFocus?: boolean
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
  fontSize: 13,
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
 * and focus returns to the trigger on dismiss — except for an item that declared `takesFocus`,
 * where the control it opened keeps the keyboard instead.
 */
export function RowMenu({
  label,
  items,
  testId,
  persistent = false,
  icon = 'more_horiz',
}: RowMenuProps) {
  // The action of an item that said it was opening something which takes the keyboard, held until
  // the menu has actually gone. A ref, not state: nothing renders from it, and `onCloseAutoFocus`
  // has to read it in the same dismissal that set it, before any re-render could have delivered a
  // new value.
  //
  // Held rather than run immediately because Radix traps focus inside the open menu. Measured in a
  // browser on 2026-09-10: with the menu open, `focus()` on any element outside it is pulled back
  // to the menu container within the same tick. Radix flushes an item's `onSelect` synchronously
  // (`dispatchDiscreteCustomEvent` wraps it in `flushSync`), so a control mounted by the selection
  // takes the keyboard while the trap is still live, loses it again at once, and is left on
  // `document.body` when the menu unmounts. Running the action from `onCloseAutoFocus` puts it
  // after the scope has torn down, where the control's own focus sticks.
  const pendingSelect = useRef<(() => void) | null>(null)
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
          onCloseAutoFocus={(event) => {
            const opensAControl = pendingSelect.current
            // Cleared unconditionally, before anything else can throw: *every* dismissal reaches
            // this handler — choosing an item, Escape, a click outside — and only some of them
            // chose anything. An action left here by a `takesFocus` selection would fire again on
            // the next dismissal, which selected nothing.
            pendingSelect.current = null
            if (!opensAControl) return
            // Radix returns focus to the trigger as the menu closes, which is right for almost
            // every item and wrong for one that is opening a control to ask for an answer: it
            // would take the keyboard off that control the moment it arrived (`F309`).
            event.preventDefault()
            opensAControl()
          }}
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
                // An item that opens a control which wants the keyboard runs on close instead of
                // now; see `pendingSelect`. Everything else fires here, unchanged, and keeps
                // Radix's focus return to the trigger.
                if (item.takesFocus === true) {
                  pendingSelect.current = item.onSelect
                  return
                }
                item.onSelect()
              }}
            >
              <span>{item.label}</span>
              {item.disabled && item.reason && (
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{item.reason}</span>
              )}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
