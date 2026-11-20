import * as React from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { LocationSwitch, type PanelLocation } from './LocationSwitch'
import '@/styles/panel-tabs.css'

/** A shell the Hub found installed on its computer (spec `a-terminal-in-the-side-panel`, FR-4). */
export interface ShellOption {
  id: string
  /** "PowerShell 7", "Git Bash", "Ubuntu-24.04". */
  label: string
  /** Where it was found, or for WSL that it is a Linux distribution. */
  detail?: string
  wsl?: boolean
}

/** One open shell of this conversation. */
export interface OpenShell {
  id: string
  option: ShellOption
  location: PanelLocation
  /** The directory as the shell sees it: a WSL shell's is the translated `/mnt/c/...` path. */
  directory: string
  /** Null while it runs; the exit code once it has ended by itself. */
  exitCode: number | null
}

export type TerminalUnavailable = 'remote' | 'docker'

export interface TerminalTabProps {
  agent: string
  /** Set when no terminal is offered, and why (FR-1, FR-3). */
  unavailable?: TerminalUnavailable | null
  shells: OpenShell[]
  activeId: string | null
  onSelect: (id: string) => void
  onClose: (id: string) => void
  onRestart: (id: string) => void
  /** Shells found on the Hub's computer, and the operator's last pick (preselected). */
  options: ShellOption[]
  lastPick: { optionId: string; location: PanelLocation } | null
  onOpen: (optionId: string, location: PanelLocation) => void
  /** Null when the agent has a worktree; otherwise why the worktree choice is unavailable. */
  worktreeUnavailable?: string | null
  /** Sends the selection, or the visible screen, to the composer, unsent (FR-11). */
  onSendToAgent: (id: string) => void
  limit?: number
  /** The active shell's terminal surface. The app mounts the terminal emulator; the mock a recording. */
  children?: React.ReactNode
}

const UNAVAILABLE: Record<TerminalUnavailable, { title: string; hint: string }> = {
  remote: {
    title: 'The terminal opens only on the computer AgentWeave runs on.',
    hint: 'You are using AgentWeave from another computer. A terminal here would let anyone who can reach this page run commands on the computer AgentWeave runs on, so it is not offered.',
  },
  docker: {
    title: 'The terminal is not available in Docker mode.',
    hint: 'This AgentWeave runs inside a container, so a shell would open there, not on your computer. Run AgentWeave natively to use the terminal.',
  },
}

/** The side panel's Terminal tab: up to four shells per conversation, each in the agent's worktree or
 *  the project root. They keep running while the operator is elsewhere; closing, Restart, a page
 *  reload or the Hub stopping ends them and everything they started. The conversation's agent can
 *  read them but never type into them. */
export function TerminalTab(props: TerminalTabProps) {
  const { agent, unavailable, shells, activeId, onSelect, onClose, onRestart, onSendToAgent, limit = 4, children } = props
  if (unavailable) {
    const text = UNAVAILABLE[unavailable]
    return (
      <div className="aw-ptab" data-testid="terminal-tab" data-unavailable={unavailable}>
        <div className="aw-ptab-empty">
          <span className="aw-ptab-empty-icon">
            <Icon name="lock" size={18} />
          </span>
          <p>{text.title}</p>
          <p className="aw-ptab-empty-hint">{text.hint}</p>
        </div>
      </div>
    )
  }
  const active = shells.find((s) => s.id === activeId) ?? null
  const full = shells.length >= limit
  return (
    <div className="aw-ptab aw-term" data-testid="terminal-tab">
      <div className="aw-term-strip" role="tablist" aria-label="Shells">
        {shells.map((s) => (
          <div key={s.id} className="aw-term-shelltab" data-active={s.id === activeId ? 'true' : undefined} data-ended={s.exitCode !== null ? 'true' : undefined}>
            <button type="button" role="tab" aria-selected={s.id === activeId} className="aw-term-shelltab-main" onClick={() => onSelect(s.id)} title={`${s.option.label} · ${s.directory}`}>
              <span className="aw-term-dot" aria-hidden />
              <span className="aw-term-shelltab-name">{s.option.label}</span>
              <span className="aw-term-shelltab-where">{s.location === 'worktree' ? 'worktree' : 'root'}</span>
            </button>
            <button type="button" className="aw-term-shelltab-close" aria-label={`Close ${s.option.label}`} title="Close this shell and end everything it started" onClick={() => onClose(s.id)}>
              <Icon name="close" size={12} />
            </button>
          </div>
        ))}
        <NewShellMenu {...props} full={full} />
      </div>
      {active ? (
        <>
          <div className="aw-ptab-head aw-term-head">
            <div className="aw-term-where" title={active.directory}>
              <Icon name="terminal" size={12} />
              <span className="aw-term-shell">{active.option.label}</span>
              {active.option.wsl && <span className="aw-term-chip">WSL</span>}
              <span className="aw-term-dir">{active.directory}</span>
            </div>
            <div className="aw-ptab-controls">
              <Button variant="ghost" size="xs" onClick={() => onSendToAgent(active.id)} title={`Put your selection, or what is on screen, into the message to ${agent}. Nothing is sent until you send it.`}>
                <Icon name="send" size={13} />
                Send to {agent}
              </Button>
              <Button variant="ghost" size="xs" onClick={() => onRestart(active.id)} title="End this shell and everything it started, and open the same shell again">
                <Icon name="restart_alt" size={13} />
                Restart
              </Button>
            </div>
          </div>
          <div className="aw-term-surface" role="region" aria-label={`Terminal: ${active.option.label}`}>
            {children}
          </div>
          {active.exitCode !== null && (
            <div className="aw-term-ended" role="status">
              <span>
                Ended with exit code <b>{active.exitCode}</b>.
              </span>
              <Button variant="outline" size="xs" onClick={() => onRestart(active.id)}>
                Open it again
              </Button>
            </div>
          )}
        </>
      ) : (
        <div className="aw-ptab-empty">
          <span className="aw-ptab-empty-icon">
            <Icon name="terminal" size={18} />
          </span>
          <p>No shell open.</p>
          <p className="aw-ptab-empty-hint">Open one with + above, in {agent}’s worktree or the project root.</p>
        </div>
      )}
      <p className="aw-term-foot">
        <span>
          {shells.length} of {limit} shells
        </span>
        <span aria-hidden>·</span>
        <span title={`${agent} can read the last 500 lines of each of these shells. It cannot type into them.`}>
          <Icon name="visibility" size={11} /> {agent} can read these
        </span>
        <span aria-hidden>·</span>
        <span>They keep running while you are elsewhere; reloading the page ends them.</span>
      </p>
    </div>
  )
}

/** + : where the new shell opens, then which shell. The last pick is marked and listed first. */
function NewShellMenu({ agent, options, lastPick, onOpen, worktreeUnavailable, limit = 4, full }: TerminalTabProps & { full: boolean }) {
  const [where, setWhere] = React.useState<PanelLocation>(lastPick?.location ?? (worktreeUnavailable ? 'root' : 'worktree'))
  const ordered = lastPick ? [...options].sort((a, b) => Number(b.id === lastPick.optionId) - Number(a.id === lastPick.optionId)) : options
  if (full) {
    return (
      <span className="aw-term-new" data-disabled="true" title={`${limit} shells is the limit for one thread. Close one to open another.`}>
        <Icon name="add" size={14} />
        <span className="aw-term-limit">Limit of {limit} reached</span>
      </span>
    )
  }
  return (
    <Menu>
      <MenuTrigger asChild>
        <button type="button" className="aw-term-new" aria-label="New shell" title="New shell">
          <Icon name="add" size={14} />
        </button>
      </MenuTrigger>
      <MenuContent align="start" className="aw-term-menu">
        <MenuLabel>Open in</MenuLabel>
        <div className="aw-term-menu-where" onKeyDown={(e) => e.stopPropagation()}>
          <LocationSwitch agent={agent} value={where} onChange={(next) => (next === 'worktree' && worktreeUnavailable ? undefined : setWhere(next))} />
          {worktreeUnavailable && <p className="aw-term-menu-why">{worktreeUnavailable}</p>}
        </div>
        <MenuSeparator />
        <MenuLabel>Shell</MenuLabel>
        {ordered.map((o) => (
          <MenuItem key={o.id} icon={o.wsl ? 'hard_drive' : 'terminal'} onSelect={() => onOpen(o.id, where)}>
            <span className="aw-term-menu-item">
              <span>{o.label}</span>
              {lastPick?.optionId === o.id && <span className="aw-term-chip">last used</span>}
              {o.detail && <span className="aw-term-menu-detail">{o.detail}</span>}
            </span>
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  )
}
