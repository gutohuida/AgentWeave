import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  corpusRefusal,
  useDetectDrift,
  useResolveDrift,
  useSpecCoverage,
  useSpecDrift,
  type DriftCandidate,
  type DriftResolution,
  type UnwatchedEvidence,
} from '@/api/spec'

const ANSWERS: { resolution: DriftResolution; label: string; title: string }[] = [
  {
    resolution: 'specification_updated',
    label: 'Spec updated',
    title: 'The implementation is right; the specification has been changed to match it.',
  },
  {
    resolution: 'implementation_corrected',
    label: 'Code corrected',
    title:
      'The implementation was wrong and is being put back. The next scan asks again while the change is still there.',
  },
  {
    resolution: 'no_change_required',
    label: 'No change',
    title: 'The change does not affect what this requirement says.',
  },
]

/** What clears each reason a piece of accepted evidence is not watched (design D3). */
const UNWATCHED_REMEDY: Record<UnwatchedEvidence['reason'], string> = {
  names_no_file:
    'it names no file or commit in the tree — put a file path or a commit id in the locator to have it watched',
  recorded_before_watching:
    'recorded before drift watched files, and its merge into the main line was not found — record it again to have it watched',
  no_footprint: 'the Hub could not read the workspace when it was recorded — record it again',
}

const line: React.CSSProperties = { fontSize: 12, color: 'var(--text-2)', margin: 0 }
const quiet: React.CSSProperties = { fontSize: 11, color: 'var(--text-3)', margin: 0 }

function shortId(value: string | null): string {
  return value ? value.slice(0, 7) : 'removed'
}

function CandidateRow({ candidate }: { candidate: DriftCandidate }) {
  const resolve = useResolveDrift()
  const [refusal, setRefusal] = useState<string | null>(null)
  return (
    <div
      data-testid={`spec-drift-row-${candidate.id}`}
      style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '6px 0', borderTop: '1px solid var(--border)' }}
    >
      <p style={{ ...line, color: 'var(--text)' }}>
        <strong>{candidate.requirement?.identifier ?? 'A requirement'}</strong>
        {candidate.evidence ? ` · verified by ${candidate.evidence.summary} (${candidate.evidence.actor})` : ''}
      </p>
      {Object.entries(candidate.observed).map(([path, change]) => (
        <p key={path} style={quiet}>
          {path}: {shortId(change.was)} → {shortId(change.now)}
        </p>
      ))}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {ANSWERS.map((answer) => (
          <Button
            key={answer.resolution}
            size="xs"
            variant="outline"
            title={answer.title}
            disabled={resolve.isPending}
            onClick={() => {
              setRefusal(null)
              resolve.mutate(
                { id: candidate.id, resolution: answer.resolution },
                { onError: (error) => setRefusal(corpusRefusal(error)?.message ?? 'Answering failed.') },
              )
            }}
          >
            {answer.label}
          </Button>
        ))}
      </div>
      {refusal && (
        <p role="alert" style={{ ...quiet, color: 'var(--destructive)' }}>
          {refusal}
        </p>
      )}
    </div>
  )
}

/**
 * The document's drift: its open candidates, oldest first, each answered with one of three words,
 * and the evidence drift does not watch (`drift-is-scanned-and-answered-on-the-document`, F129).
 *
 * Shown beneath the coverage bar wherever this document has something to say about drift --
 * candidates, unwatched evidence, or accepted evidence that could drift; otherwise nothing.
 */
export function SpecDriftPanel({ path }: { path: string }) {
  const { data, refetch, error: driftError } = useSpecDrift(path)
  const { data: coverage, error: coverageError } = useSpecCoverage(path)
  const detect = useDetectDrift()
  const [scanned, setScanned] = useState<string | null>(null)
  const [showUnwatched, setShowUnwatched] = useState(false)

  const candidates = data?.drift ?? []
  const unwatched = data?.unwatched ?? []
  const totals = coverage?.totals ?? {}
  const watchable = (totals.verified ?? 0) + (totals.drifting ?? 0) + (totals.stale ?? 0)
  // A read that failed is said, not taken for "nothing drifting" (the n11 ratchet's rule).
  const loadError = driftError ?? coverageError
  if (!loadError && candidates.length === 0 && unwatched.length === 0 && watchable === 0) return null

  const scan = () => {
    setScanned(null)
    detect.mutate(undefined, {
      onSuccess: async (answer) => {
        // Scanning is project-wide; "on this document" is what the refetched strip now holds of
        // what was raised (design D2), so it is counted after the refetch, not before.
        const raised = answer.raised ?? []
        const fresh = await refetch()
        const here = new Set((fresh.data?.drift ?? []).map((c) => c.id))
        const onThis = raised.filter((id) => here.has(id)).length
        setScanned(`${raised.length} new — ${onThis} on this document`)
      },
      onError: (error) => setScanned(corpusRefusal(error)?.message ?? 'The scan failed.'),
    })
  }

  return (
    <div
      data-testid="spec-drift-panel"
      className="shrink-0"
      style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '8px 16px', borderBottom: '1px solid var(--border)' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <p style={{ ...line, fontWeight: 600 }}>
          {candidates.length === 0
            ? 'Drifting: nothing to answer'
            : `Drifting: ${candidates.length} to answer — say which one was wrong`}
        </p>
        <Button size="xs" variant="outline" data-testid="spec-drift-scan" disabled={detect.isPending} onClick={scan}>
          Scan for drift
        </Button>
        {scanned && (
          <span data-testid="spec-drift-scanned" style={quiet}>
            Scanned the project: {scanned}
          </span>
        )}
      </div>
      {loadError && (
        <p role="alert" data-testid="spec-drift-load-error" style={{ ...quiet, color: 'var(--destructive)' }}>
          Drift could not be read: {corpusRefusal(loadError)?.message ?? String(loadError)}
        </p>
      )}
      {candidates.map((candidate) => (
        <CandidateRow key={candidate.id} candidate={candidate} />
      ))}
      {unwatched.length > 0 && (
        <div data-testid="spec-drift-unwatched">
          <button
            type="button"
            onClick={() => setShowUnwatched((open) => !open)}
            style={{ ...quiet, background: 'none', border: 'none', padding: 0, cursor: 'pointer', textDecoration: 'underline' }}
          >
            {unwatched.length === 1
              ? '1 piece of accepted evidence here is not watched for drift'
              : `${unwatched.length} pieces of accepted evidence here are not watched for drift`}
          </button>
          {showUnwatched &&
            unwatched.map((entry) => (
              <p key={entry.evidence_id} style={quiet}>
                {entry.requirement.identifier} · {entry.summary}: {UNWATCHED_REMEDY[entry.reason]}
              </p>
            ))}
        </div>
      )}
    </div>
  )
}
