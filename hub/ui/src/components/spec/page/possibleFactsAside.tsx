import * as React from 'react'
import { useSpecPossibleFacts } from '@/api/vault'
import { SpecPossibleFacts } from './SpecPossibleFacts'

/** The full spec page's aside for each requirement, fed from the Hub: the possible backing facts
 *  the document's newest spec-vault check named (FR-10). A Hub that names none draws nothing. */
export function usePossibleFactsAside(path: string): (identifier: string) => React.ReactNode {
  const { data } = useSpecPossibleFacts(path)
  return React.useCallback(
    (identifier: string) => <SpecPossibleFacts facts={(data ?? []).filter((f) => f.requirement === identifier)} />,
    [data],
  )
}
