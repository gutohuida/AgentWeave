import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { useDialogFocus } from '@/hooks/useDialogFocus'
import { tint } from '@/lib/colorTint'
import type { Charter, CharterCreate } from '@/api/charters'

/** The charter dialog: a name and the Markdown body. The save mutation and its refusal are the
 *  caller's; the refusal is rendered inside the form that caused it (F187). */
export function CharterForm({
  title,
  initial,
  isPending,
  error,
  onCancel,
  onSubmit,
}: {
  title: string
  initial: Charter | null
  isPending: boolean
  error: string | null
  onCancel: () => void
  onSubmit: (values: CharterCreate) => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [content, setContent] = useState(initial?.content ?? '')
  const panelRef = useRef<HTMLDivElement>(null)
  useDialogFocus(true, panelRef, onCancel)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'var(--scrim)' }}
      onClick={onCancel}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-label={title}
        aria-modal="true"
        aria-labelledby="charter-form-title"
        className="lifted-surface surface-enter w-[min(672px,calc(100vw-32px))] p-5"
        style={{ background: 'var(--surface)' }}
        onClick={(event) => event.stopPropagation()}
      >
        <h2 id="charter-form-title" className="mb-4 text-base font-medium" style={{ color: 'var(--text)' }}>{title}</h2>
        <label className="mb-1 block text-xs" style={{ color: 'var(--text-3)' }} htmlFor="charter-name">
          Name
        </label>
        <Input
          id="charter-name"
          aria-label="Charter name"
          data-dialog-initial-focus
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mb-3 px-3 py-2 text-sm"
        />
        <label className="mb-1 block text-xs" style={{ color: 'var(--text-3)' }} htmlFor="charter-content">
          Content
        </label>
        <Textarea
          id="charter-content"
          aria-label="Charter content"
          value={content}
          onChange={(event) => setContent(event.target.value)}
          className="h-72 px-3 py-2 font-mono text-sm"
        />
        {error && (
          <div
            role="alert"
            className="mt-3 rounded-md px-3 py-2 text-xs"
            style={{ background: tint('var(--red)'), color: 'var(--red)' }}
          >
            {error}
          </div>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onSubmit({ name: name.trim(), content })}
            disabled={isPending || !name.trim()}
          >
            {isPending ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}
