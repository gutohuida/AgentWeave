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
import { useVaultChecked } from '@/api/vault'
import { serializeDestination, projectDestination } from '@/lib/navigation'
import { toast } from '@/lib/toast'
import { useConfigStore } from '@/store/configStore'
import { openTraces } from '@/store/tracesRequestStore'
import { useSpecDeletionStore } from '@/store/specDeletionStore'
import { keptDetail } from '@/lib/eventSummary'
import { useAmendmentNotices } from '../amendmentNotices'
import { SpecPlaceUnder } from '../SpecPlaceUnder'
import { useRetiredRequirementsNotice } from '../retiredRequirementsNotice'
import { useSpecPhaseControls } from '../useSpecPhaseControls'
import { buildViews, documentView, findingsOf, listEntries, parsePayload, textOfPage } from './adapt'
import { useListPreferences } from './hooks'
import { NO_DOCUMENT_FILTERS, type CheckState, type DocumentFilters, type ListPreferences, type SpecAction, type SpecListEntry } from './model'
import { SpecDocumentFacts } from './SpecDocumentFacts'
import type { HeaderNotice } from './SpecNotices'
import type { PlainDocument } from './SpecPlainDocument'
import { SpecRetrospective } from './SpecRetrospective'
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

/** Whether some of the document's facts (`SpecDocumentFacts`) could not be read, so the line may be missing some. */
function useFactsUnread(path: string): boolean {
  const { error: specError } = useSpec(path)
  const { error: coverageError } = useSpecCoverage(path)
  const { error: vaultCheckedError } = useVaultChecked(path)
  const { data: documents, error: documentsError } = useSpecDocuments()
  const record = documents?.documents.find((entry) => entry.path === path)
  const { error: tasksError } = useDocumentTasks(record?.id ?? null)
  return [specError, coverageError, vaultCheckedError, documentsError, tasksError].some(Boolean)
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
  const amendmentNotices = useAmendmentNotices(path)
  const retiredNotice = useRetiredRequirementsNotice(path, host.onOpenTasks)
  const factsUnread = useFactsUnread(path)
  const deleted = useSpecDeletionStore((s) => s.notice)
  const clearDeleted = useSpecDeletionStore((s) => s.clear)

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

  // Everything the banner used to stack between the header and the body, as the header's notices
  // (spec `the-spec-header-redesigned`, FR-5, FR-7). The facts are in the header's second row, the
  // build's strip in the builds section, and the dialogs stay where they were.
  const unread = [list.error, recordsError, coverageError, tasksError].find(Boolean)
  const notices: HeaderNotice[] = []
  if (unread) {
    notices.push({
      id: 'unread',
      tone: 'error',
      testId: 'spec-unread',
      summary: `Part of this page could not be read: ${readableApiError(unread, 'the Hub did not answer.')}`,
    })
  }
  if (factsUnread) {
    notices.push({
      id: 'facts-unread',
      tone: 'warn',
      testId: 'spec-facts-unread',
      summary: "Some of this document's facts could not be read, so the facts beside the phase may be missing some.",
    })
  }
  if (deleted) {
    // F829, F838: what "Delete document" removed, and any branch kept from a deleted task.
    notices.push({
      id: 'deleted',
      tone: 'info',
      testId: 'spec-deleted-note',
      summary:
        deleted.tasks === 0
          ? `Deleted “${deleted.title}”. It had no tasks.`
          : `Deleted “${deleted.title}” and its ${deleted.tasks} ${deleted.tasks === 1 ? 'task' : 'tasks'}.`,
      body: (deleted.kept ?? []).length ? (
        <ul>
          {(deleted.kept ?? []).map((kept) => (
            <li key={kept.task_id} data-testid="spec-deleted-kept">
              {kept.error
                ? `Could not clean up the checkout of ${kept.task_id}: ${kept.error}`
                : `Kept ${kept.branch ?? 'its branch'}${keptDetail(kept)} from a deleted task.`}
            </li>
          ))}
        </ul>
      ) : undefined,
      defaultOpen: true,
      action: { label: 'Dismiss', onClick: clearDeleted },
    })
  }
  notices.push(...(controls?.notices ?? []), ...amendmentNotices)
  if (retiredNotice) notices.push(retiredNotice)

  const health = ({ jump }: { jump: (anchor: string) => void }) => (
    <SpecDocumentFacts path={path} specList={list.specList} onOpenTasks={host.onOpenTasks} onOpenRequirement={jump} inHeader />
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
        {controls?.facts}
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
      // The runs of the build's tasks, listed in Activity → Traces (FR-12).
      const project = useConfigStore.getState().selectedProjectId
      if (project) openTraces(project, { build: build.id, label: `build ${build.number}` })
    },
    onStopBuild: (build) =>
      stop.mutate(
        { id: build.id },
        {
          onSuccess: () => toast({ title: `Build ${build.number} stopped`, description: 'Work in progress stays on its branch.' }),
          onError: (error: unknown) => toast({ title: 'Could not stop the build', description: readableApiError(error, 'The Hub refused.'), tone: 'error' }),
        },
      ),
    notices,
    health,
    buildActions: controls?.buildActions,
    dialogs: controls?.dialogs,
    retrospective:
      doc.kind === 'change-spec'
        ? ({ flash, onCopyLink }) => <SpecRetrospective path={path} now={now} flash={flash} onCopyLink={onCopyLink} />
        : undefined,
  }
  return { status: 'ready', surface }
}
