import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AgentSummary } from '@/api/agents'
import { NewConversationSurface } from '@/components/agents/NewConversationSurface'
import { useConfigStore } from '@/store/configStore'
import { MODEL_CATALOG_FIXTURE } from './support/modelCatalogFixture'

/**
 * The new-conversation surface is the second composer, and the one the first message is sent
 * from. It passed no agent posture at all, so its pill read the catalog's default for every agent
 * (`the-permissions-pill-shows-the-posture-the-run-gets`, R3; F283).
 */

let roster: AgentSummary[] = []

vi.mock('@/api/agents', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/agents')>()
  return { ...actual, useAgents: () => ({ data: roster }) }
})
vi.mock('@/api/runners', () => ({
  useRunners: () => ({ data: [{ id: 'runner-claude', cli: 'claude', model: 'claude-sonnet-5' }] }),
}))
vi.mock('@/api/workspace', () => ({ useWorkspacePaths: () => ({ data: [] }) }))
vi.mock('@/api/modelCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/modelCatalog')>()
  return { ...actual, useModelCatalog: () => ({ data: MODEL_CATALOG_FIXTURE }) }
})

const fetchMock = vi.fn()
;(globalThis as unknown as { fetch: ReturnType<typeof vi.fn> }).fetch = fetchMock

function row(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'claude',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    runner: 'claude',
    runner_id: 'runner-claude',
    ...overrides,
  }
}

function renderFor(summary: AgentSummary) {
  roster = [summary]
  render(
    <NewConversationSurface
      projectId="proj-a"
      projectName="Website"
      agent={summary.name}
      onChooseAgent={vi.fn()}
      onStarted={vi.fn()}
    />,
  )
}

const permissionsPill = () => screen.getByRole('button', { name: /^Permissions:/ })

describe('the new-conversation pill shows the posture the first run gets', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    useConfigStore.setState({
      apiKey: 'aw_live_TESTKEY',
      hubUrl: 'http://hub.test',
      selectedProjectId: 'proj-a',
      isConfigured: true,
      bootstrapState: 'ready',
    })
  })

  it("reads the agent's own default", () => {
    renderFor(row({ default_permission_mode: 'manual' }))
    expect(permissionsPill()).toHaveTextContent('Ask me')
  })

  it('reads the posture at rest when the agent states none', () => {
    renderFor(row({ permission_mode_at_rest: 'acceptEdits' }))
    expect(permissionsPill()).toHaveTextContent('Edit files')
  })

  it('sends no override for what it only shows', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: 'started', conversation_id: 'conv-1' }), {
        status: 200,
      }),
    )
    renderFor(row({ default_permission_mode: 'manual' }))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'go' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send message' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    expect(body.overrides).toBeUndefined()
  })
})
