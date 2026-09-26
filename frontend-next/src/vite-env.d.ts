interface ImportMetaEnv {
  // Set by the Dockerfile from the GIT_COMMIT build arg; unset in `npm run dev`.
  readonly VITE_GIT_COMMIT?: string
  // Set by the Dockerfile from the APP_VERSION build arg (ci.yml): "v0.1.0" for
  // a release, "v0.1.0-abc1234" otherwise; unset in `npm run dev`.
  readonly VITE_APP_VERSION?: string
  // Set by the Dockerfile to the build's UTC time (ISO 8601); unset in `npm run dev`.
  readonly VITE_BUILD_TIMESTAMP?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
