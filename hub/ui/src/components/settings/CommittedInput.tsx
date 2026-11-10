import * as React from 'react'
import { Input, Textarea } from '@/components/ui/input'

/** A text or number field that applies when you finish with it, not on every keystroke: Enter or
 *  leaving the field commits, Escape puts the stored value back. Settings apply on change, and a
 *  number typed "1", "12", "120" must not be saved three times or toast three times. Invalid input
 *  is shown on the field (`aria-invalid`), says why beneath it, and is never committed. */
export function CommittedInput({
  value,
  onCommit,
  validate,
  numeric,
  width,
  placeholder,
  id,
  ariaLabel,
  suffix,
  disabled,
}: {
  value: string
  onCommit: (value: string) => void
  /** An error sentence, or null when the draft is acceptable. */
  validate?: (draft: string) => string | null
  numeric?: boolean
  width?: number
  placeholder?: string
  id?: string
  ariaLabel?: string
  /** A unit after the field ("hops", "agents"). */
  suffix?: string
  disabled?: boolean
}) {
  const [draft, setDraft] = React.useState(value)
  // The last value handed to `onCommit`, so Enter (which commits, then blurs) and the blur it
  // causes save once, not twice, while the Hub's answer is still on its way.
  const committed = React.useRef(value)
  React.useEffect(() => {
    setDraft(value)
    committed.current = value
  }, [value])
  const error = validate ? validate(draft) : null
  const commit = () => {
    if (error) return
    const next = draft.trim()
    if (next === value || next === committed.current) return
    committed.current = next
    onCommit(next)
  }
  const showError = error && draft !== value
  return (
    <span className="aw-committed">
      <Input
        id={id}
        aria-label={ariaLabel}
        value={draft}
        disabled={disabled}
        placeholder={placeholder}
        inputMode={numeric ? 'numeric' : undefined}
        aria-invalid={error ? true : undefined}
        title={error ?? undefined}
        style={width ? { width } : undefined}
        className={numeric ? 'tabular text-right' : undefined}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            commit()
            ;(e.target as HTMLInputElement).blur()
          }
          if (e.key === 'Escape') setDraft(value)
        }}
      />
      {suffix ? <span className="aw-committed-suffix">{suffix}</span> : null}
      {showError ? (
        <span className="aw-committed-error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  )
}

/** The text-body twin of `CommittedInput`, for a command, a list or Markdown: it grows with its
 *  content and applies when you leave it (Ctrl+Enter also commits; Escape puts the stored value
 *  back). Long text saves once per edit, not per keystroke and not behind a Save button
 *  (`settings-in-the-app-s-style-where-you-expect-them`). Surrounding whitespace is kept unless
 *  `trim` is set, since Markdown can mean it. */
export function CommittedTextarea({
  value,
  onCommit,
  validate,
  placeholder,
  id,
  ariaLabel,
  mono,
  minRows = 1,
  trim,
  disabled,
  testId,
}: {
  value: string
  onCommit: (value: string) => void
  validate?: (draft: string) => string | null
  placeholder?: string
  id?: string
  ariaLabel?: string
  mono?: boolean
  /** The height it starts at while empty or short. */
  minRows?: number
  trim?: boolean
  disabled?: boolean
  testId?: string
}) {
  const [draft, setDraft] = React.useState(value)
  const committed = React.useRef(value)
  React.useEffect(() => {
    setDraft(value)
    committed.current = value
  }, [value])
  const error = validate ? validate(draft) : null
  const commit = () => {
    if (error) return
    const next = trim ? draft.trim() : draft
    if (next === value || next === committed.current) return
    committed.current = next
    onCommit(next)
  }
  return (
    <span className="aw-committed aw-committed-block">
      <Textarea
        id={id}
        data-testid={testId}
        aria-label={ariaLabel}
        value={draft}
        disabled={disabled}
        placeholder={placeholder}
        rows={minRows}
        aria-invalid={error ? true : undefined}
        className={['aw-textarea-grow', mono ? 'font-mono' : null].filter(Boolean).join(' ')}
        style={{ minHeight: `calc(${minRows} * 1.5em + 14px)` }}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault()
            commit()
          }
          if (e.key === 'Escape') setDraft(value)
        }}
      />
      {error && draft !== value ? (
        <span className="aw-committed-error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  )
}
