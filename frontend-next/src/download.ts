// Saves a blob under a name, through a temporary link. The Flutter app's
// version needed a typed array (#51); a Blob from fetch is already one.
// The link is revoked later rather than at once: some browsers only start the
// download after the click has returned, and a revoked URL saves nothing.
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
