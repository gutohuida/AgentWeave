import * as React from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { Icon } from '@/components/common/Icon'

/** Menus and the menu-based select.
 *
 *  A native `<select>` opens the operating system's own list, which ignores the theme (white on
 *  Windows in dark mode) and truncates its own label ("Claude (default) — Provider defa"). These
 *  open a themed menu that grows from its trigger (`aw-pop`, scale .98 + fade, 160ms), sized to
 *  its longest option, with the selected one checked. Keyboard: arrows, type-ahead, Enter, Esc
 *  (all Radix). */

export const Menu = DropdownMenu.Root
export const MenuTrigger = DropdownMenu.Trigger

export function MenuContent({
  children,
  align = 'end',
  className,
  ...props
}: DropdownMenu.DropdownMenuContentProps) {
  return (
    <DropdownMenu.Portal>
      <DropdownMenu.Content
        align={align}
        sideOffset={6}
        collisionPadding={12}
        className={['aw-menu aw-pop', className].filter(Boolean).join(' ')}
        {...props}
      >
        {children}
      </DropdownMenu.Content>
    </DropdownMenu.Portal>
  )
}

export function MenuItem({
  icon,
  shortcut,
  destructive,
  children,
  ...props
}: DropdownMenu.DropdownMenuItemProps & { icon?: string; shortcut?: string; destructive?: boolean }) {
  return (
    <DropdownMenu.Item className="aw-menu-item" data-destructive={destructive ? 'true' : undefined} {...props}>
      {icon ? <Icon name={icon} size={14} className="aw-menu-item-icon" /> : <span className="aw-menu-item-icon" />}
      <span className="min-w-0 flex-1 truncate">{children}</span>
      {shortcut ? <kbd className="aw-kbd">{shortcut}</kbd> : null}
    </DropdownMenu.Item>
  )
}

export function MenuLabel({ children }: { children: React.ReactNode }) {
  return <DropdownMenu.Label className="aw-menu-label">{children}</DropdownMenu.Label>
}

export function MenuSeparator() {
  return <DropdownMenu.Separator className="aw-menu-separator" />
}

export interface SelectOption<T extends string> {
  value: T
  label: string
  /** A second line, muted: what choosing it means. */
  detail?: string
  /** Leading mark (an icon name, or a node such as a ProviderMark). */
  icon?: React.ReactNode
  /** Listed, but not choosable (a provider whose CLI is not installed); `detail` says why. */
  disabled?: boolean
}

/** A select that opens a themed menu. The trigger shows the full label of the choice (it sizes
 *  to fit, up to `maxWidth`, then truncates with the full text in its title). */
export function MenuSelect<T extends string>({
  value,
  onChange,
  options,
  label,
  id,
  maxWidth = 280,
  disabled,
  testId,
  placeholder = 'Choose…',
}: {
  value: T
  onChange: (value: T) => void
  options: ReadonlyArray<SelectOption<T>>
  /** Accessible name when no visible label points at `id`. */
  label?: string
  id?: string
  maxWidth?: number
  disabled?: boolean
  /** `data-testid` on the trigger. */
  testId?: string
  /** What the trigger reads while `value` matches no option. */
  placeholder?: string
}) {
  const current = options.find((o) => o.value === value)
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger data-slot="select-trigger"
        id={id}
        data-testid={testId}
        disabled={disabled}
        aria-label={label}
        className="aw-select-trigger"
        style={{ maxWidth }}
        title={current?.label}
      >
        {current?.icon ? <span className="aw-select-icon">{typeof current.icon === 'string' ? <Icon name={current.icon} size={14} /> : current.icon}</span> : null}
        <span className="min-w-0 flex-1 truncate text-left">{current?.label ?? placeholder}</span>
        <Icon name="expand_more" size={14} className="aw-select-chevron" />
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={6} collisionPadding={12} className="aw-menu aw-pop" style={{ minWidth: 'var(--radix-dropdown-menu-trigger-width)' }}>
          <DropdownMenu.RadioGroup value={value} onValueChange={(next) => onChange(next as T)}>
            {options.map((option) => (
              <DropdownMenu.RadioItem key={option.value} value={option.value} disabled={option.disabled} className="aw-menu-item" data-two-line={option.detail ? 'true' : undefined}>
                <span className="aw-menu-item-icon">
                  {option.icon ? (typeof option.icon === 'string' ? <Icon name={option.icon} size={14} /> : option.icon) : null}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{option.label}</span>
                  {option.detail ? <span className="aw-menu-item-detail">{option.detail}</span> : null}
                </span>
                <DropdownMenu.ItemIndicator className="aw-menu-check">
                  <Icon name="check" size={14} />
                </DropdownMenu.ItemIndicator>
              </DropdownMenu.RadioItem>
            ))}
          </DropdownMenu.RadioGroup>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
