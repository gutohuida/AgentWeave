import * as RadixToast from '@radix-ui/react-toast'
import { useToastStore, type ToastTone } from '@/lib/toast'
import { Icon } from '@/components/common/Icon'

/** Confirmations and undo. `@radix-ui/react-toast` was installed and never used, so a saved
 *  setting, an archived agent or a queued job said nothing, or said it inline in amber text.
 *
 *  Call `toast({ title, description?, tone?, action? })` from anywhere. Toasts stack bottom-right,
 *  4s each, paused on hover and while the window is hidden (Radix), announced politely to screen
 *  readers (errors assertively). Motion: rise + fade in 320ms on the out-curve, out 180ms. */

const TONE_ICON: Record<ToastTone, string | null> = { neutral: null, success: 'check_circle', error: 'error' }

export function Toaster() {
  const { items, close, remove } = useToastStore()
  return (
    <RadixToast.Provider swipeDirection="right" duration={4000}>
      {items.map((item) => {
        const tone = item.tone ?? 'neutral'
        const icon = TONE_ICON[tone]
        return (
          <RadixToast.Root
            key={item.id}
            open={item.open}
            duration={item.duration}
            type={tone === 'error' ? 'foreground' : 'background'}
            onOpenChange={(open) => {
              if (!open) {
                close(item.id)
                window.setTimeout(() => remove(item.id), 220)
              }
            }}
            className="aw-toast"
            data-tone={tone}
          >
            {icon ? <Icon name={icon} size={15} className="aw-toast-icon" /> : null}
            <div className="min-w-0 flex-1">
              <RadixToast.Title className="aw-toast-title">{item.title}</RadixToast.Title>
              {item.description ? <RadixToast.Description className="aw-toast-desc">{item.description}</RadixToast.Description> : null}
            </div>
            {item.action ? (
              <RadixToast.Action data-slot="toast-action" altText={item.action.label} className="aw-toast-action" onClick={item.action.onClick}>
                {item.action.label}
              </RadixToast.Action>
            ) : null}
            <RadixToast.Close data-slot="toast-close" className="aw-toast-close" aria-label="Dismiss">
              <Icon name="close" size={12} />
            </RadixToast.Close>
          </RadixToast.Root>
        )
      })}
      <RadixToast.Viewport className="aw-toast-viewport" />
    </RadixToast.Provider>
  )
}
