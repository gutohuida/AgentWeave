/** The containers' data: what the Hub answers, turned into the props the redesigned page's
 *  components take (spec `the-spec-page-redesigned`, task `wire`). The Spec tab and the
 *  conversation's side panel call the same two hooks, so they cannot show different things. */
import * as React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { MenuItem } from '@/components/ui/menu'
import { useBuildFigures } from '@/api/buildFigures'
import { readableApiError } from '@/api/client'
import {
  useSpec,
  useSpecCoverage,
  useSpecDocuments,
  useSpecList,
  useStopBuild,
  type SpecListResponse,
} from '@/api/spec'
import { useDocumentTasks } from '@/api/tasks'
import { serializeDestination, projectDestination } from '@/lib/navigation'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { SpecAmendmentsPanel } from '../SpecAmendmentsPanel'
import { SpecDeletedNote } from '../SpecDeletedNote'
import { SpecPlaceUnder } from '../SpecPlaceUnder'
import { SpecRetiredRequirements } from '../SpecRetiredRequirements'
import { useSpecPhaseControls } from '../useSpecPhaseControls'
import { buildViews, documentView, findingsOf, listEntries, parsePayload, textOfPage } from './adapt'
import { useListPreferences } from './hooks'
import { NO_DOCUMENT_FILTERS, type CheckState, type DocumentFilters, type ListPreferences, type SpecAction, type SpecListEntry } from './model'
import { SpecDocumentFacts } from './SpecDocumentFacts'
import type { PlainDocument } from './SpecPlainDocument'
import type { HeaderChrome } from './SpecPageHeader'
import type { SpecSurfaceProps } from './SpecWorkspace'
import type { LoopSummary } from '@/api/loops'

// ── The list ────────────────────────────────────────────────────────────

export interface SpecListData {
  entries: SpecListEntry[]
  loading: boolean
  specList: SpecListResponse | undefined
  refetch: () => void
  /** Why the list could not be read, when it could not. */
  error: unknown
  prefs: ListPreferences
  setPrefs: (next: ListPreferences) => void
}

/** Every document the project holds, as the list and the picker draw them, with the operator's
 *  filters and order (kept per project in this browser). */
export function useSpecListData(): SpecListData {
  const projectId = useConfigStore((s) => s.selectedProjectId) ?? ''
  const { data: specList, isLoading, refetch, error: listError } = useSpecList()
  const { data: records, error: recordsError } = useSpecDocuments()
  const [prefs, setPrefs] = useListPreferences(projectId)
  const entries = React.useMemo(() => (specList ? listEntries(specList.specs, records?.documents ?? []) : []), [specList, records])
  return { entries, loading: isLoading, specList, refetch: () => void refetch(), error: listError ?? recordsError, prefs, setPrefs }
}

/** A running build's progress per document path, for the picker's cards. */
export function useBuildProgress(): Record<string, { done: number; total: number }> {
  const { data: records, error } = useSpecDocuments()
  return React.useMemo(
    () => error ? {} : Object.fromEntries((records?.documents ?? []).filter((d) => d.build).map((d) => [d.path, { done: d.build!.done, total: d.build!.total }])),
    [records, error],
  )
}

// ── One document ────────────────────────────────────────────────────────

export interface SpecSurfaceHost {
  /** Open another document (a roadmap, a neighbouring slice, a link). */
  onOpenDocument: (path: string) => void
  /** The Tasks tab, filtered to these tasks. */
  onOpenTasks?: (taskIds: string[], specDocumentId?: string) => void
  onOpenLoop?: (loop: LoopSummary) => void
  /** The document was deleted: leave it. */
  onDeleted?: () => void
  /** A position a link named, opened on arrival. */
  initialAnchor?: string | null
}

export type SpecSurfaceResult =
  | { status: 'loading' }
  | { status: 'unreadable'; message: string; plain: PlainDocument | null }
  | { status: 'ready'; surface: SpecSurfaceProps }

/** Ticks, so "started 3m ago" and a running build's age stay true without a refetch. */
function useNow(everyMs = 30_000): Date {
  const [now, setNow] = React.useState(() => new Date())
  React.useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), everyMs)
    return () => window.clearInterval(timer)
  }, [everyMs])
  return now
}

function copy(text: string) {
  void navigator.clipboard?.writeText(text).catch(() => undefined)
}

/** The open document as the page's components take it. Call it under a `key` of the path: Check's
 *  findings and the document's filters belong to the document. */
export function useSpecSurface(path: string, host: SpecSurfaceHost): SpecSurfaceResult {
  const projectId = useConfigStore((s) => s.selectedProjectId) ?? ''
  const { data: specDoc, isError: readFailed, error: readError } = useSpec(path)
  const { data: records, error: recordsError } = useSpecDocuments()
  const list = useSpecListData()
  const record = records?.documents.find((d) => d.path === path)
  const { data: coverage, error: coverageError } = useSpecCoverage(path)
  const { data: tasks, error: tasksError } = useDocumentTasks(record?.id ?? null)
  const builds = React.useMemo(() => specDoc?.builds ?? [], [specDoc?.builds])
  const figures = useBuildFigures(builds)
  const stop = useStopBuild()
  const queryClient = useQueryClient()
  const now = useNow()
  const [filters, setFilters] = React.useState<DocumentFilters>(NO_DOCUMENT_FILTERS)
  const controls = useSpecPhaseControls(path, host.onOpenLoop, host.onDeleted, { inlineFindings: true })

  // `at` changes whenever a check answers, so the result pill plays its entrance again.
  const checking = controls?.findings.checking ?? false
  const answers = React.useRef(0)
  const wasChecking = React.useRef(false)
  if (wasChecking.current && !checking) answers.current += 1
  wasChecking.current = checking

  const payload = React.useMemo(() => (specDoc ? parsePayload(specDoc.content) : null), [specDoc])

  if (readFailed && !specDoc) {
    return { status: 'unreadable', message: readableApiError(readError, 'The Hub could not read this document.'), plain: null }
  }
  if (!specDoc || !records) return { status: 'loading' }
  if (!payload) {
    return {
      status: 'unreadable',
      message: 'This document has no structure the page can draw.',
      plain: { path, phase: record?.phase ?? null, text: textOfPage(specDoc.content) },
    }
  }

  const entry = list.entries.find((e) => e.path === path)
  const effectiveRecord = record ?? {
    id: entry?.id ?? path,
    path,
    title: entry?.title ?? path,
    kind: entry?.kind ?? 'baseline',
    phase: 'current' as const,
    rigor: 'sketch' as const,
    content_digest: null,
    explore_closed: false,
    updated_at: specDoc.updated_at ?? '',
  }
  const clean = !!controls && controls.findings.checked && controls.findings.blocking.length === 0
  const doc = documentView({
    record: effectiveRecord,
    payload,
    updatedAt: specDoc.updated_at ?? effectiveRecord.updated_at,
    coverage: coverage?.requirements ?? [],
    tasks: tasks ?? [],
    builds,
    entries: list.entries,
    checkedClean: clean,
    foldReady: !!controls?.actions.fold,
    sliceDocuments: specDoc.slice_documents,
  })

  const check: CheckState = checking
    ? { status: 'checking' }
    : controls?.findings.checked
      ? {
          status: 'done',
          findings: findingsOf(controls.findings.blocking, controls.findings.gaps, doc, payload),
          at: String(answers.current),
        }
      : { status: 'idle' }

  const buildList = buildViews(builds, tasks ?? [], figures)
  const linkTo = (anchor: string | null) =>
    `${window.location.origin}${window.location.pathname}${serializeDestination(projectDestination(projectId, 'spec', path, anchor))}`

  const onAction = (action: SpecAction) => {
    if (!controls) {
      toast({ title: 'The Hub keeps no record of this document', description: 'Adopt it from the list first.' })
      return
    }
    switch (action) {
      case 'check':
        return controls.actions.check()
      case 'approve':
        return controls.actions.approve()
      case 'approve-and-build':
        return controls.actions.approveAndBuild()
      case 'build':
        return controls.actions.build()
      case 'reopen':
        return controls.actions.reopen()
      case 'fold':
        return controls.actions.fold?.()
      case 'open-build':
        return
    }
  }

  const unread = [list.error, recordsError, coverageError, tasksError].find(Boolean)
  const banner = ({ jump }: { jump: (anchor: string) => void }) => (
    <div className="aw-sp-banner" data-testid="spec-banner">
      {unread ? (
        <p className="aw-spec-message" data-tone="warn" data-testid="spec-unread">
          <span className="aw-spec-message-text">Part of this page could not be read: {readableApiError(unread, 'the Hub did not answer.')}</span>
        </p>
      ) : null}
      <SpecDeletedNote />
      {controls ? controls.messages : null}
      <SpecDocumentFacts path={path} specList={list.specList} onOpenTasks={host.onOpenTasks} onOpenRequirement={jump} />
      <SpecAmendmentsPanel path={path} />
      <SpecRetiredRequirements path={path} onOpenTasks={host.onOpenTasks} />
      {controls ? controls.dialogs : null}
    </div>
  )

  const node = list.specList?.specs.find((e) => e.path === path)
  const refresh = () => {
    for (const key of ['specs', 'specDocuments', 'specCoverage', 'tasks', 'loops']) {
      void queryClient.invalidateQueries({ queryKey: ['project', projectId, key] })
    }
    void queryClient.invalidateQueries({ queryKey: ['project', projectId, 'spec', path] })
  }
  // Everything the phase controls offer that the page's own buttons do not draw (one source).
  const chrome: HeaderChrome = {
    moreItems: (
      <>
        {controls?.menu}
        <MenuItem icon="refresh" onSelect={refresh}>
          Refresh
        </MenuItem>
      </>
    ),
    badges: (
      <>
        {controls?.badges}
        {doc.state === 'archived' ? (
          <span className="aw-sp-meta-fact" data-testid="spec-archived-marker">
            Archived
          </span>
        ) : null}
        {/* D4 (F206): a filed document, under a valid index, can be placed in the hierarchy. */}
        {node?.state === 'filed' && list.specList?.manifest?.state === 'valid' ? (
          <SpecPlaceUnder path={path} parent={node.parent ?? null} specList={list.specList} />
        ) : null}
      </>
    ),
  }

  const surface: SpecSurfaceProps = {
    chrome,
    doc,
    builds: buildList,
    check,
    filters,
    onFiltersChange: setFilters,
    now,
    initialAnchor: host.initialAnchor ?? null,
    onAction,
    onOpenDocument: host.onOpenDocument,
    onCopyLink: (anchor) => {
      copy(linkTo(anchor))
      toast({ title: 'Link copied', description: anchor ? 'Opens this document at that place.' : 'Opens this document.', tone: 'success' })
    },
    onCopyPath: () => {
      copy(path)
      toast({ title: 'Path copied', tone: 'success' })
    },
    onArchive: controls?.archive,
    onDelete: controls?.remove,
    onStartBuild: () => onAction('build'),
    onOpenRuns: (build) => {
      const ids = (tasks ?? []).filter((t) => t.build_id === build.id).map((t) => t.id)
      if (host.onOpenTasks && ids.length) host.onOpenTasks(ids)
      else toast({ title: `Build ${build.number}`, description: `${build.runs} runs. Open the Spec tab to see its tasks.` })
    },
    onStopBuild: (build) =>
      stop.mutate(
        { id: build.id },
        {
          onSuccess: () => toast({ title: `Build ${build.number} stopped`, description: 'Work in progress stays on its branch.' }),
          onError: (error: unknown) => toast({ title: 'Could not stop the build', description: readableApiError(error, 'The Hub refused.'), tone: 'error' }),
        },
      ),
    banner,
  }
  return { status: 'ready', surface }
}
