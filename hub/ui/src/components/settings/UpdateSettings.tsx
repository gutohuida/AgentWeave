import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { SettingsGroup, SettingsRow } from '@/components/ui/settings'
import { appWindowApi, updateTarget, type UpdateStatus } from '@/hooks/useNotifications'

/** The checkout's own switch (change `a-development-checkout-updates-the-same-way`, FR-10). */
const CHECKOUT_AUTO_LABEL = 'Restart onto master automatically when I open AgentWeave'

/**
 * 'Update automatically when I open AgentWeave' and the Update button (change
 * `agentweave-updates-itself`). Everything comes from the launcher's window bridge, so a browser
 * tab, which has none, shows nothing. The button names the work running and applies only after the
 * operator confirms; the launcher reloads this window when the update ends.
 *
 * A Hub run from a git checkout (`a-development-checkout-updates-the-same-way`) shows its own
 * switch, off by default, how far local master is ahead, and offers the restart onto master only
 * on master; its prompt names any uncommitted files.
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
          setAuto(s.kind === 'checkout' ? Boolean(s.auto_checkout) : Boolean(s.auto))
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

  const checkout = status?.kind === 'checkout'
  if (!status || (!status.applicable && !checkout)) return null

  const changeAuto = (on: boolean) => {
    setAuto(on)
    appWindowApi()
      ?.set_auto_update?.(on, checkout ? 'checkout' : 'pip')
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
  const target = updateTarget(status)
  const label = checkout ? CHECKOUT_AUTO_LABEL : 'Update automatically when I open AgentWeave'
  let workText: string | null
  if (checkout) {
    workText = asking
  } else {
    const running = asking ?? (status.work?.running ? status.work.description : null)
    workText = running ? `${running}. Updating stops it.` : null
  }

  return (
    <SettingsGroup
      title="Updates"
      description={
        checkout
          ? 'This AgentWeave runs from a git checkout; updating restarts it onto local master.'
          : 'New releases of AgentWeave from PyPI.'
      }
    >
      <SettingsRow
        label={label}
        description={
          checkout
            ? 'Off: opening the app never restarts it. On: it restarts onto master first when master is ahead, the checkout is clean and nothing is running. The Update button stays either way.'
            : 'Opening the app upgrades it first when nothing is running. The Update button stays either way.'
        }
        control={
          <Switch
            checked={auto}
            onCheckedChange={changeAuto}
            aria-label={label}
            data-testid={checkout ? 'auto-update-checkout' : 'auto-update'}
          />
        }
      />
      {checkout && status.summary ? (
        <p className="px-4 pb-3 text-xs text-muted-foreground" data-testid="update-summary">
          {status.summary}
        </p>
      ) : null}
      {status.available && target ? (
        <SettingsRow
          label={checkout ? `master is ahead: ${target}` : `Version ${target} is available`}
          description={workText ?? undefined}
          control={
            asking ? (
              <span className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setAsking(null)} data-testid="update-cancel">
                  Cancel
                </Button>
                <Button size="sm" disabled={busy} onClick={() => apply(true)} data-testid="update-confirm">
                  {checkout ? 'Restart onto master' : 'Stop it and update'}
                </Button>
              </span>
            ) : (
              <Button size="sm" disabled={busy} onClick={() => apply(false)} data-testid="update-button">
                {`Update to ${target}`}
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
