import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import {
  STATUS_CONFIG,
  getStatusConfig,
  StatusDot,
} from '@/lib/agentStatus'
describe('Q6 / Q13 — lib/agentStatus: deduplicated helpers and components', () => {
  describe('STATUS_CONFIG and getStatusConfig', () => {
    it('covers the known statuses with consistent shape', () => {
      for (const key of ['running', 'stalled', 'active', 'idle', 'waiting']) {
        expect(STATUS_CONFIG[key]).toBeDefined()
        expect(STATUS_CONFIG[key].dotColor).toMatch(/^var\(--/)
        expect(typeof STATUS_CONFIG[key].pulse).toBe('boolean')
        expect(STATUS_CONFIG[key].label).toBeTruthy()
      }
    })

    it('marks running as the only pulsing status', () => {
      expect(STATUS_CONFIG.running.pulse).toBe(true)
      expect(STATUS_CONFIG.stalled.pulse).toBe(false)
      expect(STATUS_CONFIG.active.pulse).toBe(false)
      expect(STATUS_CONFIG.idle.pulse).toBe(false)
      expect(STATUS_CONFIG.waiting.pulse).toBe(false)
    })

    it('getStatusConfig returns the matching config for known statuses', () => {
      expect(getStatusConfig('running').label).toBe('Running')
      expect(getStatusConfig('waiting').dotColor).toBe('var(--amber)')
    })

    it('getStatusConfig returns a safe default for unknown statuses', () => {
      const cfg = getStatusConfig('nonexistent')
      expect(cfg.dotColor).toBe('var(--text-3)')
      expect(cfg.pulse).toBe(false)
      expect(cfg.label).toBe('nonexistent')
      expect(cfg.labelColor).toBe('var(--text-3)')
    })

    it('default fallback does not mutate STATUS_CONFIG', () => {
      // The fallback is a new object — calling getStatusConfig twice should
      // return independent objects, not a shared mutable default.
      const a = getStatusConfig('unknown-a')
      const b = getStatusConfig('unknown-b')
      expect(a).not.toBe(b)
      expect(a.label).toBe('unknown-a')
      expect(b.label).toBe('unknown-b')
    })
  })

  describe('<StatusDot />', () => {
    it('renders the static dot for an idle agent (no pulse)', () => {
      const { container } = render(<StatusDot status="idle" />)
      // The animate-ping element is a <span> child of the outer flex wrapper.
      const animating = container.querySelectorAll('.animate-ping')
      expect(animating.length).toBe(0)
    })

    it('renders the animate-ping halo for a running agent', () => {
      const { container } = render(<StatusDot status="running" />)
      const animating = container.querySelectorAll('.animate-ping')
      expect(animating.length).toBe(1)
    })

    it('uses the size class for the dot wrapper', () => {
      const { container: sm } = render(<StatusDot status="idle" size="sm" />)
      const { container: lg } = render(<StatusDot status="idle" size="lg" />)
      expect(sm.querySelector('span')?.className).toContain('h-2')
      expect(lg.querySelector('span')?.className).toContain('h-3')
    })

    it('uses the dot color from the status config', () => {
      const { container } = render(<StatusDot status="waiting" />)
      const dot = container.querySelector('span span:last-child') as HTMLElement
      expect(dot.style.background).toBe('var(--amber)')
    })
  })
})
