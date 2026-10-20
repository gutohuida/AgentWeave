import * as React from 'react'
import { readableApiError } from '@/api/client'
import {
  fileKindOf,
  isFact,
  isNoVault,
  useCloseVaultReport,
  useDistilVaultSource,
  useResolveContradiction,
  useUpdateVaultSettings,
  useUploadVaultFile,
  useUploadVaultSource,
  useVaultContradictions,
  useVaultEntry,
  useVaultFactRecords,
  useVaultFile,
  useVaultMap,
  useVaultReports,
  useVaultSettings,
  vaultFileMediaType,
  type VaultContradiction,
  type VaultEntry,
  type VaultEntryPage,
  type VaultSettings,
  type VaultType,
} from '@/api/vault'
import { Icon } from '@/components/common/Icon'
import { toast } from '@/lib/toast'
import type { VaultAddInput, VaultAddResult } from './VaultAddDialog'
import { VaultLibrary } from './VaultLibrary'
import type { VaultFact } from './VaultReader'
import { hasTrackedFile } from './vaultKinds'
import '@/styles/vault.css'

/**
 * The Vault tab: the library (`VaultLibrary`) fed from the Hub
 * (`a-vault-the-operator-fills-with-text-and-agents-can-read`).
 *
 * A Hub that predates the vault answers its routes 404. The bundle reaches the operator's app on
 * reload, possibly before their server restarts, so that reads as a state rather than an error;
 * so does a 404 from the newer contradiction and report routes, which only drops their views.
 *
 * After an add or an extraction the map, the contradictions and the reports are re-read every
 * few seconds for a few minutes, because the manager writes facts, and checks them, in the
 * background.
 */
const WATCH_MS = 3 * 60 * 1000
const WATCH_EVERY_MS = 3000

// Shown until the settings arrive, and if they cannot be read; the storage dialog says why.
const NO_SETTINGS: VaultSettings = { private_location: null, effective_private_location: '', default_visibility: 'tracked' }

export function VaultScreen() {
  const [watching, setWatching] = React.useState(0)
  const every = watching ? WATCH_EVERY_MS : false
  const map = useVaultMap(every)
  const settings = useVaultSettings()
  const contradictions = useVaultContradictions(every)
  const reports = useVaultReports(every)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [focusFactId, setFocusFactId] = React.useState<string | null>(null)
  // The source being read for facts, and how many facts it had when that started.
  const [extracting, setExtracting] = React.useState<{ id: string; facts: number } | null>(null)

  // Each watch restarts the clock: a later extraction gets its own few minutes.
  React.useEffect(() => {
    if (!watching) return
    const timer = setTimeout(() => {
      setWatching(0)
      setExtracting(null)
    }, WATCH_MS)
    return () => clearTimeout(timer)
  }, [watching])
  const watch = () => setWatching((count) => count + 1)

  const entries = React.useMemo(() => map.data ?? [], [map.data])
  const selected = entries.find((entry) => entry.id === selectedId) ?? null
  const factsOf = React.useCallback(
    (id: string) => entries.filter((entry) => isFact(entry) && (entry.sources ?? []).includes(id)),
    [entries],
  )
  const mapFacts = React.useMemo(() => (selected && !isFact(selected) ? factsOf(selected.id) : []), [selected, factsOf])
  const records = useVaultFactRecords(mapFacts.map((fact) => fact.id))
  const facts: VaultFact[] = mapFacts.map((fact, i) => {
    const record = records[i]?.data
    return record ? { ...fact, claim: record.claim, citations: record.citations } : fact
  })

  // Facts arrived for the source being extracted: it is done.
  const extractingFacts = extracting ? factsOf(extracting.id).length : 0
  React.useEffect(() => {
    if (extracting && extractingFacts > extracting.facts) {
      setExtracting(null)
      toast({ title: 'Facts extracted', description: 'Each one cites the lines it rests on.', tone: 'success' })
    }
  }, [extracting, extractingFacts])

  const pages = useVaultEntry(selected?.id ?? null)
  const loaded = pages.data?.pages ?? []
  const first = loaded[0]
  const page: VaultEntryPage | null = first
    ? { ...first, content: first.content === null ? null : loaded.map((p) => p.content ?? '').join('') }
    : null
  const fileKind = selected ? fileKindOf(selected.media_type) : null
  const file = useVaultFile(selected?.id ?? '', Boolean(selected && fileKind && (selected.available || hasTrackedFile(selected))))

  const upload = useUploadVaultSource()
  const uploadFile = useUploadVaultFile()
  const distil = useDistilVaultSource()
  const resolve = useResolveContradiction()
  const closeReport = useCloseVaultReport()
  const updateSettings = useUpdateVaultSettings()

  if (isNoVault(map.error) || isNoVault(settings.error)) {
    return (
      <div className="vault-state" data-testid="vault-none">
        <Icon name="library" size={20} />
        <p>This Hub has no vault yet. It arrives when the Hub is restarted on a version that has one.</p>
      </div>
    )
  }
  if (map.error) {
    return (
      <div className="vault-state" role="alert">
        <Icon name="alert_triangle" size={20} />
        <p>{readableApiError(map.error, "Could not read this project's vault.")}</p>
      </div>
    )
  }
  if (!map.data) {
    return (
      <div className="vault-state">
        <div aria-label="Loading the vault" className="skeleton aw-delayed h-[160px] w-full max-w-[720px]" />
      </div>
    )
  }

  /** Open a source, or a fact: under its source with it marked, or on its own when its source is
   *  not in the map. */
  const open = (id: string | null) => {
    const fact = id ? entries.find((entry) => entry.id === id && isFact(entry)) : undefined
    const source = fact ? (fact.sources ?? []).find((s) => entries.some((e) => e.id === s && !isFact(e))) : undefined
    setSelectedId(source ?? id)
    setFocusFactId(source ? (fact?.id ?? null) : null)
  }

  // A side's source is shown by name, never by id.
  const named = (list: VaultContradiction[]): VaultContradiction[] =>
    list.map((c) => ({
      ...c,
      sides: c.sides.map((side) => ({
        ...side,
        source: side.source ? (entries.find((e) => e.id === side.source)?.name ?? null) : null,
      })),
    }))

  const notices = [
    contradictions.error && !isNoVault(contradictions.error)
      ? readableApiError(contradictions.error, "Could not read this project's contradictions.")
      : null,
    reports.error && !isNoVault(reports.error) ? readableApiError(reports.error, "Could not read this project's reports.") : null,
  ].filter((n): n is string => Boolean(n))

  const add = async (input: VaultAddInput): Promise<VaultAddResult | void> => {
    if (input.kind === 'text') {
      try {
        const entry = await upload.mutateAsync({
          name: input.name,
          type: input.type as VaultType,
          content: input.content,
          visibility: input.visibility,
          ...(input.dated ? { dated: input.dated } : {}),
        })
        open(entry.id)
        watch()
        toast({ title: `Added “${entry.name}”`, tone: 'success', description: 'Agents see it in their next turn.' })
      } catch (error) {
        return { error: readableApiError(error, 'Could not add that source.') }
      }
      return
    }
    const added: VaultEntry[] = []
    const refused: Array<{ file: File; reason: string }> = []
    for (const one of input.files) {
      const path = (one as File & { webkitRelativePath?: string }).webkitRelativePath || one.name
      // The folder path stays in the name, so the library can group by it.
      const name = path.replace(/\.[^./]+$/, '')
      const mediaType = vaultFileMediaType(one)
      const type = (input.typeChosen ? input.type : mediaType ? 'document' : 'transcript') as VaultType
      const fields = { name, type, visibility: input.visibility, ...(input.dated ? { dated: input.dated } : {}) }
      try {
        if (mediaType) {
          added.push(await uploadFile.mutateAsync({ ...fields, file: one, mediaType }))
        } else {
          let content: string
          try {
            content = await one.text()
          } catch {
            refused.push({ file: one, reason: 'it could not be read as text' })
            continue
          }
          added.push(await upload.mutateAsync({ ...fields, content }))
        }
      } catch (error) {
        refused.push({ file: one, reason: readableApiError(error, 'the Hub refused it') })
      }
    }
    if (added.length) {
      open(added[added.length - 1]!.id)
      watch()
      toast({
        title: added.length === 1 ? `Added “${added[0]!.name}”` : `Added ${added.length} files`,
        tone: 'success',
        description: 'Agents see them in their next turn.',
      })
    }
    if (refused.length) {
      return {
        error:
          refused.length === 1
            ? `${refused[0]!.file.name}: ${refused[0]!.reason}`
            : `${refused.length} files were not added: ${refused.map((r) => `${r.file.name} (${r.reason})`).join('; ')}`,
        keep: refused.map((r) => r.file),
      }
    }
  }

  return (
    <VaultLibrary
      entries={entries}
      settings={settings.data ?? NO_SETTINGS}
      settingsError={settings.error ? readableApiError(settings.error, "Could not read the vault's settings.") : null}
      selectedId={selectedId}
      onSelect={open}
      page={page}
      facts={facts}
      contradictions={named(contradictions.data ?? [])}
      reports={reports.data ?? []}
      notices={notices}
      extractingId={distil.isPending ? distil.variables : (extracting?.id ?? null)}
      onAdd={add}
      onExtractFacts={(id) =>
        distil.mutate(id, {
          onSuccess: () => {
            setExtracting({ id, facts: factsOf(id).length })
            watch()
            toast({
              title: 'Extracting facts in the background',
              description: 'They appear under the source as they are written.',
            })
          },
          onError: (error) =>
            toast({ title: 'Could not extract facts', description: readableApiError(error, 'The Hub refused.'), tone: 'error' }),
        })
      }
      onResolve={async (id, stands, note) => {
        try {
          await resolve.mutateAsync({ id, stands, note })
          toast({ title: stands ? 'Recorded which fact holds' : 'Recorded that neither holds', description: 'Saved as a decision in the vault.', tone: 'success' })
        } catch (error) {
          return { error: readableApiError(error, 'Could not record that decision.') }
        }
      }}
      onCloseReport={async (id, note) => {
        try {
          await closeReport.mutateAsync({ id, note })
          toast({ title: 'Report closed', tone: 'success' })
        } catch (error) {
          return { error: readableApiError(error, 'Could not close that report.') }
        }
      }}
      onSaveSettings={async (next) => {
        const current = settings.data
        // Only what changed: the two are independent settings.
        const change = {
          ...(current?.default_visibility !== next.default_visibility ? { default_visibility: next.default_visibility } : {}),
          ...((current?.private_location ?? null) !== next.private_location ? { private_location: next.private_location } : {}),
        }
        if (!Object.keys(change).length) return
        try {
          await updateSettings.mutateAsync(change)
          toast({ title: 'Vault storage saved', tone: 'success' })
        } catch (error) {
          return { error: readableApiError(error, 'Could not save that change.') }
        }
      }}
      reader={{
        hasMore: pages.hasNextPage,
        loadingMore: pages.isFetchingNextPage,
        onLoadMore: () => void pages.fetchNextPage(),
        error: pages.error ? readableApiError(pages.error, 'Could not read this entry.') : null,
        fileError: file.error ? readableApiError(file.error, 'Could not load this file.') : null,
        file: file.url && fileKind ? { kind: fileKind, url: file.url } : null,
        focusFactId,
      }}
      now={new Date()}
    />
  )
}
