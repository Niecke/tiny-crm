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
})
