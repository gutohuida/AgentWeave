import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import {
  useCheckBuildPullRequest,
  useMainAgainstGitHub,
  useUpdateMainFromGitHub,
  type BuildPullRequest,
} from '@/api/pullRequests'
import { formatDateTime } from '@/lib/format'

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
    </div>
  )
}

/**
 * 'main is behind GitHub' with Update (FR-11): shown where the project's local main trails
 * GitHub's after a merge. Update fast-forwards once that is safe, and says why when it is not.
 */
export function MainBehindNotice() {
  const { data: main } = useMainAgainstGitHub()
  const update = useUpdateMainFromGitHub()
  const answer = update.data
  const shown = answer ?? main
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
