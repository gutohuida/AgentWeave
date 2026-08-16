import { useEffect, useMemo, useState } from 'react'
import { Command } from 'cmdk'
import { Icon } from '@/components/common/Icon'
import { conversationLabel, type AgentConversation } from '@/api/agentChat'
import type { SpecDocumentRecord } from '@/api/spec'
import type { Task } from '@/api/tasks'

export interface CommandPaletteAgent {
  name: string
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

  const close = () => setOpen(false)

  const conversationRows = useMemo(
    () =>
      conversations.map((conversation) => ({
        conversation,
        label: `${conversation.agent} — ${conversationLabel(conversation)}`,
      })),
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
      <Command.Input autoFocus placeholder="Search conversations, agents, documents, tasks…" />
      <Command.List>
        <Command.Empty>No matches.</Command.Empty>

        {conversationRows.length > 0 && (
          <Command.Group heading="Conversations">
            {conversationRows.map(({ conversation, label }) => (
              <Command.Item
                key={conversation.id}
                value={`conversation-${conversation.id}-${label}`}
                onSelect={() => {
                  onOpenConversation(conversation.agent, conversation.id)
                  close()
                }}
              >
                <Icon name="chat" size={14} style={{ color: 'var(--text-3)' }} />
                <span>{label}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

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
                <Icon name="smart_toy" size={14} style={{ color: 'var(--text-3)' }} />
                <span>{agent.name}</span>
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
                <Icon name="description" size={14} style={{ color: 'var(--text-3)' }} />
                <span>{document.title}</span>
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
                <Icon name="task_alt" size={14} style={{ color: 'var(--text-3)' }} />
                <span>{task.title}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}
      </Command.List>
    </Command.Dialog>
  )
}
