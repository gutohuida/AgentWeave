import { Icon } from '@/components/common/Icon'
import { useDocumentFlow } from '@/api/loops'
import { useSpec, useSpecDocuments } from '@/api/spec'

/**
 * What approving this document did (`a-document-says-how-it-will-be-built-and-approval-starts-it`,
 * design D7). Mounted in `SpecDocumentPanel` under `SpecPhaseBar`. A record, not an alert — it has
 * no dismiss, and stays visible for as long as the document is approved. Renders nothing when the
 * Hub has not returned `approval_outcome`: a document with no report yet, or a bundle talking to
 * an un-restarted `:8000` that predates it entirely (the `:8000` skew).
 *
 * It carries no Start a flow… button of its own (Opus review, note 6): the one control is
 * `SpecPhaseBar`'s, directly above it. While no unarchived flow declares the document (change 1's
 * `useDocumentFlow` lookup), this appends a pointer at that control instead of growing a second
 * one for the same action. The stored report always says what approval did, whether or not a flow
 * exists now — the pointer is the only part of this screen that changes as the world moves on.
 */
export function SpecApprovalReport({ path }: { path: string }) {
  const { data: specDoc, isError: specError } = useSpec(path)
  const { data: docsData, isError: docsError } = useSpecDocuments()
  const document = docsData?.documents.find((entry) => entry.path === path)
  const flow = useDocumentFlow(document?.id)

  // On a failed fetch there is nothing accepted to show, and no false claim in showing nothing.
  const outcome = specError || docsError ? undefined : specDoc?.approval_outcome
  if (!outcome) return null

  // Only a change-spec document ever gets a flow (D4), so the pointer at Start a flow… — the
  // control `SpecPhaseBar` offers only there — means nothing anywhere else.
  const pointToStartFlow = document?.kind === 'change-spec' && !flow

  return (
    <div
      data-testid="spec-approval-report"
      className="flex shrink-0 flex-col gap-1 px-3 py-2 text-xs"
      style={{ borderBottom: '1px solid var(--border)', color: 'var(--text-2)' }}
    >
      {outcome.created.length > 0 && (
        <div data-testid="approval-created">
          <span style={{ color: 'var(--text-3)' }}>Created </span>
          {outcome.created.map((task, i) => (
            <span key={task.id}>
              {i > 0 ? ', ' : ''}
              {task.title} (<code>{task.key}</code>)
            </span>
          ))}
        </div>
      )}

      {outcome.already_served.map((entry) => (
        <div
          key={entry.key}
          className="flex items-start gap-1.5"
          data-testid="approval-already-served"
        >
          <Icon name="info" size={13} />
          <span>
            <code>{entry.key}</code> was not created: a hand-made task already serves{' '}
            {entry.requirements.join(', ')}.
          </span>
        </div>
      ))}

      {outcome.failed && (
        <div
          className="flex items-start gap-1.5"
          data-testid="approval-failed"
          style={{ color: 'var(--amber)' }}
        >
          <Icon name="warning" size={13} />
          <span>The board could not be built: {outcome.failed}</span>
        </div>
      )}

      {(outcome.refreshed ?? []).map((task) => (
        <div key={task.id} className="flex items-start gap-1.5" data-testid="approval-refreshed">
          <Icon name="info" size={13} />
          <span>
            <code>{task.key}</code> refreshed to {task.title}
            {task.fields.length > 0 && <>: {task.fields.map((f) => f.replace(/_/g, ' ')).join(', ')}</>}
            {task.linked.length > 0 && <>; linked {task.linked.join(', ')}</>}
            {task.unlinked.length > 0 && <>; unlinked {task.unlinked.join(', ')}</>}.
          </span>
        </div>
      ))}

      {(outcome.closed_linking_retired ?? []).map((task) => (
        <div
          key={task.id}
          className="flex items-start gap-1.5"
          data-testid="approval-closed-retired"
          style={{ color: 'var(--amber)' }}
        >
          <Icon name="warning" size={13} />
          <span>
            <code>{task.key}</code> is {task.status} and left as delivered, but still links retired{' '}
            {task.requirements.join(', ')}.
          </span>
        </div>
      ))}

      {(outcome.no_longer_declared ?? []).map((task) => (
        <div
          key={task.id}
          className="flex items-start gap-1.5"
          data-testid="approval-no-longer-declared"
          style={{ color: 'var(--amber)' }}
        >
          <Icon name="warning" size={13} />
          <span>
            <code>{task.key}</code> ({task.status}) is no longer declared by this document; it was left
            on the board.
          </span>
        </div>
      ))}

      {outcome.dependencies_not_honoured.map((dep, i) => (
        <div
          key={`${dep.task_id}:${dep.reference}:${i}`}
          className="flex items-start gap-1.5"
          data-testid="approval-dependency-problem"
          style={{ color: 'var(--amber)' }}
        >
          <Icon name="warning" size={13} />
          <span>
            <code>{dep.task_key}</code> → <code>{dep.reference}</code>: {dep.reason}
          </span>
        </div>
      ))}

      {outcome.flow.messages.map((message, i) => (
        <div key={i} data-testid="approval-flow-message">
          {message}
        </div>
      ))}

      {pointToStartFlow && (
        <div data-testid="approval-start-flow-pointer" style={{ color: 'var(--text-3)' }}>
          … use Start a flow… above.
        </div>
      )}
    </div>
  )
}
