interface ImportMetaEnv {
  // Set by the Dockerfile from the GIT_COMMIT build arg; unset in `npm run dev`.
  readonly VITE_GIT_COMMIT?: string
  // Set by the Dockerfile to the build's UTC time (ISO 8601); unset in `npm run dev`.
  readonly VITE_BUILD_TIMESTAMP?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
