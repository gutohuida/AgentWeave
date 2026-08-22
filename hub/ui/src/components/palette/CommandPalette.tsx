import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import * as Dialog from '@radix-ui/react-dialog'
import { formatDistanceToNow } from 'date-fns'
import { Icon } from '@/components/common/Icon'
import { conversationLabel, type AgentConversation } from '@/api/agentChat'
import type { SpecDocumentRecord } from '@/api/spec'
import type { Task } from '@/api/tasks'
import { agentColorVars } from '@/lib/agentColors'
import { hubDate } from '@/lib/hubTime'

export interface CommandPaletteAgent {
  name: string
  color_index?: number | null
  status?: string
  display_model?: string
}

interface CommandPaletteProps {
  agents: CommandPaletteAgent[]
  conversations: AgentConversation[]
  documents: SpecDocumentRecord[]
  tasks: Task[]
  onOpenConversation: (agent: string, conversationId: string) => void
  onOpenAgent: (agent: string) => void
  onOpenDocument: (path: string) => void
  onOpenTask: (taskId: string) => void
}

/**
 * Cmd+K / Ctrl+K quick navigation (D3). Reads data the app already loaded elsewhere — no fetch
 * of its own — and hands every selection to the same navigation functions the sidebar and other
 * screens already call, so opening something from here is indistinguishable from opening it any
 * other way.
 *
 * Requiring a modifier key is what makes the "typing a literal k in the composer" guard
 * unnecessary as a separate check: a bare `k` keystroke, wherever focus is, never matches this
 * listener, so the shortcut composes with every text field in the app for free.
 */
export function CommandPalette({
  agents,
  conversations,
  documents,
  tasks,
  onOpenConversation,
  onOpenAgent,
  onOpenDocument,
  onOpenTask,
}: CommandPaletteProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey)) return
      if (event.key.toLowerCase() !== 'k') return
      event.preventDefault()
      setOpen((value) => !value)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  const close = () => {
    setOpen(false)
    setQuery('')
  }

  const highlight = (text: string) => {
    const needle = query.trim()
    if (!needle) return text
    const index = text.toLocaleLowerCase().indexOf(needle.toLocaleLowerCase())
    if (index < 0) return text
    return <>{text.slice(0, index)}<mark>{text.slice(index, index + needle.length)}</mark>{text.slice(index + needle.length)}</>
  }

  const conversationRows = useMemo(
    () =>
      conversations.map((conversation) => {
        // `conversationLabel` returns the conversation's whole opening prompt. Putting that in
        // cmdk's `value` made every conversation match nearly any query — a prompt that says
        // "Implement task-1f82d976 (Deadline-based admission decision) against spec document
        // spdoc-…" matches the task's title, the document, and the agent's name, so typing any of
        // them ranked six conversations above the thing actually named. Measured: with a task
        // title typed, all six top hits were conversations and Enter never reached the task.
        //
        // The search text is the conversation's opening words, not its whole body. A long prompt
        // also dilutes cmdk's score, so truncating makes the remaining matches rank properly.
        const full = conversationLabel(conversation)
        const title = full.length > 60 ? `${full.slice(0, 60).trimEnd()}…` : full
        return {
          conversation,
          label: `${conversation.agent} — ${title}`,
          searchText: `${conversation.agent} ${title}`,
        }
      }),
    [conversations],
  )

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      className="command-palette lifted-surface fixed left-1/2 top-[15vh] z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden"
      overlayClassName="command-palette-overlay fixed inset-0 z-50"
    >
      <Dialog.Title className="sr-only">Command palette</Dialog.Title>
      <Dialog.Description className="sr-only">Search the current project's agents, tasks, specification documents, and conversations.</Dialog.Description>
      <Command.Input autoFocus value={query} onValueChange={setQuery} placeholder="Search conversations, agents, documents, tasks…" />
      <Command.List>
        <Command.Empty>
          <span className="block font-medium" style={{ color: 'var(--text-2)' }}>No matches</span>
          <span className="mt-1 block">Try an agent, task, document, or conversation name.</span>
        </Command.Empty>

        {agents.length > 0 && (
          <Command.Group heading="Agents">
            {agents.map((agent) => (
              <Command.Item
                key={agent.name}
                value={`agent-${agent.name}`}
                onSelect={() => {
                  onOpenAgent(agent.name)
                  close()
                }}
              >
                <span className="palette-agent-icon" style={{ background: agentColorVars(agent.color_index).tint, color: agentColorVars(agent.color_index).accent, borderColor: agentColorVars(agent.color_index).border }}><Icon name="smart_toy" size={13} /></span>
                <span className="palette-row-main">
                  <span className="palette-row-title">{highlight(agent.name)}</span>
                  <span className="palette-row-sub">{agent.display_model ?? 'Agent'}{agent.status ? ` · ${agent.status}` : ''}</span>
                </span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {tasks.length > 0 && (
          <Command.Group heading="Tasks">
            {tasks.map((task) => (
              <Command.Item
                key={task.id}
                value={`task-${task.id}-${task.title}`}
                onSelect={() => {
                  onOpenTask(task.id)
                  close()
                }}
              >
                <Icon name="task_alt" size={14} className="palette-row-icon" style={{ color: 'var(--text-3)' }} />
                <span className="palette-row-main"><span className="palette-row-title">{highlight(task.title)}</span><span className="palette-row-sub">{task.assignee ? `Assigned to ${task.assignee}` : 'Unassigned'} · updated {formatDistanceToNow(hubDate(task.updated), { addSuffix: true })}</span></span>
                <span className="palette-status-chip" data-status={task.status}>{task.status.replace(/_/g, ' ')}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}
        {documents.length > 0 && (
          <Command.Group heading="Spec documents">
            {documents.map((document) => (
              <Command.Item
                key={document.id}
                value={`document-${document.id}-${document.title}`}
                onSelect={() => {
                  onOpenDocument(document.path)
                  close()
                }}
              >
                <Icon name="description" size={14} className="palette-row-icon" style={{ color: 'var(--text-3)' }} />
                <span className="palette-row-main"><span className="palette-row-title">{highlight(document.title)}</span><span className="palette-row-sub">{document.kind.replace(/-/g, ' ')} · updated {formatDistanceToNow(hubDate(document.updated_at), { addSuffix: true })}</span></span>
                <span className="palette-status-chip" data-status={document.phase}>{document.phase}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        {conversationRows.length > 0 && (
          <Command.Group heading="Conversations">
            {conversationRows.map(({ conversation, label, searchText }) => (
              <Command.Item
                key={conversation.id}
                value={`conversation-${conversation.id}-${searchText}`}
                onSelect={() => {
                  onOpenConversation(conversation.agent, conversation.id)
                  close()
                }}
              >
                <span className="palette-agent-dot" style={{ background: agentColorVars(agents.find((item) => item.name === conversation.agent)?.color_index).accent }} />
                <span className="palette-row-main"><span className="palette-row-title">{highlight(label)}</span><span className="palette-row-sub">Conversation · updated {formatDistanceToNow(hubDate(conversation.updated_at), { addSuffix: true })}</span></span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

      </Command.List>
      <div className="palette-footer" aria-hidden="true">
        <span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span>
        <span><kbd>↵</kbd> Open</span>
        <span><kbd>Esc</kbd> Close</span>
      </div>
    </Command.Dialog>
  )
}
