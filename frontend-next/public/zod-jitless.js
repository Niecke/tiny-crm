// Zod compiles object parsers with new Function() unless told not to, and
// probes for that by calling Function('') — which the Content-Security-Policy
// (no 'unsafe-eval', #155) refuses and reports as a violation on every page.
// Zod reads the flag when a schema is built, and the bundle builds its schemas
// in the same chunk as Zod itself, so z.config() in main.tsx would run too
// late. Zod keeps its config on this global and only creates it when absent,
// so a classic script that runs before any module sets it in time.
globalThis.__zod_globalConfig = { ...globalThis.__zod_globalConfig, jitless: true }
