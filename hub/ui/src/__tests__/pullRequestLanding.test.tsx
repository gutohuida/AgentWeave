/**
 * PR landing in the app (`a-build-lands-as-one-pull-request`, FR-1, FR-11, FR-13): the Build dialog
 * offers 'A pull request' only where the project has it on; the build card and a task show the PR's
 * link, state, last-asked time and GitHub's error; 'main is behind GitHub' offers Update and says
 * why when it cannot.
 */
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuildPlanDialog } from '@/components/spec/BuildPlanDialog'
import { MainBehindNotice, PullRequestLine } from '@/components/spec/PullRequestLine'
import { useConfigStore } from '@/store/configStore'

const posts: string[] = []
let main: Record<string, unknown> | null = null

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    getJson: vi.fn(async () => ({ main })),
    postJson: vi.fn(async (path: string) => {
      posts.push(path)
      if (path.endsWith('/main/update')) return { main: { ...main, behind: true, reason: 'main is checked out with uncommitted changes' } }
      return { pull_request: null, main }
    }),
  }
})

beforeEach(() => {
  posts.length = 0
  main = null
  useConfigStore.setState({
    apiKey: 'aw_live_TESTKEY',
    hubUrl: 'http://hub.test',
    selectedProjectId: 'proj-test',
    isConfigured: true,
    bootstrapState: 'ready',
  })
})
afterEach(cleanup)

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

function dialog(pullRequestLanding: boolean) {
  return (
    <BuildPlanDialog
      open
      onOpenChange={() => {}}
      title="Demo"
      approve={false}
      recommended={undefined}
      tasks={[]}
      agents={[]}
      now={new Date('2026-11-07T00:00:00Z')}
      pullRequestLanding={pullRequestLanding}
      onConfirm={() => {}}
    />
  )
}

describe('the Build dialog', () => {
  it('offers only main and nowhere where PR landing is off', () => {
    wrap(dialog(false))
    expect(screen.queryByText('A pull request')).toBeNull()
    expect(screen.getByText('The main branch')).toBeTruthy()
    expect(screen.getByText('Nowhere')).toBeTruthy()
  })

  it('offers a pull request where it is on', () => {
    wrap(dialog(true))
    expect(screen.getByText('A pull request')).toBeTruthy()
  })
})

describe('the pull request line', () => {
  it('shows link, state and last-asked time, and checks now', async () => {
    wrap(
      <PullRequestLine
        buildId="build-1"
        pullRequest={{ number: 7, url: 'https://github.com/o/r/pull/7', state: 'draft', last_asked_at: '2026-11-07T00:00:00Z', error: null }}
      />,
    )
    expect(screen.getByTestId('build-pull-request-link').getAttribute('href')).toBe('https://github.com/o/r/pull/7')
    expect(screen.getByTestId('build-pull-request-state').textContent).toBe('draft')
    expect(screen.getByTestId('build-pull-request-asked').textContent).toMatch(/asked GitHub/)
    expect(screen.queryByTestId('build-pull-request-error')).toBeNull()
    await userEvent.click(screen.getByTestId('build-pull-request-check'))
    await waitFor(() => expect(posts[0]).toContain('/builds/build-1/pull-request/check?wait=true'))
  })

  it("shows GitHub's error, and no check button on a task", () => {
    wrap(
      <PullRequestLine
        pullRequest={{ number: 7, url: 'https://github.com/o/r/pull/7', state: 'draft', last_asked_at: null, error: 'remote: protected branch' }}
      />,
    )
    expect(screen.getByTestId('build-pull-request-error').textContent).toContain('remote: protected branch')
    expect(screen.queryByTestId('build-pull-request-check')).toBeNull()
  })
})

describe('CI on the build card (the-pr-s-ci-is-the-full-check, FR-9)', () => {
  const pr = {
    number: 7,
    url: 'https://github.com/o/r/pull/7',
    state: 'draft' as const,
    last_asked_at: '2026-11-07T00:00:00Z',
    error: null,
    ci: {
      state: 'pending' as const,
      head_sha: 'abcdef1234567',
      last_asked_at: '2026-11-07T00:01:00Z',
      error: null,
      checks: [
        { name: 'unit', state: 'pending' as const, url: 'https://github.com/o/r/runs/1' },
        { name: 'lint', state: 'pending' as const, url: 'https://github.com/o/r/runs/2' },
      ],
    },
  }

  it('lists each counted check as pending with its link, and the last ask', () => {
    wrap(<PullRequestLine buildId="build-1" pullRequest={pr} />)
    expect(screen.getByTestId('build-ci-state').textContent).toBe('pending')
    const items = screen.getAllByTestId('build-ci-check')
    expect(items.map((li) => li.textContent)).toEqual(['unit · pending', 'lint · pending'])
    expect(items[0].querySelector('a')?.getAttribute('href')).toBe('https://github.com/o/r/runs/1')
    expect(screen.getByTestId('build-ci-asked').textContent).toMatch(/asked GitHub/)
  })

  it("shows a failed ask with GitHub's error and a check failing on main too", () => {
    wrap(
      <PullRequestLine
        buildId="build-1"
        pullRequest={{
          ...pr,
          ci: {
            ...pr.ci,
            state: 'failing_on_main',
            error: 'HTTP 502',
            checks: [{ name: 'unit', state: 'failed', url: null, main_result: 'failed' }],
          },
        }}
      />,
    )
    expect(screen.getByTestId('build-ci-state').textContent).toBe('failing on main too')
    expect(screen.getByTestId('build-ci-check').textContent).toContain('also failing on main')
    expect(screen.getByTestId('build-ci-error').textContent).toContain('HTTP 502')
  })

  it('shows nothing where CI was never read', () => {
    wrap(<PullRequestLine buildId="build-1" pullRequest={{ ...pr, ci: null }} />)
    expect(screen.queryByTestId('build-ci')).toBeNull()
  })
})

describe('main behind GitHub', () => {
  it('is silent while main is not behind', async () => {
    main = { branch: 'master', behind: false, can_update: false, reason: null }
    wrap(<MainBehindNotice />)
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByTestId('main-behind-github')).toBeNull()
  })

  it('shows the notice, and Update says why it cannot yet', async () => {
    main = { branch: 'master', behind: true, can_update: false, reason: 'master is checked out with uncommitted changes' }
    wrap(<MainBehindNotice />)
    const notice = await screen.findByTestId('main-behind-github')
    expect(notice.textContent).toContain('master is behind GitHub')
    expect(notice.textContent).toContain('uncommitted changes')
    await userEvent.click(screen.getByTestId('main-behind-github-update'))
    await waitFor(() => expect(posts[0]).toContain('/main/update'))
  })
})
