import type { SpecPossibleFact } from '@/api/vault'
import '@/styles/spec-page.css'

export type { SpecPossibleFact }

/** A requirement's possible backing facts, under its statement on the full spec page only. Draws
 *  nothing for a requirement the check named none for. */
export function SpecPossibleFacts({ facts }: { facts: SpecPossibleFact[] }) {
  if (!facts.length) return null
  return (
    <div className="aw-sp-possible-facts" data-testid="spec-possible-facts">
      <div className="aw-sp-possible-facts-head">
        Possibly backed by
        <span className="aw-sp-possible-badge" title="Named by the spec-vault check; nobody has confirmed it">
          not confirmed
        </span>
      </div>
      <ul>
        {facts.map((f) => (
          <li key={f.fact} title={f.fact}>
            <span>
              {f.claim} <span className="aw-sp-possible-source">· {f.source ?? 'source not in the vault'}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="aw-sp-possible-facts-note aw-sp-muted">
        The vault check thinks these may back this requirement. They raise no warning until the author lists them.
      </p>
    </div>
  )
}
