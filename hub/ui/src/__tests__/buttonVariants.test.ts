import { describe, expect, it } from 'vitest'
import { buttonVariants } from '@/components/ui/button'

describe('Button — ghost variant draws no border in any state (composer/chrome refinement §1)', () => {
  it('ghost declares no hover or active border utility', () => {
    const classes = buttonVariants({ variant: 'ghost', size: 'md' })
    expect(classes).not.toMatch(/(hover|active):border/)
  })

  it('the base transparent border is the only border rule in play, so hover cannot shift box dimensions', () => {
    // The base class's `border border-transparent` is unconditional — present at rest,
    // hover, and active alike. If `ghost` contributed no other `border*` token, there is
    // nothing that could change the rendered border width between states. Tokenised by
    // whitespace rather than a loose regex scan — a naive `border` substring match also
    // catches `transition-[...,border-color,...]`, which is not a border-width utility.
    const classes = buttonVariants({ variant: 'ghost', size: 'md' })
    const borderTokens = classes.split(/\s+/).filter((token) => /^border(-\S+)?$/.test(token)).sort()
    expect(borderTokens).toEqual(['border', 'border-transparent'])
  })

  it('outline and destructive keep their resting border unchanged (not migrated to borderless)', () => {
    expect(buttonVariants({ variant: 'outline', size: 'md' })).toMatch(/\bborder-\[var\(--border\)\]/)
    expect(buttonVariants({ variant: 'destructive', size: 'md' })).toMatch(/\bborder-\[color-mix/)
  })

  it('the pill size declares no radius, leaving rounding entirely to the caller', () => {
    // See button.tsx's own comment: a size variant that shipped a `rounded-*` class would
    // fight a caller-supplied `rounded-full` for specificity with no defined winner.
    expect(buttonVariants({ variant: 'ghost', size: 'pill' })).not.toMatch(/\brounded/)
  })

  it('every variant/size combination keeps a focus indicator', () => {
    for (const variant of ['primary', 'ghost', 'outline', 'destructive'] as const) {
      expect(buttonVariants({ variant, size: 'pill' })).toContain('focus-visible:ring-2')
    }
  })
})
