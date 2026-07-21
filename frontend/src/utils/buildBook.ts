/**
 * Build Book — data shaping
 *
 * Turns a project's capacity-constrained schedule (calculateSchedule) plus the
 * tracker model (buildTrackerSheet) into a day-by-day manufacturing book:
 *
 *  - Work packages: one per (planned day, station) group of part tasks, in
 *    dependency order — "PKG 04 · Day 3 · SAW: pull this stock, cut these
 *    parts, send them to Deburr, stage kits for A01/A03".
 *  - Kit chapters: one per weldment/assembly in build order — kit list with
 *    which package produces each part, weld sequence with time budget.
 *  - Calendar matrix: station-hours per working day (from schedule stationDays).
 *  - Stock pull summary: raw material totals from routing_materials.
 *
 * Packages are sequence-first (PKG numbers) with planned days printed as
 * guidance, so the book stays valid when the shop drifts off the calendar.
 * Pure functions — the same structure will feed the phase-2 backend PDF
 * generator (embedded prints).
 */

import {
  buildTrackerSheet,
  addWorkingDays,
  purchasedDisplay,
  isDocumentItem,
  kitSuppliedMap,
  type TrackerInputs,
  type TrackerSheet,
  type TrackerMilestone,
  type TrackerGroup,
  type TrackerPurchasedRow,
  type TrackerBundle,
} from './buildTracker'
import type { ScheduleResult, ScheduledTask } from './scheduling'

// mirrors backend print_packet.py STATION_ABBREV
export const STATION_ABBREV: Record<string, string> = {
  'Receiving': 'RCV',
  'Saw': 'SAW',
  'Deburr': 'DBR',
  'Waterjet': 'WJ',
  'Press Brake': 'PB',
  'Weld Jigging': 'JIG',
  'Tig Welding': 'TIG',
  'Dual Shield Weld': 'DS',
  'Weld Cleanup': 'WCU',
  'Pipe Bending': 'PIP',
  'Hole Punch - Iron Worker': 'HP',
  'Part Staging': 'STG',
  'Mechanical Assembly': 'ASM',
  'Plumbing': 'PLM',
  'Wiring': 'WIR',
  'Inspection': 'INS',
  'Galvanizing': 'GAL',
  'Paint and Paint Prep': 'PNT',
  'Vinyl Wrap': 'VW',
}

export function stationAbbrev(name: string): string {
  return STATION_ABBREV[name] || name.slice(0, 3).toUpperCase()
}

/**
 * Relative-day label: 0-indexed schedule day -> shop-facing "D1", "D2", ...
 * The single shared helper for every date-free rendering (master design book);
 * mirrored by dayLabel() in backend master_design_book.py.
 */
export function dayLabel(day: number): string {
  return `D${day + 1}`
}

/**
 * Operations that happen as the tail of every primary operation — operator
 * judgment ("no sharp corners, dimensions right"), not planned work. They get
 * no package cards and no print sets; they remain as per-part checkboxes on
 * the Tracker sheet and as steps in assembly kit sequences.
 */
export const SECONDARY_STATIONS = new Set(['Deburr', 'Inspection'])

// ============================================================================
// TYPES
// ============================================================================

export interface BookRoutingMaterial {
  item_id: string
  qty_required: number | null
  raw_materials: { description: string | null; material_code: string | null } | null
}

export interface BookInputs extends Omit<TrackerInputs, 'schedule' | 'format'> {
  schedule: ScheduleResult
  routingMaterials?: BookRoutingMaterial[]
  /** item_ids that have a current PDF print in the files table */
  printItemIds?: string[]
}

export interface BookPackageLine {
  item_number: string   // internal PDM number
  displayNumber: string // shop-facing PN (mmc/spn prefixes dropped, supplier_pn preferred)
  name: string
  qty: number
  estMin: number
  next: string | null // abbrev of the next station this part goes to, null = last op
  feeds: string[]     // assembly rids this part belongs to (e.g. ['A01'])
  done: boolean
  /** kit_number of the vendor bundle supplying this part finished, else null */
  sourcedFrom: string | null
}

export interface BookStockPull {
  description: string
  qty: number
  parts: number
}

export interface BookPackage {
  id: string   // 'PKG 04'
  seq: number
  day: number
  date: string // planned date, e.g. 'WED JUL 9' ('' without a start date)
  stationName: string
  stationAbbrev: string
  stationGroup: string
  estMin: number
  lines: BookPackageLine[]
  stockPull: BookStockPull[]
  stageFor: string[] // assembly rids whose parts finish their routing here
  done: boolean      // everything in this package already recorded complete
}

export interface BookWeldStep {
  station: string
  abbrev: string
  estMin: number
  done: boolean
  /** planned schedule day (0-indexed) of this step's task, null if unscheduled */
  day: number | null
  /** routing.notes for this step — assembly method instructions written by engineering */
  notes: string | null
}

export interface BookKitPart {
  rid: string
  item_number: string
  name: string
  qty: number
  readyBy: string | null // package id producing this part ('PKG 07'), null = no routing
  readyDay: number | null
  done: boolean
  /** kit_number of the vendor bundle supplying this part finished, else null */
  sourcedFrom: string | null
}

export interface BookKit {
  rid: string
  item_number: string
  name: string
  qty: number
  startDay: number | null
  endDay: number | null
  startDate: string
  endDate: string
  estMin: number
  weldSeq: BookWeldStep[]
  parts: BookKitPart[]
  childAsms: { rid: string; item_number: string; name: string }[]
  hasPrint: boolean
  partPrints: number // how many of its parts have PDF prints
  /** drawing numbers + revs to pull from the print packet for this kit */
  printRefs: { item_number: string; revision: string | null }[]
}

export interface BookReferenceDoc {
  item_number: string
  name: string
  revision: string | null
  hasPrint: boolean
}

export interface BookCalendar {
  stations: { code: string; abbrev: string; name: string }[]
  days: {
    day: number
    date: string
    cells: ({ hours: number; pkgs: string[] } | null)[]
  }[]
}

export interface BuildBook {
  project: TrackerInputs['project']
  generatedAt: Date
  startDate: Date | null
  milestones: TrackerMilestone[]
  summary: {
    totalHours: number
    totalDays: number
    fabParts: number
    /** leaf parts supplied finished in a vendor bundle (received, inspected, staged) */
    kitSupplied: number
    assemblies: number
    purchased: number
    packageCount: number
    byGroup: { group: string; hours: number }[]
  }
  stock: BookStockPull[]
  calendar: BookCalendar
  packages: BookPackage[]
  kits: BookKit[]
  /** controlled document items (csd... / third-letter-d) attached to the project */
  referenceDocs: BookReferenceDoc[]
  /** purchased items checklist (shop-facing display numbers + source), from the tracker model */
  purchased: TrackerPurchasedRow[]
  /** vendor bundles supplying finished parts (see Documentation/38) */
  bundles: TrackerBundle[]
}

// ============================================================================
// HELPERS
// ============================================================================

function fmtDay(date: Date | null): string {
  if (!date || isNaN(date.getTime())) return ''
  const wd = date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase()
  const md = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()
  return `${wd} ${md}`
}

function round1(n: number): number {
  return Math.round(n * 10) / 10
}

// ============================================================================
// MAIN
// ============================================================================

export function buildBook(inp: BookInputs): BuildBook {
  const now = inp.now ?? new Date()
  const schedule = inp.schedule

  // reuse the tracker model for classification, ordering, milestones, groups
  const sheet: TrackerSheet = buildTrackerSheet({ ...inp, schedule, format: 'tabloid' })

  const info = new Map<
    string,
    { item_number: string; name: string; supplier_pn: string | null; revision: string | null }
  >()
  const projQty = new Map<string, number>()
  for (const p of inp.parts) {
    if (!p.items) continue
    info.set(p.item_id, {
      item_number: p.items.item_number,
      name: p.items.name || p.items.description || '',
      supplier_pn: p.items.supplier_pn ?? null,
      revision: p.items.revision ?? null,
    })
    projQty.set(p.item_id, p.quantity)
  }

  const asmByItem = new Map(sheet.asmRows.map(a => [a.item_id, a]))
  const asmSet = new Set(asmByItem.keys())

  // feeds: item -> assembly rids that consume it (direct BOM parents that are assemblies)
  const feedsOf = new Map<string, string[]>()
  for (const b of inp.bom) {
    const parentAsm = asmByItem.get(b.parent_item_id)
    if (!parentAsm || !info.has(b.child_item_id)) continue
    if (!feedsOf.has(b.child_item_id)) feedsOf.set(b.child_item_id, [])
    const list = feedsOf.get(b.child_item_id)!
    if (!list.includes(parentAsm.rid)) list.push(parentAsm.rid)
  }

  // per-item routed station order (deduped by station_id) + step notes
  const routeOrder = new Map<string, string[]>() // item_id -> station_ids in sequence
  const stepNotes = new Map<string, string>()    // `${item_id}|${station_id}` -> routing.notes
  const sortedRouting = [...inp.routing].sort((a, b) => a.sequence - b.sequence)
  for (const r of sortedRouting) {
    if (!info.has(r.item_id)) continue
    if (!routeOrder.has(r.item_id)) routeOrder.set(r.item_id, [])
    const list = routeOrder.get(r.item_id)!
    if (!list.includes(r.station_id)) list.push(r.station_id)
    if (r.notes && !stepNotes.has(`${r.item_id}|${r.station_id}`)) {
      stepNotes.set(`${r.item_id}|${r.station_id}`, r.notes)
    }
  }

  const wsById = new Map(inp.workstations.map(w => [w.id, w]))
  const wsByCode = new Map(inp.workstations.map(w => [w.station_code, w]))
  const sortOrderOf = (stationId: string): number => {
    const ws = wsById.get(stationId) as any
    return typeof ws?.sort_order === 'number' ? ws.sort_order : 999
  }

  // kit-supplied leaf parts (vendor bundles) — same derivation as the tracker
  const kitOf = kitSuppliedMap(inp.kitSources, inp.bom)

  // materials per item. Kit-supplied parts arrive cut, so they pull no raw stock —
  // applyKitSourcing already drops their rows; this guards a caller that forgot.
  const matsOf = new Map<string, { description: string; qty: number }[]>()
  for (const m of inp.routingMaterials || []) {
    if (!info.has(m.item_id) || kitOf.has(m.item_id)) continue
    const desc = m.raw_materials?.description || m.raw_materials?.material_code || 'Material'
    if (!matsOf.has(m.item_id)) matsOf.set(m.item_id, [])
    matsOf.get(m.item_id)!.push({ description: desc, qty: m.qty_required ?? 0 })
  }

  const printSet = new Set(inp.printItemIds || [])

  // ---- work packages: one per station (all days consolidated) ----------------
  // secondary ops (deburr/inspection) are folded into their primary operation
  const isSecondary = (stationId: string) =>
    SECONDARY_STATIONS.has(wsById.get(stationId)?.station_name || '')
  const partTasks = schedule.tasks.filter(
    t => !asmSet.has(t.item_id) && info.has(t.item_id) && !isSecondary(t.station_id)
  )
  const pkgGroups = new Map<string, ScheduledTask[]>()
  for (const t of partTasks) {
    const key = t.station_id  // group by station only, not day
    if (!pkgGroups.has(key)) pkgGroups.set(key, [])
    pkgGroups.get(key)!.push(t)
  }

  // Sort by station sort order only (no day dimension)
  const groupEntries = [...pkgGroups.entries()].sort((a, b) => {
    return sortOrderOf(a[0]) - sortOrderOf(b[0])
  })

  const packages: BookPackage[] = []
  const pkgOfTask = new Map<string, BookPackage>() // task id -> package
  let seq = 0
  for (const [stationId, tasks] of groupEntries) {
    seq++
    // Day is now the earliest day any task at this station starts
    const day = Math.min(...tasks.map(t => t.start_day))
    const ws = wsById.get(stationId)
    const stationName = ws?.station_name || tasks[0]?.station_code || '?'
    tasks.sort((a, b) => a.item_number.localeCompare(b.item_number))

    const lines: BookPackageLine[] = []
    const stockAgg = new Map<string, { qty: number; parts: number }>()
    const stageFor = new Set<string>()

    for (const t of tasks) {
      const route = routeOrder.get(t.item_id) || []
      const idx = route.indexOf(t.station_id)
      // next PRIMARY station — deburr/inspection happen at the tail of this op
      let nextId: string | null = null
      if (idx >= 0) {
        for (let i = idx + 1; i < route.length; i++) {
          if (!isSecondary(route[i]!)) {
            nextId = route[i]!
            break
          }
        }
      }
      const nextName = nextId ? wsById.get(nextId)?.station_name || null : null
      const feeds = feedsOf.get(t.item_id) || []

      lines.push({
        item_number: t.item_number,
        displayNumber: purchasedDisplay(t.item_number, info.get(t.item_id)?.supplier_pn),
        name: info.get(t.item_id)?.name || '',
        qty: t.quantity,
        estMin: round1(t.duration_min),
        next: nextName ? stationAbbrev(nextName) : null,
        feeds,
        done: t.is_complete,
        sourcedFrom: kitOf.get(t.item_id)?.kit_number ?? null,
      })

      // stock pull at the item's first routed station
      if (idx === 0) {
        for (const m of matsOf.get(t.item_id) || []) {
          const cur = stockAgg.get(m.description) || { qty: 0, parts: 0 }
          cur.qty += m.qty * (projQty.get(t.item_id) || 1)
          cur.parts++
          stockAgg.set(m.description, cur)
        }
      }
      if (!nextId) for (const f of feeds) stageFor.add(f)
    }

    const pkg: BookPackage = {
      id: `PKG ${String(seq).padStart(2, '0')}`,
      seq,
      day,
      date: sheet.startDate ? fmtDay(addWorkingDays(sheet.startDate, day)) : '',
      stationName,
      stationAbbrev: stationAbbrev(stationName),
      stationGroup: (ws?.station_group as string) || '',
      estMin: round1(tasks.reduce((n, t) => n + t.duration_min, 0)),
      lines,
      stockPull: [...stockAgg.entries()]
        .map(([description, v]) => ({ description, qty: round1(v.qty), parts: v.parts }))
        .sort((a, b) => b.qty - a.qty),
      stageFor: [...stageFor].sort(),
      done: tasks.every(t => t.is_complete),
    }
    packages.push(pkg)
    for (const t of tasks) pkgOfTask.set(t.id, pkg)
  }

  // package that PRODUCES an item = package of its last PRIMARY routed task
  const producerOf = new Map<string, BookPackage>()
  for (const [itemId, route] of routeOrder) {
    if (asmSet.has(itemId)) continue
    for (let i = route.length - 1; i >= 0; i--) {
      const pkg = pkgOfTask.get(`${itemId}_${route[i]}`)
      if (pkg) {
        producerOf.set(itemId, pkg)
        break
      }
    }
  }

  // ---- kit chapters ----------------------------------------------------------
  // merge tracker groups (which may be split across pages) by assembly rid
  const groupByRef = new Map<string, TrackerGroup>()
  for (const page of sheet.pages) {
    for (const g of [...page.colA, ...page.colB]) {
      const existing = groupByRef.get(g.ref)
      if (existing) existing.rows = [...existing.rows, ...g.rows]
      else groupByRef.set(g.ref, { ...g, rows: [...g.rows] })
    }
  }

  const childAsmsOf = (asmItemId: string) =>
    inp.bom
      .filter(b => b.parent_item_id === asmItemId && asmSet.has(b.child_item_id))
      .map(b => asmByItem.get(b.child_item_id)!)
      .map(a => ({ rid: a.rid, item_number: a.item_number, name: a.name }))

  const kits: BookKit[] = sheet.asmRows.map(a => {
    const tasks = schedule.tasks
      .filter(t => t.item_id === a.item_id)
      .sort((x, y) => x.sequence - y.sequence)
    const startDay = tasks.length ? Math.min(...tasks.map(t => t.start_day)) : null
    const endDay = tasks.length ? Math.max(...tasks.map(t => t.end_day)) : null
    const group = groupByRef.get(a.rid)
    const parts: BookKitPart[] = (group?.rows || []).map(r => {
      const producer = producerOf.get(r.item_id)
      return {
        rid: r.rid,
        item_number: r.item_number,
        name: r.name,
        qty: r.qty,
        readyBy: producer?.id ?? null,
        readyDay: producer?.day ?? null,
        done: r.rowDone,
        sourcedFrom: r.sourcedFrom,
      }
    })
    // drawings to pull for this kit: the assembly print + each part's print (with rev)
    const printRefs: { item_number: string; revision: string | null }[] = []
    if (printSet.has(a.item_id)) {
      printRefs.push({ item_number: a.item_number, revision: info.get(a.item_id)?.revision ?? null })
    }
    const seenRef = new Set<string>()
    for (const r of group?.rows || []) {
      if (seenRef.has(r.item_id) || !printSet.has(r.item_id)) continue
      seenRef.add(r.item_id)
      printRefs.push({ item_number: r.item_number, revision: info.get(r.item_id)?.revision ?? null })
    }

    return {
      rid: a.rid,
      item_number: a.item_number,
      name: a.name,
      qty: a.qty,
      startDay,
      endDay,
      startDate: sheet.startDate && startDay !== null ? fmtDay(addWorkingDays(sheet.startDate, startDay)) : '',
      endDate: sheet.startDate && endDay !== null ? fmtDay(addWorkingDays(sheet.startDate, endDay)) : '',
      estMin: round1(tasks.reduce((n, t) => n + t.duration_min, 0)),
      weldSeq: tasks.map(t => {
        const nm = wsById.get(t.station_id)?.station_name || t.station_code
        return {
          station: nm,
          abbrev: stationAbbrev(nm),
          estMin: round1(t.duration_min),
          done: t.is_complete,
          day: t.start_day,
          notes: stepNotes.get(`${t.item_id}|${t.station_id}`) ?? null,
        }
      }),
      parts,
      childAsms: childAsmsOf(a.item_id),
      hasPrint: printSet.has(a.item_id),
      partPrints: parts.filter(p => {
        const id = (group?.rows || []).find(r => r.rid === p.rid)?.item_id
        return id ? printSet.has(id) : false
      }).length,
      printRefs,
    }
  })

  // ---- calendar matrix (station-hours per day from the scheduler) -----------
  const usedCodes = [...schedule.stationDays.keys()].filter(c => c)
  usedCodes.sort((a, b) => {
    const wa = wsByCode.get(a) as any
    const wb = wsByCode.get(b) as any
    return (wa?.sort_order ?? 999) - (wb?.sort_order ?? 999)
  })
  const calendar: BookCalendar = {
    stations: usedCodes.map(code => {
      const nm = wsByCode.get(code)?.station_name || code
      return { code, abbrev: stationAbbrev(nm), name: nm }
    }),
    days: [],
  }
  for (let d = 0; d < schedule.total_days; d++) {
    const cells = usedCodes.map(code => {
      const slot = schedule.stationDays.get(code)?.[d]
      const mins = slot?.used_minutes || 0
      if (mins <= 0) return null
      const pkgs = packages.filter(p => p.day === d && wsByCode.get(code)?.station_name === p.stationName).map(p => p.id)
      return { hours: round1(mins / 60), pkgs }
    })
    if (cells.every(c => c === null)) continue
    calendar.days.push({
      day: d,
      date: sheet.startDate ? fmtDay(addWorkingDays(sheet.startDate, d)) : `Day ${d + 1}`,
      cells,
    })
  }

  // ---- stock summary + totals ------------------------------------------------
  const stockAll = new Map<string, { qty: number; parts: number }>()
  for (const [itemId, mats] of matsOf) {
    for (const m of mats) {
      const cur = stockAll.get(m.description) || { qty: 0, parts: 0 }
      cur.qty += m.qty * (projQty.get(itemId) || 1)
      cur.parts++
      stockAll.set(m.description, cur)
    }
  }

  const referenceDocs: BookReferenceDoc[] = inp.parts
    .filter(p => p.items && isDocumentItem(p.items.item_number))
    .map(p => ({
      item_number: p.items!.item_number,
      name: p.items!.name || p.items!.description || '',
      revision: p.items!.revision ?? null,
      hasPrint: printSet.has(p.item_id),
    }))
    .sort((a, b) => a.item_number.localeCompare(b.item_number))

  const groupHours = new Map<string, number>()
  for (const t of schedule.tasks) {
    const g = (wsByCode.get(t.station_code)?.station_group as string) || 'Other'
    groupHours.set(g, (groupHours.get(g) || 0) + t.duration_min)
  }

  return {
    project: inp.project,
    generatedAt: now,
    startDate: sheet.startDate,
    milestones: sheet.milestones,
    summary: {
      totalHours: round1(schedule.tasks.reduce((n, t) => n + t.duration_min, 0) / 60),
      totalDays: schedule.total_days,
      fabParts: sheet.fabTotal,
      kitSupplied: sheet.kitSuppliedTotal,
      assemblies: sheet.asmTotal,
      purchased: sheet.purchasedTotal,
      packageCount: packages.length,
      byGroup: [...groupHours.entries()]
        .map(([group, mins]) => ({ group, hours: round1(mins / 60) }))
        .sort((a, b) => b.hours - a.hours),
    },
    stock: [...stockAll.entries()]
      .map(([description, v]) => ({ description, qty: round1(v.qty), parts: v.parts }))
      .sort((a, b) => b.qty - a.qty),
    calendar,
    packages,
    kits,
    referenceDocs,
    purchased: sheet.purchased,
    bundles: sheet.bundles,
  }
}
