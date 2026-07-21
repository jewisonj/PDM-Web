/**
 * Master Design Book — data engine (Phase 1 of Documentation/36)
 *
 * Turns a template project (TEST-PROG01 / Standard Spa) into the date-free,
 * completion-free MASTER book model plus the section descriptors the backend
 * hashes, diffs, and renders into swap-able booklet PDFs:
 *
 *   00-SPINE        cover + buy list + master checklist (D1..Dn) + TOC data
 *   I-{ABBREV}      one per station/process (identity = station_code)
 *   II-{ITEM}       one per assembly kit  (identity = item_number)
 *   II-REF          controlled design-reference documents (csd items)
 *   III-00          general reference blank template
 *
 * Guarantees the backend relies on (see Documentation/36 sections 3-5):
 *  - DETERMINISM: inputs are canonically sorted before scheduling, so identical
 *    data always yields identical descriptors (scheduling tie-breaks by input
 *    order — unsorted inputs would cause phantom rev bumps).
 *  - DATE-FREE: start_date AND due_date are nulled before the engines run
 *    (buildTracker back-derives a start date from due_date otherwise); only
 *    0-indexed integer day fields remain — render via dayLabel().
 *  - BLANK: no completion data is even accepted; done flags are additionally
 *    force-cleared post-build (unrouted made parts get rowDone=true from the
 *    tracker's gate exemption — buildTracker.ts colState/makePartRow).
 *  - STABLE CROSS-REFS: package ids (PKG 04) and assembly rids (A01) are
 *    display ordinals that reshuffle; every cross-reference in descriptor
 *    payloads is translated to section codes (I-SAW / II-CSA00020), and kit
 *    part row ids are kit-local (P01...) rather than the tracker's global F##.
 */

import {
  buildBook,
  dayLabel,
  type BuildBook,
  type BookInputs,
  type BookRoutingMaterial,
} from './buildBook'
import {
  purchasedSource,
  applyKitSourcing,
  isReferenceOnlyItem,
  type TrackerProject,
  type TrackerPartInput,
  type TrackerBomInput,
  type TrackerWorkstation,
  type TrackerBundle,
  type KitSourceInput,
} from './buildTracker'
import {
  calculateSchedule,
  type PartData,
  type BomData,
  type RoutingData,
  type ScheduleResult,
} from './scheduling'

export { dayLabel }

// ============================================================================
// TYPES
// ============================================================================

/** routing rows need scheduling fields (id, est_time_min) + tracker fields (notes, workstations) */
export interface MasterRoutingInput {
  id: string
  item_id: string
  station_id: string
  sequence: number
  est_time_min: number | null
  notes?: string | null
  workstations: { station_code: string; station_name: string } | null
}

export interface MasterBookInputs {
  project: TrackerProject
  parts: TrackerPartInput[]
  bom: TrackerBomInput[]
  routing: MasterRoutingInput[]
  workstations: (TrackerWorkstation & { sort_order?: number })[]
  routingMaterials?: BookRoutingMaterial[]
  /** item_ids that have a current PDF print in the files table */
  printItemIds?: string[]
  /** vendor bundles supplying finished parts, from project_item_source + project_kits.
   *  The book follows the sourcing assignment only — `use_kit` is a pricing toggle and
   *  must never rev a controlled document (Documentation/38 §3). */
  kitSources?: KitSourceInput[]
  now?: Date
}

export type SectionKind =
  | 'spine'
  | 'work_package'
  | 'assembly'
  | 'design_reference'
  | 'general_reference'

export interface SectionPrintItem {
  item_number: string
  /** null = reference document (no qty stamp) */
  qty: number | null
}

export interface SectionDescriptor {
  section_code: string
  kind: SectionKind
  title: string
  sort_order: number
  /** stable diff-match key — NEVER printed (Documentation/36 section 3) */
  identity: Record<string, unknown>
  /** printed-but-unstable metadata (day, positions) — hashed, not identity */
  display: Record<string, unknown> | null
  /** kind-specific table data: done-stripped, cross-refs as section codes */
  payload: Record<string, unknown>
  /** ordered print bind list (bind order = booklet page order) */
  print_items: SectionPrintItem[]
  /** purchased (mmc/spn) numbers excluded from print binding + MISSING warnings */
  no_print_expected: string[]
}

export interface QtyMismatch {
  item_number: string
  project_qty: number
  bom_rollup_qty: number
}

export interface QtyCheck {
  ok: boolean
  mismatches: QtyMismatch[]
}

export interface ChecklistRow {
  kind: 'package' | 'kit_step' | 'milestone'
  /** 0-indexed schedule day; -1 = before D1 (e.g. M10 order milestone) */
  day: number
  stn: string | null
  text: string
  estH: number | null
  /** section code this row points at (SEE column); null for milestones */
  see: string | null
  /** milestone op number (10, 20...) for milestone rows */
  op: number | null
}

export interface MasterDesignBook {
  meta: {
    product_item_number: string
    template_project_code: string
    title: string
    day_count: number
    generated_at: Date
  }
  /** the master-mode BuildBook (D-days only, all done flags false) */
  book: BuildBook
  sections: SectionDescriptor[]
  qtyCheck: QtyCheck
}

// ============================================================================
// HELPERS
// ============================================================================

function isPurchasedNumber(itemNumber: string): boolean {
  const n = itemNumber.toLowerCase()
  return n.startsWith('mmc') || n.startsWith('spn')
}

function round1(n: number): number {
  return Math.round(n * 10) / 10
}

export interface SectionBundle {
  kit_number: string
  kit_name: string
  vendor: string | null
  /** distinct parts of this bundle handled by THIS section */
  partCount: number
}

/** vendor bundles represented in a set of package lines, with per-section part counts */
function bundlesIn(
  lines: { item_number: string; sourcedFrom: string | null }[],
  byNumber: Map<string, TrackerBundle>
): SectionBundle[] {
  const counts = new Map<string, Set<string>>()
  for (const l of lines) {
    if (!l.sourcedFrom) continue
    if (!counts.has(l.sourcedFrom)) counts.set(l.sourcedFrom, new Set())
    counts.get(l.sourcedFrom)!.add(l.item_number)
  }
  return [...counts.entries()]
    .map(([kit_number, items]) => {
      const b = byNumber.get(kit_number)
      return {
        kit_number,
        kit_name: b?.kit_name ?? kit_number,
        vendor: b?.vendor ?? null,
        partCount: items.size,
      }
    })
    .sort((a, b) => a.kit_number.localeCompare(b.kit_number))
}

/** canonical input copies — deterministic order regardless of DB result order */
function canonicalize(inp: MasterBookInputs): MasterBookInputs {
  const partNum = new Map(inp.parts.map(p => [p.item_id, p.items?.item_number ?? '']))
  const key = (id: string) => `${partNum.get(id) ?? ''}|${id}`
  return {
    ...inp,
    parts: [...inp.parts].sort((a, b) => key(a.item_id).localeCompare(key(b.item_id))),
    bom: [...inp.bom].sort(
      (a, b) =>
        key(a.parent_item_id).localeCompare(key(b.parent_item_id)) ||
        key(a.child_item_id).localeCompare(key(b.child_item_id))
    ),
    routing: [...inp.routing].sort(
      (a, b) =>
        key(a.item_id).localeCompare(key(b.item_id)) ||
        a.sequence - b.sequence ||
        a.station_id.localeCompare(b.station_id)
    ),
    workstations: [...inp.workstations].sort(
      (a, b) => (a.sort_order ?? 999) - (b.sort_order ?? 999) || a.station_code.localeCompare(b.station_code)
    ),
    routingMaterials: inp.routingMaterials
      ? [...inp.routingMaterials].sort(
          (a, b) =>
            key(a.item_id).localeCompare(key(b.item_id)) ||
            (a.raw_materials?.description ?? '').localeCompare(b.raw_materials?.description ?? '')
        )
      : undefined,
    printItemIds: inp.printItemIds ? [...inp.printItemIds].sort() : undefined,
    kitSources: inp.kitSources
      ? [...inp.kitSources].sort(
          (a, b) =>
            a.kit_number.localeCompare(b.kit_number) || key(a.item_id).localeCompare(key(b.item_id))
        )
      : undefined,
  }
}

/** force every completion-derived flag false — the master book is always blank */
function blankDoneFlags(book: BuildBook): void {
  for (const p of book.packages) {
    p.done = false
    for (const l of p.lines) l.done = false
  }
  for (const k of book.kits) {
    for (const s of k.weldSeq) s.done = false
    for (const pt of k.parts) pt.done = false
  }
  for (const m of book.milestones) {
    m.plan = ''
    m.actual = ''
  }
  for (const row of book.purchased) {
    row.ordDone = false
    row.rcvDone = false
    row.rcvPartial = null
  }
}

/**
 * Recursive BOM quantity rollup from the top assembly, compared against the
 * flat mrp_project_parts quantities. The known data quirk: the two can drift
 * (e.g. a part used in two subassemblies flattened as qty 1). A qty-stamped
 * controlled print with a wrong quantity is the one failure the master book
 * must not ship, so mismatches gate the backend update (Documentation/36 4.3).
 */
function checkQuantities(
  project: TrackerProject,
  parts: TrackerPartInput[],
  bom: TrackerBomInput[]
): QtyCheck {
  const projQty = new Map<string, number>()
  const numOf = new Map<string, string>()
  for (const p of parts) {
    if (!p.items) continue
    projQty.set(p.item_id, p.quantity)
    numOf.set(p.item_id, p.items.item_number)
  }
  const topId = project.top_assembly_id
  if (!topId || !projQty.has(topId)) return { ok: true, mismatches: [] }

  // parent links, in-project pairs only
  const parents = new Map<string, { parent: string; qty: number }[]>()
  for (const b of bom) {
    if (!projQty.has(b.parent_item_id) || !projQty.has(b.child_item_id)) continue
    if (!parents.has(b.child_item_id)) parents.set(b.child_item_id, [])
    parents.get(b.child_item_id)!.push({ parent: b.parent_item_id, qty: b.quantity })
  }

  // usage(id) = total quantity per top build, memoized bottom-up over the DAG.
  // NOTE: a naive walk-down accumulator double-counts grandchildren when a
  // subassembly is reachable through multiple BOM paths (e.g. door hardware
  // under two door weldments) — usage must sum over PARENT usages, once each.
  const memo = new Map<string, number>()
  const usage = (id: string, stack: Set<string>): number => {
    if (id === topId) return projQty.get(topId) || 1
    if (memo.has(id)) return memo.get(id)!
    if (stack.has(id)) return 0 // defensive: BOM cycles should not exist
    stack.add(id)
    let total = 0
    for (const p of parents.get(id) || []) {
      total += usage(p.parent, stack) * p.qty
    }
    stack.delete(id)
    memo.set(id, total)
    return total
  }

  const mismatches: QtyMismatch[] = []
  for (const id of projQty.keys()) {
    if (id === topId) continue
    // zz* reference items never reach the book — a stale quantity on one must not
    // block a publish (Documentation/38 §3.1)
    if (isReferenceOnlyItem(numOf.get(id) || '')) continue
    const expected = usage(id, new Set())
    if (expected === 0) continue // not reachable from the top assembly (manual attach, docs)
    const flat = projQty.get(id) || 0
    if (flat !== expected) {
      mismatches.push({
        item_number: numOf.get(id) || id,
        project_qty: flat,
        bom_rollup_qty: expected,
      })
    }
  }
  mismatches.sort((a, b) => a.item_number.localeCompare(b.item_number))
  return { ok: mismatches.length === 0, mismatches }
}

/** milestone day placement for the checklist, derived from the schedule */
function milestoneDays(
  schedule: ScheduleResult,
  workstations: MasterBookInputs['workstations'],
  asmItemIds: Set<string>
): Map<number, number> {
  const nameOf = new Map(workstations.map(w => [w.id, w.station_name]))
  const groupOfCode = new Map(workstations.map(w => [w.station_code, w.station_group || '']))
  const maxEnd = (pred: (t: ScheduleResult['tasks'][number]) => boolean): number | null => {
    const matching = schedule.tasks.filter(pred)
    return matching.length ? Math.max(...matching.map(t => t.end_day)) : null
  }
  const days = new Map<number, number>()
  days.set(10, -1) // order purchased BEFORE D1
  // M20 = purchased items received. Assembly routings can START with a
  // Receiving step (staging equipment onto the line, e.g. csa00080) — those
  // are build steps, not procurement, and must not drag M20 late.
  const m20 = maxEnd(t => nameOf.get(t.station_id) === 'Receiving' && !asmItemIds.has(t.item_id))
  const m30 = maxEnd(t => groupOfCode.get(t.station_code) === 'Fabrication')
  const m40 = maxEnd(t => groupOfCode.get(t.station_code) === 'Weld')
  const m50 = maxEnd(t => groupOfCode.get(t.station_code) === 'Assembly')
  const m60 = maxEnd(t => nameOf.get(t.station_id) === 'Inspection')
  if (m20 !== null) days.set(20, m20)
  if (m30 !== null) days.set(30, m30)
  if (m40 !== null) days.set(40, m40)
  if (m50 !== null) days.set(50, m50)
  if (m60 !== null) days.set(60, m60)
  days.set(70, schedule.total_days - 1)
  return days
}

// ============================================================================
// MAIN
// ============================================================================

export function masterDesignBook(rawInputs: MasterBookInputs): MasterDesignBook {
  const inp = canonicalize(rawInputs)

  // MASTER MODE: no dates (both — buildTracker back-derives start from due),
  // no completion data at all.
  const masterProject: TrackerProject = { ...inp.project, start_date: null, due_date: null }

  // Parts bought finished in a vendor bundle are received, inspected and staged —
  // not sawn. Synthesized per project; the global routing table is never touched.
  const sourced = applyKitSourcing({
    routing: inp.routing,
    routingMaterials: inp.routingMaterials,
    kitSources: inp.kitSources,
    workstations: inp.workstations,
    bom: inp.bom,
  })

  const schedule = calculateSchedule(
    inp.parts as unknown as PartData[],
    inp.bom as BomData[],
    sourced.routing as unknown as RoutingData[],
    []
  )

  const bookInputs: BookInputs = {
    project: masterProject,
    parts: inp.parts,
    bom: inp.bom,
    routing: sourced.routing,
    completion: [],
    workstations: inp.workstations,
    schedule,
    routingMaterials: sourced.routingMaterials,
    printItemIds: inp.printItemIds,
    kitSources: inp.kitSources,
    now: inp.now,
  }
  const book = buildBook(bookInputs)
  blankDoneFlags(book)

  const sections = masterSections(book, schedule, inp)
  const qtyCheck = checkQuantities(inp.project, inp.parts, inp.bom)

  const topPart = inp.parts.find(p => p.item_id === inp.project.top_assembly_id)
  const productNumber = topPart?.items?.item_number ?? ''
  const productName = topPart?.items?.name || topPart?.items?.description || productNumber

  return {
    meta: {
      product_item_number: productNumber,
      template_project_code: inp.project.project_code,
      title: `${(productName || 'Product').toUpperCase()} MASTER DESIGN BOOK`,
      day_count: schedule.total_days,
      generated_at: book.generatedAt,
    },
    book,
    sections,
    qtyCheck,
  }
}

// ============================================================================
// SECTION ENUMERATION
// ============================================================================

export function masterSections(
  book: BuildBook,
  schedule: ScheduleResult,
  inp: MasterBookInputs
): SectionDescriptor[] {
  const stationCodeOf = new Map(inp.workstations.map(w => [w.station_name, w.station_code]))
  const supplierNameOf = new Map(
    inp.parts.filter(p => p.items).map(p => [p.items!.item_number, p.items!.supplier_name ?? null])
  )

  // ---- section codes -------------------------------------------------------
  // Work packages: I-{ABBREV} — one section per station (all days consolidated).
  // Parts grouped by station, not by day — daily scheduling tracked externally.
  const pkgCode = new Map<string, string>() // BookPackage.id -> section code
  for (const p of book.packages) {
    pkgCode.set(p.id, `I-${p.stationAbbrev}`)
  }

  // Assemblies: II-{ITEM_NUMBER}; rid (A01) is a display ordinal only.
  const kitCode = new Map<string, string>() // rid -> section code
  for (const k of book.kits) kitCode.set(k.rid, `II-${k.item_number.toUpperCase()}`)
  const toKitCode = (rid: string) => kitCode.get(rid) ?? rid

  const sections: SectionDescriptor[] = []

  // ---- Section I: one descriptor per work package (one per station) ---------
  const bundleByNumber = new Map(book.bundles.map(b => [b.kit_number, b]))
  let sort = 100
  for (const p of book.packages) {
    const code = pkgCode.get(p.id)!
    const stationCode = stationCodeOf.get(p.stationName) ?? p.stationAbbrev
    const printItems: SectionPrintItem[] = []
    const noPrint: string[] = []
    const lines = p.lines.map(l => {
      const purchased = isPurchasedNumber(l.item_number)
      if (purchased) noPrint.push(l.item_number)
      else printItems.push({ item_number: l.item_number, qty: l.qty })
      return {
        item_number: l.item_number,
        displayNumber: l.displayNumber,
        name: l.name,
        qty: l.qty,
        estMin: l.estMin,
        next: l.next,
        feeds: l.feeds.map(toKitCode),
        // bundle wins over supplier: a bundled part is not separately purchased
        source:
          l.sourcedFrom ??
          (purchased ? purchasedSource(l.item_number, supplierNameOf.get(l.item_number)) : null),
      }
    })
    // bundles this package handles, with the count of lines it covers here — the
    // renderer prints a "VERIFY N PARTS AGAINST PRINTS ON RECEIPT" band from this
    const pkgBundles = bundlesIn(p.lines, bundleByNumber)
    sections.push({
      section_code: code,
      kind: 'work_package',
      title: p.stationName.toUpperCase(),
      sort_order: sort,
      identity: { station_code: stationCode },  // one section per station, no occurrence
      // No day field - scheduling tracked externally on tracking sheet
      display: null,
      payload: {
        stationName: p.stationName,
        stationAbbrev: p.stationAbbrev,
        estMin: p.estMin,
        lines,
        stockPull: p.stockPull,
        stageFor: p.stageFor.map(toKitCode),
        // only present when this package handles a bundle — a section with no bundle
        // keeps its exact payload shape, so it does not rev just because the feature
        // was added (no phantom "TABLE DATA REVISED")
        ...(pkgBundles.length ? { bundles: pkgBundles } : {}),
      },
      print_items: printItems,
      no_print_expected: noPrint,
    })
    sort += 10
  }

  // ---- Section II: one descriptor per assembly kit ---------------------------
  // wide gap: package range (100 + 10n) must never collide with kits
  sort = 5000
  for (const k of book.kits) {
    const code = kitCode.get(k.rid)!
    const printItems: SectionPrintItem[] = [{ item_number: k.item_number, qty: k.qty }]
    const noPrint: string[] = []
    const parts = k.parts.map((pt, i) => {
      const purchased = isPurchasedNumber(pt.item_number)
      if (purchased) noPrint.push(pt.item_number)
      else printItems.push({ item_number: pt.item_number, qty: pt.qty })
      return {
        // kit-LOCAL row id: the tracker's F## ids are a global sequence that
        // renumbers across the whole book on any BOM edit — churn.
        rid: `P${String(i + 1).padStart(2, '0')}`,
        item_number: pt.item_number,
        displayNumber: purchased
          ? book.purchased.find(r => r.item_number === pt.item_number)?.displayNumber ?? pt.item_number
          : pt.item_number,
        name: pt.name,
        qty: pt.qty,
        readyBy: pt.readyBy ? pkgCode.get(pt.readyBy) ?? null : null,
        readyDay: pt.readyDay,
        // bundle wins over supplier: a bundled part is not separately purchased
        source:
          pt.sourcedFrom ??
          (purchased ? purchasedSource(pt.item_number, supplierNameOf.get(pt.item_number)) : null),
      }
    })
    sections.push({
      section_code: code,
      kind: 'assembly',
      title: `${k.name.toUpperCase()} -- ${k.item_number.toUpperCase()}`,
      sort_order: sort,
      identity: { item_number: k.item_number },
      // NOTE: the DFS rid (A01) is deliberately NOT here — it reshuffles on any
      // BOM edit and is never printed on kit pages; hashing it would phantom-rev
      // every assembly booklet (adversarial review finding M1)
      display: { startDay: k.startDay, endDay: k.endDay },
      payload: {
        item_number: k.item_number,
        name: k.name,
        qty: k.qty,
        estMin: k.estMin,
        parts,
        weldSeq: k.weldSeq.map(s => ({
          station: s.station,
          abbrev: s.abbrev,
          estMin: s.estMin,
          day: s.day,
          notes: s.notes,
        })),
        childAsms: k.childAsms.map(c => ({
          code: toKitCode(c.rid),
          item_number: c.item_number,
          name: c.name,
        })),
      },
      print_items: printItems,
      no_print_expected: noPrint,
    })
    sort += 10
  }

  // ---- II-REF: controlled design reference documents -------------------------
  sections.push({
    section_code: 'II-REF',
    kind: 'design_reference',
    title: 'DESIGN REFERENCE',
    sort_order: 9000,
    identity: { singleton: 'design_reference' },
    display: null,
    payload: {
      docs: book.referenceDocs.map(d => ({
        item_number: d.item_number,
        name: d.name,
        revision: d.revision,
      })),
    },
    print_items: book.referenceDocs.map(d => ({ item_number: d.item_number, qty: null })),
    no_print_expected: [],
  })

  // ---- III-00: general reference blank template -------------------------------
  sections.push({
    section_code: 'III-00',
    kind: 'general_reference',
    title: 'GENERAL REFERENCE',
    sort_order: 9500,
    identity: { singleton: 'general_reference', index: 0 },
    display: null,
    payload: { template_version: 1, notesPages: 6, photoPages: 4 },
    print_items: [],
    no_print_expected: [],
  })

  // ---- 00-SPINE (built last: its payload embeds the checklist + buy list; the
  // backend adds the final section rev map before hashing — two-phase spine) ----
  const checklist = buildChecklist(book, schedule, inp, pkgCode, kitCode)
  sections.unshift({
    section_code: '00-SPINE',
    kind: 'spine',
    title: 'CHECKLIST + BUY LIST + TOC',
    sort_order: 0,
    identity: { singleton: 'spine' },
    display: null,
    payload: {
      summary: book.summary,
      milestones: book.milestones.map(m => ({ op: m.op, title: m.title })),
      checklist: checklist.map(r => ({ ...r })),
      // vendor bundles are ordered as one line item — never priced on shop paper.
      // Present only when the book has bundles (see note on package payload above).
      ...(book.bundles.length
        ? {
            bundles: book.bundles.map(b => ({
              kit_number: b.kit_number,
              kit_name: b.kit_name,
              vendor: b.vendor,
              partCount: b.partCount,
            })),
          }
        : {}),
      buyList: book.purchased.map(r => ({
        item_number: r.item_number, // internal key — never printed
        displayNumber: r.displayNumber,
        source: r.source,
        name: r.name,
        qty: r.qty,
        longLead: r.longLead,
      })),
      stock: book.stock,
    },
    print_items: [],
    no_print_expected: [],
  })

  return sections
}

// ============================================================================
// SPINE CHECKLIST — packages + kit steps + milestones, day-ordered
// ============================================================================

function buildChecklist(
  book: BuildBook,
  schedule: ScheduleResult,
  inp: MasterBookInputs,
  pkgCode: Map<string, string>,
  kitCode: Map<string, string>
): ChecklistRow[] {
  const purchasedNums = new Set(book.purchased.map(r => r.item_number))
  const rows: ChecklistRow[] = []

  for (const p of book.packages) {
    const allPurchased = p.lines.length > 0 && p.lines.every(l => purchasedNums.has(l.item_number))
    const bundled = p.lines.filter(l => l.sourcedFrom).length
    let text: string
    if (allPurchased) {
      text = `Work package - receive ${p.lines.length} purchased items`
    } else if (bundled > 0) {
      text = `Work package - ${p.stationName.toLowerCase()} ${p.lines.length} parts (${bundled} bundled)`
    } else {
      text = `Work package - ${p.stationName.toLowerCase()} ${p.lines.length} parts`
    }
    rows.push({
      kind: 'package',
      day: p.day,
      stn: p.stationAbbrev,
      text,
      estH: round1(p.estMin / 60),
      see: pkgCode.get(p.id)!,
      op: null,
    })
  }

  for (const k of book.kits) {
    k.weldSeq.forEach((s, i) => {
      if (s.day === null) return
      rows.push({
        kind: 'kit_step',
        day: s.day,
        stn: s.abbrev,
        text: `${k.name.toUpperCase()} - step ${(i + 1) * 10} ${s.station.toLowerCase()}`,
        estH: round1(s.estMin / 60),
        see: kitCode.get(k.rid)!,
        op: null,
      })
    })
  }

  const itemIdOf = new Map(
    inp.parts.filter(p => p.items).map(p => [p.items!.item_number, p.item_id])
  )
  const asmItemIds = new Set(
    book.kits.map(k => itemIdOf.get(k.item_number)).filter((id): id is string => !!id)
  )
  const msDays = milestoneDays(schedule, inp.workstations, asmItemIds)
  for (const m of book.milestones) {
    const day = msDays.get(m.op)
    if (day === undefined) continue
    rows.push({
      kind: 'milestone',
      day,
      stn: null,
      text: m.title,
      estH: null,
      see: null,
      op: m.op,
    })
  }

  // day ascending; within a day: ops first, then the milestone band that closes
  // the day; deterministic tie-breaks on see-code then text.
  rows.sort(
    (a, b) =>
      a.day - b.day ||
      (a.kind === 'milestone' ? 1 : 0) - (b.kind === 'milestone' ? 1 : 0) ||
      (a.op ?? 0) - (b.op ?? 0) ||
      (a.see ?? '').localeCompare(b.see ?? '') ||
      a.text.localeCompare(b.text)
  )
  return rows
}
