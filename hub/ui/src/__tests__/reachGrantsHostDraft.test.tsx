import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ReachGrantsEditor } from '@/components/environment/ReachGrantsEditor'
import type { ReachGrants } from '@/api/projects'

function Form({ onSave }: { onSave: (grants: ReachGrants) => void }) {
  const [grants, setGrants] = useState<ReachGrants>({ roots: [], hosts: ['localhost:*'] })
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        onSave(grants)
      }}
    >
      <ReachGrantsEditor grants={grants} onChange={setGrants} />
      <button type="submit">Save settings</button>
    </form>
  )
}

describe('F796: a host typed but not added is not lost on save', () => {
  it('saves the host that is still in the field when Save is pressed', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<Form onSave={onSave} />)
    await user.type(screen.getByLabelText('Granted host'), 'registry.npmjs.org')
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(onSave).toHaveBeenCalledWith({ roots: [], hosts: ['localhost:*', 'registry.npmjs.org'] })
    expect((screen.getByLabelText('Granted host') as HTMLInputElement).value).toBe('')
  })
})
