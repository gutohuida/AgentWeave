import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { SettingsGroup, SettingsRow } from '@/components/ui/settings'
import { appWindowApi, type UpdateStatus } from '@/hooks/useNotifications'

/**
 * 'Update automatically when I open AgentWeave' and the Update button (change
 * `agentweave-updates-itself`). Everything comes from the launcher's window bridge, so a browser
 * tab, which has none, shows nothing. The button names the work running and applies only after the
 * operator confirms; the launcher reloads this window when the update ends.
 */
export function UpdateSettings() {
  const [status, setStatus] = React.useState<UpdateStatus | null>(null)
  const [auto, setAuto] = React.useState(true)
  const [asking, setAsking] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [note, setNote] = React.useState<string | null>(null)

  React.useEffect(() => {
    let live = true
    const read = () => {
      const api = appWindowApi()
      if (!api?.update_status) return
      api
        .update_status()
        .then((s) => {
          if (!live) return
          setStatus(s)
          setAuto(Boolean(s.auto))
        })
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

  const changeAuto = (on: boolean) => {
    setAuto(on)
    appWindowApi()
      ?.set_auto_update?.(on)
      ?.then((saved) => {
        if (!saved) setAuto(!on)
      })
      .catch(() => setAuto(!on))
  }

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
  const workText = asking ?? (status.work?.running ? status.work.description : null)

  return (
    <SettingsGroup title="Updates" description="New releases of AgentWeave from PyPI.">
      <SettingsRow
        label="Update automatically when I open AgentWeave"
        description="Opening the app upgrades it first when nothing is running. The Update button stays either way."
        control={
          <Switch
            checked={auto}
            onCheckedChange={changeAuto}
            aria-label="Update automatically when I open AgentWeave"
            data-testid="auto-update"
          />
        }
      />
      {status.available && status.latest ? (
        <SettingsRow
          label={`Version ${status.latest} is available`}
          description={workText ? `${workText}. Updating stops it.` : undefined}
          control={
            asking ? (
              <span className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setAsking(null)} data-testid="update-cancel">
                  Cancel
                </Button>
                <Button size="sm" disabled={busy} onClick={() => apply(true)} data-testid="update-confirm">
                  Stop it and update
                </Button>
              </span>
            ) : (
              <Button size="sm" disabled={busy} onClick={() => apply(false)} data-testid="update-button">
                {`Update to ${status.latest}`}
              </Button>
            )
          }
        />
      ) : null}
      {note || failure ? (
        <p className="px-4 pb-3 text-xs text-destructive" data-testid="update-failure">
          {note ? `The update did not finish: ${note}` : `The last update failed: ${failure}`}
        </p>
      ) : null}
    </SettingsGroup>
  )
}
