import { describe, expect, it } from 'vitest'
import { AGENT_COLOR_PALETTE_SIZE, agentColorVars } from '@/lib/agentColors'

describe('agentColorVars', () => {
  it('maps index 0 to the first hue', () => {
    expect(agentColorVars(0)).toEqual({
      accent: 'var(--agent-1)',
      tint: 'var(--agent-1-tint)',
      border: 'var(--agent-1-border)',
    })
  })

  it('cycles once the palette is exhausted', () => {
    expect(agentColorVars(AGENT_COLOR_PALETTE_SIZE)).toEqual(agentColorVars(0))
    expect(agentColorVars(AGENT_COLOR_PALETTE_SIZE + 3)).toEqual(agentColorVars(3))
  })

  it('falls back to a neutral treatment when no colour is assigned', () => {
    const neutral = { accent: 'var(--text-3)', tint: 'var(--surface-2)', border: 'var(--border)' }
    expect(agentColorVars(null)).toEqual(neutral)
    expect(agentColorVars(undefined)).toEqual(neutral)
  })

  it('gives adjacent indices distinct hues', () => {
    const distinctAccents = new Set(
      Array.from({ length: AGENT_COLOR_PALETTE_SIZE }, (_, i) => agentColorVars(i).accent),
    )
    expect(distinctAccents.size).toBe(AGENT_COLOR_PALETTE_SIZE)
  })
})
