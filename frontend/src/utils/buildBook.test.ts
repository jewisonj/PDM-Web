import { describe, it, expect } from 'vitest'
import { buildBook, type BookInputs } from './buildBook'
import { calculateSchedule, type PartData, type BomData, type RoutingData } from './scheduling'

// Mini spa-like fixture (same shape as buildTracker.test.ts):
//   csa10 FINISHED ASSY -> csa20 FRAME WELDMENT -> csa30 LOWER FRAME
//   parts csp01 (tube x2), csp05 (post, used in csa30 AND csa20), csp21 (floor),
//   csp63 (latch bar), cspro (receive-only), mmc1/spn1 purchased, zzz1 reference.

const WS = [
  { id: 's-rcv', station_code: '005', station_name: 'Receiving', station_group: 'QC', sort_order: 5 },
  { id: 's-saw', station_code: '010', station_name: 'Saw', station_group: 'Fabrication', sort_order: 10 },
  { id: 's-dbr', station_code: '011', station_name: 'Deburr', station_group: 'Fabrication', sort_order: 12 },
  { id: 's-wj', station_code: '012', station_name: 'Waterjet', station_group: 'Fabrication', sort_order: 11 },
  { id: 's-brk', station_code: '013', station_name: 'Press Brake', station_group: 'Fabrication', sort_order: 13 },
  { id: 's-jig', station_code: '014', station_name: 'Weld Jigging', station_group: 'Weld', sort_order: 14 },
  { id: 's-tig', station_code: '015', station_name: 'Tig Welding', station_group: 'Weld', sort_order: 15 },
  { id: 's-wcu', station_code: '017', station_name: 'Weld Cleanup', station_group: 'Weld', sort_order: 17 },
  { id: 's-asm', station_code: '025', station_name: 'Mechanical Assembly', station_group: 'Assembly', sort_order: 25 },
  { id: 's-ins', station_code: '050', station_name: 'Inspection', station_group: 'QC', sort_order: 50 },
]
const wsByName = new Map(WS.map(w => [w.station_name, w]))

function item(id: string, num: string, name: string) {
  return { id, item_number: num, name, description: null, thickness: null, material: null }
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
  mmc1: { ...item('i-mmc1', 'mmc90098a036', 'WASHER'), supplier_pn: '90098A036', supplier_name: 'McMaster-Carr' },
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

// assembly-method note on the frame weldment's jigging step (rendered in the kit sheet)
;(routing.find(r => r.item_id === ITEMS.csa20.id && r.station_id === 's-jig') as any).notes =
  'Set TANK WALL at distance from edge; FLOOR SUB against it sets wall spacing; then MECH WALL'

const completion = [
  { item_id: ITEMS.csp01.id, station_id: 's-saw', qty_complete: 2, completed_at: '2026-07-01T18:00:00Z' },
  { item_id: ITEMS.csp05.id, station_id: 's-saw', qty_complete: 1, completed_at: '2026-07-02T18:00:00Z' },
  { item_id: ITEMS.mmc1.id, station_id: 's-rcv', qty_complete: 4, completed_at: '2026-06-28T18:00:00Z' },
]

const routingMaterials = [
  { item_id: ITEMS.csp01.id, qty_required: 24, raw_materials: { description: '2x2x0.125 SS Square Tube', material_code: 'SS' } },
  { item_id: ITEMS.csp05.id, qty_required: 36, raw_materials: { description: '2x2x0.125 SS Square Tube', material_code: 'SS' } },
  { item_id: ITEMS.csp21.id, qty_required: 100, raw_materials: { description: '0.078" SS Sheet', material_code: 'SS' } },
]

function makeInputs(): BookInputs {
  const schedule = calculateSchedule(
    parts as unknown as PartData[],
    bom as BomData[],
    routing as unknown as RoutingData[],
    completion.map(c => ({ item_id: c.item_id, station_id: c.station_id }))
  )
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
    routingMaterials,
    printItemIds: [ITEMS.csa30.id, ITEMS.csp01.id, ITEMS.csp21.id, ITEMS.csd1.id],
    now: new Date('2026-07-05T12:00:00'),
  }
}

describe('buildBook', () => {
  const book = buildBook(makeInputs())

  it('creates sequenced packages ordered by day then station', () => {
    expect(book.packages.length).toBeGreaterThan(3)
    expect(book.packages.map(p => p.id)).toEqual(
      book.packages.map((_, i) => `PKG ${String(i + 1).padStart(2, '0')}`)
    )
    for (let i = 1; i < book.packages.length; i++) {
      expect(book.packages[i]!.day).toBeGreaterThanOrEqual(book.packages[i - 1]!.day)
    }
    // day 0 fires receiving + first cuts
    expect(book.packages[0]!.day).toBe(0)
  })

  it('excludes assembly weld tasks from packages (they live in kits)', () => {
    const allLineNums = book.packages.flatMap(p => p.lines.map(l => l.item_number))
    expect(allLineNums.every(n => !n.startsWith('csa'))).toBe(true)
  })

  it('builds a receiving package containing purchased items', () => {
    const rcv = book.packages.find(p => p.stationAbbrev === 'RCV')!
    expect(rcv).toBeDefined()
    const nums = rcv.lines.map(l => l.item_number)
    expect(nums).toContain('mmc90098a036')
    expect(nums).toContain('spntank')
    expect(nums).toContain('csp00230')
    // shop-facing numbers drop the PDM prefixes
    expect(rcv.lines.find(l => l.item_number === 'mmc90098a036')!.displayNumber).toBe('90098A036')
    expect(rcv.lines.find(l => l.item_number === 'spntank')!.displayNumber).toBe('TANK')
    expect(rcv.lines.find(l => l.item_number === 'csp00230')!.displayNumber).toBe('csp00230')
  })

  it('gives lines a next PRIMARY station and assembly feeds', () => {
    const saw = book.packages.find(p => p.stationAbbrev === 'SAW' && p.lines.some(l => l.item_number === 'csp00010'))!
    const tube = saw.lines.find(l => l.item_number === 'csp00010')!
    // Saw > Deburr > Inspection: deburr/inspection fold into the saw op, so saw is the last primary
    expect(tube.next).toBeNull()
    expect(tube.feeds).toEqual(['A01']) // csa30 = A01 (deepest first)
    expect(saw.stageFor).toContain('A01')
    const post = saw.lines.find(l => l.item_number === 'csp00050')
    if (post) expect(post.feeds.sort()).toEqual(['A01', 'A02'])
    // Waterjet > Press Brake > Deburr > Inspection: WJ's next primary is the brake
    const wj = book.packages.find(p => p.stationAbbrev === 'WJ' && p.lines.some(l => l.item_number === 'csp00210'))!
    expect(wj.lines.find(l => l.item_number === 'csp00210')!.next).toBe('PB')
  })

  it('creates no packages for secondary operations (deburr/inspection)', () => {
    expect(book.packages.every(p => !['DBR', 'INS'].includes(p.stationAbbrev))).toBe(true)
  })

  it('aggregates stock pulls at the first operation only', () => {
    const withStock = book.packages.filter(p => p.stockPull.length > 0)
    expect(withStock.length).toBeGreaterThan(0)
    const allPulls = withStock.flatMap(p => p.stockPull)
    const tube = allPulls.filter(s => s.description === '2x2x0.125 SS Square Tube')
    // csp01: 24 x qty2 = 48, csp05: 36 x qty2 = 72 -> total 120 across saw package(s)
    expect(tube.reduce((n, s) => n + s.qty, 0)).toBe(120)
    // stock pulls only appear on first-op packages
    for (const p of book.packages.filter(p => p.stationAbbrev === 'PB')) {
      expect(p.stockPull).toHaveLength(0)
    }
  })

  it('marks stage-for kits on final-op packages', () => {
    const lastOpPkgs = book.packages.filter(p => p.stageFor.length > 0)
    expect(lastOpPkgs.length).toBeGreaterThan(0)
    const staged = new Set(lastOpPkgs.flatMap(p => p.stageFor))
    expect(staged.has('A01')).toBe(true)
  })

  it('builds kit chapters in assembly build order with weld sequences', () => {
    expect(book.kits.map(k => k.item_number)).toEqual(['csa00030', 'csa00020', 'csa00010'])
    const a01 = book.kits[0]!
    expect(a01.weldSeq.map(s => s.abbrev)).toEqual(['JIG', 'TIG', 'WCU', 'INS'])
    expect(a01.estMin).toBe(40)
    expect(a01.parts.map(p => p.item_number)).toEqual(['csp00010', 'csp00050'])
    // every kit part knows which package produces it
    for (const p of a01.parts) {
      expect(p.readyBy).toMatch(/^PKG \d+/)
    }
    // weldment starts after its parts are producible
    const maxReady = Math.max(...a01.parts.map(p => p.readyDay ?? 0))
    expect(a01.startDay!).toBeGreaterThan(maxReady - 1)
  })

  it('carries routing step notes into kit weld sequences', () => {
    const frame = book.kits.find(k => k.item_number === 'csa00020')!
    expect(frame.weldSeq[0]!.notes).toContain('TANK WALL')
    expect(frame.weldSeq[1]!.notes).toBeNull()
    const lower = book.kits.find(k => k.item_number === 'csa00030')!
    expect(lower.weldSeq.every(s => s.notes === null)).toBe(true)
  })

  it('tracks print availability per kit', () => {
    const a01 = book.kits[0]!
    expect(a01.hasPrint).toBe(true) // csa30 in printItemIds
    expect(a01.partPrints).toBe(1)  // csp01 only
    const a03 = book.kits[2]!
    expect(a03.hasPrint).toBe(false)
  })

  it('lists pull-print references (drawing # + rev) per kit', () => {
    const a01 = book.kits[0]!
    expect(a01.printRefs.map(r => r.item_number)).toEqual(['csa00030', 'csp00010'])
    // csa20 has no assembly print; csp21 (its child) does
    const a02 = book.kits[1]!
    expect(a02.printRefs.map(r => r.item_number)).toEqual(['csp00210'])
  })

  it('builds a calendar whose hours match the scheduler station-days', () => {
    expect(book.calendar.stations.length).toBeGreaterThan(3)
    const saw = book.calendar.stations.findIndex(s => s.abbrev === 'SAW')
    const day0 = book.calendar.days.find(d => d.day === 0)!
    const sawCell = day0.cells[saw]
    expect(sawCell).not.toBeNull()
    // csp01 (10min x2) + csp05 (10min x2) = 40 min = 0.7h
    expect(sawCell!.hours).toBeCloseTo(0.7, 1)
    expect(sawCell!.pkgs.length).toBeGreaterThan(0)
  })

  it('summarizes stock and hours', () => {
    const tube = book.stock.find(s => s.description === '2x2x0.125 SS Square Tube')!
    expect(tube.qty).toBe(120)
    expect(tube.parts).toBe(2)
    expect(book.summary.totalHours).toBeGreaterThan(0)
    expect(book.summary.packageCount).toBe(book.packages.length)
    expect(book.summary.byGroup.map(g => g.group)).toContain('Fabrication')
    expect(book.milestones).toHaveLength(7)
  })

  it('lists document items as reference prints, never as work rows', () => {
    expect(book.referenceDocs).toHaveLength(1)
    const doc = book.referenceDocs[0]!
    expect(doc.item_number).toBe('csd00010')
    expect(doc.revision).toBe('B')
    expect(doc.hasPrint).toBe(true)
    const allLines = book.packages.flatMap(p => p.lines.map(l => l.item_number))
    expect(allLines).not.toContain('csd00010')
    expect(book.kits.flatMap(k => k.parts.map(p => p.item_number))).not.toContain('csd00010')
  })

  it('flags packages already recorded complete', () => {
    const sawPkgs = book.packages.filter(p => p.stationAbbrev === 'SAW')
    // both saw items have completion rows -> their package(s) print as done
    expect(sawPkgs.some(p => p.done)).toBe(true)
    const rcv = book.packages.find(p => p.stationAbbrev === 'RCV')!
    expect(rcv.done).toBe(false) // spn1/cspro not received
  })
})
