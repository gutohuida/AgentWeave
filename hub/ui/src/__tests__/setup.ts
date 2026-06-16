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
// @ts-expect-error - assigning to a global for jsdom
globalThis.IntersectionObserver = StubObserver
// @ts-expect-error - assigning to a global for jsdom
globalThis.ResizeObserver = StubObserver

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
