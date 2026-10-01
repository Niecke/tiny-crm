/// <reference types="vitest/config" />
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Served at the root since the cutover (#122). It spent its preview under
// /next/; the image's Caddyfile still redirects that prefix here, so old
// links and bookmarks keep working.
export default defineConfig({
  plugins: [
    // Must come before react(): it generates src/routeTree.gen.ts from
    // src/routes/ and splits each route into its own chunk.
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
  ],
  // Unit tests (FRONTEND.md, "Tests"). Dates and numbers are formatted in the
  // browser's timezone and locale, so both are pinned: the same run gives the
  // same strings on a laptop in Vienna and on a CI runner in UTC. The zone is
  // west of Greenwich on purpose — that is where a date read as UTC midnight
  // turns into the day before, the bug src/format.ts exists to avoid.
  test: {
    environment: 'jsdom',
    env: { TZ: 'America/New_York', LANG: 'en_US.UTF-8', LC_ALL: 'en_US.UTF-8' },
    setupFiles: ['src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/routeTree.gen.ts', 'src/api/schema.d.ts', 'src/routes/**', 'src/test/**', 'src/**/*.test.{ts,tsx}'],
      reporter: ['text', 'json-summary'],
    },
  },
})
