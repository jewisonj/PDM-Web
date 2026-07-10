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
  /** vendor bundles supplying finished parts (see Documentation/38). Omit for the
   *  pre-kit behavior — every part is made in-house. */
  kitSources?: KitSourceInput[]
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
  /** kit_number of the vendor bundle supplying this part finished, else null */
  sourcedFrom: string | null
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
  /** vendor bundles supplying finished parts, with their part counts */
  bundles: TrackerBundle[]
  fabDone: number
  /** part ROWS that are made in-house. A part used by two assemblies counts twice —
   *  same convention as before kit sourcing, so fabTotal + kitSuppliedTotal is the
   *  old fabTotal. (TrackerBundle.partCount counts DISTINCT part numbers instead.) */
  fabTotal: number
  kitSuppliedTotal: number
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

type ItemClass = 'assembly' | 'made' | 'kit_supplied' | 'purchased' | 'ref' | 'doc'

/** Third-letter-'d' items (csd0001, wmd0100...) are controlled documents — design books,
 *  build references — not physical parts. They never appear as tracker/book work rows;
 *  the Build Book lists them as reference prints instead. */
export function isDocumentItem(itemNumber: string): boolean {
  return /^[a-z]{2}d\d/i.test(itemNumber)
}

/** The zz* family is reference-only: sub-components of purchased items uploaded for CAD
 *  reference (zzz1071a59a), and legacy reference numbers (zzc551436, zz_hingebody). They
 *  are excluded from all manufacturing views, routing requirements, cost reports, BOMs,
 *  and design books.
 *
 *  Deliberately matches the whole `zz` family, not just `zzz`: narrowing this to `zzz`
 *  would reclassify the routing-less zzc* reference items as makeable parts. */
export function isReferenceOnlyItem(itemNumber: string): boolean {
  return itemNumber.toLowerCase().startsWith('zz')
}

/** Returns true if the item should be excluded from manufacturing views
 *  (documents, zz reference items, purchased mmc/spn parts).
 *
 *  ⚠ Dashboard/report use only — NOT for the build documents. The Build Book and Master
 *  Design Book need mmc/spn items: they are the spine BUY LIST and the receiving work
 *  packages. Use isReferenceOnlyItem()/isDocumentItem() there instead. */
export function excludeFromManufacturing(itemNumber: string): boolean {
  const lower = itemNumber.toLowerCase()
  return (
    isDocumentItem(itemNumber) ||
    isReferenceOnlyItem(itemNumber) ||
    lower.startsWith('mmc') ||
    lower.startsWith('spn')
  )
}

// ============================================================================
// KIT SOURCING (vendor bundles of finished parts — see Documentation/38)
// ============================================================================

/** One part's vendor-bundle assignment, from project_item_source + project_kits.
 *  `use_kit` is deliberately NOT modelled: it is a pricing toggle, and a cost
 *  experiment must never change a controlled build document. */
export interface KitSourceInput {
  item_id: string
  kit_number: string // 'KIT-001'
  kit_name: string // 'Tube Laser Bundle'
  vendor: string | null // 'Precision Tube Laser'
}

export interface TrackerBundle {
  kit_number: string
  kit_name: string
  vendor: string | null
  partCount: number
}

/**
 * Routing synthesized for kit-supplied parts: they arrive finished, so the shop
 * receives them, inspects them, and stages them to their area.
 *
 * Times are PER UNIT and deliberately small. The 5-min house norm on Receiving is
 * the cost of an individually purchased item (unpack, count and log one McMaster
 * box); a bundle arrives as a single shipment of many pre-cut parts. Buying finished
 * parts must never cost MORE shop labor than making them — at 5/5/5 the SPA0030
 * bundle charged 435 min against the 193 min of in-house work it replaced, which
 * lengthened the schedule instead of shortening it.
 */
export const KIT_SUPPLIED_ROUTING: { stationName: string; sequence: number; estMin: number }[] = [
  { stationName: 'Receiving', sequence: 10, estMin: 1 },
  { stationName: 'Inspection', sequence: 20, estMin: 2 },
  { stationName: 'Part Staging', sequence: 30, estMin: 1 },
]

/**
 * item_id -> bundle, for kit-sourced items that are LEAF parts.
 *
 * A kit-sourced item that is a BOM parent (a pre-welded weldment) is out of scope:
 * buying it would retire its whole assembly section. Those are excluded here, so
 * classification and routing synthesis agree on exactly one set of items.
 */
export function kitSuppliedMap(
  kitSources: KitSourceInput[] | undefined,
  bom: { parent_item_id: string }[]
): Map<string, KitSourceInput> {
  const map = new Map<string, KitSourceInput>()
  if (!kitSources?.length) return map
  const parents = new Set(bom.map(b => b.parent_item_id))
  for (const k of kitSources) {
    if (parents.has(k.item_id)) continue // assembly-level kit: not supported
    map.set(k.item_id, k)
  }
  return map
}

export interface SourcedRoutingRow {
  id: string
  item_id: string
  station_id: string
  sequence: number
  est_time_min: number | null
  notes?: string | null
  workstations: { station_code: string; station_name: string } | null
}

/**
 * Rewrite routing for kit-supplied parts, per project.
 *
 * The `routing` table has no project_id — it is global per item — so the parts a
 * vendor supplies pre-cut here are still sawn in other projects. Sourcing lives in
 * the per-project project_item_source table, so the receive-and-inspect flow is
 * SYNTHESIZED at build time and the routing table is never touched.
 *
 * Also drops the parts' routing_materials: the vendor already cut them, so the
 * receiving booklet must not tell the shop to pull raw tube stock.
 */
export function applyKitSourcing<M extends { item_id: string }>(args: {
  routing: SourcedRoutingRow[]
  routingMaterials?: M[]
  kitSources?: KitSourceInput[]
  workstations: TrackerWorkstation[]
  bom: { parent_item_id: string }[]
}): { routing: SourcedRoutingRow[]; routingMaterials: M[] } {
  const supplied = kitSuppliedMap(args.kitSources, args.bom)
  const materials = args.routingMaterials ?? []
  if (supplied.size === 0) return { routing: args.routing, routingMaterials: materials }

  const stationByName = new Map(args.workstations.map(w => [w.station_name, w]))
  const kept = args.routing.filter(r => !supplied.has(r.item_id))

  const synthesized: SourcedRoutingRow[] = []
  for (const itemId of supplied.keys()) {
    for (const op of KIT_SUPPLIED_ROUTING) {
      const ws = stationByName.get(op.stationName)
      if (!ws) continue // station not configured — skip rather than invent one
      synthesized.push({
        id: `kit-${itemId}-${ws.id}`,
        item_id: itemId,
        station_id: ws.id,
        sequence: op.sequence,
        est_time_min: op.estMin,
        notes: null,
        workstations: { station_code: ws.station_code, station_name: ws.station_name },
      })
    }
  }

  return {
    routing: [...kept, ...synthesized],
    routingMaterials: materials.filter(m => !supplied.has(m.item_id)),
  }
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

  // ---- kit sourcing (leaf parts supplied finished in a vendor bundle) ----
  const kitOf = kitSuppliedMap(inp.kitSources, inp.bom)

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
    if (isReferenceOnlyItem(num)) {
      cls = 'ref'
    } else if (isDocumentItem(num)) {
      cls = 'doc'
    } else if (kitOf.has(id)) {
      // bought finished in a bundle: receive + inspect + stage, but still a member of
      // the assemblies it goes into (kitSuppliedMap already excluded BOM parents)
      cls = 'kit_supplied'
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
  /** parts that physically go into an assembly's stage set: made in-house or supplied
   *  finished in a bundle. Purchased hardware is tracked on the buy list instead. */
  const isStageSetPart = (id: string): boolean => {
    const c = classify(id)
    return c === 'made' || c === 'kit_supplied'
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
      // kit-supplied parts stay in the stage set: the welder still needs the list of
      // tubes that go into this weldment, even though the vendor cut them
      if (!isStageSetPart(c.child)) continue
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
  // loose parts (no assembly parent in project)
  const loose = [...info.keys()]
    .filter(id => isStageSetPart(id) && !placed.has(id))
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
      sourcedFrom: kitOf.get(itemId)?.kit_number ?? null,
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

  // ---- bundles ------------------------------------------------------------------
  const bundleAgg = new Map<string, TrackerBundle>()
  for (const k of kitOf.values()) {
    const cur = bundleAgg.get(k.kit_number)
    if (cur) cur.partCount++
    else
      bundleAgg.set(k.kit_number, {
        kit_number: k.kit_number,
        kit_name: k.kit_name,
        vendor: k.vendor,
        partCount: 1,
      })
  }
  const bundles = [...bundleAgg.values()].sort((a, b) => a.kit_number.localeCompare(b.kit_number))

  // ---- header stats -----------------------------------------------------------
  // kit-supplied parts share the group rows with made parts but are not fabricated
  const allRows = groups.flatMap(g => g.rows)
  const fabTotal = allRows.filter(r => r.sourcedFrom === null).length
  const kitSuppliedTotal = allRows.length - fabTotal
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
    bundles,
    fabDone,
    fabTotal,
    kitSuppliedTotal,
    asmDone,
    asmTotal,
    purchasedTotal: purchased.length,
    pctComplete,
  }
}
