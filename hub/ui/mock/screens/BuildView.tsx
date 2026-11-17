import * as React from 'react'
import { BuildView } from '@/components/builds/BuildView'
import { toast } from '@/lib/toast'
import { buildFor, colorIndexer, DEFAULT_BUILD, nowFor, RECORDED_BUILDS, useBuildHash, useSeedRunTraces } from '../buildsMock'

const colorIndexOf = colorIndexer(RECORDED_BUILDS)

/** One build's view: `#build/<id>?task=<ref>&run=<id>&filter=needs-you`, plus `&state=` for the
 *  states the recording lacks (see `BUILD_MOCK_STATES`). The container the app will hold is this:
 *  the address in, the read in, callbacks out. */
export default function BuildViewScreen() {
  const { buildId, address, state, setAddress } = useBuildHash()
  const id = buildId ?? DEFAULT_BUILD
  const read = React.useMemo(() => buildFor(id, state), [id, state])
  useSeedRunTraces(read)

  // mock state: loading, a failed first read, and a failed refresh over data already shown.
  const status = state === 'loading' ? 'loading' : state === 'error' ? 'error' : 'ready'
  return (
    <BuildView
      read={status === 'ready' ? read : null}
      status={status}
      errorMessage="The Hub did not answer: the build could not be read."
      refreshError={state === 'stale' ? 'the Hub has not answered for 40 seconds.' : null}
      now={nowFor(read)}
      address={address}
      onAddressChange={setAddress}
      onRetry={() => toast({ title: 'Reads the build again' })}
      onOpenDocument={() => toast({ title: 'Opens the spec', description: read?.build.document_title })}
      onOpenConversation={(run) => toast({ title: `Opens ${run.agent}'s conversation`, description: 'The conversation this run happened in.' })}
      colorIndexOf={colorIndexOf}
    />
  )
}
