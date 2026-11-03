import { readableApiError } from '@/api/client'
import { useReviewSpecAmendments, useSpecAmendments, useSpecDocuments, type SpecAmendment } from '@/api/spec'
import { OP_LABEL, PROPOSED_LABEL } from './amendmentLabels'
import { AmendmentRow, ProposalRow } from './SpecAmendmentsPanel'
import type { HeaderNotice } from './page/SpecNotices'

/** A row whose change is in the document: applied at once, or accepted (as the panel reads it). */
function recorded(amendment: SpecAmendment): boolean {
  return !amendment.state || amendment.state === 'applied' || amendment.state === 'accepted'
}

/**
 * The amendments waiting on the operator, as the redesigned header's notices (spec
 * `the-spec-header-redesigned`, FR-7): one per unreviewed change or open proposal, whose body is its
 * row here (reason, how to check, and Mark reviewed, Accept or Decline, or a report's answers), and
 * Mark all reviewed when more than one waits. Reviewed and decided rows wait on nobody, so they are
 * no notice; a list that could not be read is one.
 */
export function useAmendmentNotices(path: string): HeaderNotice[] {
  const { data: documentsData, isError: documentsError } = useSpecDocuments()
  const record = documentsData?.documents.find((entry) => entry.path === path)
  const mayHave =
    documentsError ||
    (record?.amendments?.total ?? 0) > 0 ||
    (record?.amendments?.proposed ?? 0) > 0
  const { data, error } = useSpecAmendments(path, mayHave)
  const review = useReviewSpecAmendments()
  if (!mayHave) return []
  const notices: HeaderNotice[] = []
  if (error) {
    notices.push({
      id: 'amendments-error',
      tone: 'warn',
      summary: `Could not load the amendments: ${readableApiError(error, 'the Hub did not answer.')}`,
    })
  }
  const amendments = data?.amendments ?? []
  const unreviewed = amendments.filter((amendment) => recorded(amendment) && !amendment.reviewed)
  if (unreviewed.length > 1) {
    notices.push({
      id: 'amendments-all',
      tone: 'warn',
      summary: `${unreviewed.length} amendments not reviewed`,
      action: { label: 'Mark all reviewed', onClick: () => review.mutate({ path }), disabled: review.isPending },
    })
  }
  for (const amendment of amendments) {
    if (recorded(amendment)) {
      if (amendment.reviewed) continue
      notices.push({
        id: amendment.id,
        tone: 'warn',
        testId: `spec-notice-amendment-${amendment.id}`,
        summary: (
          <>
            {OP_LABEL[amendment.op] ?? amendment.op} <code>{amendment.target}</code>
            {amendment.identifier ? ` (${amendment.identifier})` : ''} · @{amendment.author} ·{' '}
            {amendment.op === 'cannot_satisfy' ? 'not answered' : 'not reviewed'}
          </>
        ),
        body: (
          <ul className="flex flex-col gap-1">
            <AmendmentRow
              path={path}
              amendment={amendment}
              busy={review.isPending}
              onReview={() => review.mutate({ path, ids: [amendment.id] })}
            />
          </ul>
        ),
      })
    } else if (amendment.state === 'proposed') {
      notices.push({
        id: amendment.id,
        tone: 'warn',
        testId: `spec-notice-amendment-${amendment.id}`,
        summary: (
          <>
            {PROPOSED_LABEL[amendment.op] ?? amendment.op} <code>{amendment.target}</code> · @{amendment.author} · waiting for you
          </>
        ),
        body: (
          <ul className="flex flex-col gap-1">
            <ProposalRow path={path} amendment={amendment} />
          </ul>
        ),
      })
    }
  }
  return notices
}
