import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Which Hub `npm run dev` talks to. This was pinned to 8000, which meant the dev server could
// only ever reach the default instance — so a throwaway Hub started on another port (its own
// port, its own DATABASE_URL) was unreachable from the dev server, and the one mode you most
// want to test against was the one you could not proxy to.
//   AW_DEV_HUB=http://127.0.0.1:8010 npm run dev
const hubTarget = process.env.AW_DEV_HUB || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    // Screens load as their own chunks (`src/lib/lazyScreens.ts`), but their stylesheets stay in
    // the one file, in import order: a screen's rules refine index.css's at equal specificity, and
    // per-chunk CSS would apply them in whatever order the chunks happened to load.
    cssCodeSplit: false,
  },
  server: {
    proxy: {
      '/api': hubTarget,
      '/health': hubTarget,
    },
  },
})
