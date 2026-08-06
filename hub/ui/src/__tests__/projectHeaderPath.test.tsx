import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ProjectHeader } from '@/components/layout/ProjectHeader'

const DEEP_PATH = 'C:\\Users\\op\\projects\\suite\\service\\api\\testbed\\two-codex-agents\\workspace'

describe('ProjectHeader path — structure, not a joined string (composer/chrome refinement §5)', () => {
  it('renders a multi-segment path as multiple elements, not one text node', () => {
    render(
      <ProjectHeader
        projectName="Website"
        pathDisplay="C:\\Users\\op\\project"
        agentCount={2}
        directoryAvailable
        onOpenSetup={vi.fn()}
      />,
    )
    // Each rendered segment is queryable on its own — a single joined text node would not
    // expose "project" as a distinct match separate from "Users" or "op".
    expect(screen.getByText('C:\\')).toBeInTheDocument()
    expect(screen.getByText('Users')).toBeInTheDocument()
    expect(screen.getByText('project')).toBeInTheDocument()
  })

  it('keeps the agent count and the path out of the same line element', () => {
    render(
      <ProjectHeader
        projectName="Website"
        pathDisplay="C:\\Users\\op\\project"
        agentCount={3}
        directoryAvailable
        onOpenSetup={vi.fn()}
      />,
    )
    const agentLine = screen.getByText('3 agents')
    const pathSegment = screen.getByText('project')
    expect(agentLine).not.toBe(pathSegment)
    // Neither element contains the other's text — they are genuinely separate lines, not
    // one <p> with the agent count and path both inside it.
    expect(agentLine.textContent).not.toContain('project')
    expect(pathSegment.closest('p')?.textContent).not.toContain('agent')
  })

  it('elides a deep path in the middle and keeps its head and tail, with the full path on hover', () => {
    render(
      <ProjectHeader
        projectName="Website"
        pathDisplay={DEEP_PATH}
        agentCount={1}
        directoryAvailable
        onOpenSetup={vi.fn()}
      />,
    )
    expect(screen.getByText('…')).toBeInTheDocument()
    expect(screen.getByText('C:\\')).toBeInTheDocument()
    expect(screen.getByText('workspace')).toBeInTheDocument()
    // Elided out of the middle — neither of these mid-path segments should be present.
    expect(screen.queryByText('suite')).not.toBeInTheDocument()
    expect(screen.queryByText('service')).not.toBeInTheDocument()
    expect(screen.getByText('…').closest('p')).toHaveAttribute('title', DEEP_PATH)
  })

  it('renders no path row when directoryAvailable is false', () => {
    render(
      <ProjectHeader
        projectName="Website"
        pathDisplay="C:\\Users\\op\\project"
        agentCount={1}
        directoryAvailable={false}
        onOpenSetup={vi.fn()}
      />,
    )
    expect(screen.getByText('Directory unavailable')).toBeInTheDocument()
    expect(screen.queryByText('project')).not.toBeInTheDocument()
  })
})
