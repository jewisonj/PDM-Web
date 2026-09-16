/**
 * Pure helpers for the Shop Companion (unit-tested, no DOM assumptions except resizeImage).
 */
import type { ShopAssembly, ShopItem } from '../services/shopNotesApi'

export interface Suggestable {
  id: string
  item_number: string
  name: string
}

/** Case-insensitive match on item number or name; item-number prefix hits rank first. */
export function filterItems<T extends Suggestable>(items: T[], query: string, limit = 12): T[] {
  const q = query.trim().toLowerCase()
  if (!q) return items.slice(0, limit)
  const starts: T[] = []
  const contains: T[] = []
  for (const it of items) {
    const num = (it.item_number || '').toLowerCase()
    const name = (it.name || '').toLowerCase()
    if (num.startsWith(q)) starts.push(it)
    else if (num.includes(q) || name.includes(q)) contains.push(it)
    if (starts.length >= limit) break
  }
  return [...starts, ...contains].slice(0, limit)
}

/** Parts that belong directly under an assembly come first; everything else after. */
export function partsForAssembly(parts: ShopItem[], assemblyId: string | null): ShopItem[] {
  if (!assemblyId) return parts
  const children = parts.filter(p => p.parent_ids.includes(assemblyId) && p.id !== assemblyId)
  const rest = parts.filter(p => !p.parent_ids.includes(assemblyId) && p.id !== assemblyId)
  return [...children, ...rest]
}

/** The assembly to auto-fill when a part is picked: its (first) parent that is a known assembly. */
export function defaultAssemblyForPart(part: ShopItem, assemblies: ShopAssembly[]): ShopAssembly | null {
  for (const pid of part.parent_ids) {
    const asm = assemblies.find(a => a.id === pid)
    if (asm) return asm
  }
  return null
}

export function itemLabel(it: { item_number: string; name?: string | null } | null | undefined): string {
  if (!it) return ''
  return it.name ? `${it.item_number} — ${it.name}` : it.item_number
}

/**
 * Downscale a photo on the phone before upload so shop Wi-Fi/cellular uploads stay quick.
 * Honors EXIF orientation via createImageBitmap when available. Returns a JPEG blob.
 */
export async function resizeImage(file: Blob, maxEdge = 1600, quality = 0.82): Promise<Blob> {
  let bitmap: ImageBitmap | HTMLImageElement
  let width: number
  let height: number
  let cleanup: (() => void) | null = null

  if (typeof createImageBitmap === 'function') {
    try {
      bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' } as ImageBitmapOptions)
    } catch {
      bitmap = await createImageBitmap(file)
    }
    width = bitmap.width
    height = bitmap.height
    cleanup = () => (bitmap as ImageBitmap).close()
  } else {
    const url = URL.createObjectURL(file)
    try {
      bitmap = await new Promise<HTMLImageElement>((resolve, reject) => {
        const img = new Image()
        img.onload = () => resolve(img)
        img.onerror = () => reject(new Error('Could not read image'))
        img.src = url
      })
    } finally {
      cleanup = () => URL.revokeObjectURL(url)
    }
    width = bitmap.naturalWidth
    height = bitmap.naturalHeight
  }

  const scale = Math.min(1, maxEdge / Math.max(width, height))
  const w = Math.max(1, Math.round(width * scale))
  const h = Math.max(1, Math.round(height * scale))

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    cleanup?.()
    return file
  }
  ctx.drawImage(bitmap as CanvasImageSource, 0, 0, w, h)
  cleanup?.()

  const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', quality))
  return blob || file
}
