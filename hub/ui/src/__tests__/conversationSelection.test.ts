import { describe, expect, it } from 'vitest'
import {
  agentDestination,
  isNewConversationDestination,
  newConversationDestination,
  NEW_CONVERSATION_ID,
  parseDestination,
  projectDestination,
  resolveConversationSelection,
  serializeDestination,
  type SelectableConversation,
} from '@/lib/navigation'

/** Ordered most recent activity first, as the project listing endpoint returns them. */
const conversations: SelectableConversation[] = [
  { id: 'conv-codex-new', agent: 'codex' },
  { id: 'conv-claude-new', agent: 'claude' },
  { id: 'conv-claude-old', agent: 'claude' },
]

describe('which conversation a destination opens', () => {
  it('opens the one the destination names', () => {
    const destination = agentDestination('proj-1', 'claude', 'conv-claude-old')
    expect(resolveConversationSelection(destination, conversations)).toBe('conv-claude-old')
  })

  it('opens the agent’s most recent when the destination names none', () => {
    const destination = agentDestination('proj-1', 'claude')
    expect(resolveConversationSelection(destination, conversations)).toBe('conv-claude-new')
  })

  it('does not borrow another agent’s conversation', () => {
    const destination = agentDestination('proj-1', 'haiku')
    expect(resolveConversationSelection(destination, conversations)).toBeNull()
  })

  it('opens nothing while the conversation list has not arrived', () => {
    expect(resolveConversationSelection(agentDestination('proj-1', 'claude'), [])).toBeNull()
  })

  it('leaves the new-conversation surface alone once the list resolves', () => {
    const destination = newConversationDestination('proj-1', 'claude')
    expect(isNewConversationDestination(destination)).toBe(true)
    // The bug this sentinel exists to prevent: an operator who asked for an empty composer must
    // not have their most recent thread opened underneath them a render later.
    expect(resolveConversationSelection(destination, conversations)).toBeNull()
  })

  it('is not a conversation question at all on a project destination', () => {
    expect(resolveConversationSelection(projectDestination('proj-1'), conversations)).toBeNull()
    expect(isNewConversationDestination(projectDestination('proj-1'))).toBe(false)
  })

  it('round-trips the new-conversation surface through the URL', () => {
    const destination = newConversationDestination('proj-1', 'claude')
    const search = serializeDestination(destination)
    expect(search).toContain(`conversation=${NEW_CONVERSATION_ID}`)
    expect(parseDestination(search)).toEqual(destination)
  })
})
