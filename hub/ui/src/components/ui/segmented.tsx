import * as React from 'react'

/** The one way to pick a view. Board/Dependencies, Ledger/Activity/Logs and Story/Details were
 *  three different controls; this is the Activity one, made shared. Arrow keys move between
 *  options (a radio group), and the selected option's fill slides rather than jumping. */
export interface SegmentedOption<T extends string> {
  value: T
  label: React.ReactNode
  count?: number
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  size = 'sm',
  className,
}: {
  value: T
  onChange: (value: T) => void
  options: ReadonlyArray<SegmentedOption<T>>
  label: string
  size?: 'xs' | 'sm'
  className?: string
}) {
  const refs = React.useRef<Array<HTMLButtonElement | null>>([])
  const index = Math.max(0, options.findIndex((o) => o.value === value))
  const onKeyDown = (event: React.KeyboardEvent) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    event.preventDefault()
    const next = (index + step + options.length) % options.length
    onChange(options[next]!.value)
    refs.current[next]?.focus()
  }
  return (
    <div
      role="radiogroup"
      aria-label={label}
      data-size={size}
      className={['aw-segmented', className].filter(Boolean).join(' ')}
      onKeyDown={onKeyDown}
    >
      {options.map((option, i) => (
        <button data-slot="segmented-option"
          key={option.value}
          ref={(el) => {
            refs.current[i] = el
          }}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          tabIndex={option.value === value ? 0 : -1}
          data-active={option.value === value ? 'true' : 'false'}
          className="aw-segmented-option"
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined ? <span className="aw-segmented-count">{option.count}</span> : null}
        </button>
      ))}
    </div>
  )
}
