import * as React from 'react'
import type { VaultSettings, VaultVisibility } from '@/api/vault'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { MenuSelect } from '@/components/ui/menu'
import { Field } from '@/components/ui/settings'
import type { VaultActionResult } from './VaultReview'

/** Where entries are kept. Was a form permanently on the vault page ("Where entries go"); it is
 *  set once, so it lives behind the library's gear. */
export function VaultStorageDialog({
  open,
  onOpenChange,
  settings,
  error: readError,
  onSave,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  settings: VaultSettings
  /** Why the settings could not be read. */
  error?: string | null
  /** Answers `{ error }` with the Hub's reason when it refuses; the dialog stays open. */
  onSave: (next: { default_visibility: VaultVisibility; private_location: string | null }) => VaultActionResult | void
}) {
  const [visibility, setVisibility] = React.useState<VaultVisibility>(settings.default_visibility)
  const [location, setLocation] = React.useState(settings.private_location ?? '')
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (!open) return
    setVisibility(settings.default_visibility)
    setLocation(settings.private_location ?? '')
    setError(null)
  }, [open, settings])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Vault storage"
        description="Where new entries are kept unless you choose otherwise when adding one."
        width={520}
        footer={
          <>
            <DialogClose asChild>
              <Button variant="ghost" size="sm">
                Cancel
              </Button>
            </DialogClose>
            <Button
              variant="primary"
              size="sm"
              data-testid="vault-settings-save"
              disabled={pending || Boolean(readError)}
              onClick={async () => {
                setPending(true)
                setError(null)
                const result = await onSave({ default_visibility: visibility, private_location: location.trim() || null })
                setPending(false)
                if (result?.error) setError(result.error)
                else onOpenChange(false)
              }}
            >
              {pending ? 'Saving…' : 'Save'}
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {readError ? (
            <p className="vault-note" data-tone="amber" role="alert">
              {readError}
            </p>
          ) : null}
          <Field label="New entries go">
            <MenuSelect
              label="New entries go"
              testId="vault-settings-default"
              value={visibility}
              onChange={setVisibility}
              maxWidth={480}
              options={[
                { value: 'tracked', label: 'In the repository', detail: 'Committed with the project, so teammates and their agents see it.', icon: 'call_split' },
                { value: 'private', label: 'Private, this machine', detail: 'Kept outside the repository. Only agents on this machine read it.', icon: 'lock' },
              ]}
            />
          </Field>
          <Field
            label="Private entries folder"
            htmlFor="vault-private-location"
            hint={location.trim() ? 'Outside the repository.' : 'Leave it empty to use the folder shown in the field.'}
            error={error ?? undefined}
          >
            <Input
              id="vault-private-location"
              data-testid="vault-settings-location"
              value={location}
              placeholder={settings.effective_private_location}
              onChange={(e) => setLocation(e.target.value)}
              className="font-mono text-[12px]"
            />
          </Field>
        </div>
      </DialogContent>
    </Dialog>
  )
}
