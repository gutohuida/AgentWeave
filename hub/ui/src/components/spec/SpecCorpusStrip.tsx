import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  corpusRefusal,
  useAdoptSpecCorpus,
  useReindexSpec,
  type CorpusAdoptResult,
  type ReindexResult,
  type SpecDiagnostic,
  type SpecListResponse,
} from '@/api/spec'

/** The diagnostics a rebuild answers when it will not choose a home (`spec_documents.build_index`):
 *  the home one first, then `index_home_required`. Keyed on the code, never on position. */
const HOME_CODES = new Set(['index_home_required', 'home_ambiguous', 'home_missing'])

interface SpecCorpusStripProps {
  specList: SpecListResponse
  /** A document was adopted from the tree since the last rebuild: adoption files nothing in the
   *  index, so the strip says a rebuild is what files it (design D3). */
  adoptedSinceRebuild?: boolean
  onRebuilt?: () => void
}

const lineStyle: React.CSSProperties = { fontSize: 12, color: 'var(--text-2)', margin: 0 }
const quietStyle: React.CSSProperties = { fontSize: 11, color: 'var(--text-3)', margin: 0 }

function totals(result: ReindexResult) {
  const counts = { created: 0, reworded: 0, retired: 0 }
  for (const entry of Object.values(result.documents ?? {})) {
    if (!entry) continue
    counts.created += entry.created.length
    counts.reworded += entry.reworded.length
    counts.retired += entry.retired.length
  }
  return counts
}

function diagnosticLine(d: SpecDiagnostic): string {
  return d.path ? `${d.code} — ${d.path}` : d.code
}

/**
 * The corpus's own state, at the top of the document browser (`the-corpus-is-indexed-arranged-and-
 * adopted-from-the-app`, D1-D3; F206): whether there is a usable index and which document is its
 * home, how many documents on disk the Hub does not track, and the two actions that change either.
 *
 * Every sentence is the Hub's answer read back. The home is never chosen here: when a rebuild says
 * it will not guess one, the strip asks the operator (D2).
 */
export function SpecCorpusStrip({ specList, adoptedSinceRebuild = false, onRebuilt }: SpecCorpusStripProps) {
  const reindex = useReindexSpec()
  const adoptAll = useAdoptSpecCorpus()
  const [result, setResult] = useState<ReindexResult | null>(null)
  const [adopted, setAdopted] = useState<CorpusAdoptResult | null>(null)
  const [home, setHome] = useState('')
  const [error, setError] = useState<string | null>(null)

  const manifestState = specList.manifest?.state ?? 'absent'
  const valid = manifestState === 'valid'
  const untracked = specList.specs.filter((s) => !s.document_id)
  const tracked = specList.specs.filter((s) => !!s.document_id)
  const homeTitle = specList.specs.find((s) => s.path === specList.home)?.title ?? specList.home

  const rebuild = (chosen?: string) => {
    setError(null)
    reindex.mutate(chosen ? { home: chosen } : {}, {
      onSuccess: (answer) => {
        setResult(answer)
        setHome('')
        onRebuilt?.()
      },
      onError: (e) => setError(corpusRefusal(e)?.message ?? 'The rebuild failed.'),
    })
  }

  const adoptEverything = () => {
    setError(null)
    adoptAll.mutate(undefined, {
      onSuccess: (answer) => setAdopted(answer),
      onError: (e) => setError(corpusRefusal(e)?.message ?? 'Adopting failed.'),
    })
  }

  const written = result?.index.written ?? null
  const diagnostics = result?.index.diagnostics ?? []
  const askHome = !!result && !written && diagnostics.some((d) => d.code === 'index_home_required')
  const writeFailed = !!result && !written && diagnostics.find((d) => d.code === 'index_write_failed')
  const nothingToIndex = !!result && !written && !askHome && !writeFailed
  const otherDiagnostics = diagnostics.filter(
    (d) => !HOME_CODES.has(d.code) && d.code !== 'index_write_failed',
  )
  const rebuildPrimary = !valid || adoptedSinceRebuild || askHome || !!writeFailed
  const busy = reindex.isPending || adoptAll.isPending

  // Nothing to say when the index is valid, nothing is untracked and nothing was just done —
  // except the quiet Rebuild, which is always reachable (D1).
  return (
    <div
      data-testid="spec-corpus-strip"
      className="shrink-0"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        padding: '8px 10px',
        borderBottom: '1px solid var(--border)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <p data-testid="spec-corpus-index" style={valid ? quietStyle : lineStyle}>
          {valid
            ? `Index: home is ${homeTitle ?? 'not recorded'}`
            : 'No usable index — hierarchy and home are not recorded'}
        </p>
        <Button
          size="xs"
          variant={rebuildPrimary ? 'primary' : 'ghost'}
          data-testid="spec-corpus-rebuild"
          disabled={busy}
          onClick={() => rebuild()}
        >
          Rebuild index
        </Button>
      </div>

      {untracked.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <p data-testid="spec-corpus-untracked" style={lineStyle}>
            {untracked.length === 1
              ? '1 document on disk is not tracked'
              : `${untracked.length} documents on disk are not tracked`}
          </p>
          <Button
            size="xs"
            variant="outline"
            data-testid="spec-corpus-adopt-all"
            disabled={busy}
            onClick={adoptEverything}
          >
            Adopt all {untracked.length}
          </Button>
        </div>
      )}

      {adoptedSinceRebuild && !result && (
        <p data-testid="spec-corpus-adopted-note" style={lineStyle}>
          Adopted documents are filed in the index on the next rebuild.
        </p>
      )}

      {adopted && (
        <div data-testid="spec-corpus-adopt-result" style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <p style={lineStyle}>
            Adopted {adopted.adopted.length}
            {adopted.skipped.length > 0 ? `, skipped ${adopted.skipped.length}` : ''}.
            {adopted.adopted.length > 0 ? ' Rebuild the index to file them.' : ''}
          </p>
          {adopted.skipped.map((path) => (
            <p key={path} style={quietStyle}>
              {path}: {adopted.documents[path]?.message ?? 'not adopted'}
            </p>
          ))}
          {adopted.diagnostics.map((d, i) => (
            <p key={i} style={quietStyle}>
              {diagnosticLine(d)}
            </p>
          ))}
        </div>
      )}

      {askHome && (
        <div data-testid="spec-corpus-home-question" style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <label style={lineStyle} htmlFor="spec-corpus-home-select">
            Which document is the corpus's home?
          </label>
          <select
            id="spec-corpus-home-select"
            data-testid="spec-corpus-home-select"
            value={home}
            onChange={(e) => setHome(e.target.value)}
            className="control-field"
            style={{ fontSize: 12, maxWidth: 280 }}
          >
            <option value="">Choose a document…</option>
            {tracked.map((s) => (
              <option key={s.path} value={s.path}>
                {s.title ?? s.path}
              </option>
            ))}
          </select>
          <Button
            size="xs"
            data-testid="spec-corpus-home-confirm"
            disabled={!home || busy}
            onClick={() => rebuild(home)}
          >
            Rebuild with this home
          </Button>
        </div>
      )}

      {writeFailed && (
        <p data-testid="spec-corpus-write-failed" style={lineStyle}>
          The index could not be written: {writeFailed.actual ?? 'no reason given'}. The requirements
          were rebuilt.
        </p>
      )}

      {nothingToIndex && (
        <p data-testid="spec-corpus-nothing" style={lineStyle}>
          Nothing to index: no tracked document is on disk. Adopt the documents first.
        </p>
      )}

      {written && result && (
        <div data-testid="spec-corpus-summary" style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <p style={lineStyle}>
            {(() => {
              const t = totals(result)
              return (
                `Indexed ${written.documents} documents · created ${t.created} · reworded ` +
                `${t.reworded} · retired ${t.retired} · re-rendered ${result.corpus.rerendered.length}`
              )
            })()}
          </p>
          {result.corpus.skipped.map((skip) => (
            <p key={skip.path} style={quietStyle}>
              Skipped {skip.path}: {skip.reason}
              {skip.message ? ` (${skip.message})` : ''}
            </p>
          ))}
        </div>
      )}

      {result && otherDiagnostics.length > 0 && (
        <div data-testid="spec-corpus-diagnostics" style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {otherDiagnostics.map((d, i) => (
            <p key={i} style={quietStyle}>
              {diagnosticLine(d)}
            </p>
          ))}
        </div>
      )}

      {error && (
        <p role="alert" data-testid="spec-corpus-error" style={{ ...lineStyle, color: 'var(--destructive)' }}>
          {error}
        </p>
      )}
    </div>
  )
}
