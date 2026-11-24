import * as React from 'react'
import { isNoVault, useSpecPossibleFacts } from '@/api/vault'
import { SpecPossibleFacts } from './SpecPossibleFacts'

/** The full spec page's aside for each requirement, fed from the Hub: the possible backing facts
 *  the document's newest spec-vault check named (FR-10). A Hub that names none, or has no vault,
 *  draws nothing; one whose answer could not be read says so rather than looking like none. */
export function usePossibleFactsAside(path: string): (identifier: string) => React.ReactNode {
  const { data, error } = useSpecPossibleFacts(path)
  const unreadable = error && !isNoVault(error) ? error.message : null
  return React.useCallback(
    (identifier: string) =>
      unreadable ? (
        <p className="aw-sp-possible-facts-note aw-sp-muted" data-testid="spec-possible-facts-unreadable">
          Possible backing facts could not be read: {unreadable}
        </p>
      ) : (
        <SpecPossibleFacts facts={(data ?? []).filter((f) => f.requirement === identifier)} />
      ),
    [data, unreadable],
  )
}
