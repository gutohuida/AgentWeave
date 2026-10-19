import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { OutsideWritesLine } from '@/components/agents/AgentTimeline'
import { ReachGrantsEditor } from '@/components/environment/ReachGrantsEditor'
import { cleanGrants } from '@/lib/reachGrants'

describe('reach-1019: granted reach and the outside-write line', () => {
  it('saves no blank root, and nothing granted as null', () => {
    expect(cleanGrants({ roots: [{ path: '  ', access: 'read' }], hosts: [] })).toBeNull()
    expect(
      cleanGrants({ roots: [{ path: ' {temp} ', access: 'readwrite' }], hosts: ['localhost:*'] }),
    ).toEqual({ roots: [{ path: '{temp}', access: 'readwrite' }], hosts: ['localhost:*'] })
    expect(cleanGrants(null)).toBeNull()
  })

  it('adds a host and the temp folder', () => {
    const onChange = vi.fn()
    render(<ReachGrantsEditor grants={{ roots: [], hosts: [] }} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Granted host'), { target: { value: 'localhost:*' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add host' }))
    expect(onChange).toHaveBeenLastCalledWith({ roots: [], hosts: ['localhost:*'] })
    fireEvent.click(screen.getByRole('button', { name: 'Add the temp folder' }))
    expect(onChange).toHaveBeenLastCalledWith({
      roots: [{ path: '{temp}', access: 'readwrite' }],
      hosts: [],
    })
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
