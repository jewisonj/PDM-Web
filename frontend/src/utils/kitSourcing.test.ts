import { describe, it, expect } from 'vitest'
import {
  applyKitSourcing,
  kitSuppliedMap,
  isReferenceOnlyItem,
  excludeFromManufacturing,
  type KitSourceInput,
  type SourcedRoutingRow,
} from './buildTracker'
import { buildBook, type BookInputs } from './buildBook'
import { calculateSchedule, type PartData, type BomData, type RoutingData } from './scheduling'

// ---------------------------------------------------------------------------
// Fixture (see Documentation/38): csa10 -> csa20 -> csa30 -> {csp01, csp05}
// csp01 TUBE is supplied finished in vendor bundle KIT-001; it is sawn otherwise.
// zzc1 is a routing-less reference item that must stay invisible.
// ---------------------------------------------------------------------------

const WS = [
  { id: 's-rcv', station_code: '005', station_name: 'Receiving', station_group: 'QC', sort_order: 5 },
  { id: 's-saw', station_code: '010', station_name: 'Saw', station_group: 'Fabrication', sort_order: 10 },
  { id: 's-dbr', station_code: '011', station_name: 'Deburr', station_group: 'Fabrication', sort_order: 12 },
  { id: 's-stg', station_code: '020', station_name: 'Part Staging', station_group: 'Assembly', sort_order: 20 },
  { id: 's-jig', station_code: '014', station_name: 'Weld Jigging', station_group: 'Weld', sort_order: 14 },
  { id: 's-tig', station_code: '015', station_name: 'Tig Welding', station_group: 'Weld', sort_order: 15 },
  { id: 's-asm', station_code: '025', station_name: 'Mechanical Assembly', station_group: 'Assembly', sort_order: 25 },
  { id: 's-ins', station_code: '050', station_name: 'Inspection', station_group: 'QC', sort_order: 50 },
]
const wsByName = new Map(WS.map(w => [w.station_name, w]))

function item(id: string, num: string, name: string, supplier_pn: string | null = null, supplier_name: string | null = null) {
  return { id, item_number: num, name, description: null, thickness: null, material: null, supplier_pn, supplier_name }
}

const ITEMS = {
  csa10: item('i-csa10', 'csa00010', 'FINISHED ASSY'),
  csa20: item('i-csa20', 'csa00020', 'FRAME WELDMENT'),
  csa30: item('i-csa30', 'csa00030', 'LOWER FRAME'),
  csp01: item('i-csp01', 'csp00010', 'TUBE'),
  csp05: item('i-csp05', 'csp00050', 'POST'),
  mmc1: item('i-mmc1', 'mmc90098a036', 'WASHER', '90098A036', 'McMaster-Carr'),
  zzc1: item('i-zzc1', 'zzc551436', 'REF ONLY'),
}

const parts = [
  { item_id: ITEMS.csa10.id, quantity: 1, items: ITEMS.csa10 },
  { item_id: ITEMS.csa20.id, quantity: 1, items: ITEMS.csa20 },
  { item_id: ITEMS.csa30.id, quantity: 1, items: ITEMS.csa30 },
  { item_id: ITEMS.csp01.id, quantity: 2, items: ITEMS.csp01 },
  { item_id: ITEMS.csp05.id, quantity: 1, items: ITEMS.csp05 },
  { item_id: ITEMS.mmc1.id, quantity: 4, items: ITEMS.mmc1 },
  { item_id: ITEMS.zzc1.id, quantity: 2, items: ITEMS.zzc1 },
]

const bom = [
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.csa20.id, quantity: 1 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.mmc1.id, quantity: 4 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.zzc1.id, quantity: 2 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.csa30.id, quantity: 1 },
  { parent_item_id: ITEMS.csa30.id, child_item_id: ITEMS.csp01.id, quantity: 2 },
  { parent_item_id: ITEMS.csa30.id, child_item_id: ITEMS.csp05.id, quantity: 1 },
]

let rid = 0
function ops(itemId: string, stationNames: string[], estMin = 30): SourcedRoutingRow[] {
  return stationNames.map((nm, i) => {
    const ws = wsByName.get(nm)!
    return {
      id: `r-${++rid}`,
      item_id: itemId,
      station_id: ws.id,
      sequence: (i + 1) * 10,
      est_time_min: estMin,
      notes: null,
      workstations: { station_code: ws.station_code, station_name: ws.station_name },
    }
  })
}

const baseRouting: SourcedRoutingRow[] = [
  ...ops(ITEMS.csp01.id, ['Saw', 'Deburr', 'Inspection']),
  ...ops(ITEMS.csp05.id, ['Saw', 'Deburr', 'Inspection']),
  ...ops(ITEMS.csa30.id, ['Weld Jigging', 'Tig Welding']),
  ...ops(ITEMS.csa20.id, ['Weld Jigging', 'Tig Welding']),
  ...ops(ITEMS.csa10.id, ['Mechanical Assembly']),
  ...ops(ITEMS.mmc1.id, ['Receiving'], 3),
]

const routingMaterials = [
  { item_id: ITEMS.csp01.id, qty_required: 24, raw_materials: { description: '2x2 SS Tube', material_code: 'SS' } },
  { item_id: ITEMS.csp05.id, qty_required: 36, raw_materials: { description: '2x2 SS Tube', material_code: 'SS' } },
]

const KIT_001: KitSourceInput = {
  item_id: ITEMS.csp01.id,
  kit_number: 'KIT-001',
  kit_name: 'Tube Laser Bundle',
  vendor: 'Precision Tube Laser',
}

function makeBook(kitSources?: KitSourceInput[]): ReturnType<typeof buildBook> {
  const sourced = applyKitSourcing({
    routing: baseRouting,
    routingMaterials,
    kitSources,
    workstations: WS,
    bom,
  })
  const schedule = calculateSchedule(
    parts as unknown as PartData[],
    bom as BomData[],
    sourced.routing as unknown as RoutingData[],
    []
  )
  const inputs: BookInputs = {
    project: {
      id: 'p-1', project_code: 'TEST', description: null, customer: null,
      due_date: null, start_date: null, top_assembly_id: ITEMS.csa10.id,
    },
    parts: parts as any,
    bom,
    routing: sourced.routing as any,
    completion: [],
    workstations: WS as any,
    schedule,
    routingMaterials: sourced.routingMaterials as any,
    printItemIds: [],
    kitSources,
    now: new Date('2026-07-10T12:00:00'),
  }
  return buildBook(inputs)
}

const pkgFor = (book: ReturnType<typeof buildBook>, abbrev: string) =>
  book.packages.filter(p => p.stationAbbrev === abbrev)
const linesIn = (book: ReturnType<typeof buildBook>, abbrev: string) =>
  pkgFor(book, abbrev).flatMap(p => p.lines.map(l => l.item_number))

// ===========================================================================

describe('reference-item helpers', () => {
  it('treats the whole zz family as reference, not just zzz', () => {
    expect(isReferenceOnlyItem('zzz1071a59a')).toBe(true)
    expect(isReferenceOnlyItem('zzc551436')).toBe(true)
    expect(isReferenceOnlyItem('zz_hingebody')).toBe(true)
    expect(isReferenceOnlyItem('csp00010')).toBe(false)
  })

  it('excludeFromManufacturing also drops purchased parts (dashboard-only helper)', () => {
    // guards the Documentation/38 landmine: the build docs must NOT use this,
    // because they need mmc/spn for the buy list and receiving packages
    expect(excludeFromManufacturing('mmc90098a036')).toBe(true)
    expect(excludeFromManufacturing('spntank')).toBe(true)
    expect(excludeFromManufacturing('zzc551436')).toBe(true)
    expect(excludeFromManufacturing('csd00010')).toBe(true)
    expect(excludeFromManufacturing('csp00010')).toBe(false)
  })
})

describe('kitSuppliedMap', () => {
  it('maps leaf kit parts', () => {
    const m = kitSuppliedMap([KIT_001], bom)
    expect([...m.keys()]).toEqual([ITEMS.csp01.id])
    expect(m.get(ITEMS.csp01.id)!.kit_number).toBe('KIT-001')
  })

  it('excludes kit-sourced BOM parents (assembly-level kits unsupported)', () => {
    const asmKit: KitSourceInput = { ...KIT_001, item_id: ITEMS.csa30.id }
    expect(kitSuppliedMap([asmKit], bom).size).toBe(0)
  })

  it('is empty without kit sources', () => {
    expect(kitSuppliedMap(undefined, bom).size).toBe(0)
    expect(kitSuppliedMap([], bom).size).toBe(0)
  })
})

describe('applyKitSourcing', () => {
  it('passes routing through untouched when nothing is kit-sourced', () => {
    const out = applyKitSourcing({ routing: baseRouting, routingMaterials, kitSources: [], workstations: WS, bom })
    expect(out.routing).toBe(baseRouting)
    expect(out.routingMaterials).toBe(routingMaterials)
  })

  it('replaces the kit part routing with Receive -> Inspect -> Stage', () => {
    const out = applyKitSourcing({ routing: baseRouting, routingMaterials, kitSources: [KIT_001], workstations: WS, bom })
    const mine = out.routing
      .filter(r => r.item_id === ITEMS.csp01.id)
      .sort((a, b) => a.sequence - b.sequence)
    expect(mine.map(r => r.workstations!.station_name)).toEqual(['Receiving', 'Inspection', 'Part Staging'])
    expect(mine.map(r => r.sequence)).toEqual([10, 20, 30])
    expect(mine.map(r => r.est_time_min)).toEqual([1, 2, 1])
    // no saw op survives for the kit part
    expect(mine.some(r => r.workstations!.station_name === 'Saw')).toBe(false)
  })

  it('leaves every other part\'s routing alone (routing is global per item)', () => {
    const out = applyKitSourcing({ routing: baseRouting, routingMaterials, kitSources: [KIT_001], workstations: WS, bom })
    const post = out.routing.filter(r => r.item_id === ITEMS.csp05.id)
    expect(post.map(r => r.workstations!.station_name)).toEqual(['Saw', 'Deburr', 'Inspection'])
    expect(post).toEqual(baseRouting.filter(r => r.item_id === ITEMS.csp05.id))
  })

  it('drops the kit part raw-material rows (vendor already cut them)', () => {
    const out = applyKitSourcing({ routing: baseRouting, routingMaterials, kitSources: [KIT_001], workstations: WS, bom })
    expect(out.routingMaterials.map(m => m.item_id)).toEqual([ITEMS.csp05.id])
  })

  it('does not rewrite a kit-sourced assembly', () => {
    const asmKit: KitSourceInput = { ...KIT_001, item_id: ITEMS.csa30.id }
    const out = applyKitSourcing({ routing: baseRouting, routingMaterials, kitSources: [asmKit], workstations: WS, bom })
    expect(out.routing).toBe(baseRouting)
  })
})

describe('buildBook with kit sourcing', () => {
  const before = makeBook()
  const after = makeBook([KIT_001])

  it('baseline: the tube is sawn and pulls stock', () => {
    expect(linesIn(before, 'SAW')).toContain('csp00010')
    expect(before.stock.some(s => s.description === '2x2 SS Tube')).toBe(true)
    expect(before.summary.kitSupplied).toBe(0)
    expect(before.bundles).toEqual([])
  })

  it('moves the tube out of Saw and into Receiving + Part Staging', () => {
    expect(linesIn(after, 'SAW')).not.toContain('csp00010')
    expect(linesIn(after, 'RCV')).toContain('csp00010')
    expect(linesIn(after, 'STG')).toContain('csp00010')
    // the other tube part is untouched
    expect(linesIn(after, 'SAW')).toContain('csp00050')
  })

  it('routes the receiving line onward to staging', () => {
    const rcvLine = pkgFor(after, 'RCV').flatMap(p => p.lines).find(l => l.item_number === 'csp00010')!
    expect(rcvLine.next).toBe('STG')
    expect(rcvLine.sourcedFrom).toBe('KIT-001')
    expect(rcvLine.estMin).toBe(2) // 1 min receiving x qty 2
  })

  it('costs less shop labor than making the part in-house', () => {
    // the whole point of the bundle: receive+inspect+stage must beat saw+deburr+inspect
    expect(after.summary.totalHours).toBeLessThan(before.summary.totalHours)
  })

  it('KEEPS the tube in the assembly stage set (the welder still needs it)', () => {
    const lower = after.kits.find(k => k.item_number === 'csa00030')!
    const tube = lower.parts.find(p => p.item_number === 'csp00010')
    expect(tube).toBeDefined()
    expect(tube!.qty).toBe(2)
    expect(tube!.sourcedFrom).toBe('KIT-001')
    // ready when it has been staged, not when it was received
    const stgPkg = pkgFor(after, 'STG')[0]!
    expect(tube!.readyBy).toBe(stgPkg.id)
    // in-house parts are unchanged and carry no bundle
    const post = lower.parts.find(p => p.item_number === 'csp00050')!
    expect(post.sourcedFrom).toBeNull()
  })

  it('pulls no raw stock for the kit part', () => {
    // csp05 still needs tube stock; csp01's 24 x 2 = 48 must be gone
    const tubeStock = after.stock.find(s => s.description === '2x2 SS Tube')!
    expect(tubeStock.parts).toBe(1)
    expect(tubeStock.qty).toBe(36) // csp05 only
    for (const p of after.packages) {
      const pulled = p.stockPull.flatMap(s => s.description)
      if (p.stationAbbrev === 'RCV' || p.stationAbbrev === 'STG') expect(pulled).toEqual([])
    }
  })

  it('keeps the kit part off the buy list, and keeps real purchases on it', () => {
    const buy = after.purchased.map(r => r.item_number)
    expect(buy).not.toContain('csp00010')
    expect(buy).toContain('mmc90098a036')
  })

  it('surfaces the bundle and counts parts as supplied, not fabricated', () => {
    expect(after.bundles).toEqual([
      { kit_number: 'KIT-001', kit_name: 'Tube Laser Bundle', vendor: 'Precision Tube Laser', partCount: 1 },
    ])
    expect(after.summary.kitSupplied).toBe(1)
    expect(after.summary.fabParts).toBe(before.summary.fabParts - 1)
  })

  it('shortens the schedule (no sawing the bundled tube)', () => {
    expect(after.summary.totalHours).toBeLessThan(before.summary.totalHours)
  })

  it('never surfaces zz reference items', () => {
    const everywhere = JSON.stringify([after.packages, after.kits, after.purchased])
    expect(everywhere).not.toContain('zzc551436')
    expect(after.summary.fabParts).toBeGreaterThan(0)
  })
})

describe('buildBook defensive stock guard', () => {
  it('suppresses kit-part stock even if applyKitSourcing was not called', () => {
    const schedule = calculateSchedule(
      parts as unknown as PartData[], bom as BomData[],
      baseRouting as unknown as RoutingData[], []
    )
    const book = buildBook({
      project: {
        id: 'p-1', project_code: 'TEST', description: null, customer: null,
        due_date: null, start_date: null, top_assembly_id: ITEMS.csa10.id,
      },
      parts: parts as any,
      bom,
      routing: baseRouting as any,
      completion: [],
      workstations: WS as any,
      schedule,
      routingMaterials: routingMaterials as any, // NOT filtered
      kitSources: [KIT_001],
      now: new Date('2026-07-10T12:00:00'),
    })
    const tubeStock = book.stock.find(s => s.description === '2x2 SS Tube')!
    expect(tubeStock.parts).toBe(1) // csp05 only — csp01's stock suppressed
  })
})
