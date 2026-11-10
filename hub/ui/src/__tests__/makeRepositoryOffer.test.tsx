import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MakeRepositoryOffer } from '@/components/settings/MakeRepositoryOffer'

/** 'Make this a git repository' (`a-new-project-starts-as-a-git-repository-with-an-agents-md`,
 *  FR-6): the list first, the repository only on confirmation. */
describe('MakeRepositoryOffer', () => {
  const handlers = () => ({ onStart: vi.fn(), onCancel: vi.fn(), onConfirm: vi.fn() })

  it('offers the action and asks for the list on start, confirming nothing', () => {
    const on = handlers()
    render(<MakeRepositoryOffer started={false} {...on} />)
    fireEvent.click(screen.getByRole('button', { name: /make this a git repository/i }))
    expect(on.onStart).toHaveBeenCalledOnce()
    expect(on.onConfirm).not.toHaveBeenCalled()
  })

  it('cannot be confirmed until the list has been read', () => {
    render(<MakeRepositoryOffer started preview={null} {...handlers()} />)
    expect(screen.getByRole('button', { name: /make the repository/i })).toBeDisabled()
  })

  it('names every previewed file and AGENTS.md, and confirms exactly the list shown', () => {
    const on = handlers()
    render(
      <MakeRepositoryOffer
        started
        preview={{ files: ['README.md', 'src/main.py'], agents_md: true }}
        {...on}
      />,
    )
    const list = screen.getByRole('list', { name: /files the first commit would hold/i })
    expect(within(list).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'AGENTS.md (new)',
      'README.md',
      'src/main.py',
    ])
    fireEvent.click(screen.getByRole('button', { name: /make the repository/i }))
    expect(on.onConfirm).toHaveBeenCalledWith(['README.md', 'src/main.py'])
  })

  it('says why a confirm was refused', () => {
    render(
      <MakeRepositoryOffer
        started
        preview={{ files: ['a.txt'], agents_md: false }}
        refusal="the folder's files changed since the preview"
        {...handlers()}
      />,
    )
    expect(screen.getByText(/files changed since the preview/)).toBeInTheDocument()
    expect(screen.queryByText('AGENTS.md (new)')).toBeNull()
  })
})
