import * as React from 'react'
import { readableApiError } from '@/api/client'
import { useCreateSpecDocument } from '@/api/spec'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/settings'
import { capabilityPathFor } from './model'

/** The spec list's way to start a capability: a title, the path it gives, and the Hub's answer. */
export function NewCapabilityAction({ onOpen }: { onOpen: (path: string) => void }) {
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <button data-slot="filter-chip" type="button" className="aw-sp-chip" data-testid="new-capability" onClick={() => setOpen(true)}>
        <Icon name="add" size={13} />
        New capability
      </button>
      {open ? (
        <NewCapabilityDialog
          onClose={() => setOpen(false)}
          onCreated={(path) => {
            setOpen(false)
            onOpen(path)
          }}
        />
      ) : null}
    </>
  )
}

function NewCapabilityDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (path: string) => void }) {
  const create = useCreateSpecDocument()
  const [title, setTitle] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const path = capabilityPathFor(title)

  async function confirm() {
    if (!path || create.isPending) return
    setError(null)
    try {
      const created = await create.mutateAsync({ path, title: title.trim(), kind: 'capability' })
      onCreated(created.path)
    } catch (refusal) {
      setError(readableApiError(refusal, 'The Hub refused to create this capability.'))
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        title="New capability"
        description="A capability describes what the product does now. It starts empty; finished changes are folded into it."
        width={480}
        footer={
          <>
            <DialogClose asChild>
              <Button variant="ghost" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button variant="primary" size="sm" data-testid="new-capability-confirm" disabled={!path || create.isPending} onClick={confirm}>
              {create.isPending ? 'Creating…' : 'Create capability'}
            </Button>
          </>
        }
      >
        <Field label="Title">
          <Input
            autoFocus
            data-testid="new-capability-title"
            aria-label="Title"
            value={title}
            maxLength={512}
            onChange={(event) => {
              setTitle(event.target.value)
              setError(null)
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                void confirm()
              }
            }}
          />
        </Field>
        <p className="mt-2 text-xs" style={{ color: 'var(--text-3)' }} data-testid="new-capability-path">
          {path ? (
            <>
              Created at <code>{path}</code>
            </>
          ) : title.trim() ? (
            'This title has no letters or digits to make a path from.'
          ) : (
            'The title gives the path.'
          )}
        </p>
        {error ? (
          <p role="alert" className="mt-2 text-xs" data-testid="new-capability-error" style={{ color: 'var(--amber)' }}>
            {error}
          </p>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
