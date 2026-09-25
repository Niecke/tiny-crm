import { tanstackRouter } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Served under /next/ until the cutover (#122): the Flutter app keeps the root
// and Caddy routes /next/* to this build. Dev mirrors that path so a link that
// works on localhost:5173/next/ also works on the deployed instance.
export default defineConfig({
  base: '/next/',
  plugins: [
    // Must come before react(): it generates src/routeTree.gen.ts from
    // src/routes/ and splits each route into its own chunk.
    tanstackRouter({ target: 'react', autoCodeSplitting: true }),
    react(),
  ],
})
