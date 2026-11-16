import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { appWindowApi, type UpdateStatus } from '@/hooks/useNotifications'

/**
 * The Update button (change `agentweave-updates-itself`, FR-4, FR-5): shown in the app window
 * whenever a newer version exists, whatever screen is open and whether or not work is running.
 * Pressed with work running it names the work and applies only after the operator confirms; the
 * launcher reloads the window when the update ends, and a failed update is stated here from the
 * result the launcher recorded. Mounted once beside ClosePrompt; a browser tab has no bridge, so
 * shows nothing.
 */
export function UpdateButton() {
  const [status, setStatus] = React.useState<UpdateStatus | null>(null)
  const [asking, setAsking] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [note, setNote] = React.useState<string | null>(null)
  const [dismissed, setDismissed] = React.useState(false)

  React.useEffect(() => {
    let live = true
    const read = () => {
      const api = appWindowApi()
      if (!api?.update_status) return
      api
        .update_status()
        .then((s) => live && setStatus(s))
        .catch(() => {})
    }
    read()
    window.addEventListener('pywebviewready', read)
    return () => {
      live = false
      window.removeEventListener('pywebviewready', read)
    }
  }, [])

  if (!status || !status.applicable) return null

  const apply = (confirmed: boolean) => {
    const api = appWindowApi()
    if (!api?.apply_update) return
    setBusy(true)
    setNote(null)
    api
      .apply_update(confirmed)
      .then((answer) => {
        if (answer.state === 'needs_confirm') {
          setAsking(answer.detail)
        } else {
          setAsking(null)
          setNote(answer.state === 'failed' || answer.state === 'blocked' ? answer.detail : null)
        }
      })
      .catch(() => {})
      .finally(() => setBusy(false))
  }

  const failure = status.message?.state === 'failed' ? status.message.detail : null
  const showButton = status.available && status.latest
  if (!showButton && !failure && !note) return null

  return (
    <>
      <div
        className="fixed bottom-4 right-4 z-50 flex max-w-sm flex-col items-end gap-2"
        data-testid="update-banner"
      >
        {note || (failure && !dismissed) ? (
          <p
            className="rounded-md border bg-background p-3 text-xs text-destructive shadow"
            data-testid="update-banner-failure"
            onClick={() => setDismissed(true)}
          >
            {note ? `The update did not finish: ${note}` : `The last update failed: ${failure}`}
          </p>
        ) : null}
        {showButton ? (
          <Button size="sm" disabled={busy} onClick={() => apply(false)} data-testid="update-banner-button">
            {`Update to ${status.latest}`}
          </Button>
        ) : null}
      </div>
      <Dialog open={asking !== null} onOpenChange={(open) => (open ? undefined : setAsking(null))}>
        {asking !== null ? (
          <DialogContent
            title={`Update to ${status.latest}?`}
            description={`${asking}. Updating stops it.`}
            footer={
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setAsking(null)} data-testid="update-banner-cancel">
                  Cancel
                </Button>
                <Button
                  variant="destructive"
                  disabled={busy}
                  onClick={() => apply(true)}
                  data-testid="update-banner-confirm"
                >
                  Stop it and update
                </Button>
              </div>
            }
          >
            {null}
          </DialogContent>
        ) : null}
      </Dialog>
    </>
  )
}
