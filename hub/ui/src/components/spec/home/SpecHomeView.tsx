import { useMemo } from 'react'
import { useProjectBuilds } from '@/api/projectBuilds'
import { useSpecDocuments } from '@/api/spec'
import { SpecHome } from './SpecHome'
import { homeBuilds, homeCapabilities } from './homeModel'

/** How often the home asks again, so a build that starts or finishes shows within ten seconds even
 *  where an SSE event is missed (`home-live`). The events already refresh it at once. */
const REFRESH_MS = 5000

/** The Spec home fed from `GET /project/builds` and `GET /project/documents`. */
export function SpecHomeView({ onOpen }: { onOpen: (path: string, anchor?: string) => void }) {
  const { data: rows } = useProjectBuilds(REFRESH_MS)
  const { data: documents } = useSpecDocuments()
  const builds = useMemo(() => homeBuilds(rows ?? []), [rows])
  const capabilities = useMemo(() => homeCapabilities(documents?.documents ?? []), [documents])
  return <SpecHome builds={builds} capabilities={capabilities} now={new Date()} onOpen={onOpen} />
}
