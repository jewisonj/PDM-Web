/**
 * Build Tracker Sheet — data shaping
 *
 * Turns raw project data (parts, BOM, routing, workstations, part_completion)
 * into the structure rendered by MrpBuildTrackerView (one-page 11x17 shop sheet).
 *
 * Pure functions, no Supabase access: the same logic can later back the
 * photo-sync pipeline (reading marks off a photographed sheet keys on the
 * same row IDs and column definitions produced here).
 *
 * Completion semantics match MrpShopView: one part_completion row per
 * (project, item, station), qty_complete normally the full project quantity.
 * A station is "done" when its row covers the item's project quantity;
 * anything less prints as a partial tally.
 */

import type { ScheduleResult } from './scheduling'

// ============================================================================
// COLUMN DEFINITIONS (station_name -> printed column)
// ============================================================================

export interface TrackerColumn {
  key: string
  label: string
  stations: string[]        // workstation station_name values folded into this column
  gate?: boolean            // rendered shaded with a heavy left border (handoff gate)
  alwaysApplicable?: boolean // open box even when the station is not in the routing
}

export const PART_COLUMNS: TrackerColumn[] = [
  { key: 'SAW', label: 'SAW', stations: ['Saw'] },
  { key: 'WJ', label: 'WJ', stations: ['Waterjet'] },
  { key: 'BRK', label: 'PB', stations: ['Press Brake'] },
  { key: 'BND', label: 'BND', stations: ['Pipe Bending', 'Hole Punch - Iron Worker'] },
  { key: 'DBR', label: 'DBR', stations: ['Deburr'] },
  { key: 'INS', label: 'INS', stations: ['Inspection'] },
  { key: 'STG', label: '▸STG', stations: ['Part Staging'], gate: true, alwaysApplicable: true },
]

export const ASM_COLUMNS: TrackerColumn[] = [
  { key: 'JIG', label: 'JIG', stations: ['Weld Jigging'] },
  { key: 'TIG', label: 'TIG', stations: ['Tig Welding'] },
  { key: 'DS', label: 'DS', stations: ['Dual Shield Weld'] },
  { key: 'WCU', label: 'WCU', stations: ['Weld Cleanup'] },
  { key: 'ASM', label: 'ASM', stations: ['Mechanical Assembly', 'Plumbing', 'Wiring', 'Vinyl Wrap'] },
  { key: 'INS', label: 'INS', stations: ['Inspection'] },
]

// ============================================================================
// INPUT / OUTPUT TYPES
// ============================================================================

export interface TrackerProject {
  id: string
  project_code: string
  description: string | null
  customer: string | null
  due_date: string | null
  start_date: string | null
  top_assembly_id: string | null
}

export interface TrackerPartInput {
  item_id: string
  quantity: number
  items: {
    id: string
    item_number: string
    name?: string | null
    description?: string | null
    thickness?: number | null
    material?: string | null
    supplier_pn?: string | null
    supplier_name?: string | null
    revision?: string | null
  } | null
}

/**
 * Shop-facing part number for purchased items: the mmc/spn prefixes are PDM
 * bookkeeping — the floor sees the supplier's own PN (supplier_pn when set,
 * else the item number with the prefix stripped, uppercased).
 */
export function purchasedDisplay(itemNumber: string, supplierPn?: string | null): string {
  const n = itemNumber.toLowerCase()
  if (n.startsWith('mmc') || n.startsWith('spn')) {
    return (supplierPn || itemNumber.slice(3)).toUpperCase()
  }
  return itemNumber
}

export function purchasedSource(itemNumber: string, supplierName?: string | null): string {
  if (supplierName) return supplierName
  const n = itemNumber.toLowerCase()
  if (n.startsWith('mmc')) return 'McMaster-Carr'
  if (n.startsWith('spn')) return 'Supplier'
  return '—'
}

export interface TrackerBomInput {
  parent_item_id: string
  child_item_id: string
  quantity: number
}

export interface TrackerRoutingInput {
  item_id: string
  station_id: string
  sequence: number
  notes?: string | null
  workstations: { station_code: string; station_name: string } | null
}

export interface TrackerCompletionInput {
  item_id: string
  station_id: string
  qty_complete: number | null
  completed_at?: string | null
}

export interface TrackerWorkstation {
  id: string
  station_code: string
  station_name: string
  station_group: string | null
}

export type TrackerFormat = 'tabloid' | 'letter'

export interface TrackerInputs {
  project: TrackerProject
  parts: TrackerPartInput[]
  bom: TrackerBomInput[]
  routing: TrackerRoutingInput[]
  completion: TrackerCompletionInput[]
  workstations: TrackerWorkstation[]
  schedule?: ScheduleResult | null
  now?: Date
  /** 'tabloid' = one 11x17 sheet; 'letter' = 8.5x11 landscape pages (parts pages + status page) */
  format?: TrackerFormat
}

export interface TrackerBox {
  applicable: boolean
  done: boolean            // pre-printed: recorded complete in system
  partial: number | null   // pre-printed tally (qty recorded, less than needed)
  gate: boolean
}

export interface TrackerPartRow {
  rid: string
  item_id: string
  item_number: string
  name: string
  qty: number
  boxes: TrackerBox[]
  rowDone: boolean         // all applicable non-gate boxes done
}

export interface TrackerGroup {
  ref: string              // rid of parent assembly ('A07') or '—'
  assembly_number: string
  name: string
  rows: TrackerPartRow[]
  readyDone: number
  readyTotal: number
  cont?: boolean           // continuation of a split group
}

export interface TrackerAsmRow {
  rid: string
  item_id: string
  item_number: string
  name: string
  qty: number
  readyDone: number
  readyTotal: number
  boxes: TrackerBox[]
  rowDone: boolean
}

export interface TrackerPurchasedRow {
  rid: string
  item_number: string      // internal PDM number (photo-sync key, not printed)
  displayNumber: string    // shop-facing PN (supplier_pn / prefix stripped)
  source: string           // McMaster-Carr, supplier name, or '—'
  name: string
  qty: number
  longLead: boolean
  ordDone: boolean         // never pre-filled (no data source) — reserved
  rcvDone: boolean
  rcvPartial: number | null
}

export interface TrackerMilestone {
  rid: string
  op: number
  title: string
  plan: string
  actual: string
  gate?: boolean
}

export interface TrackerPage {
  colA: TrackerGroup[]
  colB: TrackerGroup[]
  showRail: boolean        // right rail (milestones/purchased/log) on first page only
}

export interface TrackerSheet {
  project: TrackerProject
  generatedAt: Date
  startDate: Date | null
  format: TrackerFormat
  pages: TrackerPage[]
  asmRows: TrackerAsmRow[]
  milestones: TrackerMilestone[]
  purchased: TrackerPurchasedRow[]
  fabDone: number
  fabTotal: number
  asmDone: number
  asmTotal: number
  purchasedTotal: number
  pctComplete: number      // stations complete / stations routed, 0-100
}

// ============================================================================
// DATE HELPERS (working days, same convention as MrpProjectTrackingView)
// ============================================================================

function isWeekend(date: Date): boolean {
  const day = date.getDay()
  return day === 0 || day === 6
}

export function addWorkingDays(date: Date, numDays: number): Date {
  const result = new Date(date)
  let remaining = numDays
  while (remaining > 0) {
    result.setDate(result.getDate() + 1)
    if (!isWeekend(result)) remaining--
  }
  return result
}

export function subtractWorkingDays(date: Date, numDays: number): Date {
  const result = new Date(date)
  let remaining = numDays
  while (remaining > 0) {
    result.setDate(result.getDate() - 1)
    if (!isWeekend(result)) remaining--
  }
  return result
}

function fmtPlan(date: Date | null): string {
  if (!date || isNaN(date.getTime())) return ''
  return date
    .toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    .toUpperCase()
}

function fmtActual(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}/${d.getDate()}`
}

// ============================================================================
// MAIN
// ============================================================================

type ItemClass = 'assembly' | 'made' | 'purchased' | 'ref' | 'doc'

/** Third-letter-'d' items (csd0001, wmd0100...) are controlled documents — design books,
 *  build references — not physical parts. They never appear as tracker/book work rows;
 *  the Build Book lists them as reference prints instead. */
export function isDocumentItem(itemNumber: string): boolean {
  return /^[a-z]{2}d\d/i.test(itemNumber)
}

const PAGE_ROW_CAP_TABLOID = 48 // data rows + group header rows per part column
const PAGE_ROW_CAP_LETTER = 32

export function buildTrackerSheet(inp: TrackerInputs): TrackerSheet {
  const now = inp.now ?? new Date()
  const format: TrackerFormat = inp.format ?? 'tabloid'

  // ---- lookups --------------------------------------------------------
  const info = new Map<
    string,
    { item_number: string; name: string; supplier_pn: string | null; supplier_name: string | null }
  >()
  const projQty = new Map<string, number>()
  for (const p of inp.parts) {
    if (!p.items) continue
    info.set(p.item_id, {
      item_number: p.items.item_number,
      name: p.items.name || p.items.description || '',
      supplier_pn: p.items.supplier_pn ?? null,
      supplier_name: p.items.supplier_name ?? null,
    })
    projQty.set(p.item_id, p.quantity)
  }
  const inProject = (id: string) => info.has(id)

  const children = new Map<string, { child: string; qty: number }[]>()
  for (const b of inp.bom) {
    if (!inProject(b.parent_item_id) || !inProject(b.child_item_id)) continue
    if (!children.has(b.parent_item_id)) children.set(b.parent_item_id, [])
    children.get(b.parent_item_id)!.push({ child: b.child_item_id, qty: b.quantity })
  }
  for (const list of children.values()) {
    list.sort((a, b) =>
      (info.get(a.child)?.item_number || '').localeCompare(info.get(b.child)?.item_number || '')
    )
  }

  const stationName = new Map<string, string>()
  const stationGroupByCode = new Map<string, string>()
  const stationIdByName = new Map<string, string>()
  for (const w of inp.workstations) {
    stationName.set(w.id, w.station_name)
    stationGroupByCode.set(w.station_code, w.station_group || '')
    stationIdByName.set(w.station_name, w.id)
  }

  // routed stations per item (deduped by station_id, sequence order)
  const routedByItem = new Map<string, { station_id: string; station_name: string }[]>()
  const sortedRouting = [...inp.routing].sort((a, b) => a.sequence - b.sequence)
  for (const r of sortedRouting) {
    if (!inProject(r.item_id)) continue
    if (!routedByItem.has(r.item_id)) routedByItem.set(r.item_id, [])
    const list = routedByItem.get(r.item_id)!
    if (list.some(s => s.station_id === r.station_id)) continue
    const name = r.workstations?.station_name || stationName.get(r.station_id) || ''
    list.push({ station_id: r.station_id, station_name: name })
  }
  const groupOfStation = (name: string): string => {
    const ws = inp.workstations.find(w => w.station_name === name)
    return ws?.station_group || ''
  }

  // completion per (item, station)
  const completionRow = new Map<string, { qty: number; at: string | null }>()
  for (const c of inp.completion) {
    const key = `${c.item_id}|${c.station_id}`
    const prev = completionRow.get(key)
    const qty = (prev?.qty || 0) + (c.qty_complete ?? 0)
    const at =
      !prev?.at || (c.completed_at && c.completed_at > prev.at) ? c.completed_at ?? prev?.at ?? null : prev.at
    completionRow.set(key, { qty, at })
  }

  // ---- classification --------------------------------------------------
  const classOf = new Map<string, ItemClass>()
  const classify = (id: string): ItemClass => {
    if (classOf.has(id)) return classOf.get(id)!
    const num = (info.get(id)?.item_number || '').toLowerCase()
    const routed = routedByItem.get(id) || []
    const groups = routed.map(s => groupOfStation(s.station_name))
    const hasFabOrWeld = groups.some(g => g === 'Fabrication' || g === 'Weld')
    const hasWeldOrAsm = groups.some(g => g === 'Weld' || g === 'Assembly')
    const hasReceiving = routed.some(s => s.station_name === 'Receiving')

    let cls: ItemClass
    if (num.startsWith('zz')) {
      cls = 'ref'
    } else if (isDocumentItem(num)) {
      cls = 'doc'
    } else if (num.startsWith('mmc') || num.startsWith('spn')) {
      cls = 'purchased'
    } else if (children.has(id) && (hasWeldOrAsm || childrenLookMade(id))) {
      cls = 'assembly'
    } else if (hasReceiving && !hasFabOrWeld) {
      cls = 'purchased'
    } else {
      cls = 'made'
    }
    classOf.set(id, cls)
    return cls
  }
  function childrenLookMade(id: string): boolean {
    // assembly fallback when routing is missing: any non-ref, non-purchased-prefix child
    return (children.get(id) || []).some(c => {
      const n = (info.get(c.child)?.item_number || '').toLowerCase()
      return !n.startsWith('zz') && !n.startsWith('mmc') && !n.startsWith('spn')
    })
  }

  // ---- assembly ordering: DFS post-order from top assembly -------------
  const asmOrder: string[] = []
  const visited = new Set<string>()
  const visit = (id: string) => {
    if (visited.has(id) || classify(id) !== 'assembly') return
    visited.add(id)
    for (const c of children.get(id) || []) visit(c.child)
    asmOrder.push(id)
  }
  if (inp.project.top_assembly_id && inProject(inp.project.top_assembly_id)) {
    visit(inp.project.top_assembly_id)
  }
  const remaining = [...info.keys()]
    .filter(id => classify(id) === 'assembly' && !visited.has(id))
    .sort((a, b) => (info.get(a)!.item_number).localeCompare(info.get(b)!.item_number))
  for (const id of remaining) visit(id)

  const asmRid = new Map<string, string>()
  asmOrder.forEach((id, i) => asmRid.set(id, `A${String(i + 1).padStart(2, '0')}`))

  // ---- box computation --------------------------------------------------
  // Partial allocation across duplicate rows of the same item+column.
  const allocRemaining = new Map<string, number>() // `${item}|${colKey}` -> qty still allocatable

  function colState(itemId: string, col: TrackerColumn, isMade: boolean) {
    const routed = routedByItem.get(itemId) || []
    let matched = routed.filter(s => col.stations.includes(s.station_name))
    if (matched.length === 0 && col.alwaysApplicable && isMade) {
      const sid = stationIdByName.get(col.stations[0]!)
      matched = sid ? [{ station_id: sid, station_name: col.stations[0]! }] : []
      if (matched.length === 0) return { applicable: true, done: false, qty: 0 }
      const row = completionRow.get(`${itemId}|${matched[0]!.station_id}`)
      const need = projQty.get(itemId) || 1
      return { applicable: true, done: !!row && row.qty >= need, qty: row?.qty || 0 }
    }
    if (matched.length === 0) return { applicable: false, done: false, qty: 0 }
    const need = projQty.get(itemId) || 1
    let minQty = Infinity
    let allRows = true
    for (const s of matched) {
      const row = completionRow.get(`${itemId}|${s.station_id}`)
      if (!row) { allRows = false; minQty = 0 } else { minQty = Math.min(minQty, row.qty) }
    }
    if (!isFinite(minQty)) minQty = 0
    return { applicable: true, done: allRows && minQty >= need, qty: minQty }
  }

  function partBox(itemId: string, col: TrackerColumn, rowQty: number): TrackerBox {
    const st = colState(itemId, col, true)
    if (!st.applicable) return { applicable: false, done: false, partial: null, gate: !!col.gate }
    if (st.done) return { applicable: true, done: true, partial: null, gate: !!col.gate }
    // partial allocation for duplicate rows
    const key = `${itemId}|${col.key}`
    if (!allocRemaining.has(key)) allocRemaining.set(key, st.qty)
    const rem = allocRemaining.get(key)!
    const alloc = Math.max(0, Math.min(rowQty, rem))
    allocRemaining.set(key, rem - alloc)
    if (alloc >= rowQty && alloc > 0) return { applicable: true, done: true, partial: null, gate: !!col.gate }
    if (alloc > 0) return { applicable: true, done: false, partial: alloc, gate: !!col.gate }
    return { applicable: true, done: false, partial: null, gate: !!col.gate }
  }

  // ---- part groups -------------------------------------------------------
  let fCount = 0
  const groups: TrackerGroup[] = []
  const placed = new Set<string>()

  for (const asmId of asmOrder) {
    const rows: TrackerPartRow[] = []
    const parentQty = projQty.get(asmId) || 1
    for (const c of children.get(asmId) || []) {
      if (classify(c.child) !== 'made') continue
      placed.add(c.child)
      rows.push(makePartRow(c.child, c.qty * parentQty))
    }
    if (rows.length === 0) continue
    const inf = info.get(asmId)!
    groups.push({
      ref: asmRid.get(asmId) || '—',
      assembly_number: inf.item_number,
      name: inf.name || inf.item_number.toUpperCase(),
      rows,
      readyDone: rows.filter(r => r.rowDone).length,
      readyTotal: rows.length,
    })
  }
  // loose made parts (no assembly parent in project)
  const loose = [...info.keys()]
    .filter(id => classify(id) === 'made' && !placed.has(id))
    .sort((a, b) => info.get(a)!.item_number.localeCompare(info.get(b)!.item_number))
  if (loose.length > 0) {
    const rows = loose.map(id => makePartRow(id, projQty.get(id) || 1))
    groups.push({
      ref: '—',
      assembly_number: '',
      name: 'LOOSE / UNASSIGNED PARTS',
      rows,
      readyDone: rows.filter(r => r.rowDone).length,
      readyTotal: rows.length,
    })
  }

  function makePartRow(itemId: string, qty: number): TrackerPartRow {
    const inf = info.get(itemId)!
    const boxes = PART_COLUMNS.map(col => partBox(itemId, col, qty))
    const rowDone = boxes.every(b => !b.applicable || b.gate || b.done)
    fCount++
    return {
      rid: `F${String(fCount).padStart(2, '0')}`,
      item_id: itemId,
      item_number: inf.item_number,
      name: inf.name,
      qty,
      boxes,
      rowDone,
    }
  }

  // ---- assembly matrix ----------------------------------------------------
  const groupByAsm = new Map(groups.map(g => [g.assembly_number, g]))
  const asmRows: TrackerAsmRow[] = asmOrder.map(id => {
    const inf = info.get(id)!
    const qty = projQty.get(id) || 1
    const boxes = ASM_COLUMNS.map(col => {
      const st = colState(id, col, false)
      if (!st.applicable) return { applicable: false, done: false, partial: null, gate: false }
      if (st.done) return { applicable: true, done: true, partial: null, gate: false }
      const partial = st.qty > 0 && st.qty < qty ? st.qty : null
      return { applicable: true, done: false, partial, gate: false }
    })
    return {
      rid: asmRid.get(id)!,
      item_id: id,
      item_number: inf.item_number,
      name: inf.name,
      qty,
      readyDone: 0,
      readyTotal: 0,
      boxes,
      rowDone: boxes.every(b => !b.applicable || b.done),
    }
  })
  // fill parts-ready fractions (own made rows + child assemblies fully done)
  const asmRowDoneCache = new Map<string, boolean>()
  for (const row of asmRows) asmRowDoneCache.set(row.item_id, row.rowDone)
  for (const row of asmRows) {
    const childAsms = (children.get(row.item_id) || []).filter(c => classify(c.child) === 'assembly')
    const g = groupByAsm.get(row.item_number)
    row.readyDone = (g?.readyDone || 0) + childAsms.filter(c => asmRowDoneCache.get(c.child)).length
    row.readyTotal = (g?.readyTotal || 0) + childAsms.length
  }

  // ---- purchased checklist -------------------------------------------------
  const purchasedIds = [...info.keys()].filter(id => classify(id) === 'purchased')
  purchasedIds.sort((a, b) => {
    const an = info.get(a)!.item_number.toLowerCase()
    const bn = info.get(b)!.item_number.toLowerCase()
    const all = an.startsWith('mmc') ? 1 : 0
    const bll = bn.startsWith('mmc') ? 1 : 0
    return all - bll || an.localeCompare(bn)
  })
  const rcvStationId = stationIdByName.get('Receiving')
  const purchased: TrackerPurchasedRow[] = purchasedIds.map((id, i) => {
    const inf = info.get(id)!
    const qty = projQty.get(id) || 1
    const row = rcvStationId ? completionRow.get(`${id}|${rcvStationId}`) : undefined
    const rcvDone = !!row && row.qty >= qty
    return {
      rid: `P${String(i + 1).padStart(2, '0')}`,
      item_number: inf.item_number,
      displayNumber: purchasedDisplay(inf.item_number, inf.supplier_pn),
      source: purchasedSource(inf.item_number, inf.supplier_name),
      name: inf.name,
      qty,
      longLead: !inf.item_number.toLowerCase().startsWith('mmc'),
      ordDone: false,
      rcvDone,
      rcvPartial: !rcvDone && row && row.qty > 0 ? row.qty : null,
    }
  })

  // ---- milestones ------------------------------------------------------------
  const due = inp.project.due_date ? new Date(inp.project.due_date + 'T00:00:00') : null
  let startDate: Date | null = inp.project.start_date
    ? new Date(inp.project.start_date + 'T00:00:00')
    : null
  if (!startDate && due && inp.schedule) {
    startDate = subtractWorkingDays(due, inp.schedule.total_days)
  }

  const milestones: TrackerMilestone[] = []
  {
    const tasks = inp.schedule?.tasks || []
    const phase = (pred: (stationCode: string, stationNm: string) => boolean) => {
      const matching = tasks.filter(t => {
        const nm = stationName.get(t.station_id) || ''
        return pred(t.station_code, nm)
      })
      if (matching.length === 0) return { plan: '', actual: '' }
      const endDay = Math.max(...matching.map(t => t.end_day))
      const plan = startDate ? fmtPlan(addWorkingDays(startDate, endDay)) : ''
      let actual = ''
      if (matching.every(t => t.is_complete)) {
        let latest: string | null = null
        for (const t of matching) {
          const row = completionRow.get(`${t.item_id}|${t.station_id}`)
          if (row?.at && (!latest || row.at > latest)) latest = row.at
        }
        actual = fmtActual(latest)
      }
      return { plan, actual }
    }
    const grp = (code: string) => stationGroupByCode.get(code) || ''
    const mRecv = phase((_c, nm) => nm === 'Receiving')
    const mFab = phase(c => grp(c) === 'Fabrication')
    const mWeld = phase(c => grp(c) === 'Weld')
    const mAsm = phase(c => grp(c) === 'Assembly')
    const mIns = phase((_c, nm) => nm === 'Inspection')
    milestones.push(
      { rid: 'M10', op: 10, title: 'All purchased parts ordered', plan: fmtPlan(startDate), actual: '' },
      { rid: 'M20', op: 20, title: 'All purchased received & staged', plan: mRecv.plan, actual: mRecv.actual },
      { rid: 'M30', op: 30, title: 'ALL PARTS CUT & DEBURRED — ▸ TO FAB', plan: mFab.plan, actual: mFab.actual, gate: true },
      { rid: 'M40', op: 40, title: 'All weldments welded & cleaned', plan: mWeld.plan, actual: mWeld.actual },
      { rid: 'M50', op: 50, title: 'Mechanical & final assembly complete', plan: mAsm.plan, actual: mAsm.actual },
      { rid: 'M60', op: 60, title: 'Final inspection complete', plan: mIns.plan, actual: mIns.actual },
      { rid: 'M70', op: 70, title: 'Crate & ship', plan: due ? fmtPlan(due) : '', actual: '' },
    )
  }

  // ---- header stats -----------------------------------------------------------
  const fabTotal = groups.reduce((n, g) => n + g.rows.length, 0)
  const fabDone = groups.reduce((n, g) => n + g.readyDone, 0)
  const asmTotal = asmRows.length
  const asmDone = asmRows.filter(r => r.rowDone).length
  let stationsTotal = 0
  let stationsDone = 0
  for (const [itemId, routed] of routedByItem) {
    const need = projQty.get(itemId) || 1
    for (const s of routed) {
      stationsTotal++
      const row = completionRow.get(`${itemId}|${s.station_id}`)
      if (row && row.qty >= need) stationsDone++
    }
  }
  const pctComplete = stationsTotal > 0 ? (stationsDone / stationsTotal) * 100 : 0

  // ---- pagination -----------------------------------------------------------
  // tabloid: everything on one 11x17 page (rail shares page 1 with parts);
  // letter: parts flow across 8.5x11 landscape pages, then a final status page
  //         carries the assembly matrix, milestones, purchased list and log.
  const pages: TrackerPage[] = []
  {
    const cap = format === 'letter' ? PAGE_ROW_CAP_LETTER : PAGE_ROW_CAP_TABLOID
    const railRows = format === 'letter' ? 0 : asmRows.length + 3 // matrix reserve on tabloid page 1 col B
    const budgets: { colA: number; colB: number }[] = [{ colA: cap, colB: cap - railRows }]
    let page = 0
    let col: 'colA' | 'colB' = 'colA'
    let used = 0
    pages.push({ colA: [], colB: [], showRail: format !== 'letter' })

    const advance = () => {
      if (col === 'colA') { col = 'colB'; used = 0 } else {
        page++
        pages.push({ colA: [], colB: [], showRail: false })
        budgets.push({ colA: cap, colB: cap })
        col = 'colA'
        used = 0
      }
    }
    const budget = () => (col === 'colA' ? budgets[page]!.colA : budgets[page]!.colB)

    for (const g of groups) {
      let rows = [...g.rows]
      let first = true
      while (rows.length > 0) {
        let avail = budget() - used - 1 // -1 for the group header row
        if (avail < 2) { advance(); continue }
        const take = rows.slice(0, avail)
        rows = rows.slice(avail)
        pages[page]![col].push({ ...g, rows: take, cont: !first })
        used += take.length + 1
        first = false
        if (rows.length > 0) advance()
      }
    }

    if (format === 'letter') {
      // dedicated status page (assembly matrix + milestones + purchased + log)
      pages.push({ colA: [], colB: [], showRail: true })
    }
  }

  return {
    project: inp.project,
    generatedAt: now,
    startDate,
    format,
    pages,
    asmRows,
    milestones,
    purchased,
    fabDone,
    fabTotal,
    asmDone,
    asmTotal,
    purchasedTotal: purchased.length,
    pctComplete,
  }
}
