interface ImportMetaEnv {
  // Set by the Dockerfile from the GIT_COMMIT build arg; unset in `npm run dev`.
  readonly VITE_GIT_COMMIT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
