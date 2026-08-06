import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'

/**
 * The Hub's control primitive.
 *
 * Three rules make controls feel deliberate, and all three are in the base
 * class rather than the variants, so no variant can opt out:
 *
 *  1. `border border-transparent` is ALWAYS present. Quiet variants render it
 *     transparent and colour it on hover. Because the border occupies layout at
 *     rest, gaining emphasis never displaces the control or its neighbours —
 *     the usual approach of adding a border on hover shifts content by a pixel.
 *
 *  2. Horizontal padding subtracts the border thickness, so label insets look
 *     identical whether or not the border is visible.
 *
 *  3. Raised variants are lit from above at rest and invert while pressed: the
 *     top-edge highlight becomes an inset shadow and the resting elevation is
 *     removed, so the control reads as physically depressed.
 *
 * Icons are subordinate by default (reduced opacity), using a selector that
 * leaves explicitly-coloured icons alone.
 */
const buttonVariants = cva(
  [
    'relative inline-flex shrink-0 cursor-pointer items-center justify-center gap-2',
    'whitespace-nowrap font-medium outline-none',
    'border border-transparent',
    'transition-[background-color,border-color,box-shadow,color,opacity]',
    'duration-[var(--dur-fast)] ease-[var(--ease)]',
    'focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-1',
    'focus-visible:ring-offset-[var(--bg)]',
    'disabled:pointer-events-none disabled:opacity-[0.64] disabled:shadow-none',
    "[&_svg:not([class*='opacity-'])]:opacity-80",
    '[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:-mx-0.5',
    // Coarse pointers get a full-size target without changing visual size.
    'pointer-coarse:after:absolute pointer-coarse:after:left-1/2 pointer-coarse:after:top-1/2',
    'pointer-coarse:after:min-h-11 pointer-coarse:after:min-w-11',
    'pointer-coarse:after:-translate-x-1/2 pointer-coarse:after:-translate-y-1/2',
    'pointer-coarse:after:content-[""]',
  ].join(' '),
  {
    variants: {
      variant: {
        /** Raised. Lit from above; inverts and sits down when pressed. */
        primary: [
          'bg-[var(--primary)] text-[var(--primary-foreground)] border-[var(--primary)]',
          'shadow-[inset_0_1px_0_var(--lift-hi),0_1px_3px_rgb(0_0_0/0.24)]',
          'hover:bg-[var(--primary-hover)]',
          'active:bg-[var(--primary-active)]',
          'active:shadow-[inset_0_1px_0_var(--press-lo)]',
        ].join(' '),
        /** Quiet. Floats in nothing until touched — hover/active brighten fill and text only,
         * never the border, so nothing is ever drawn around a resting control. */
        ghost: [
          'bg-transparent text-[var(--text)]',
          'hover:bg-[var(--accent)]',
          'active:bg-[var(--accent)] active:shadow-[inset_0_1px_0_var(--press-lo)]',
          "[&_svg:not([class*='text-'])]:text-[var(--text-2)]",
        ].join(' '),
        /** Bounded but unfilled. */
        outline: [
          'bg-[var(--surface-2)] text-[var(--text)] border-[var(--border)]',
          'shadow-[0_1px_2px_rgb(0_0_0/0.16)]',
          'hover:border-[var(--border-hi)] hover:bg-[var(--surface-3)]',
          'active:shadow-[inset_0_1px_0_var(--press-lo)]',
          "[&_svg:not([class*='text-'])]:text-[var(--text-2)]",
        ].join(' '),
        destructive: [
          'bg-[var(--error-cont)] text-[var(--on-error-cont)]',
          'border-[color-mix(in_oklab,var(--destructive)_50%,transparent)]',
          'hover:bg-[color-mix(in_oklab,var(--destructive)_20%,transparent)]',
          'hover:border-[color-mix(in_oklab,var(--destructive)_75%,transparent)]',
          'active:shadow-[inset_0_1px_0_var(--press-lo)]',
        ].join(' '),
      },
      size: {
        xs: 'h-7 gap-1 rounded-[var(--radius-sm)] px-[calc(0.5rem-1px)] text-xs',
        sm: 'h-8 gap-1.5 rounded-[var(--radius-md)] px-[calc(0.625rem-1px)] text-[13px]',
        md: 'h-9 rounded-[var(--radius-lg)] px-[calc(0.75rem-1px)] text-[13px]',
        lg: 'h-10 rounded-[var(--radius-lg)] px-[calc(0.875rem-1px)] text-sm',
        icon: 'size-9 rounded-[var(--radius-lg)] p-0',
        'icon-sm': 'size-8 rounded-[var(--radius-md)] p-0',
        'icon-xs': 'size-7 rounded-[var(--radius-sm)] p-0',
        /** Content height and padding only — deliberately no `rounded-*` class, so a
         * caller supplying `rounded-full` (the composer-control appearance) never has to
         * out-specificity a radius this variant already set. Used by composer triggers
         * (model, effort, conversation routing, target agent), which round to a pill at
         * their own height rather than the fixed radius scale. */
        pill: 'h-8 gap-1 px-2.5 text-xs',
      },
    },
    defaultVariants: { variant: 'ghost', size: 'md' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        ref={ref}
        type={asChild ? undefined : (type ?? 'button')}
        data-slot="button"
        className={[buttonVariants({ variant, size }), className].filter(Boolean).join(' ')}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'

export { buttonVariants }
