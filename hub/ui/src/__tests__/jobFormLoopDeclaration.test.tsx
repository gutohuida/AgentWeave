/**
 * The operator can say what approving a loop's tasks does to their own main branch.
 *
 * `work_needs_evidence` decides whether a loop's approved work is merged from the commit a reviewer
 * accepted or from the task's own branch tip. Without a control here it would be an agent-only
 * setting — `create_loop` takes it, this form is the only operator-facing surface that creates a
 * loop — and its default would be one the operator could neither see nor opt out of.
 *
 * The opt-in rule is the same one `stop_when_queue_empties` already has, and for the same reason a
 * comment in `JobForm` gives: a controlled checkbox always renders a value, so sending it
 * unconditionally would opt every job into being a loop the Hub's `purpose is not None` rule would
 * then honour. The Hub refuses it on a job that is not becoming a loop, so this is not merely tidy.
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { JobForm } from '@/components/jobs/JobForm'

vi.mock('@/api/agents', () => ({
  useAgents: () => ({ data: [{ name: 'builder' }] }),
}))

function fill() {
  fireEvent.change(screen.getByPlaceholderText(/Daily Standup/i), {
    target: { value: 'A job' },
  })
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'builder' } })
  fireEvent.change(screen.getByPlaceholderText(/message to send/i), { target: { value: 'go' } })
}

describe('JobForm — the loop declaration', () => {
  it('sends nothing about evidence when the job is not a loop', () => {
    const onSubmit = vi.fn()
    render(<JobForm onSubmit={onSubmit} onCancel={() => {}} isPending={false} />)
    fill()
    fireEvent.click(screen.getByRole('button', { name: /^Create/ }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('work_needs_evidence')
  })

  it('sends what the control says once the job is a loop', () => {
    const onSubmit = vi.fn()
    render(<JobForm onSubmit={onSubmit} onCancel={() => {}} isPending={false} />)
    fill()
    fireEvent.click(screen.getByText(/make this a loop/i))
    fireEvent.click(screen.getByTestId('job-form-work-needs-evidence'))
    fireEvent.click(screen.getByRole('button', { name: /^Create/ }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0].work_needs_evidence).toBe(true)
  })

  it('sends false — not nothing — when the loop section was opened and left alone', () => {
    // The distinction the Hub keeps: "the operator said no" and "the operator did not say" are
    // different rows, and only the second resolves to the product's current default.
    const onSubmit = vi.fn()
    render(<JobForm onSubmit={onSubmit} onCancel={() => {}} isPending={false} />)
    fill()
    fireEvent.click(screen.getByText(/make this a loop/i))
    fireEvent.click(screen.getByRole('button', { name: /^Create/ }))

    expect(onSubmit.mock.calls[0][0].work_needs_evidence).toBe(false)
  })

  it('says what the setting decides, in terms of the main branch', () => {
    render(<JobForm onSubmit={() => {}} onCancel={() => {}} isPending={false} />)
    fireEvent.click(screen.getByText(/make this a loop/i))

    expect(screen.getByText(/main branch/)).toBeTruthy()
  })
})
