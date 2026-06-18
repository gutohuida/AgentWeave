import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  contextBarColor,
  STATUS_CONFIG,
  getStatusConfig,
  StatusDot,
  DevRoleTagList,
} from '@/lib/agentStatus'
import type { AgentSummary } from '@/api/agents'

function makeAgent(overrides: Partial<AgentSummary> = {}): AgentSummary {
  return {
    name: 'test-agent',
    status: 'idle',
    message_count: 0,
    active_task_count: 0,
    ...overrides,
  }
}

describe('Q6 / Q13 — lib/agentStatus: deduplicated helpers and components', () => {
  describe('contextBarColor', () => {
    it('returns var(--red) when warning is true (regardless of percent)', () => {
      expect(contextBarColor(0, true)).toBe('var(--red)')
      expect(contextBarColor(50, true)).toBe('var(--red)')
      expect(contextBarColor(99, true)).toBe('var(--red)')
    })

    it('returns var(--red) when percent >= 70 and no warning', () => {
      expect(contextBarColor(70, false)).toBe('var(--red)')
      expect(contextBarColor(95, false)).toBe('var(--red)')
    })

    it('returns var(--amber) when percent is in the 40..69 range', () => {
      expect(contextBarColor(40, false)).toBe('var(--amber)')
      expect(contextBarColor(55, false)).toBe('var(--amber)')
      expect(contextBarColor(69, false)).toBe('var(--amber)')
    })

    it('returns var(--green) when percent < 40 and no warning', () => {
      expect(contextBarColor(0, false)).toBe('var(--green)')
      expect(contextBarColor(39, false)).toBe('var(--green)')
    })
  })

  describe('STATUS_CONFIG and getStatusConfig', () => {
    it('covers the four known statuses with consistent shape', () => {
      for (const key of ['running', 'active', 'idle', 'waiting']) {
        expect(STATUS_CONFIG[key]).toBeDefined()
        expect(STATUS_CONFIG[key].dotColor).toMatch(/^var\(--/)
        expect(typeof STATUS_CONFIG[key].pulse).toBe('boolean')
        expect(STATUS_CONFIG[key].label).toBeTruthy()
      }
    })

    it('marks running as the only pulsing status', () => {
      expect(STATUS_CONFIG.running.pulse).toBe(true)
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

  describe('<DevRoleTagList />', () => {
    it('renders nothing when the agent has neither dev_roles nor dev_role', () => {
      const { container } = render(<DevRoleTagList agent={makeAgent()} />)
      expect(container.firstChild).toBeNull()
    })

    it('renders one pill per role from dev_roles[] with the matching label', () => {
      render(
        <DevRoleTagList
          agent={makeAgent({
            dev_roles: ['backend_dev', 'tech_lead'],
            dev_role_labels: ['Backend Dev', 'Tech Lead'],
          })}
        />
      )
      expect(screen.getByText('Backend Dev')).toBeInTheDocument()
      expect(screen.getByText('Tech Lead')).toBeInTheDocument()
    })

    it('falls back to the role id when no matching label is present', () => {
      render(
        <DevRoleTagList agent={makeAgent({ dev_roles: ['qa_engineer'] })} />
      )
      expect(screen.getByText('qa_engineer')).toBeInTheDocument()
    })

    it('renders the legacy single dev_role with its label', () => {
      render(
        <DevRoleTagList
          agent={makeAgent({ dev_role: 'qa', dev_role_label: 'QA Engineer' })}
        />
      )
      expect(screen.getByText('QA Engineer')).toBeInTheDocument()
      expect(screen.queryByText('qa')).not.toBeInTheDocument()
    })

    it('falls back to the role id when no label is provided (legacy)', () => {
      render(<DevRoleTagList agent={makeAgent({ dev_role: 'qa' })} />)
      expect(screen.getByText('qa')).toBeInTheDocument()
    })

    it('caps visible pills to maxItems when provided', () => {
      render(
        <DevRoleTagList
          agent={makeAgent({
            dev_roles: ['a', 'b', 'c', 'd'],
            dev_role_labels: ['A', 'B', 'C', 'D'],
          })}
          maxItems={2}
        />
      )
      expect(screen.getByText('A')).toBeInTheDocument()
      expect(screen.getByText('B')).toBeInTheDocument()
      expect(screen.queryByText('C')).not.toBeInTheDocument()
      expect(screen.queryByText('D')).not.toBeInTheDocument()
    })

    it('uses the purple color scheme on every pill', () => {
      const { container } = render(
        <DevRoleTagList agent={makeAgent({ dev_roles: ['x'] })} />
      )
      const pill = container.querySelector('span') as HTMLElement
      expect(pill.style.color).toBe('var(--purple)')
      // jsdom normalizes the rgba spacing, so match the digits with a regex.
      expect(pill.style.background).toMatch(/rgba\(\s*168\s*,\s*85\s*,\s*247\s*,\s*0\.1\s*\)/)
    })
  })
})
