import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { appWindowApi } from '@/hooks/useNotifications'
import { describeWork, type CloseChoice, type WorkRunning } from '@/lib/closePrompt'

declare global {
  interface Window {
    /** Called by the app window's launcher when a close finds work running (cli._AppWindowCloser). */
    awClosePrompt?: (work: WorkRunning) => void
  }
}

/**
 * The three-way prompt the app window shows when it is closed while work runs (change
 * `agentweave-is-its-own-app-on-windows`, D4, FR-8). The launcher has already cancelled the close;
 * the answer goes back through the window's bridge, which stops it all, closes the window only, or
 * does nothing. Every way out of the dialog answers, so the launcher is never left waiting.
 * Mounted once, in App; in a browser tab nothing calls it.
 */
export function ClosePrompt() {
  const [work, setWork] = React.useState<WorkRunning | null>(null)
  const [stopping, setStopping] = React.useState(false)

  React.useEffect(() => {
    window.awClosePrompt = (next) => {
      setStopping(false)
      setWork(next)
    }
    return () => {
      delete window.awClosePrompt
    }
  }, [])

  const answer = (choice: CloseChoice) => {
    if (choice === 'stop') setStopping(true)
    else setWork(null)
    appWindowApi()?.close_choice?.(choice)?.catch(() => {})
  }

  return (
    <Dialog open={work !== null} onOpenChange={(open) => (open ? undefined : stopping ? undefined : answer('cancel'))}>
      {work ? (
        <DialogContent
          title="AgentWeave is still working"
          description={`${describeWork(work)}. Closing the window stops AgentWeave.`}
          footer={
            <div className="flex flex-wrap justify-end gap-2" data-testid="close-prompt-choices">
              <Button variant="ghost" onClick={() => answer('cancel')} disabled={stopping}>
                Cancel
              </Button>
              <Button variant="outline" onClick={() => answer('keep')} disabled={stopping}>
                Keep running in the background
              </Button>
              <Button variant="destructive" onClick={() => answer('stop')} disabled={stopping}>
                {stopping ? 'Stopping…' : 'Stop it all and close'}
              </Button>
            </div>
          }
        >
          {work.turn_agents?.length ? (
            <ul className="text-xs" style={{ color: 'var(--text-2)' }} data-testid="close-prompt-turns">
              {work.turn_agents.map((turn, i) => (
                <li key={`${turn.project}-${turn.agent}-${i}`}>
                  {turn.agent} in {turn.project}
                </li>
              ))}
            </ul>
          ) : null}
        </DialogContent>
      ) : null}
    </Dialog>
  )
}
