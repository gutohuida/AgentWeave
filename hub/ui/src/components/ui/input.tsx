import * as React from 'react'
import { Icon } from '@/components/common/Icon'

function classes(base: string, className?: string) {
  return [base, className].filter(Boolean).join(' ')
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input ref={ref} data-slot="input" className={classes('control-field', className)} {...props} />
  ),
)
Input.displayName = 'Input'

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} data-slot="textarea" className={classes('control-field', className)} {...props} />
  ),
)
Textarea.displayName = 'Textarea'

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  wrapperClassName?: string
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, wrapperClassName, children, ...props }, ref) => (
    <span className={classes('control-select-wrap block', wrapperClassName)}>
      <select ref={ref} data-slot="select" className={classes('control-field', className)} {...props}>
        {children}
      </select>
      <Icon className="control-select-icon" name="expand_more" size={14} aria-hidden="true" />
    </span>
  ),
)
Select.displayName = 'Select'
