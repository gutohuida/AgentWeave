import { useMemo } from 'react'
import { Icon } from '@/components/common/Icon'
import { Button } from '@/components/ui/button'
import { useProjectEvidence, useSpecList } from '@/api/spec'
import { buildInventory } from './specNavigation'
import { SpecTree } from './SpecTree'
import { SpecDefectsReport } from './SpecDefectsReport'

interface SpecRailNavProps {
  projectName: string
  currentPath: string | null
  onSelect: (path: string) => void
  onBack: () => void
  /** Whether the evidence view is open, and how to open it (slice evidence-browser). */
  evidenceOpen?: boolean
  onOpenEvidence?: () => void
}

/**
 * The specification tree, in the rail, while the Spec screen is open.
 *
 * It replaces the project tree rather than sitting beside it, the way Environment and agent
 * settings already replace it — the operator's own reading of the shape: *"Is it possible to make
 * it like the config screen where the navigation replaces the left navigation? Two navigations are
 * weird."* They were right, and it is the same mistake the Spec page made the first time round,
 * one level out: a screen that needs navigation should use the rail rather than grow a second one
 * next to it.
 *
 * The back control is what keeps that honest. Taking the rail over is only acceptable while there
 * is one press that gives it back.
 */
export function SpecRailNav({
  projectName,
  currentPath,
  onSelect,
  onBack,
  evidenceOpen = false,
  onOpenEvidence,
}: SpecRailNavProps) {
  // Same query key as the Spec screen's, so standing in for the project tree costs no request.
  const { data: specList } = useSpecList()
  const inventory = useMemo(() => buildInventory(specList), [specList])
  const { data: evidence } = useProjectEvidence(!!onOpenEvidence)
  const pieces = evidence?.evidence?.length ?? null

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="mb-3 w-full justify-start"
        data-testid="spec-rail-back"
        aria-label={`Back to ${projectName}`}
        onClick={onBack}
      >
        <Icon name="arrow_left" size={15} />
        {projectName}
      </Button>
      <div className="mb-3 flex items-center gap-2 px-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)]" style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}>
          <Icon name="article" size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold" style={{ color: 'var(--text)' }}>Specification</div>
          <div className="truncate text-[11px]" style={{ color: 'var(--text-3)' }}>Document authority</div>
        </div>
        <span className="aw-chip" data-pill="true" aria-label={`${inventory.nodes.length} documents`}>
          {inventory.nodes.length}
        </span>
      </div>
      {onOpenEvidence ? (
        <button
          type="button"
          className="aw-rail-entry mb-2"
          aria-current={evidenceOpen ? 'page' : undefined}
          onClick={onOpenEvidence}
          data-testid="spec-rail-evidence"
        >
          <Icon name="fact_check" size={15} />
          Evidence
          {pieces !== null ? <span className="aw-rail-count">{pieces}</span> : null}
        </button>
      ) : null}
      <nav
        aria-label="Specification documents"
        data-testid="spec-rail-tree"
        className="min-h-0 flex-1 overflow-y-auto"
      >
        <SpecTree
          inventory={inventory}
          currentPath={currentPath}
          onSelect={(node) => onSelect(node.path)}
          density="rail"
        />
      </nav>
      <SpecDefectsReport currentPath={currentPath} onSelect={onSelect} />
    </>
  )
}
