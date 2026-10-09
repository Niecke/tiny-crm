import { type Api, unwrap } from './api/client'
import type { BusinessCardImport } from './api/types'

// Longest edge a card photo is sent at. Plenty for the small print on a card,
// and a phone's 12-megapixel photo shrinks from several MB to a few hundred KB —
// well under the backend's 5 MB a side.
export const MAX_EDGE = 1600

// The photo as a JPEG no larger than MAX_EDGE on its longest side. Drawing it
// through a canvas also turns what a phone camera produces (HEIC on an iPhone)
// into something the backend accepts. A file the browser cannot decode is
// sent as it is, and the backend says what is wrong with it.
export async function shrinkPhoto(file: File): Promise<Blob> {
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    const scale = Math.min(1, MAX_EDGE / Math.max(image.naturalWidth, image.naturalHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(image.naturalWidth * scale)
    canvas.height = Math.round(image.naturalHeight * scale)
    canvas.getContext('2d')?.drawImage(image, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
    return blob ?? file
  } catch {
    return file
  } finally {
    URL.revokeObjectURL(url)
  }
}

export async function scanCard(api: Api, front: File, back: File | null) {
  const form = new FormData()
  form.append('front', await shrinkPhoto(front), 'front.jpg')
  if (back) form.append('back', await shrinkPhoto(back), 'back.jpg')
  return unwrap(
    api.POST('/business-cards/scan', {
      // The schema types the files as strings; the real body is the FormData.
      body: {} as never,
      bodySerializer: () => form,
    }),
  )
}

export const importCard = (api: Api, body: BusinessCardImport) => unwrap(api.POST('/business-cards/import', { body }))
