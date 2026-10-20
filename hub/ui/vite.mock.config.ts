import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// The UI mock: the real components and tokens rendered against fixture data from the Terra replica,
// with no Hub. Builds to dist-mock/ and never touches hub/hub/static/ui (the bundle :8000 serves).
//   npx vite --config vite.mock.config.ts          (dev, http://localhost:5199/mock.html)
//   npx vite build --config vite.mock.config.ts    (static, dist-mock/)
export default defineConfig({
  plugins: [react()],
  base: './',
  resolve: { alias: { '@': path.resolve(__dirname, './src'), '@mock': path.resolve(__dirname, './mock') } },
  // node_modules is a junction into the main checkout in the mock worktree; let Vite serve from it.
  server: { port: 5199, fs: { strict: false } },
  // ASCII output: the markdown library carries a literal U+FFFD, which the artifact host refuses as
  // broken text; escaped it is the same string.
  esbuild: { charset: 'ascii' },
  build: { outDir: 'dist-mock', emptyOutDir: true, rollupOptions: { input: path.resolve(__dirname, 'mock.html') } },
})
