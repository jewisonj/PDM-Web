import { describe, it, expect } from 'vitest'
import { masterDesignBook, dayLabel, type MasterBookInputs } from './masterDesignBook'
import type { KitSourceInput } from './buildTracker'

// Mini spa fixture (same shape as buildBook.test.ts / buildTracker.test.ts):
//   csa10 FINISHED ASSY -> csa20 FRAME WELDMENT -> csa30 LOWER FRAME
//   csp01 (tube), csp05 (post, used in csa30 AND csa20), csp21 (floor),
//   cspnr (UNROUTED made part — the tracker rowDone gate-exemption edge),
//   cspro (receive-only csp), mmc1/spn1 purchased, zzz1 ref, csd1 document.
// csp01 carries a big est time so Saw overflows one day -> I-SAW-1 and I-SAW-2.

const WS = [
  { id: 's-rcv', station_code: '005', station_name: 'Receiving', station_group: 'QC', sort_order: 5 },
  { id: 's-saw', station_code: '010', station_name: 'Saw', station_group: 'Fabrication', sort_order: 10 },
  { id: 's-dbr', station_code: '011', station_name: 'Deburr', station_group: 'Fabrication', sort_order: 12 },
  { id: 's-wj', station_code: '012', station_name: 'Waterjet', station_group: 'Fabrication', sort_order: 11 },
  { id: 's-brk', station_code: '013', station_name: 'Press Brake', station_group: 'Fabrication', sort_order: 13 },
  { id: 's-jig', station_code: '014', station_name: 'Weld Jigging', station_group: 'Weld', sort_order: 14 },
  { id: 's-lw', station_code: '015', station_name: 'Light Weld', station_group: 'Weld', sort_order: 15 },
  { id: 's-wcu', station_code: '017', station_name: 'Weld Cleanup', station_group: 'Weld', sort_order: 17 },
  { id: 's-stg', station_code: '020', station_name: 'Part Staging', station_group: 'Assembly', sort_order: 20 },
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
  cspnr: item('i-cspnr', 'csp00990', 'UNROUTED BRACKET'),
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
  { item_id: ITEMS.cspnr.id, quantity: 1, items: ITEMS.cspnr },
  { item_id: ITEMS.cspro.id, quantity: 1, items: ITEMS.cspro },
  { item_id: ITEMS.mmc1.id, quantity: 4, items: ITEMS.mmc1 },
  { item_id: ITEMS.spn1.id, quantity: 1, items: ITEMS.spn1 },
  { item_id: ITEMS.zzz1.id, quantity: 2, items: ITEMS.zzz1 },
  { item_id: ITEMS.csd1.id, quantity: 1, items: ITEMS.csd1 },
]

const bom = [
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.csa20.id, quantity: 1 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.mmc1.id, quantity: 4 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.spn1.id, quantity: 1 },
  { parent_item_id: ITEMS.csa10.id, child_item_id: ITEMS.zzz1.id, quantity: 2 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.csa30.id, quantity: 1 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.csp05.id, quantity: 1 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.csp21.id, quantity: 1 },
  { parent_item_id: ITEMS.csa20.id, child_item_id: ITEMS.cspro.id, quantity: 1 },
  { parent_item_id: ITEMS.csa30.id, child_item_id: ITEMS.csp01.id, quantity: 2 },
  { parent_item_id: ITEMS.csa30.id, child_item_id: ITEMS.csp05.id, quantity: 1 },
  { parent_item_id: ITEMS.csa30.id, child_item_id: ITEMS.cspnr.id, quantity: 1 },
]

let routingId = 0
function ops(itemId: string, stationNames: string[], estMin = 10) {
  return stationNames.map((nm, i) => {
    const ws = wsByName.get(nm)!
    return {
      id: `r-${++routingId}`,
      item_id: itemId,
      station_id: ws.id,
      sequence: (i + 1) * 10,
      est_time_min: estMin,
      notes: null as string | null,
      workstations: { station_code: ws.station_code, station_name: ws.station_name },
    }
  })
}

// csp01 saw time large enough to overflow one saw day -> saw work on 2 days
const routing = [
  ...ops(ITEMS.csp01.id, ['Saw', 'Deburr', 'Inspection'], 500),
  ...ops(ITEMS.csp05.id, ['Saw', 'Deburr', 'Inspection'], 300),
  ...ops(ITEMS.csp21.id, ['Waterjet', 'Press Brake', 'Deburr', 'Inspection']),
  ...ops(ITEMS.csa30.id, ['Weld Jigging', 'Light Weld', 'Weld Cleanup', 'Inspection']),
  ...ops(ITEMS.csa20.id, ['Weld Jigging', 'Light Weld', 'Weld Cleanup', 'Inspection']),
  ...ops(ITEMS.csa10.id, ['Mechanical Assembly', 'Inspection']),
  ...ops(ITEMS.cspro.id, ['Receiving']),
  ...ops(ITEMS.mmc1.id, ['Receiving']),
  ...ops(ITEMS.spn1.id, ['Receiving']),
]
routing.find(r => r.item_id === ITEMS.csa20.id && r.station_id === 's-jig')!.notes =
  'Set TANK WALL at distance from edge; FLOOR SUB against it sets wall spacing'

const routingMaterials = [
  { item_id: ITEMS.csp01.id, qty_required: 24, raw_materials: { description: '2x2x0.125 SS Square Tube', material_code: 'SS' } },
  { item_id: ITEMS.csp21.id, qty_required: 100, raw_materials: { description: '0.078" SS Sheet', material_code: 'SS' } },
]

function makeInputs(): MasterBookInputs {
  return {
    // deliberately dated project — the master engine must null both dates
    project: {
      id: 'p-1',
      project_code: 'TEST-MINI',
      description: 'Mini Spa',
      customer: 'MWES',
      due_date: '2026-08-01',
      start_date: '2026-07-01',
      top_assembly_id: ITEMS.csa10.id,
    },
    parts: [...parts],
    bom: [...bom],
    routing: [...routing],
    workstations: [...WS],
    routingMaterials: [...routingMaterials],
    printItemIds: [ITEMS.csa30.id, ITEMS.csp01.id, ITEMS.csp21.id, ITEMS.csd1.id],
    now: new Date('2026-07-05T12:00:00'),
  }
}

describe('masterDesignBook', () => {
  const master = masterDesignBook(makeInputs())
  const { book, sections } = master

  it('derives product meta from the top assembly', () => {
    expect(master.meta.product_item_number).toBe('csa00010')
    expect(master.meta.template_project_code).toBe('TEST-MINI')
    expect(master.meta.title).toContain('MASTER DESIGN BOOK')
    expect(master.meta.day_count).toBe(book.summary.totalDays)
  })

  it('is date-free even when the template project carries dates', () => {
    expect(book.startDate).toBeNull()
    for (const p of book.packages) expect(p.date).toBe('')
    for (const k of book.kits) {
      expect(k.startDate).toBe('')
      expect(k.endDate).toBe('')
    }
    for (const m of book.milestones) {
      expect(m.plan).toBe('')
      expect(m.actual).toBe('')
    }
    // no calendar month strings anywhere in the descriptors
    const json = JSON.stringify(sections)
    expect(json).not.toMatch(/JUL|AUG|2026/)
  })

  it('forces every done flag blank — including the unrouted-part edge', () => {
    for (const p of book.packages) {
      expect(p.done).toBe(false)
      for (const l of p.lines) expect(l.done).toBe(false)
    }
    for (const k of book.kits) {
      for (const s of k.weldSeq) expect(s.done).toBe(false)
      for (const pt of k.parts) expect(pt.done).toBe(false)
    }
    // cspnr has no routing: the tracker's gate exemption marks it rowDone —
    // the master must still report it blank
    const lower = book.kits.find(k => k.item_number === 'csa00030')!
    const unrouted = lower.parts.find(p => p.item_number === 'csp00990')!
    expect(unrouted.done).toBe(false)
    // no done keys survive into descriptor payloads at all
    expect(JSON.stringify(sections)).not.toMatch(/"done"/)
  })

  it('is deterministic under shuffled input order', () => {
    const shuffled = makeInputs()
    shuffled.parts.reverse()
    shuffled.bom.reverse()
    shuffled.routing.reverse()
    shuffled.workstations.reverse()
    shuffled.printItemIds!.reverse()
    const again = masterDesignBook(shuffled)
    expect(JSON.stringify(again.sections)).toBe(JSON.stringify(sections))
    expect(again.qtyCheck).toEqual(master.qtyCheck)
  })

  it('enumerates sections: spine first, packages, kits, II-REF, III-00 last', () => {
    expect(sections[0]!.section_code).toBe('00-SPINE')
    expect(sections[sections.length - 1]!.section_code).toBe('III-00')
    expect(sections.filter(s => s.kind === 'design_reference')).toHaveLength(1)
    const codes = sections.map(s => s.section_code)
    expect(new Set(codes).size).toBe(codes.length) // unique
    const sorts = sections.map(s => s.sort_order)
    expect([...sorts].sort((a, b) => a - b)).toEqual(sorts) // ordered
    for (const s of sections.filter(x => x.kind === 'work_package')) {
      expect(s.section_code).toMatch(/^I-[A-Z]+-\d+$/)
    }
    for (const s of sections.filter(x => x.kind === 'assembly')) {
      expect(s.section_code).toMatch(/^II-CSA\d+$/)
    }
  })

  it('keys work packages by station occurrence ordered by day', () => {
    const saw = sections.filter(s => s.section_code.startsWith('I-SAW-'))
    expect(saw.length).toBeGreaterThanOrEqual(2) // 800 min of saw work > one day
    expect(saw.map(s => s.section_code)).toEqual(saw.map((_, i) => `I-SAW-${i + 1}`))
    const days = saw.map(s => (s.display as any).day)
    for (let i = 1; i < days.length; i++) expect(days[i]).toBeGreaterThan(days[i - 1])
    expect((saw[0]!.identity as any).station_code).toBe('010')
    expect((saw[0]!.identity as any).occurrence).toBe(1)
  })

  it('translates all cross-references to section codes', () => {
    const lower = sections.find(s => s.section_code === 'II-CSA00030')!
    const payload = lower.payload as any
    for (const pt of payload.parts) {
      if (pt.readyBy) expect(pt.readyBy).toMatch(/^I-[A-Z]+-\d+$/)
    }
    const frame = sections.find(s => s.section_code === 'II-CSA00020')!
    expect((frame.payload as any).childAsms.map((c: any) => c.code)).toContain('II-CSA00030')
    for (const s of sections.filter(x => x.kind === 'work_package')) {
      const p = s.payload as any
      for (const ln of p.lines) {
        for (const f of ln.feeds) expect(f).toMatch(/^II-CSA\d+$/)
      }
      for (const st of p.stageFor) expect(st).toMatch(/^II-CSA\d+$/)
    }
    // no raw display ordinals leak into payloads
    expect(JSON.stringify(sections.map(s => s.payload))).not.toMatch(/"A0\d"|"PKG \d/)
  })

  it('gives kit parts kit-local row ids, not global tracker F-numbers', () => {
    for (const s of sections.filter(x => x.kind === 'assembly')) {
      const rids = (s.payload as any).parts.map((p: any) => p.rid)
      expect(rids).toEqual(rids.map((_: any, i: number) => `P${String(i + 1).padStart(2, '0')}`))
    }
  })

  it('excludes purchased items from print binding, keeps them as lines w/ source', () => {
    const rcv = sections.find(s => s.section_code.startsWith('I-RCV-'))!
    const printNums = rcv.print_items.map(p => p.item_number)
    expect(printNums).toContain('csp00230') // receiving-routed csp CAN have a print
    expect(printNums).not.toContain('mmc90098a036')
    expect(printNums).not.toContain('spntank')
    expect(rcv.no_print_expected.sort()).toEqual(['mmc90098a036', 'spntank'])
    const mmcLine = (rcv.payload as any).lines.find((l: any) => l.item_number === 'mmc90098a036')
    expect(mmcLine.displayNumber).toBe('90098A036')
    expect(mmcLine.source).toBe('McMaster-Carr')
  })

  it('binds kit prints assembly-first with quantities', () => {
    const lower = sections.find(s => s.section_code === 'II-CSA00030')!
    expect(lower.print_items[0]).toEqual({ item_number: 'csa00030', qty: 1 })
    const nums = lower.print_items.map(p => p.item_number)
    expect(nums).toContain('csp00010')
    expect(nums).toContain('csp00990') // unrouted made part still gets its print slot
  })

  it('lists reference documents with null qty (no stamp)', () => {
    const ref = sections.find(s => s.section_code === 'II-REF')!
    expect((ref.payload as any).docs).toEqual([
      { item_number: 'csd00010', name: 'SPA BUILD DESIGN BOOK', revision: 'B' },
    ])
    expect(ref.print_items).toEqual([{ item_number: 'csd00010', qty: null }])
  })

  it('builds the spine: buy list with shop-facing numbers + day-ordered checklist', () => {
    const spine = sections[0]!
    const payload = spine.payload as any
    const buyNums = payload.buyList.map((r: any) => r.displayNumber)
    expect(buyNums).toContain('90098A036')
    expect(buyNums).toContain('TANK')
    expect(buyNums.every((n: string) => !/^(MMC|SPN)/i.test(n) || n === 'TANK')).toBe(true)
    const rows = payload.checklist as any[]
    expect(rows.length).toBeGreaterThan(5)
    for (let i = 1; i < rows.length; i++) {
      expect(rows[i].day).toBeGreaterThanOrEqual(rows[i - 1].day)
    }
    expect(rows.some(r => r.kind === 'package' && /^I-/.test(r.see))).toBe(true)
    expect(rows.some(r => r.kind === 'kit_step' && /^II-/.test(r.see))).toBe(true)
    const m10 = rows.find(r => r.kind === 'milestone' && r.op === 10)!
    expect(m10.day).toBe(-1) // order purchased before D1
    expect(rows[0]).toBe(m10)
    const receivePkg = rows.find(r => r.kind === 'package' && /^I-RCV/.test(r.see))!
    expect(receivePkg.text).toContain('receive')
    expect(receivePkg.text).toContain('purchased items')
  })

  it('passes the qty gate when flat quantities match the BOM rollup', () => {
    // csp05: 1 (csa20) + 1 (csa30) = 2 = flat qty; csp01: 2x1 = 2 = flat qty
    expect(master.qtyCheck).toEqual({ ok: true, mismatches: [] })
  })

  it('flags flat-vs-rollup quantity mismatches', () => {
    const bad = makeInputs()
    bad.parts = bad.parts.map(p =>
      p.item_id === ITEMS.csp01.id ? { ...p, quantity: 1 } : p
    )
    const result = masterDesignBook(bad)
    expect(result.qtyCheck.ok).toBe(false)
    expect(result.qtyCheck.mismatches).toEqual([
      { item_number: 'csp00010', project_qty: 1, bom_rollup_qty: 2 },
    ])
  })

  it('rolls up correctly through multi-path sub-assemblies (no double count)', () => {
    // Diamond with GRANDCHILDREN: csaDD used by csa20 (x1) AND csa30 (x1);
    // cspDD sits inside csaDD (x3). True usage: csaDD = 2, cspDD = 6.
    // A naive walk-down accumulator revisits csaDD and inflates cspDD.
    const inp = makeInputs()
    const csaDD = item('i-csadd', 'csa00099', 'SHARED SUB')
    const cspDD = item('i-cspdd', 'csp00880', 'SHARED SUB PART')
    inp.parts.push(
      { item_id: csaDD.id, quantity: 2, items: csaDD },
      { item_id: cspDD.id, quantity: 6, items: cspDD }
    )
    inp.bom.push(
      { parent_item_id: ITEMS.csa20.id, child_item_id: csaDD.id, quantity: 1 },
      { parent_item_id: ITEMS.csa30.id, child_item_id: csaDD.id, quantity: 1 },
      { parent_item_id: csaDD.id, child_item_id: cspDD.id, quantity: 3 }
    )
    inp.routing.push(
      ...ops(csaDD.id, ['Weld Jigging', 'Light Weld']),
      ...ops(cspDD.id, ['Saw'])
    )
    const result = masterDesignBook(inp)
    expect(result.qtyCheck).toEqual({ ok: true, mismatches: [] })
  })

  it('skips items unreachable from the top assembly (manual attaches)', () => {
    // csd1 (document) and zzz1 are attached to the project but have no BOM
    // path under csa00010 that rolls up — they must not produce mismatches.
    expect(
      master.qtyCheck.mismatches.map(m => m.item_number)
    ).not.toContain('csd00010')
  })

  it('exposes dayLabel as the single D-day formatter', () => {
    expect(dayLabel(0)).toBe('D1')
    expect(dayLabel(17)).toBe('D18')
  })

  it('ignores stale quantities on zz reference items in the qty gate', () => {
    const inp = makeInputs()
    // zzz1's flat qty (2) already matches its rollup; break it and prove the gate
    // still passes — reference items never reach the book, so they must not block it
    inp.parts = inp.parts.map(p =>
      p.item_id === ITEMS.zzz1.id ? { ...p, quantity: 999 } : p
    )
    expect(masterDesignBook(inp).qtyCheck.ok).toBe(true)
  })

  it('carries schedule days on kit weld steps for the checklist', () => {
    for (const k of book.kits) {
      for (const s of k.weldSeq) expect(typeof s.day).toBe('number')
    }
  })

  it('omits the bundles key entirely when nothing is kit-sourced', () => {
    // absent, not [] — a section with no bundle must keep its exact payload shape so
    // adding the feature does not phantom-rev it
    const spine = sections[0]!
    expect('bundles' in (spine.payload as any)).toBe(false)
    for (const s of sections.filter(x => x.kind === 'work_package')) {
      expect('bundles' in (s.payload as any)).toBe(false)
    }
  })

  it('M20 tracks purchased receiving only, not assembly staging steps', () => {
    // give the TOP assembly a late Receiving first step (like csa00080's
    // equipment staging) — it must NOT drag M20 past M30
    const inp = makeInputs()
    const ws = wsByName.get('Receiving')!
    inp.routing = [
      {
        id: 'r-late-rcv', item_id: ITEMS.csa10.id, station_id: ws.id, sequence: 5,
        est_time_min: 60, notes: null,
        workstations: { station_code: ws.station_code, station_name: ws.station_name },
      },
      ...inp.routing,
    ]
    const result = masterDesignBook(inp)
    const spine = result.sections[0]!
    const rows = (spine.payload as any).checklist as any[]
    const m20 = rows.find(r => r.kind === 'milestone' && r.op === 20)!
    const m30 = rows.find(r => r.kind === 'milestone' && r.op === 30)!
    const lateAsmRcv = Math.max(
      ...result.book.kits
        .filter(k => k.item_number === 'csa00010')
        .flatMap(k => k.weldSeq.filter(s => s.abbrev === 'RCV').map(s => s.day ?? 0))
    )
    expect(m20.day).toBeLessThanOrEqual(m30.day)
    expect(m20.day).toBeLessThan(lateAsmRcv)
  })
})

// ===========================================================================
// Kit sourcing (Documentation/38)
// ===========================================================================

const KIT_001: KitSourceInput = {
  item_id: ITEMS.csp01.id,
  kit_number: 'KIT-001',
  kit_name: 'Tube Laser Bundle',
  vendor: 'Precision Tube Laser',
}

describe('masterDesignBook with kit sourcing', () => {
  function withKit(): MasterBookInputs {
    return { ...makeInputs(), kitSources: [KIT_001] }
  }
  const master = masterDesignBook(withKit())
  const { sections } = master
  const codeOf = (pred: (s: any) => boolean) => sections.find(pred)!
  const rcv = codeOf(s => s.section_code.startsWith('I-RCV-'))
  const stg = codeOf(s => s.section_code.startsWith('I-STG-'))

  it('routes the bundled tube through receive/inspect/stage, out of Saw', () => {
    const sawLines = sections
      .filter(s => s.section_code.startsWith('I-SAW-'))
      .flatMap(s => (s.payload as any).lines.map((l: any) => l.item_number))
    expect(sawLines).not.toContain('csp00010')
    expect(sawLines).toContain('csp00050') // in-house part untouched

    const rcvLines = (rcv.payload as any).lines.map((l: any) => l.item_number)
    expect(rcvLines).toContain('csp00010')
    expect((stg.payload as any).lines.map((l: any) => l.item_number)).toContain('csp00010')
  })

  it('labels bundled lines with the kit number, not a supplier', () => {
    const line = (rcv.payload as any).lines.find((l: any) => l.item_number === 'csp00010')
    expect(line.source).toBe('KIT-001')
    expect(line.next).toBe('STG')
    // real purchases keep their supplier
    const washer = (rcv.payload as any).lines.find((l: any) => l.item_number === 'mmc90098a036')
    expect(washer.source).toBe('McMaster-Carr')
  })

  it('bands the receiving booklet with the bundle it must verify', () => {
    expect((rcv.payload as any).bundles).toEqual([
      { kit_number: 'KIT-001', kit_name: 'Tube Laser Bundle', vendor: 'Precision Tube Laser', partCount: 1 },
    ])
  })

  it('keeps the tube in the assembly stage set, ready by the staging package', () => {
    const lower = codeOf(s => s.section_code === 'II-CSA00030')
    const tube = (lower.payload as any).parts.find((p: any) => p.item_number === 'csp00010')
    expect(tube).toBeDefined()
    expect(tube.source).toBe('KIT-001')
    expect(tube.readyBy).toBe(stg.section_code)
    // and it still binds its print — receiving inspects against the drawing
    expect(lower.print_items.map(p => p.item_number)).toContain('csp00010')
    expect(rcv.print_items.map(p => p.item_number)).toContain('csp00010')
  })

  it('pulls no raw stock in the receiving or staging booklets', () => {
    expect((rcv.payload as any).stockPull).toEqual([])
    expect((stg.payload as any).stockPull).toEqual([])
  })

  it('lists the bundle on the spine and keeps it off the buy list', () => {
    const spine = sections[0]!
    expect((spine.payload as any).bundles).toEqual([
      { kit_number: 'KIT-001', kit_name: 'Tube Laser Bundle', vendor: 'Precision Tube Laser', partCount: 1 },
    ])
    const buy = (spine.payload as any).buyList.map((r: any) => r.item_number)
    expect(buy).not.toContain('csp00010')
    expect(buy).toContain('mmc90098a036')
    // spine stats split fabricated from supplied
    expect((spine.payload as any).summary.kitSupplied).toBe(1)
  })

  it('flags bundled counts on the checklist', () => {
    const spine = sections[0]!
    const rows = (spine.payload as any).checklist as any[]
    const rcvRow = rows.find(r => r.see === rcv.section_code)!
    expect(rcvRow.text).toContain('bundled')
  })

  it('stays deterministic under shuffled kit sources', () => {
    const a = masterDesignBook(withKit())
    const shuffled = withKit()
    shuffled.parts = [...shuffled.parts].reverse()
    shuffled.routing = [...shuffled.routing].reverse()
    shuffled.kitSources = [...shuffled.kitSources!].reverse()
    const b = masterDesignBook(shuffled)
    expect(JSON.stringify(b.sections)).toBe(JSON.stringify(a.sections))
  })

  it('never rewrites a kit-sourced assembly', () => {
    const inp = withKit()
    inp.kitSources = [{ ...KIT_001, item_id: ITEMS.csa30.id }]
    const result = masterDesignBook(inp)
    // csa30 keeps its weld sequence; nothing is bundled
    const lower = result.sections.find(s => s.section_code === 'II-CSA00030')!
    expect((lower.payload as any).weldSeq.map((s: any) => s.abbrev)).toContain('LW')
    expect(result.book.bundles).toEqual([])
  })
})
