import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  corpusRefusal,
  useArrangeSpecDocument,
  type SpecDiagnostic,
  type SpecListResponse,
} from '@/api/spec'
import { SpecCorpusStrip } from './SpecCorpusStrip'

const NO_PARENT = '__none__'

interface SpecPlaceUnderProps {
  path: string
  parent: string | null
  specList: SpecListResponse
}

/**
 * Place the open document under another in the corpus hierarchy (design D4, F206).
 *
 * Offers every document the index files, minus this one, plus *No parent*, with the current parent
 * chosen. A cycle or an unknown parent is the Hub's refusal, listed as it sent it; a stale index
 * (409) or a document the index does not file yet (404) offers the rebuild that fixes it.
 */
export function SpecPlaceUnder({ path, parent, specList }: SpecPlaceUnderProps) {
  const arrange = useArrangeSpecDocument()
  const [open, setOpen] = useState(false)
  const [choice, setChoice] = useState(parent ?? NO_PARENT)
  const [refusal, setRefusal] = useState<{
    status: number
    message: string
    diagnostics?: SpecDiagnostic[]
  } | null>(null)

  const candidates = specList.specs.filter((s) => s.state === 'filed' && s.path !== path)

  if (!open) {
    return (
      <Button
        variant="ghost"
        size="xs"
        data-testid="spec-place-under"
        onClick={() => {
          setChoice(parent ?? NO_PARENT)
          setRefusal(null)
          setOpen(true)
        }}
      >
        Place under…
      </Button>
    )
  }

  const place = () => {
    setRefusal(null)
    arrange.mutate(
      { path, parent: choice === NO_PARENT ? null : choice },
      {
        onSuccess: () => setOpen(false),
        onError: (error) => {
          const refused = corpusRefusal(error)
          setRefusal(
            refused
              ? { status: refused.status, message: refused.message, diagnostics: refused.diagnostics }
              : { status: 0, message: 'Placing failed.' },
          )
        },
      },
    )
  }

  const needsRebuild = refusal && (refusal.status === 409 || refusal.status === 404)

  return (
    <div
      data-testid="spec-place-under-form"
      style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <select
          aria-label="Place this document under"
          data-testid="spec-place-under-select"
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
          className="control-field"
          style={{ fontSize: 12, maxWidth: 260 }}
        >
          <option value={NO_PARENT}>No parent</option>
          {candidates.map((s) => (
            <option key={s.path} value={s.path}>
              {s.title ?? s.path}
            </option>
          ))}
        </select>
        <Button size="xs" data-testid="spec-place-under-confirm" disabled={arrange.isPending} onClick={place}>
          Place
        </Button>
        <Button size="xs" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
      {refusal && (
        <div role="alert" data-testid="spec-place-under-refusal" style={{ fontSize: 11, color: 'var(--text-2)' }}>
          <p style={{ margin: 0 }}>
            {refusal.status === 404 ? 'This document is not filed in the index yet. ' : ''}
            {refusal.message}
          </p>
          {(refusal.diagnostics ?? []).map((d, i) => (
            <p key={i} style={{ margin: 0, color: 'var(--text-3)' }}>
              {d.path ? `${d.code} — ${d.path}` : d.code}
            </p>
          ))}
        </div>
      )}
      {needsRebuild && <SpecCorpusStrip specList={specList} />}
    </div>
  )
}
