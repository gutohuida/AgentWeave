import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { ProjectManagerModal } from '@/components/projects/ProjectManagerModal'
import { joinProjectPath, pathSeparator, projectNameProblem } from '@/lib/projectTarget'

const createMutate = vi.fn()
const openMutate = vi.fn()
const nativeDialogAvailability = vi.fn()
const nativeDialogMutate = vi.fn()

vi.mock('@/api/fsBrowse', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/fsBrowse')>()),
  useDirectoryListing: () => ({
    data: {
      path: '/home/projects',
      parent: '/home',
      entries: [{ name: 'agentweave', path: '/home/projects/agentweave' }],
    },
    isLoading: false,
  }),
}))

vi.mock('@/api/projects', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/projects')>()),
  useCreateProject: () => ({ mutate: createMutate, isPending: false, error: null, reset: vi.fn() }),
  useOpenProject: () => ({ mutate: openMutate, isPending: false, error: null, reset: vi.fn() }),
}))

vi.mock('@/api/nativeDialog', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/nativeDialog')>()),
  useNativeDialogAvailability: () => nativeDialogAvailability(),
  useOpenNativeDialog: () => ({ mutate: nativeDialogMutate, isPending: false }),
}))

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

function renderCreate() {
  return render(<ProjectManagerModal mode="create" onClose={vi.fn()} onComplete={vi.fn()} />, {
    wrapper,
  })
}

function fillCreate(parent: string, name: string) {
  fireEvent.change(screen.getByLabelText('Create it in'), { target: { value: parent } })
  fireEvent.change(screen.getByLabelText('Project name'), { target: { value: name } })
}

const preview = () => screen.getByTestId('project-path-preview').textContent

beforeEach(() => {
  vi.clearAllMocks()
  nativeDialogAvailability.mockReturnValue({ data: { available: false } })
})

describe('creating a project takes a parent and a name', () => {
  it('asks for a parent and a name, not a path to splice', () => {
    renderCreate()

    expect(screen.getByLabelText('Create it in')).toBeInTheDocument()
    expect(screen.getByLabelText('Project name')).toBeInTheDocument()
    // The separate optional display name is gone in create mode: the folder name and the
    // project name are one decision, and asking twice is the confusion being removed.
    expect(screen.queryByLabelText(/Display name/)).not.toBeInTheDocument()
  })

  it('submits the composed target as the path, and sends no name', () => {
    renderCreate()
    fillCreate('/home/projects', 'my-app')

    fireEvent.click(screen.getByTestId('confirm-project-action'))

    // Asserted on the actual payload: the defect being fixed is that what the operator saw
    // and what was sent had drifted apart.
    expect(createMutate).toHaveBeenCalledTimes(1)
    expect(createMutate.mock.calls[0][0]).toEqual({ path: '/home/projects/my-app' })
    expect(createMutate.mock.calls[0][0]).not.toHaveProperty('name')
  })

  it('previews the exact path it will submit', () => {
    renderCreate()
    fillCreate('/home/projects', 'my-app')

    expect(preview()).toBe('/home/projects/my-app')

    fireEvent.click(screen.getByTestId('confirm-project-action'))
    expect(createMutate.mock.calls[0][0].path).toBe(preview())
  })

  it('composes with the separator style the operator supplied', () => {
    renderCreate()
    fillCreate('C:\\Users\\me\\projects', 'my-app')

    expect(preview()).toBe('C:\\Users\\me\\projects\\my-app')
  })

  it('tolerates a trailing separator on the parent', () => {
    renderCreate()
    fillCreate('/home/projects/', 'my-app')

    expect(preview()).toBe('/home/projects/my-app')
  })

  it('says what the name will be used for', () => {
    renderCreate()
    expect(screen.getByText('This names the new folder and the project.')).toBeInTheDocument()
  })
})

describe('a project name is a name, not a path', () => {
  it.each([
    ['nested/thing', /single folder name/],
    ['nested\\thing', /single folder name/],
    ['..', /already exists/],
    ['.', /already exists/],
  ])('refuses %s and fires no mutation', (bad, message) => {
    renderCreate()
    fillCreate('/home/projects', bad)

    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(screen.getByTestId('confirm-project-action')).toBeDisabled()

    fireEvent.click(screen.getByTestId('confirm-project-action'))
    expect(createMutate).not.toHaveBeenCalled()
  })

  it('refuses rather than rewriting a bad name into an acceptable one', () => {
    renderCreate()
    fillCreate('/home/projects', 'nested/thing')

    // Silently creating `nested-thing` would put a directory somewhere the operator never
    // saw, which is the same surprise this change exists to remove.
    expect(screen.getByLabelText('Project name')).toHaveValue('nested/thing')
    expect(preview()).not.toContain('nested-thing')
  })

  it('cannot be submitted with a parent but no name', () => {
    renderCreate()
    fireEvent.change(screen.getByLabelText('Create it in'), { target: { value: '/home/projects' } })

    expect(screen.getByTestId('confirm-project-action')).toBeDisabled()
  })

  it('does not scold before anything has been typed', () => {
    renderCreate()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('browsing supplies the parent in create mode', () => {
  it('fills the parent from the in-Hub browser, leaving the name to the operator', () => {
    renderCreate()

    fireEvent.click(screen.getByRole('button', { name: 'Open directory browser' }))
    fireEvent.click(screen.getByRole('button', { name: 'Choose this directory' }))

    expect(screen.getByLabelText('Create it in')).toHaveValue('/home/projects')
    expect(screen.getByLabelText('Project name')).toHaveValue('')
  })

  it('fills the parent from the host folder dialog', () => {
    nativeDialogAvailability.mockReturnValue({ data: { available: true } })
    nativeDialogMutate.mockImplementation((_arg, opts) =>
      opts.onSuccess({ outcome: 'chosen', path: 'C:\\chosen\\parent' }),
    )
    renderCreate()

    fireEvent.click(screen.getByRole('button', { name: 'Choose a folder' }))

    // What the picker returns is now directly usable: it is the parent, and a folder that
    // exists is exactly what a picker can return.
    expect(screen.getByLabelText('Create it in')).toHaveValue('C:\\chosen\\parent')
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'app' } })
    expect(preview()).toBe('C:\\chosen\\parent\\app')
  })
})

describe('open mode is unchanged', () => {
  function renderOpen() {
    return render(<ProjectManagerModal mode="open" onClose={vi.fn()} onComplete={vi.fn()} />, {
      wrapper,
    })
  }

  it('still takes a directory path and an optional display name', () => {
    renderOpen()

    expect(screen.getByLabelText('Directory path')).toBeInTheDocument()
    expect(screen.queryByLabelText('Project name')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Display name')).toBeInTheDocument()
  })

  it('submits the directory as typed, with the display name when given', () => {
    renderOpen()
    fireEvent.change(screen.getByLabelText('Directory path'), { target: { value: '/existing/dir' } })
    fireEvent.change(screen.getByLabelText('Display name'), { target: { value: 'Legible Name' } })

    fireEvent.click(screen.getByTestId('confirm-project-action'))

    expect(openMutate.mock.calls[0][0]).toEqual({ path: '/existing/dir', name: 'Legible Name' })
  })

  it('omits the name when the display name is left blank', () => {
    renderOpen()
    fireEvent.change(screen.getByLabelText('Directory path'), { target: { value: '/existing/dir' } })

    fireEvent.click(screen.getByTestId('confirm-project-action'))

    expect(openMutate.mock.calls[0][0]).toEqual({ path: '/existing/dir' })
  })
})

describe('projectTarget helpers', () => {
  it('detects the separator from the parent', () => {
    expect(pathSeparator('C:\\Users\\me')).toBe('\\')
    expect(pathSeparator('/home/me')).toBe('/')
    expect(pathSeparator('\\\\server\\share')).toBe('\\')
  })

  it('returns empty when either half is missing, so nothing is previewed or sent', () => {
    expect(joinProjectPath('', 'name')).toBe('')
    expect(joinProjectPath('/parent', '')).toBe('')
    expect(joinProjectPath('  ', '  ')).toBe('')
  })

  it('accepts an ordinary name', () => {
    expect(projectNameProblem('my-app')).toBeNull()
    expect(projectNameProblem('  my app  ')).toBeNull()
  })
})
