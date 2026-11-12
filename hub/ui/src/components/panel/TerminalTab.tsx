import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { LocationSwitch, type PanelLocation } from './LocationSwitch'
import '@/styles/panel-tabs.css'

export interface TerminalTabProps {
  agent: string
  location: PanelLocation
  onLocationChange: (next: PanelLocation) => void
  /** The directory the shell runs in, as the operator would recognise it. */
  directory: string
  /** The shell's name ("PowerShell", "bash"), shown beside the directory. */
  shell: string
  /** False when the Hub is reached from another machine: no terminal is offered, and why is said. */
  available: boolean
  onRestart: () => void
  /** The terminal surface itself. The app mounts the real terminal emulator here; the mock a recording. */
  children?: React.ReactNode
}

/** The side panel's Terminal tab: one shell, in the agent's worktree or the project root. A page
 *  reload ends it and starts a fresh one (operator, 2026-11-12), which the footer says. */
export function TerminalTab({ agent, location, onLocationChange, directory, shell, available, onRestart, children }: TerminalTabProps) {
  if (!available) {
    return (
      <div className="aw-ptab" data-testid="terminal-tab">
        <div className="aw-ptab-empty">
          <span className="aw-ptab-empty-icon">
            <Icon name="lock" size={18} />
          </span>
          <p>The terminal opens only on the computer AgentWeave runs on.</p>
          <p className="aw-ptab-empty-hint">You are using AgentWeave from another computer. A terminal here would let anyone who can reach this page run commands on the computer AgentWeave runs on, so it is not offered.</p>
        </div>
      </div>
    )
  }
  return (
    <div className="aw-ptab aw-term" data-testid="terminal-tab">
      <div className="aw-ptab-head aw-term-head">
        <div className="aw-ptab-controls">
          <LocationSwitch agent={agent} value={location} onChange={onLocationChange} />
          <Button variant="ghost" size="xs" onClick={onRestart} title="End this shell and start a new one">
            <Icon name="restart_alt" size={13} />
            Restart
          </Button>
        </div>
        <div className="aw-term-where" title={directory}>
          <Icon name="terminal" size={12} />
          <span className="aw-term-shell">{shell}</span>
          <span className="aw-term-dir">{directory}</span>
        </div>
      </div>
      <div className="aw-term-surface" role="region" aria-label="Terminal">
        {children}
      </div>
      <p className="aw-term-foot">Reloading the page ends this shell and starts a new one.</p>
    </div>
  )
}
