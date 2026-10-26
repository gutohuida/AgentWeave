import { StartBuildDialog } from '@/components/spec/page/SpecBuilds'
import { SpecWorkspace } from '@/components/spec/page/SpecWorkspace'
import { useListPreferences } from '@/components/spec/page/hooks'
import { toast } from '@/lib/toast'
import { PROJECT_ID } from '../fixtures'
import { useSpecMock } from '../specMock'

/** The Spec tab, redesigned (spec `the-spec-page-redesigned`). The mock bar switches the document's
 *  state and the list's layout; everything else responds as the page will. */
export default function Spec() {
  const { surface, layout, entries, startDialog } = useSpecMock('tab/spec')
  const [listPrefs, setListPrefs] = useListPreferences(PROJECT_ID)
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
      />
      <StartBuildDialog {...startDialog} />
    </>
  )
}
