import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { OutsideWritesLine } from '@/components/agents/AgentTimeline'
import { ReachGrantsChips } from '@/components/settings/ReachGrantsChips'

describe('reach-1019: granted reach and the outside-write line', () => {
  it('adds a host and the temp folder', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { rerender } = render(<ReachGrantsChips grants={{ roots: [], hosts: [] }} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /Add/ }))
    await user.click(await screen.findByRole('menuitem', { name: /A host/ }))
    await user.type(screen.getByLabelText('Host'), 'localhost:*')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(onChange).toHaveBeenLastCalledWith({ roots: [], hosts: ['localhost:*'] })

    rerender(<ReachGrantsChips grants={{ roots: [], hosts: [] }} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /Add/ }))
    await user.click(await screen.findByRole('menuitem', { name: /The temp folder/ }))
    expect(onChange).toHaveBeenLastCalledWith({
      roots: [{ path: '{temp}', access: 'readwrite' }],
      hosts: [],
    })
  })

  it('adds no blank folder, and saves nothing granted as null', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    const { rerender } = render(<ReachGrantsChips grants={{ roots: [], hosts: [] }} onChange={onChange} />)
    await user.click(screen.getByRole('button', { name: /Add/ }))
    await user.click(await screen.findByRole('menuitem', { name: /A folder/ }))
    await user.type(screen.getByLabelText('Folder path'), '   ')
    await user.click(screen.getByRole('button', { name: 'Add' }))
    expect(onChange).not.toHaveBeenCalled()

    rerender(<ReachGrantsChips grants={{ roots: [], hosts: ['localhost:*'] }} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Remove localhost:*' }))
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('switches a folder between read and read & write', () => {
    const onChange = vi.fn()
    render(<ReachGrantsChips grants={{ roots: [{ path: '{project}', access: 'read' }], hosts: [] }} onChange={onChange} />)
    expect(screen.getByText('Project folder')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'read' }))
    expect(onChange).toHaveBeenLastCalledWith({ roots: [{ path: '{project}', access: 'readwrite' }], hosts: [] })
  })

  it('shows where a run wrote outside, and nothing for a clean or unobserved run', () => {
    const { rerender } = render(
      <OutsideWritesLine
        writes={[
          { kind: 'unknown', tool: 'Write', path: 'C:/elsewhere/x.txt', calls: 1 },
          { kind: 'overflow', destinations: 3 },
        ]}
      />,
    )
    expect(screen.getByTestId('run-outside-writes').textContent).toBe(
      'Wrote outside its workspace: C:/elsewhere/x.txt and 3 more',
    )
    rerender(<OutsideWritesLine writes={[]} />)
    expect(screen.queryByTestId('run-outside-writes')).toBeNull()
    rerender(<OutsideWritesLine writes={null} />)
    expect(screen.queryByTestId('run-outside-writes')).toBeNull()
  })
})
