import '@testing-library/jest-dom/vitest'
import { afterEach, beforeEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
  localStorage.clear()
  sessionStorage.clear()
  vi.restoreAllMocks()
})

beforeEach(() => {
  // Reset storage between tests so test order does not matter
  localStorage.clear()
  sessionStorage.clear()
})

// Radix + many UI libraries touch these in module init; stub them globally.
class StubObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): unknown[] {
    return []
  }
}
;(globalThis as unknown as { IntersectionObserver: typeof StubObserver }).IntersectionObserver = StubObserver
;(globalThis as unknown as { ResizeObserver: typeof StubObserver }).ResizeObserver = StubObserver

if (typeof window !== 'undefined' && typeof window.matchMedia === 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

// jsdom does not implement scrollIntoView; stub it on the Element prototype so
// components that call it during effects don't throw.
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function () {
    // no-op
  }
}
