import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { corpusRefusal, useAdoptSpecDocument, type AdoptionDifference } from '@/api/spec'

interface SpecAdoptButtonProps {
  path: string
  onAdopted?: (path: string) => void
}

/**
 * Adopt one document found on disk that the Hub has no record of (design D3, F206).
 *
 * A refusal is shown in the Hub's own words, and a `document_exists` refusal with each field on
 * which the file and the existing record disagree, because that difference is the decision the
 * operator has to make.
 */
export function SpecAdoptButton({ path, onAdopted }: SpecAdoptButtonProps) {
  const adopt = useAdoptSpecDocument()
  const [refusal, setRefusal] = useState<{ message: string; differences?: AdoptionDifference[] } | null>(
    null,
  )

  return (
    <span
      data-testid={`spec-adopt-${path}`}
      style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}
    >
      <Button
        size="xs"
        variant="outline"
        disabled={adopt.isPending}
        onClick={(e) => {
          e.stopPropagation()
          setRefusal(null)
          adopt.mutate(
            { path },
            {
              onSuccess: () => onAdopted?.(path),
              onError: (error) => {
                const refused = corpusRefusal(error)
                setRefusal({
                  message: refused?.message ?? 'Adopting failed.',
                  differences: refused?.differences,
                })
              },
            },
          )
        }}
      >
        Adopt
      </Button>
      {refusal && (
        <span role="alert" style={{ fontSize: 11, color: 'var(--text-2)', maxWidth: 320, textAlign: 'right' }}>
          {refusal.message}
          {(refusal.differences ?? []).map((d) => (
            <span key={d.field} style={{ display: 'block', color: 'var(--text-3)' }}>
              {d.field}: file {d.file ?? '—'} vs record {d.row ?? '—'}
            </span>
          ))}
        </span>
      )}
    </span>
  )
}
