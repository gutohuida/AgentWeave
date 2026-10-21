import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ReachGrantsChips } from '@/components/settings/ReachGrantsChips'
import type { ReachGrants } from '@/api/projects'

function Editor({ onSave }: { onSave: (grants: ReachGrants | null) => void }) {
  const [grants, setGrants] = useState<ReachGrants | null>({ roots: [], hosts: ['localhost:*'] })
  return (
    <>
      <ReachGrantsChips
        grants={grants}
        onChange={(next) => {
          setGrants(next)
          onSave(next)
        }}
      />
      <button type="button">Elsewhere</button>
    </>
  )
}

async function typeHost(user: ReturnType<typeof userEvent.setup>, host: string) {
  await user.click(screen.getByRole('button', { name: /add/i }))
  await user.click(await screen.findByRole('menuitem', { name: /a host/i }))
  await user.type(screen.getByLabelText('Host'), host)
}

describe('F796: a host typed but not added is not lost', () => {
  it('adds the host still in the field when focus leaves it', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<Editor onSave={onSave} />)
    await typeHost(user, 'registry.npmjs.org')
    await user.click(screen.getByRole('button', { name: 'Elsewhere' }))
    expect(onSave).toHaveBeenCalledWith({ roots: [], hosts: ['localhost:*', 'registry.npmjs.org'] })
    expect(screen.queryByLabelText('Host')).toBeNull()
  })

  it('discards it on Cancel', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<Editor onSave={onSave} />)
    await typeHost(user, 'registry.npmjs.org')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onSave).not.toHaveBeenCalled()
  })
})
