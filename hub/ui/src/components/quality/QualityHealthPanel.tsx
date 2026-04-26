import { useTasks } from '@/api/tasks'
import { useSessionSync, QualityConfig } from '@/api/status'
import { EmptyState } from '@/components/common/EmptyState'
import { Icon } from '@/components/common/Icon'

function SettingBadge({ label, value }: { label: string; value: string }) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]"
      style={{ background: 'var(--surface-3)', color: 'var(--text-3)' }}
    >
      <span style={{ opacity: 0.6 }}>{label}</span>
      <span style={{ color: 'var(--blue)', fontWeight: 600 }}>{value}</span>
    </span>
  )
}

function minutesAgo(isoTs: string): number {
  return Math.floor((Date.now() - new Date(isoTs).getTime()) / 60_000)
}

export function QualityHealthPanel() {
  const { data: sessionSync, isLoading: syncLoading } = useSessionSync()
  const { data: tasks } = useTasks()

  const quality: QualityConfig | undefined = sessionSync?.data?.quality

  if (syncLoading) {
    return <div className="p-6 text-sm" style={{ color: 'var(--text-3)' }}>Loading…</div>
  }

  if (!quality || (!quality.review_required && !quality.docs_path && !quality.docs_threshold)) {
    return (
      <div className="p-6">
        <EmptyState
          icon="verified"
          title="No quality governance configured"
          description="Add a quality: section to agentweave.yml to enable review gates, decision docs, and echo-chamber guard."
        />
      </div>
    )
  }

  const underReview = (tasks ?? []).filter((t) => t.status === 'under_review')
  const revisionNeeded = (tasks ?? []).filter((t) => t.status === 'revision_needed')
  const docsPath = quality.docs_path ?? '.agentweave/code-docs'
  const STALE_MIN = 15

  return (
    <div className="p-6 flex flex-col gap-5 overflow-auto">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Icon name="verified_user" size={20} style={{ color: 'var(--blue)' }} />
        <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>Quality Health</span>
      </div>

      {/* Active settings */}
      <div
        className="rounded-xl p-4 flex flex-col gap-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>
          Active Settings
        </span>
        <div className="flex flex-wrap gap-2">
          <SettingBadge label="review_required" value={quality.review_required ? 'true' : 'false'} />
          <SettingBadge label="docs_threshold" value={quality.docs_threshold ?? 'never'} />
          <SettingBadge label="echo_chamber" value={quality.echo_chamber_guard ?? 'off'} />
          {quality.attribution_tag && <SettingBadge label="attribution_tag" value="true" />}
          {quality.dependency_check && <SettingBadge label="dependency_check" value="true" />}
          {quality.docs_path && <SettingBadge label="docs_path" value={quality.docs_path} />}
        </div>
      </div>

      {/* Under review */}
      <div
        className="rounded-xl p-4 flex flex-col gap-3"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>
            Under Review
          </span>
          <span
            className="text-[10px] font-semibold rounded-full px-2 py-0.5"
            style={{ background: 'var(--surface-3)', color: 'var(--text-2)' }}
          >
            {underReview.length}
          </span>
        </div>

        {underReview.length === 0 ? (
          <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
            <Icon name="check_circle" size={16} style={{ color: 'var(--green)' }} />
            All reviewed tasks clear
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {underReview.map((t) => {
              const age = t.updated ? minutesAgo(t.updated) : null
              const stale = age !== null && age >= STALE_MIN
              return (
                <div
                  key={t.id}
                  className="flex items-start justify-between rounded-lg px-3 py-2"
                  style={{
                    background: stale
                      ? 'rgba(239,68,68,0.06)'
                      : 'var(--surface-2)',
                    border: stale ? '1px solid rgba(239,68,68,0.2)' : '1px solid var(--border)',
                  }}
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="text-xs font-medium" style={{ color: 'var(--text)' }}>
                      {t.id}: {t.title}
                    </span>
                    {t.assignee && (
                      <span className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                        reviewer: {t.assignee}
                      </span>
                    )}
                    <span className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.6 }}>
                      decision doc: {docsPath}/{t.id}.md
                    </span>
                  </div>
                  {age !== null && (
                    <span
                      className="text-[11px] shrink-0 ml-3"
                      style={{ color: stale ? 'var(--red)' : 'var(--text-3)', opacity: stale ? 1 : 0.6 }}
                    >
                      {stale ? `⚠ ${age}min` : `~${age}min`}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Revision needed */}
      {revisionNeeded.length > 0 && (
        <div
          className="rounded-xl p-4 flex flex-col gap-3"
          style={{
            background: 'rgba(245,158,11,0.04)',
            border: '1px solid rgba(245,158,11,0.2)',
          }}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--text-3)' }}>
              Revision Needed
            </span>
            <span
              className="text-[10px] font-semibold rounded-full px-2 py-0.5"
              style={{ background: 'var(--surface-3)', color: 'var(--text-2)' }}
            >
              {revisionNeeded.length}
            </span>
          </div>
          <div className="flex flex-col gap-2">
            {revisionNeeded.map((t) => (
              <div key={t.id} className="flex items-center gap-2">
                <Icon name="refresh" size={14} style={{ color: 'var(--amber)' }} />
                <span className="text-xs" style={{ color: 'var(--text)' }}>
                  {t.id}: {t.title}
                </span>
                {t.assignee && (
                  <span className="text-[11px]" style={{ color: 'var(--text-3)', opacity: 0.7 }}>
                    ({t.assignee})
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
