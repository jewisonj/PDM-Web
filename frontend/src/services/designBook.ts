/**
 * Master Design Book service — data fetch + API wrappers.
 *
 * The frontend engine (utils/masterDesignBook.ts) is the single source of
 * truth for the book model; this module fetches its inputs (same queries as
 * MrpBuildBookView, minus part_completion — the master ignores completion),
 * builds the POST payload, and talks to /api/mrp/design-books.
 */

import { supabase } from './supabase'
import {
  masterDesignBook,
  type MasterDesignBook,
} from '../utils/masterDesignBook'
import type { KitSourceInput } from '../utils/buildTracker'

// ============================================================================
// Types (mirror backend design_books.py / master_design_book.py responses)
// ============================================================================

export interface BookSectionRow {
  section_code: string
  kind: 'spine' | 'work_package' | 'assembly' | 'design_reference' | 'general_reference'
  title: string
  rev: string
  status: 'current' | 'superseded' | 'retired'
  sort_order: number
  page_count: number | null
  storage_path: string | null
  updated_at: string | null
}

export interface StalePrint {
  section_code: string
  item_number: string
  bound_revision: string | null
  bound_iteration: number | null
  newest_revision: string | null
  newest_iteration: number | null
}

export interface BookChangeRow {
  from_rev: number
  to_rev: number
  created_at: string | null
  notice_path: string | null
}

export interface BookDetail {
  book_code: string
  title: string
  product_item_number: string
  template_project_id: string | null
  book_rev: number
  renderer_version: number
  status: string
  generated_at: string | null
  sections: BookSectionRow[]
  stale_prints: StalePrint[]
  changes: BookChangeRow[]
}

export interface DiffEntry {
  section_code: string
  title: string | null
  old_rev: string | null
  new_rev: string | null
  last_rev: string | null
  reasons: string[]
  page_count: number | null
}

export interface CheckWarning {
  type: 'missing_print' | 'qty_mismatch'
  section_code?: string
  item_number?: string
  project_qty?: number
  bom_rollup_qty?: number
}

export interface CheckResult {
  book_rev: number
  next_book_rev: number
  would_issue_notice: boolean
  added: DiffEntry[]
  changed: DiffEntry[]
  retired: DiffEntry[]
  unchanged: string[]
  warnings: CheckWarning[]
}

export interface UpdateResult extends Omit<CheckResult, 'next_book_rev' | 'would_issue_notice'> {
  previous_rev: number
  resumed?: boolean
  change_notice_path: string | null
  change_notice_url: string | null
  sections?: { section_code: string; rev: string; storage_path: string; page_count: number }[]
}

export interface BookListItem {
  book_code: string
  title: string
  product_item_number: string
  book_rev: number
  renderer_version: number
  status: string
  generated_at: string | null
  section_count: number
  stale_print_count: number
}

export interface DesignBookPayload {
  meta: {
    title: string
    product_item_number: string
    template_project_code: string
    create: boolean
    rebaseline: boolean
    expected_book_rev: number | null
    allow_qty_mismatch: boolean
  }
  sections: MasterDesignBook['sections']
}

// ============================================================================
// Kit sourcing — shared by the master book and the per-project Build Book/Tracker
// ============================================================================

/**
 * Vendor bundles of finished parts for a project (project_item_source + project_kits).
 *
 * `use_kit` is deliberately NOT filtered on: it is a pricing toggle, and a cost
 * experiment must never change a build document (Documentation/38 §3). Sourcing
 * changes mean reassigning parts to 'make'.
 */
export async function fetchProjectKitSources(projectId: string): Promise<KitSourceInput[]> {
  const { data } = await supabase
    .from('project_item_source')
    .select('item_id, project_kits (kit_number, kit_name, vendor)')
    .eq('project_id', projectId)
    .eq('source_type', 'kit')
  return (data || [])
    .filter((r: any) => r.project_kits)
    .map((r: any) => ({
      item_id: r.item_id,
      kit_number: r.project_kits.kit_number,
      kit_name: r.project_kits.kit_name,
      vendor: r.project_kits.vendor ?? null,
    }))
}

// ============================================================================
// Payload builder — the same fetch set as MrpBuildBookView (no completion)
// ============================================================================

export async function buildMasterModel(templateProjectCode: string): Promise<MasterDesignBook> {
  const { data: project, error: projErr } = await supabase
    .from('mrp_projects')
    .select('*')
    .eq('project_code', templateProjectCode)
    .single()
  if (projErr || !project) throw new Error(`Template project "${templateProjectCode}" not found`)

  const { data: partsData, error: partsErr } = await supabase
    .from('mrp_project_parts')
    .select('item_id, quantity, items (id, item_number, name, description, thickness, material, supplier_pn, supplier_name, revision)')
    .eq('project_id', project.id)
  if (partsErr) throw partsErr
  const itemIds = (partsData || []).map(p => p.item_id)
  if (!itemIds.length) throw new Error(`Template project "${templateProjectCode}" has no parts`)

  const [
    { data: bomData },
    { data: routingData },
    { data: stationsData },
    { data: materialsData },
    { data: printFiles },
    kitSources,
  ] = await Promise.all([
    supabase
      .from('bom')
      .select('parent_item_id, child_item_id, quantity')
      .or(`parent_item_id.in.(${itemIds.join(',')}),child_item_id.in.(${itemIds.join(',')})`),
    supabase
      .from('routing')
      .select('id, item_id, station_id, sequence, est_time_min, notes, workstations (station_code, station_name)')
      .in('item_id', itemIds)
      .order('sequence')
      .limit(3000),
    supabase.from('workstations').select('id, station_code, station_name, station_group, sort_order'),
    supabase
      .from('routing_materials')
      .select('item_id, qty_required, raw_materials (description, material_code)')
      .in('item_id', itemIds),
    supabase
      .from('files')
      .select('item_id')
      .eq('file_type', 'PDF')
      .not('file_path', 'is', null)
      .in('item_id', itemIds)
      .limit(3000),
    fetchProjectKitSources(project.id),
  ])

  return masterDesignBook({
    project: project as any,
    parts: (partsData || []) as any,
    bom: (bomData || []) as any,
    routing: (routingData || []) as any,
    workstations: (stationsData || []) as any,
    routingMaterials: (materialsData || []) as any,
    printItemIds: [...new Set((printFiles || []).map(f => f.item_id))],
    kitSources,
  })
}

export function toPayload(
  master: MasterDesignBook,
  opts: { title?: string; create: boolean; expectedBookRev: number | null; rebaseline?: boolean }
): DesignBookPayload {
  return {
    meta: {
      title: opts.title || master.meta.title,
      product_item_number: master.meta.product_item_number,
      template_project_code: master.meta.template_project_code,
      create: opts.create,
      rebaseline: opts.rebaseline ?? false,
      // ALWAYS sent when the book exists — concurrent updates must 409, not race
      expected_book_rev: opts.expectedBookRev,
      allow_qty_mismatch: false,
    },
    sections: master.sections,
  }
}

// ============================================================================
// API wrappers
// ============================================================================

async function jsonOrThrow(resp: Response) {
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    const detail = err.detail
    if (detail && typeof detail === 'object' && detail.mismatches) {
      const list = detail.mismatches
        .slice(0, 6)
        .map((m: any) => `${m.item_number}: flat ${m.project_qty} vs BOM ${m.bom_rollup_qty}`)
        .join('; ')
      const more = detail.mismatches.length > 6 ? ` (+${detail.mismatches.length - 6} more)` : ''
      throw new Error(`${detail.message} — ${list}${more}`)
    }
    throw new Error(typeof detail === 'string' ? detail : `HTTP ${resp.status}`)
  }
  return resp.json()
}

/** A book_code doubles as the bucket folder — restrict to a safe slug. */
export function slugifyBookCode(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export function isValidBookCode(code: string): boolean {
  return /^[a-z0-9]+(-[a-z0-9]+)*$/.test(code)
}

export async function listDesignBooks(): Promise<BookListItem[]> {
  const resp = await fetch('/api/mrp/design-books')
  const data = await jsonOrThrow(resp)
  return data.books || []
}

export async function getDesignBook(bookCode: string): Promise<BookDetail | null> {
  const resp = await fetch(`/api/mrp/design-books/${bookCode}`)
  if (resp.status === 404) return null
  return jsonOrThrow(resp)
}

export async function checkDesignBook(bookCode: string, payload: DesignBookPayload): Promise<CheckResult> {
  const resp = await fetch(`/api/mrp/design-books/${bookCode}/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return jsonOrThrow(resp)
}

export async function updateDesignBook(bookCode: string, payload: DesignBookPayload): Promise<UpdateResult> {
  const resp = await fetch(`/api/mrp/design-books/${bookCode}/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return jsonOrThrow(resp)
}

export async function getSectionUrl(bookCode: string, sectionCode: string): Promise<string> {
  const resp = await fetch(`/api/mrp/design-books/${bookCode}/sections/${encodeURIComponent(sectionCode)}/url`)
  const data = await jsonOrThrow(resp)
  return data.url
}

export async function getNoticeUrl(bookCode: string, toRev: number): Promise<string> {
  const resp = await fetch(`/api/mrp/design-books/${bookCode}/changes/${toRev}/url`)
  const data = await jsonOrThrow(resp)
  return data.url
}

/** POST /full streams the merged PDF — download it via the blob pattern. */
export async function downloadFullBook(bookCode: string): Promise<{ pages: string | null; sections: string | null }> {
  const resp = await fetch(`/api/mrp/design-books/${bookCode}/full`, { method: 'POST' })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }))
    throw new Error(typeof err.detail === 'string' ? err.detail : `HTTP ${resp.status}`)
  }
  const blob = await resp.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  const dispo = resp.headers.get('Content-Disposition') || ''
  const m = dispo.match(/filename="([^"]+)"/)
  a.download = m?.[1] || `${bookCode}-master-design-book.pdf`
  a.click()
  URL.revokeObjectURL(a.href)
  return {
    pages: resp.headers.get('X-Pages'),
    sections: resp.headers.get('X-Sections'),
  }
}
