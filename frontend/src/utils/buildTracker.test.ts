import { describe, it, expect } from 'vitest'
import { buildTrackerSheet, PART_COLUMNS, type TrackerInputs } from './buildTracker'
import { calculateSchedule, type PartData, type BomData, type RoutingData } from './scheduling'

// ---------------------------------------------------------------------------
// Fixture: miniature spa-like project
//
//   csa10 FINISHED ASSY (top)
//   ├── csa20 FRAME WELDMENT
//   │   ├── csa30 LOWER FRAME
//   │   │   ├── csp01 TUBE (x2)
//   │   │   └── csp05 POST (x1)   <- also used directly on csa20 (duplicate row)
//   │   ├── csp05 POST (x1)
//   │   ├── csp21 CABINET FLOOR (x1)
//   │   └── cspro ELEC BOX (x1, receive-only routing -> purchased)
//   ├── csp63 LATCH BAR (x1)
//   ├── mmc1 WASHER (x4, purchased)
//   ├── spn1 PUMP (x1, purchased long-lead)
//   └── zzz1 REF ITEM (x2, excluded)
// ---------------------------------------------------------------------------

const WS = [
  { id: 's-rcv', station_code: '005', station_name: 'Receiving', station_group: 'QC' },
  { id: 's-saw', station_code: '010', station_name: 'Saw', station_group: 'Fabrication' },
  { id: 's-dbr', station_code: '011', station_name: 'Deburr', station_group: 'Fabrication' },
  { id: 's-wj', station_code: '012', station_name: 'Waterjet', station_group: 'Fabrication' },
  { id: 's-brk', station_code: '013', station_name: 'Press Brake', station_group: 'Fabrication' },
  { id: 's-jig', station_code: '014', station_name: 'Weld Jigging', station_group: 'Weld' },
  { id: 's-tig', station_code: '015', station_name: 'Tig Welding', station_group: 'Weld' },
  { id: 's-wcu', station_code: '017', station_name: 'Weld Cleanup', station_group: 'Weld' },
  { id: 's-stg', station_code: '020', station_name: 'Part Staging', station_group: 'Assembly' },
  { id: 's-asm', station_code: '025', station_name: 'Mechanical Assembly', station_group: 'Assembly' },
  { id: 's-ins', station_code: '050', station_name: 'Inspection', station_group: 'QC' },
]
const wsByName = new Map(WS.map(w => [w.station_name, w]))

function item(
  id: string,
  num: string,
  name: string,
  supplier_pn: string | null = null,
  supplier_name: string | null = null
) {
  return { id, item_number: num, name, description: null, thickness: null, material: null, supplier_pn, supplier_name }
}

const ITEMS = {
  csa10: item('i-csa10', 'csa00010', 'FINISHED ASSY'),
  csa20: item('i-csa20', 'csa00020', 'FRAME WELDMENT'),
  csa30: item('i-csa30', 'csa00030', 'LOWER FRAME'),
  csp01: item('i-csp01', 'csp00010', 'TUBE'),
  csp05: item('i-csp05', 'csp00050', 'POST'),
  csp21: item('i-csp21', 'csp00210', 'CABINET FLOOR'),
  csp63: item('i-csp63', 'csp00630', 'LATCH BAR'),
  cspro: item('i-cspro', 'csp00230', 'ELEC BOX'),
  mmc1: item('i-mmc1', 'mmc90098a036', 'WASHER', '90098A036', 'McMaster-Carr'),
  spn1: item('i-spn1', 'spntank', 'PUMP'),
  zzz1: item('i-zzz1', 'zzz1071a59a', 'REF ITEM'),
  csd1: { ...item('i-csd1', 'csd00010', 'SPA BUILD DESIGN BOOK'), revision: 'B' },
}

const parts = [
  { item_id: ITEMS.csa10.id, quantity: 1, items: ITEMS.csa10 },
  { item_id: ITEMS.csa20.id, quantity: 1, items: ITEMS.csa20 },
  { item_id: ITEMS.csa30.id, quantity: 1, items: ITEMS.csa30 },
  { item_id: ITEMS.csp01.id, quantity: 2, items: ITEMS.csp01 },
  { item_id: ITEMS.csp05.id, quantity: 2, items: ITEMS.csp05 },
  { item_id: ITEMS.csp21.id, quantity: 1, items: ITEMS.csp21 },
  { item_id: ITEMS.csp63.id, quantity: 1, items: ITEMS.csp63 },
  { item_id: ITEMS.cspro.id, quantity: 1, items: ITEMS.cspro },
  { item_id: ITEMS.mmc1.id, quantity: 4, items: ITEMS.mmc1 },
  { item_id: ITEMS.spn1.id, quantity: 1, items: ITEMS.spn1 },
  { item_id: ITEMS.zzz1.id, quantity: 2, items: ITEMS.zzz1 },
  { item_id: ITEMS.csd1.id, quantity: 1, items: ITEMS.csd1 },
]

const bom = [
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.csd1.id, quantity: 1 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.csa20.id, quantity: 1 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.csp63.id, quantity: 1 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.mmc1.id, quantity: 4 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.spn1.id, quantity: 1 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.zzz1.id, quantity: 2 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.csa30.id, quantity: 1 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.csp05.id, quantity: 1 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.csp21.id, quantity: 1 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.cspro.id, quantity: 1 },
  { parent_item_id: ITEMS.csa30.id, child_item_id: ITEMS.csp01.id, quantity: 2 },
  { parent_item_id: ITEMS.csa30.id, child_item_id: ITEMS.csp05.id, quantity: 1 },
]

let routingId = 0
function ops(itemId: string, stationNames: string[]) {
  return stationNames.map((nm, i) => {
    const ws = wsByName.get(nm)!
    return {
      id: `r-${++routingId}`,
      item_id: itemId,
      station_id: ws.id,
      sequence: (i + 1) * 10,
      est_time_min: 10,
      workstations: { station_code: ws.station_code, station_name: ws.station_name },
    }
  })
}

const routing = [
  ...ops(ITEMS.csp01.id, ['Saw', 'Deburr', 'Inspection']),
  ...ops(ITEMS.csp05.id, ['Saw', 'Deburr', 'Inspection']),
  ...ops(ITEMS.csp21.id, ['Waterjet', 'Press Brake', 'Deburr', 'Inspection']),
  ...ops(ITEMS.csp63.id, ['Waterjet', 'Deburr', 'Inspection']),
  ...ops(ITEMS.csa30.id, ['Weld Jigging', 'Tig Welding', 'Weld Cleanup', 'Inspection']),
  ...ops(ITEMS.csa20.id, ['Weld Jigging', 'Tig Welding', 'Weld Cleanup', 'Inspection']),
  ...ops(ITEMS.csa10.id, ['Mechanical Assembly', 'Inspection']),
  ...ops(ITEMS.cspro.id, ['Receiving']),
  ...ops(ITEMS.mmc1.id, ['Receiving']),
  ...ops(ITEMS.spn1.id, ['Receiving']),
]

const completion = [
  // csp01: Saw fully done (qty 2 of 2), Deburr partial (1 of 2)
  { item_id: ITEMS.csp01.id, station_id: 's-saw', qty_complete: 2, completed_at: '2026-07-01T18:00:00Z' },
  { item_id: ITEMS.csp01.id, station_id: 's-dbr', qty_complete: 1, completed_at: '2026-07-02T18:00:00Z' },
  // csp05: Saw partial (1 of 2) — allocated to the first duplicate row only
  { item_id: ITEMS.csp05.id, station_id: 's-saw', qty_complete: 1, completed_at: '2026-07-02T18:00:00Z' },
  // csa30: jigging recorded complete
  { item_id: ITEMS.csa30.id, station_id: 's-jig', qty_complete: 1, completed_at: '2026-07-03T18:00:00Z' },
  // mmc1 received in full
  { item_id: ITEMS.mmc1.id, station_id: 's-rcv', qty_complete: 4, completed_at: '2026-06-28T18:00:00Z' },
]

function makeInputs(withSchedule = true): TrackerInputs {
  const schedule = withSchedule
    ? calculateSchedule(
        parts as unknown as PartData[],
        bom as BomData[],
        routing as unknown as RoutingData[],
        completion.map(c => ({ item_id: c.item_id, station_id: c.station_id }))
      )
    : null
  return {
    project: {
      id: 'p-1',
      project_code: 'TEST-MINI',
      description: 'Mini Spa',
      customer: 'MWES',
      due_date: '2026-08-01',
      start_date: null,
      top_assembly_id: ITEMS.csa10.id,
    },
    parts,
    bom,
    routing,
    completion,
    workstations: WS,
    schedule,
    now: new Date('2026-07-05T12:00:00'),
  }
}

// ---------------------------------------------------------------------------

describe('buildTrackerSheet', () => {
  const sheet = buildTrackerSheet(makeInputs())

  it('orders assemblies deepest-first (DFS post-order from top assembly)', () => {
    expect(sheet.asmRows.map(a => a.item_number)).toEqual(['csa00030', 'csa00020', 'csa00010'])
    expect(sheet.asmRows.map(a => a.rid)).toEqual(['A01', 'A02', 'A03'])
  })

  it('groups made parts under their parent assembly, excluding purchased and reference items', () => {
    const allGroups = sheet.pages.flatMap(p => [...p.colA, ...p.colB])
    const byRef = new Map(allGroups.map(g => [g.ref, g]))
    expect(byRef.get('A01')!.rows.map(r => r.item_number)).toEqual(['csp00010', 'csp00050'])
    // csa20's group: made children only (csp05 duplicate + csp21; ELEC BOX is receive-only -> purchased)
    expect(byRef.get('A02')!.rows.map(r => r.item_number)).toEqual(['csp00050', 'csp00210'])
    expect(byRef.get('A03')!.rows.map(r => r.item_number)).toEqual(['csp00630'])
    // no zzz anywhere
    for (const g of allGroups) {
      expect(g.rows.every(r => !r.item_number.startsWith('zzz'))).toBe(true)
    }
  })

  it('assigns sequential F row ids across groups', () => {
    const rows = sheet.pages.flatMap(p => [...p.colA, ...p.colB]).flatMap(g => g.rows)
    expect(rows.map(r => r.rid)).toEqual(['F01', 'F02', 'F03', 'F04', 'F05'])
  })

  it('marks station boxes from part_completion (done / partial / open / n-a)', () => {
    const rows = sheet.pages.flatMap(p => [...p.colA, ...p.colB]).flatMap(g => g.rows)
    const csp01 = rows.find(r => r.item_number === 'csp00010')!
    const col = (key: string) => PART_COLUMNS.findIndex(c => c.key === key)
    expect(csp01.boxes[col('SAW')]!.done).toBe(true)
    expect(csp01.boxes[col('DBR')]!.done).toBe(false)
    expect(csp01.boxes[col('DBR')]!.partial).toBe(1)
    expect(csp01.boxes[col('INS')]!.done).toBe(false)
    expect(csp01.boxes[col('WJ')]!.applicable).toBe(false)
    // STG is always an open box on made parts even when not routed
    expect(csp01.boxes[col('STG')]!.applicable).toBe(true)
    expect(csp01.boxes[col('STG')]!.done).toBe(false)
  })

  it('allocates partial quantity to duplicate rows in order', () => {
    const rows = sheet.pages.flatMap(p => [...p.colA, ...p.colB]).flatMap(g => g.rows)
    const dupes = rows.filter(r => r.item_number === 'csp00050')
    expect(dupes).toHaveLength(2)
    const saw = PART_COLUMNS.findIndex(c => c.key === 'SAW')
    // 1 of 2 sawed: first row (qty 1) shows done, second row shows nothing yet
    expect(dupes[0]!.boxes[saw]!.done).toBe(true)
    expect(dupes[1]!.boxes[saw]!.done).toBe(false)
    expect(dupes[1]!.boxes[saw]!.partial).toBeNull()
  })

  it('classifies purchased items and pre-fills received state', () => {
    const nums = sheet.purchased.map(p => p.item_number)
    expect(nums).toContain('mmc90098a036')
    expect(nums).toContain('spntank')
    expect(nums).toContain('csp00230') // receive-only routing
    expect(nums.every(n => !n.startsWith('zzz'))).toBe(true)
    const mmc = sheet.purchased.find(p => p.item_number === 'mmc90098a036')!
    expect(mmc.longLead).toBe(false)
    expect(mmc.rcvDone).toBe(true)
    const pump = sheet.purchased.find(p => p.item_number === 'spntank')!
    expect(pump.longLead).toBe(true)
    expect(pump.rcvDone).toBe(false)
  })

  it('excludes document items (third-letter d) from all work rows', () => {
    const rows = sheet.pages.flatMap(p => [...p.colA, ...p.colB]).flatMap(g => g.rows)
    expect(rows.every(r => r.item_number !== 'csd00010')).toBe(true)
    expect(sheet.purchased.every(p => p.item_number !== 'csd00010')).toBe(true)
    expect(sheet.asmRows.every(a => a.item_number !== 'csd00010')).toBe(true)
    expect(sheet.fabTotal).toBe(5) // unchanged by the document item
  })

  it('shows shop-facing part numbers for purchased items (PDM prefixes dropped)', () => {
    const mmc = sheet.purchased.find(p => p.item_number === 'mmc90098a036')!
    expect(mmc.displayNumber).toBe('90098A036') // supplier_pn preferred
    expect(mmc.source).toBe('McMaster-Carr')
    const pump = sheet.purchased.find(p => p.item_number === 'spntank')!
    expect(pump.displayNumber).toBe('TANK') // prefix stripped + uppercased fallback
    expect(pump.source).toBe('Supplier')
    const shopItem = sheet.purchased.find(p => p.item_number === 'csp00230')!
    expect(shopItem.displayNumber).toBe('csp00230') // internal numbers untouched
  })

  it('pre-fills the assembly matrix from completion', () => {
    const a01 = sheet.asmRows.find(a => a.item_number === 'csa00030')!
    const jig = a01.boxes.findIndex((_, i) => i === 0) // JIG is first column
    expect(a01.boxes[jig]!.done).toBe(true)
    expect(a01.boxes[1]!.done).toBe(false) // TIG not recorded
    // csa10 has no weld routing: JIG not applicable, ASM applicable
    const a03 = sheet.asmRows.find(a => a.item_number === 'csa00010')!
    expect(a03.boxes[0]!.applicable).toBe(false)
    expect(a03.boxes[4]!.applicable).toBe(true)
  })

  it('computes header stats and overall percent', () => {
    expect(sheet.fabTotal).toBe(5)
    expect(sheet.fabDone).toBe(0) // nothing fully through routing yet
    expect(sheet.asmTotal).toBe(3)
    expect(sheet.asmDone).toBe(0)
    expect(sheet.pctComplete).toBeGreaterThan(0)
    expect(sheet.pctComplete).toBeLessThan(100)
  })

  it('derives the 7 standard milestones with plan dates from the schedule', () => {
    expect(sheet.milestones).toHaveLength(7)
    expect(sheet.milestones.map(m => m.op)).toEqual([10, 20, 30, 40, 50, 60, 70])
    const m30 = sheet.milestones.find(m => m.rid === 'M30')!
    expect(m30.gate).toBe(true)
    expect(m30.plan).not.toBe('')
    const m70 = sheet.milestones.find(m => m.rid === 'M70')!
    expect(m70.plan).toBe('AUG 1')
  })

  it('fits a small project on a single page', () => {
    expect(sheet.pages).toHaveLength(1)
    expect(sheet.pages[0]!.showRail).toBe(true)
  })

  it('still works without a schedule (blank plan dates)', () => {
    const noSched = buildTrackerSheet(makeInputs(false))
    expect(noSched.milestones).toHaveLength(7)
    const m30 = noSched.milestones.find(m => m.rid === 'M30')!
    expect(m30.plan).toBe('')
    expect(noSched.fabTotal).toBe(5)
  })
})

describe('buildTrackerSheet — letter format', () => {
  const letter = buildTrackerSheet({ ...makeInputs(), format: 'letter' })

  it('adds a dedicated status page after the parts pages', () => {
    expect(letter.format).toBe('letter')
    const last = letter.pages[letter.pages.length - 1]!
    expect(last.showRail).toBe(true)
    expect(last.colA).toHaveLength(0)
    expect(last.colB).toHaveLength(0)
    for (const p of letter.pages.slice(0, -1)) {
      expect(p.showRail).toBe(false)
    }
  })

  it('keeps identical content across formats (rows, stats, milestones)', () => {
    const tabloid = buildTrackerSheet(makeInputs())
    const rowsOf = (s: typeof letter) =>
      s.pages.flatMap(p => [...p.colA, ...p.colB]).flatMap(g => g.rows.map(r => r.item_number + ':' + r.qty))
    expect(rowsOf(letter)).toEqual(rowsOf(tabloid))
    expect(letter.fabTotal).toBe(tabloid.fabTotal)
    expect(letter.pctComplete).toBe(tabloid.pctComplete)
    expect(letter.milestones).toEqual(tabloid.milestones)
  })

  it('respects the letter per-column row budget', () => {
    for (const p of letter.pages) {
      for (const col of [p.colA, p.colB]) {
        const units = col.reduce((n, g) => n + g.rows.length + 1, 0)
        expect(units).toBeLessThanOrEqual(32)
      }
    }
  })

  it('paginates a large project across multiple letter pages', () => {
    // inflate the fixture: 90 copies of a made part under one weldment
    const inp = makeInputs(false)
    const bigParts = [...inp.parts]
    const bigBom = [...inp.bom]
    const bigRouting = [...inp.routing]
    for (let i = 0; i < 90; i++) {
      const id = `i-bulk${i}`
      bigParts.push({
        item_id: id,
        quantity: 1,
        items: { id, item_number: `csp9${String(i).padStart(3, '0')}`, name: 'BULK PART', description: null, thickness: null, material: null },
      })
      bigBom.push({ parent_item_id: 'i-csa30', child_item_id: id, quantity: 1 })
      bigRouting.push({
        id: `r-bulk${i}`,
        item_id: id,
        station_id: 's-saw',
        sequence: 10,
        est_time_min: 5,
        workstations: { station_code: '010', station_name: 'Saw' },
      } as any)
    }
    const big = buildTrackerSheet({ ...inp, parts: bigParts, bom: bigBom, routing: bigRouting, format: 'letter' })
    expect(big.pages.length).toBeGreaterThan(2)
    const last = big.pages[big.pages.length - 1]!
    expect(last.showRail).toBe(true)
    // continuation chunks of a split group are flagged
    const conts = big.pages.flatMap(p => [...p.colA, ...p.colB]).filter(g => g.cont)
    expect(conts.length).toBeGreaterThan(0)
    // every row appears exactly once
    const rids = big.pages.flatMap(p => [...p.colA, ...p.colB]).flatMap(g => g.rows.map(r => r.rid))
    expect(new Set(rids).size).toBe(rids.length)
    expect(rids.length).toBe(big.fabTotal)
  })
})
