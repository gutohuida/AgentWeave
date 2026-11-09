import { useState } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { readableApiError } from '@/api/client'
import {
  useArchiveBatch,
  useMarkTidyReviewed,
  useSupersededDocuments,
  useTidyActs,
  type TidyAct,
  type TidyDocument,
} from '@/api/specTidy'

const ACT_LABEL: Record<string, string> = {
  fold: 'Folded',
  create_capability: 'Created capability',
  edit_capability: 'Edited capability',
  supersede: 'Marked superseded',
  clear_superseded: 'Cleared superseded',
  set_slice: 'Set roadmap slice',
}

/**
 * What an agent trusted with the specs has done, for the operator (`an-agent-the-operator-
 * trusts-can-tidy-the-specs`): the acts not yet reviewed (FR-6), with a requirement changed to match
 * the code marked apart and naming what it rests on (FR-13); and the documents marked superseded,
 * which the operator selects and archives in one action (FR-10). Archiving stays here, the operator's.
 */
export function SpecTidyPanel({ onSelect }: { onSelect: (path: string) => void }) {
  const acts = useTidyActs()
  const superseded = useSupersededDocuments()
  const actList = acts.data ?? []
  // Archived documents keep their mark (who and why); the batch archive is for those not yet archived.
  const marked = (superseded.data?.documents ?? []).filter((d) => d.phase !== 'archived')
  if (acts.error || superseded.error) {
    return (
      <p className="px-2 py-1 text-[11px]" style={{ color: 'var(--amber)' }}>
        Could not load the tidy lists: {readableApiError(acts.error ?? superseded.error, 'the Hub did not answer.')}
      </p>
    )
  }
  if (actList.length === 0 && marked.length === 0) return null
  return (
    <>
      <TidyActs acts={actList} onSelect={onSelect} />
      <SupersededList documents={marked} onSelect={onSelect} />
    </>
  )
}

function Fold({ title, count, testId, children }: { title: string; count: number; testId: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <section data-testid={testId} className="mt-2 flex flex-col gap-1 px-2 text-[11px]">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1 text-left"
        style={{ color: 'var(--text-2)', fontWeight: 600 }}
      >
        <Icon name={open ? 'expand_more' : 'chevron_right'} size={13} />
        {title}
        <span className="ml-auto" data-testid={`${testId}-count`} style={{ color: 'var(--text-3)', fontWeight: 400 }}>
          {count}
        </span>
      </button>
      {open ? children : null}
    </section>
  )
}

function TidyActs({ acts, onSelect }: { acts: TidyAct[]; onSelect: (path: string) => void }) {
  const mark = useMarkTidyReviewed()
  const [refusal, setRefusal] = useState<string | null>(null)
  if (acts.length === 0) return null
  const run = (args: { ids: string[] } | { all: true }) => {
    setRefusal(null)
    mark.mutate(args, { onError: (error: unknown) => setRefusal(readableApiError(error, 'The Hub refused.')) })
  }
  return (
    <Fold title="Tidy acts to review" count={acts.length} testId="spec-tidy-acts">
      <Button variant="ghost" size="xs" className="self-start" data-testid="spec-tidy-review-all" disabled={mark.isPending} onClick={() => run({ all: true })}>
        Mark all reviewed
      </Button>
      <ul className="flex flex-col gap-1">
        {acts.map((act) => (
          <li
            key={act.id}
            data-testid="spec-tidy-act"
            data-code-wins={act.code_wins ? 'true' : 'false'}
            className="flex flex-col gap-0.5 rounded-[var(--radius-sm)] px-1.5 py-1"
            style={act.code_wins ? { borderLeft: '2px solid var(--amber)' } : undefined}
          >
            <span style={{ color: 'var(--text-2)' }}>
              {ACT_LABEL[act.act] ?? act.act} by {act.agent}
              {act.run_id ? <span style={{ color: 'var(--text-3)' }}> · run {act.run_id}</span> : null}
            </span>
            {act.code_wins ? (
              <span data-testid="spec-tidy-code-wins" style={{ color: 'var(--amber)' }}>
                Requirement {act.code_wins.requirement} changed to match the code ({act.code_wins.cited})
                <br />
                <s>{act.code_wins.before ?? '—'}</s>
                <br />
                {act.code_wins.after ?? 'retired'}
              </span>
            ) : null}
            <span style={{ color: 'var(--text-3)' }}>{act.reason}</span>
            <span className="flex items-center gap-1">
              <button type="button" className="truncate text-left underline" style={{ color: 'var(--text-2)', maxWidth: '70%' }} onClick={() => onSelect(act.path)} title={act.path}>
                Open {act.path.replace(/\/spec\.json$/, '').split('/').pop()}
              </button>
              <Button variant="ghost" size="xs" className="ml-auto" disabled={mark.isPending} onClick={() => run({ ids: [act.id] })}>
                Reviewed
              </Button>
            </span>
          </li>
        ))}
      </ul>
      {refusal ? <span role="alert" style={{ color: 'var(--red)' }}>{refusal}</span> : null}
    </Fold>
  )
}

function SupersededList({ documents, onSelect }: { documents: TidyDocument[]; onSelect: (path: string) => void }) {
  const archive = useArchiveBatch()
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [message, setMessage] = useState<string | null>(null)
  if (documents.length === 0) return null
  const toggle = (path: string) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  const chosen = documents.map((d) => d.path).filter((p) => picked.has(p))
  const archiveChosen = () => {
    setMessage(null)
    archive.mutate(
      { paths: chosen },
      {
        onSuccess: (result) => {
          setPicked(new Set())
          if (result.refused.length > 0) {
            setMessage(result.refused.map((r) => `${r.path}: ${r.reason}`).join('\n'))
          }
        },
        onError: (error: unknown) => setMessage(readableApiError(error, 'The Hub refused the archive.')),
      },
    )
  }
  return (
    <Fold title="Superseded documents" count={documents.length} testId="spec-superseded">
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="xs" onClick={() => setPicked(new Set(documents.map((d) => d.path)))}>
          Select all
        </Button>
        <Button variant="primary" size="xs" data-testid="spec-superseded-archive" disabled={chosen.length === 0 || archive.isPending} onClick={archiveChosen}>
          Archive {chosen.length > 0 ? `${chosen.length} selected` : 'selected'}
        </Button>
      </div>
      <ul className="flex flex-col gap-1">
        {documents.map((doc) => (
          <li key={doc.path} data-testid="spec-superseded-row" className="flex items-start gap-1.5">
            <input type="checkbox" aria-label={`Select ${doc.title}`} checked={picked.has(doc.path)} onChange={() => toggle(doc.path)} className="mt-0.5" />
            <span className="flex min-w-0 flex-col">
              <button type="button" className="truncate text-left underline" style={{ color: 'var(--text-2)' }} onClick={() => onSelect(doc.path)} title={doc.path}>
                {doc.title}
              </button>
              <span style={{ color: 'var(--text-3)' }}>
                {doc.superseded ? `${doc.superseded.by}: ${doc.superseded.reason}` : ''}
                {doc.superseded?.successor ? ` → ${doc.superseded.successor}` : ''}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {message ? <span role="alert" className="whitespace-pre-line" style={{ color: 'var(--red)' }}>{message}</span> : null}
    </Fold>
  )
}
