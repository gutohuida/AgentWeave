// Unsent composer text, namespaced by project, agent, and AgentWeave conversation.
// Stored under one key as a flat map, mirroring the bounded-persistence pattern used
// for spec preferences (specPreferences.ts): corrupt or unreadable storage resets to
// empty rather than propagating a bad value, and a write failure is swallowed so the
// composer keeps working without persistence.

const STORAGE_KEY = 'aw.composer.drafts.v1'

function draftKey(projectId: string, agent: string, conversationId: string | null): string {
  return `${projectId}::${agent}::${conversationId ?? '__new__'}`
}

function readDrafts(): Record<string, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as unknown
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {}
    return parsed as Record<string, string>
  } catch {
    return {}
  }
}

function writeDrafts(drafts: Record<string, string>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(drafts))
  } catch {
    // Persisting drafts is best-effort; the composer must still work without it.
  }
}

export function getComposerDraft(
  projectId: string,
  agent: string,
  conversationId: string | null,
): string {
  const value = readDrafts()[draftKey(projectId, agent, conversationId)]
  return typeof value === 'string' ? value : ''
}

export function setComposerDraft(
  projectId: string,
  agent: string,
  conversationId: string | null,
  text: string,
): void {
  const drafts = readDrafts()
  const key = draftKey(projectId, agent, conversationId)
  if (text) {
    drafts[key] = text
  } else {
    delete drafts[key]
  }
  writeDrafts(drafts)
}

export function clearComposerDraft(
  projectId: string,
  agent: string,
  conversationId: string | null,
): void {
  setComposerDraft(projectId, agent, conversationId, '')
}
