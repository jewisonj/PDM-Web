/**
 * Shop Notes API client - the Shop Companion app (/shop) and the reviewer page (/mrp/shop-notes).
 *
 * Workers authenticate with a long-lived device token obtained from the shared shop PIN.
 * Reviewers use their normal Supabase session token.
 */
import { supabase, API_BASE_URL } from './supabase'

const TOKEN_KEY = 'shop_companion_token'
const NAME_KEY = 'shop_companion_name'
const PROJECT_KEY = 'shop_companion_project'

export interface ShopProject {
  id: string
  project_code: string
  description: string | null
  customer: string | null
  status: string | null
}

export interface ShopItem {
  id: string
  item_number: string
  name: string
  quantity?: number | null
  is_supplier_part?: boolean
  parent_ids: string[]
}

export interface ShopAssembly {
  id: string
  item_number: string
  name: string
  is_top: boolean
}

export interface ProjectItems {
  project_id: string
  project_code: string
  assemblies: ShopAssembly[]
  parts: ShopItem[]
}

export interface ShopNotePhoto {
  id: string
  file_path: string
  file_size: number | null
  mime_type: string | null
  sort_order: number
  created_at: string
  url: string | null
}

export type ShopNoteStatus = 'new' | 'reviewed' | 'resolved'

export interface ShopNote {
  id: string
  project_id: string | null
  assembly_item_id: string | null
  part_item_id: string | null
  assembly_text: string | null
  part_text: string | null
  note: string
  author_name: string | null
  status: ShopNoteStatus
  reviewer_notes: string | null
  reviewed_at: string | null
  created_at: string
  updated_at: string
  project: { id: string; project_code: string; description: string | null } | null
  assembly: { id: string; item_number: string; name: string | null } | null
  part: { id: string; item_number: string; name: string | null } | null
  photos: ShopNotePhoto[]
}

export interface NewShopNote {
  note: string
  author_name?: string | null
  project_id?: string | null
  assembly_item_id?: string | null
  part_item_id?: string | null
  assembly_text?: string | null
  part_text?: string | null
  photos: Blob[]
}

export interface ShopNotePatch {
  status?: ShopNoteStatus
  note?: string
  project_id?: string
  assembly_item_id?: string
  part_item_id?: string
  assembly_text?: string
  part_text?: string
  reviewer_notes?: string
  clear_assembly?: boolean
  clear_part?: boolean
}

// ---------------------------------------------------------------------------
// Device-side persistence (worker phone)
// ---------------------------------------------------------------------------

function safeGet(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function safeSet(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch { /* private mode etc. */ }
}

export const shopDevice = {
  getToken: () => safeGet(TOKEN_KEY),
  setToken: (t: string | null) => safeSet(TOKEN_KEY, t),
  getName: () => safeGet(NAME_KEY) || '',
  setName: (n: string) => safeSet(NAME_KEY, n),
  getProjectId: () => safeGet(PROJECT_KEY),
  setProjectId: (id: string | null) => safeSet(PROJECT_KEY, id),
}

// ---------------------------------------------------------------------------
// HTTP plumbing
// ---------------------------------------------------------------------------

export class ShopApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
    const detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body)
    throw new ShopApiError(res.status, detail || `HTTP ${res.status}`)
  }
  return res.json()
}

async function staffToken(): Promise<string> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new ShopApiError(401, 'Not logged in')
  return token
}

function shopHeaders(): Record<string, string> {
  const token = shopDevice.getToken()
  if (!token) throw new ShopApiError(401, 'PIN required')
  return { Authorization: `Bearer ${token}` }
}

async function staffHeaders(): Promise<Record<string, string>> {
  return { Authorization: `Bearer ${await staffToken()}` }
}

// ---------------------------------------------------------------------------
// Worker endpoints
// ---------------------------------------------------------------------------

export async function pinLogin(pin: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/shop-notes/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin }),
  })
  const out = await handle<{ token: string }>(res)
  shopDevice.setToken(out.token)
  return out.token
}

export async function listShopProjects(asStaff = false): Promise<ShopProject[]> {
  const headers = asStaff ? await staffHeaders() : shopHeaders()
  return handle(await fetch(`${API_BASE_URL}/shop-notes/projects`, { headers }))
}

export async function getProjectItems(projectId: string, asStaff = false): Promise<ProjectItems> {
  const headers = asStaff ? await staffHeaders() : shopHeaders()
  return handle(await fetch(`${API_BASE_URL}/shop-notes/projects/${projectId}/items`, { headers }))
}

export async function createShopNote(input: NewShopNote): Promise<ShopNote> {
  const form = new FormData()
  form.append('note', input.note || '')
  if (input.author_name) form.append('author_name', input.author_name)
  if (input.project_id) form.append('project_id', input.project_id)
  if (input.assembly_item_id) form.append('assembly_item_id', input.assembly_item_id)
  if (input.part_item_id) form.append('part_item_id', input.part_item_id)
  if (input.assembly_text) form.append('assembly_text', input.assembly_text)
  if (input.part_text) form.append('part_text', input.part_text)
  input.photos.forEach((blob, i) => {
    const ext = blob.type === 'image/png' ? 'png' : blob.type === 'image/webp' ? 'webp' : 'jpg'
    form.append('photos', blob, `photo_${i + 1}.${ext}`)
  })
  const res = await fetch(`${API_BASE_URL}/shop-notes`, { method: 'POST', headers: shopHeaders(), body: form })
  return handle(res)
}

// ---------------------------------------------------------------------------
// Reviewer endpoints (staff)
// ---------------------------------------------------------------------------

export async function listShopNotes(status: ShopNoteStatus | 'all' = 'new', projectId?: string | null): Promise<ShopNote[]> {
  const params = new URLSearchParams({ status })
  if (projectId) params.set('project_id', projectId)
  return handle(await fetch(`${API_BASE_URL}/shop-notes?${params}`, { headers: await staffHeaders() }))
}

export async function getShopNoteSummary(): Promise<Record<ShopNoteStatus, number>> {
  return handle(await fetch(`${API_BASE_URL}/shop-notes/summary`, { headers: await staffHeaders() }))
}

export async function updateShopNote(id: string, patch: ShopNotePatch): Promise<ShopNote> {
  const res = await fetch(`${API_BASE_URL}/shop-notes/${id}`, {
    method: 'PATCH',
    headers: { ...(await staffHeaders()), 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return handle(res)
}

export async function deleteShopNote(id: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/shop-notes/${id}`, { method: 'DELETE', headers: await staffHeaders() })
  await handle(res)
}
