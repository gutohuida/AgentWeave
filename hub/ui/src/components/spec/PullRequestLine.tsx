import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import {
  useCheckBuildPullRequest,
  useMainAgainstGitHub,
  useUpdateMainFromGitHub,
  type BuildPullRequest,
  type CiRead,
} from '@/api/pullRequests'
import { formatDateTime } from '@/lib/format'

const CI_STATE_WORDS: Record<string, string> = {
  pending: 'pending',
  passed: 'passed',
  failed: 'failed',
  failing_on_main: 'failing on main too',
  superseded: 'superseded by a later push',
  not_finished: 'not finished',
}

const MAIN_WORDS: Record<string, string> = {
  failed: 'also failing on main',
  passed: 'passes on main',
  none: 'main had no result',
}

/**
 * CI on a PR's head commit (`the-pr-s-ci-is-the-full-check`, FR-9): its state, the commit, each
 * counted check with its state and link, when the Hub last asked, and GitHub's error from a failed
 * ask. Nothing where the project's CI setting never read one.
 */
export function CiState({ ci, testId = 'build-ci' }: { ci: CiRead | null | undefined; testId?: string }) {
  if (!ci) return null
  const sha = ci.head_sha ? ci.head_sha.slice(0, 7) : null
  return (
    <div className="aw-spec-message-text" data-testid={testId}>
      <span>
        CI{' '}
        <span data-testid={`${testId}-state`}>{ci.state ? (CI_STATE_WORDS[ci.state] ?? ci.state) : 'not read yet'}</span>
        {sha ? ` · ${sha}` : ''}
        {' · '}
        <span data-testid={`${testId}-asked`}>
          {ci.last_asked_at ? `asked GitHub ${formatDateTime(ci.last_asked_at)}` : 'GitHub not asked yet'}
        </span>
      </span>
      {ci.checks.length ? (
        <ul data-testid={`${testId}-checks`}>
          {ci.checks.map((check) => (
            <li key={check.name} data-testid={`${testId}-check`}>
              {check.url ? (
                <a href={check.url} target="_blank" rel="noreferrer">
                  {check.name}
                </a>
              ) : (
                check.name
              )}
              {' · '}
              {check.state}
              {check.main_result ? ` · ${MAIN_WORDS[check.main_result] ?? check.main_result}` : ''}
            </li>
          ))}
        </ul>
      ) : null}
      {ci.error ? (
        <div role="alert" data-testid={`${testId}-error`}>
          GitHub said: {ci.error}
        </div>
      ) : null}
    </div>
  )
}

/**
 * The pull request a build lands as, on the build card and on each of its tasks
 * (`a-build-lands-as-one-pull-request`, FR-13): its link, its state (draft, ready, merged,
 * closed), when the Hub last asked GitHub, and GitHub's error from a failed push or ask. With
 * `buildId`, 'check now' asks GitHub and waits for the answer.
 */
export function PullRequestLine({
  pullRequest,
  buildId,
}: {
  pullRequest: BuildPullRequest | null | undefined
  buildId?: string
}) {
  const check = useCheckBuildPullRequest()
  if (!pullRequest) return null
  const { url, number, state, last_asked_at: askedAt, error } = pullRequest
  return (
    <div className="aw-spec-message-text" data-testid="build-pull-request">
      <span>
        Pull request{' '}
        {url ? (
          <a href={url} target="_blank" rel="noreferrer" data-testid="build-pull-request-link">
            {number != null ? `#${number}` : url}
          </a>
        ) : (
          'not opened yet'
        )}
        {state ? (
          <>
            {' · '}
            <span data-testid="build-pull-request-state">{state}</span>
          </>
        ) : null}
        {' · '}
        <span data-testid="build-pull-request-asked">
          {askedAt ? `asked GitHub ${formatDateTime(askedAt)}` : 'GitHub not asked yet'}
        </span>
      </span>
      {buildId ? (
        <Button
          size="xs"
          variant="ghost"
          disabled={check.isPending}
          onClick={() => check.mutate({ buildId })}
          data-testid="build-pull-request-check"
        >
          {check.isPending ? 'Asking…' : 'Check now'}
        </Button>
      ) : null}
      {error ? (
        <div role="alert" data-testid="build-pull-request-error">
          GitHub said: {error}
        </div>
      ) : null}
      {check.isError ? (
        <div role="alert">{readableApiError(check.error, 'The Hub could not ask GitHub.')}</div>
      ) : null}
      {buildId ? <CiState ci={pullRequest.ci} /> : null}
    </div>
  )
}

/**
 * 'main is behind GitHub' with Update (FR-11): shown where the project's local main trails
 * GitHub's after a merge. Update fast-forwards once that is safe, and says why when it is not.
 */
export function MainBehindNotice() {
  const { data: main, isError: mainError } = useMainAgainstGitHub()
  const update = useUpdateMainFromGitHub()
  const answer = update.data
  const shown = answer ?? main
  if (mainError && !answer) {
    return (
      <div className="aw-spec-message" role="status" data-testid="main-behind-github-unknown">
        Could not compare main with GitHub.
      </div>
    )
  }
  if (!shown || !shown.behind) return null
  const reason = answer?.reason ?? (shown.can_update ? null : shown.reason)
  return (
    <div className="aw-spec-message" role="status" data-testid="main-behind-github">
      <span className="aw-spec-message-text">
        {shown.branch} is behind GitHub
        {reason ? ` · ${reason}` : ''}
      </span>
      <Button
        size="xs"
        variant="ghost"
        disabled={update.isPending}
        onClick={() => update.mutate()}
        data-testid="main-behind-github-update"
      >
        {update.isPending ? 'Updating…' : 'Update'}
      </Button>
      {update.isError ? <span role="alert">{readableApiError(update.error, 'The Hub refused to update.')}</span> : null}
    </div>
  )
}
