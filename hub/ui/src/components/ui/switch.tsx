import * as React from 'react'

/** The one on/off control. Replaces the native checkboxes settings rows used (21 of them), so a
 *  setting that takes effect looks like one. `role="switch"` with `aria-checked`; Space and Enter
 *  toggle it (native button behaviour). The thumb stretches toward its direction of travel while
 *  pressed, then settles: the small "squish" T3 Code uses. */
export interface SwitchProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onChange'> {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  size?: 'sm' | 'md'
}

export const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ checked, onCheckedChange, size = 'md', className, disabled, ...props }, ref) => (
    <button data-slot="switch"
      ref={ref}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      data-state={checked ? 'checked' : 'unchecked'}
      data-size={size}
      className={['aw-switch', className].filter(Boolean).join(' ')}
      onClick={() => onCheckedChange(!checked)}
      {...props}
    >
      <span className="aw-switch-thumb" aria-hidden="true" />
    </button>
  ),
)
Switch.displayName = 'Switch'
