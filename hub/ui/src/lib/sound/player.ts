import './agentweave-sound.js'
import type { NotifyKind } from '@/lib/notify/classify'

/** Plays the brand's sounds live. `agentweave-sound.js` is brand/sound/agentweave-sound.js copied
 *  byte for byte (notifications.test.ts fails when they differ); it registers
 *  `globalThis.AgentWeaveSound` when loaded as a plain script, which is how this module loads it.
 *
 *  One AudioContext, made on first use. The native app window lets it run without a click (the CLI
 *  sets WebView2's autoplay policy); a browser tab keeps it suspended until the operator's first
 *  click or key press, so `unlockSoundOnFirstGesture` resumes it then. */
interface Synth {
  master: GainNode
  play: (name: string) => void
}

interface SoundModule {
  create: (ctx: BaseAudioContext, options?: { key?: string; gain?: number }) => Synth
}

let ctx: AudioContext | null = null
let synth: Synth | null = null

function engine(): { ctx: AudioContext; synth: Synth } | null {
  if (ctx && synth) return { ctx, synth }
  const mod = (globalThis as { AgentWeaveSound?: SoundModule }).AgentWeaveSound
  const Ctor = typeof window !== 'undefined' ? window.AudioContext : undefined
  if (!mod || !Ctor) return null
  try {
    ctx = new Ctor()
    synth = mod.create(ctx, { key: 'D', gain: 0.7 })
    return { ctx, synth }
  } catch {
    ctx = null
    synth = null
    return null
  }
}

export function playSound(kind: NotifyKind | 'ready', gain: number): void {
  const e = engine()
  if (!e) return
  if (e.ctx.state === 'suspended') e.ctx.resume().catch(() => {})
  e.synth.master.gain.setValueAtTime(Math.max(0, Math.min(1, gain)), e.ctx.currentTime)
  e.synth.play(kind)
}

export function unlockSoundOnFirstGesture(): () => void {
  const unlock = () => {
    const e = engine()
    if (e && e.ctx.state === 'suspended') e.ctx.resume().catch(() => {})
    remove()
  }
  const remove = () => {
    window.removeEventListener('pointerdown', unlock, true)
    window.removeEventListener('keydown', unlock, true)
  }
  window.addEventListener('pointerdown', unlock, true)
  window.addEventListener('keydown', unlock, true)
  return remove
}
