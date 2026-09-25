// Runtime configuration, read the same way the Flutter app reads it: one image
// runs in staging and production, so the API URL cannot be baked in at build
// time. /config.json sits at the site root, beside the Flutter build, and is
// shared by both apps until the cutover.
export type AppConfig = {
  apiUrl: string
}

const fallback: AppConfig = { apiUrl: 'http://localhost:8000' }

export async function loadConfig(): Promise<AppConfig> {
  try {
    const res = await fetch('/config.json', { cache: 'no-cache' })
    if (!res.ok) return fallback
    const data = (await res.json()) as Partial<AppConfig>
    return typeof data.apiUrl === 'string' ? { apiUrl: data.apiUrl } : fallback
  } catch {
    return fallback
  }
}
