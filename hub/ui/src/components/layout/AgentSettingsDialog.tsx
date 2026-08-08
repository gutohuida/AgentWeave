import * as Dialog from '@radix-ui/react-dialog'
import { useAgents } from '@/api/agents'
import { AgentInfoTab } from '@/components/agents/AgentInfoTab'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'

interface AgentSettingsDialogProps {
  /** The agent whose settings are open, or null for closed. */
  agent: string | null
  onClose: () => void
  /** Focused when the dialog closes — the row menu's trigger, which invoked it. */
  onCloseFocus?: () => void
}

/**
 * Agent settings, hosted by the rail.
 *
 * Where this lives is the requirement, not a detail: settings must open "without unmounting or
 * navigating away from the conversation". The rail outlives the content area, so a dialog
 * mounted here cannot take the open conversation down with it — which is exactly what the old
 * "Agent details" item in the conversation's own overflow menu risked.
 */
export function AgentSettingsDialog({ agent, onClose, onCloseFocus }: AgentSettingsDialogProps) {
  const { data: roster = [] } = useAgents()
  const summary = agent ? roster.find((candidate) => candidate.name === agent) ?? null : null

  return (
    <Dialog.Root open={agent !== null} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay style={{ position: 'fixed', inset: 0, background: 'var(--scrim)', zIndex: 60 }} />
        <Dialog.Content
          aria-label={`${agent ?? ''} settings`}
          data-testid="agent-settings-dialog"
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            onCloseFocus?.()
          }}
          style={{
            position: 'fixed',
            top: '10vh',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 'min(520px, 92vw)',
            maxHeight: '78vh',
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            overflow: 'hidden',
            zIndex: 61,
          }}
        >
          <Dialog.Title style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>
            {agent} settings
          </Dialog.Title>
          <Dialog.Description className="sr-only">
            Status, sessions, configuration, and statistics for {agent}.
          </Dialog.Description>
          <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: '1px solid var(--border)' }}>
            <span className="text-[13px] font-medium" style={{ color: 'var(--text)' }}>{agent}</span>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon-xs" aria-label="Close settings">
                <Icon name="close" size={16} />
              </Button>
            </Dialog.Close>
          </div>
          {summary ? (
            <AgentInfoTab agent={summary} />
          ) : (
            <div className="px-4 py-6 text-xs" style={{ color: 'var(--text-3)' }}>
              This agent is no longer in the roster.
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
