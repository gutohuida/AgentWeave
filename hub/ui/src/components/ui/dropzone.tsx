import * as React from 'react'
import { Icon } from '@/components/common/Icon'

/** File picking without the browser's "Choose File · No file chosen" button.
 *
 *  `DropZone` is the visible target (click or Enter opens the picker; files dropped on it are
 *  taken). `usePageDrop` makes a whole region accept a drop and reports whether something is
 *  being dragged over it, so a page can show its own overlay ("Drop to add to the vault"). */

export function DropZone({
  onFiles,
  accept,
  multiple = true,
  title = 'Drop files here',
  hint,
  compact,
  inputTestId,
}: {
  onFiles: (files: File[]) => void
  accept?: string
  multiple?: boolean
  title?: string
  hint?: React.ReactNode
  compact?: boolean
  /** `data-testid` on the hidden file input. */
  inputTestId?: string
}) {
  const input = React.useRef<HTMLInputElement>(null)
  const [over, setOver] = React.useState(false)
  return (
    <div data-slot="dropzone"
      role="button"
      tabIndex={0}
      className="aw-dropzone"
      data-over={over ? 'true' : 'false'}
      data-compact={compact ? 'true' : 'false'}
      onClick={() => input.current?.click()}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          input.current?.click()
        }
      }}
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setOver(false)
        onFiles(Array.from(e.dataTransfer.files))
      }}
    >
      <span className="aw-dropzone-icon" aria-hidden="true">
        <Icon name="file_plus" size={compact ? 15 : 18} />
      </span>
      <span className="min-w-0">
        <span className="aw-dropzone-title">
          {title} <span className="aw-dropzone-or">or browse</span>
        </span>
        {hint ? <span className="aw-dropzone-hint">{hint}</span> : null}
      </span>
      <input
        ref={input}
        data-testid={inputTestId}
        type="file"
        hidden
        accept={accept}
        multiple={multiple}
        onChange={(e) => {
          onFiles(Array.from(e.target.files ?? []))
          e.target.value = ''
        }}
      />
    </div>
  )
}
