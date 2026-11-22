import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PoolEditor } from '@/components/agents/pool/PoolEditor'
import type { AgentPoolEntry } from '@/api/agentPool'
import type { ModelCatalogResponse } from '@/api/modelCatalog'

/**
 * The pool editor's Add a model (`a-profile-s-pool-and-a-new-chat-can-use-any-model-of-any-
 * provider`, FR-1, F1200): it offers every catalog provider and every model of it by display name,
 * not only the models the project's runners already run, with that provider's efforts, and adds the
 * choice by provider and model so the Hub can make the runner a model no runner uses needs.
 */

const effort = (...ids: string[]) => ({
  id: 'effort',
  label: 'Effort',
  kind: 'enum' as const,
  values: ids.map((id) => ({ id, label: id[0]!.toUpperCase() + id.slice(1) })),
  default: null,
  apply: { style: 'flag' as const, template: '--effort {value}' },
})
const model = (id: string, label: string, isDefault = false) => ({ id, label, aliases: [], context_window: null, default: isDefault })

const CATALOG: ModelCatalogResponse = {
  providers: [
    {
      provider: 'claude',
      label: 'Claude Code',
      models: [model('claude-opus-5-5', 'Opus 5.5'), model('claude-sonnet-5-5', 'Sonnet 5.5', true), model('claude-haiku-5-5', 'Haiku 5.5')],
      controls: [effort('low', 'high', 'max')],
    },
    { provider: 'codex', label: 'Codex', models: [model('gpt-6-luna', 'gpt-6-luna', true), model('gpt-6-sol', 'gpt-6-sol')], controls: [effort('low', 'xhigh')] },
    { provider: 'copilot', label: 'Copilot', models: [model('gpt-6', 'GPT-6', true)], controls: [] },
  ],
}

// Builder runs only on Haiku 5.5, as a fresh project's profiles do.
const POOL: AgentPoolEntry[] = [
  { id: 'pool-1', runner_id: 'runner-haiku', runner_name: 'Haiku', cli: 'claude', model: 'claude-haiku-5-5', effort: null, default: true },
]

function renderEditor(onAdd = vi.fn(), pool = POOL) {
  render(<PoolEditor agentName="Builder" pool={pool} catalog={CATALOG} onAdd={onAdd} onRemove={vi.fn()} onMakeDefault={vi.fn()} />)
  return onAdd
}

async function pick(menu: string, option: string) {
  await userEvent.click(screen.getByRole('button', { name: menu }))
  await userEvent.click(screen.getByRole('menuitemradio', { name: option }))
}

async function listed(menu: string) {
  await userEvent.click(screen.getByRole('button', { name: menu }))
  const texts = screen.getAllByRole('menuitemradio').map((item) => item.querySelector('.truncate')?.textContent)
  await userEvent.keyboard('{Escape}')
  return texts
}

describe('the pool editor offers the whole catalog', () => {
  it('lists every provider, and under each every one of its models by display name', async () => {
    renderEditor()
    expect(await listed('Provider')).toEqual(['Claude Code', 'Codex', 'Copilot'])
    expect(screen.getByRole('button', { name: 'Model to add to Builder' })).toBeDisabled()

    await pick('Provider', 'Claude Code')
    expect(await listed('Model to add to Builder')).toEqual(['Opus 5.5', 'Sonnet 5.5', 'Haiku 5.5'])
    await pick('Provider', 'Codex')
    expect(await listed('Model to add to Builder')).toEqual(['gpt-6-luna', 'gpt-6-sol'])
    await pick('Provider', 'Copilot')
    expect(await listed('Model to add to Builder')).toEqual(['GPT-6'])
  })

  it('offers that provider’s efforts plus the usual one, and none where it declares none', async () => {
    renderEditor()
    await pick('Provider', 'Codex')
    expect(await listed('Effort')).toEqual(['Its usual effort', 'Low', 'Xhigh'])
    await pick('Provider', 'Copilot')
    expect(screen.getByRole('button', { name: 'Effort' })).toBeDisabled()
  })

  it('adds a model no runner of the project uses, by provider, model and effort', async () => {
    const onAdd = renderEditor()
    await pick('Provider', 'Claude Code')
    await pick('Model to add to Builder', 'Opus 5.5')
    await pick('Effort', 'High')
    await userEvent.click(screen.getByRole('button', { name: /^Add\b/ }))
    expect(onAdd).toHaveBeenCalledWith({ provider: 'claude', model: 'claude-opus-5-5', effort: 'high' })
  })

  it('refuses a model already in the pool at that effort before asking the Hub', async () => {
    const onAdd = renderEditor()
    await pick('Provider', 'Claude Code')
    await pick('Model to add to Builder', 'Haiku 5.5')
    expect(screen.getByText('It is already in the list.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Add\b/ })).toBeDisabled()
    expect(onAdd).not.toHaveBeenCalled()
  })

  it('shows an added entry by its model’s name and effort', () => {
    renderEditor(vi.fn(), [
      ...POOL,
      { id: 'pool-2', runner_id: 'runner-opus', runner_name: 'Claude Code — Opus 5.5', cli: 'claude', model: 'claude-opus-5-5', effort: 'high', default: false },
    ])
    expect(screen.getByRole('list', { name: 'Models Builder may run on' })).toHaveTextContent('Opus 5.5 · High')
  })
})
