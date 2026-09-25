// Runtime configuration, read the same way the Flutter app reads it: one image
// runs in staging and production, so the API URL cannot be baked in at build
// time. The chart mounts config.json into this image at /next/config.json —
// its own copy, not the Flutter one at the root, so /next keeps working when
// the Flutter pod is down and nothing changes at the cutover.
export type AppConfig = {
  apiUrl: string
}

const fallback: AppConfig = { apiUrl: 'http://localhost:8000' }

export async function loadConfig(): Promise<AppConfig> {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}config.json`, { cache: 'no-cache' })
    if (!res.ok) return fallback
    const data = (await res.json()) as Partial<AppConfig>
    return typeof data.apiUrl === 'string' ? { apiUrl: data.apiUrl } : fallback
  } catch {
    return fallback
  }
}
