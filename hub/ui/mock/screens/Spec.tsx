import { BuildPlanDialog } from '@/components/spec/build/BuildPlanDialog'
import { SpecWorkspace } from '@/components/spec/page/SpecWorkspace'
import { useListPreferences } from '@/components/spec/page/hooks'
import { toast } from '@/lib/toast'
import { PROJECT_ID } from '../fixtures'
import { useQueryClient } from '@tanstack/react-query'
import * as React from 'react'
import { SpecListFooter } from '@/components/spec/SpecListFooter'
import defectsJson from '../fixtures/spec_defects.json'
import { useSpecMock } from '../specMock'

/** The Spec tab, redesigned (spec `the-spec-page-redesigned`). The mock bar switches the document's
 *  state and the list's layout; everything else responds as the page will. */
export default function Spec() {
  const { surface, layout, entries, planDialog } = useSpecMock('tab/spec')
  const [listPrefs, setListPrefs] = useListPreferences(PROJECT_ID)
  // mock state: the defects report as the operator's Hub answered it on 2026-11-02 (14 changes,
  // 72 defects), and its evidence count then.
  const client = useQueryClient()
  React.useMemo(() => client.setQueryData(['project', PROJECT_ID, 'specs', 'defects'], defectsJson), [client])
  const listFooter = (
    <SpecListFooter
      onOpenEvidence={() => toast({ title: 'Opens the evidence page' })}
      evidenceOpen={false}
      evidenceCount={992}
      evidenceError={false}
      currentPath={surface.doc.path}
      onSelect={() => toast({ title: 'Opens that change' })}
    />
  )
  return (
    <>
      <SpecWorkspace
        key={layout}
        {...surface}
        entries={entries}
        listPrefs={listPrefs}
        onListPrefsChange={setListPrefs}
        onNew={() => toast({ title: 'Starts a new change', description: 'With an agent, in a conversation.' })}
        layout={layout}
        listFooter={listFooter}
      />
      <BuildPlanDialog {...planDialog} />
    </>
  )
}
