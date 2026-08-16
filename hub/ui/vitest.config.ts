/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__tests__/setup.ts'],
    include: ['src/**/__tests__/**/*.{test,spec}.{ts,tsx}'],
    css: false,
    // The userEvent-driven page tests finish in ~1s on their own but routinely
    // exceed vitest's 5s default when 95 files share the machine — a different
    // one timed out on each full-suite run. They are slow under load, not hung.
    testTimeout: 20000,
  },
})
