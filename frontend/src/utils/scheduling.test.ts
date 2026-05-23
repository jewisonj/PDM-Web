/**
 * Unit tests for scheduling algorithm
 */
import { describe, it, expect } from 'vitest'
import {
  buildDependencyGraph,
  createScheduledTasks,
  prioritizeTasks,
  calculateSchedule,
  type PartData,
  type BomData,
  type RoutingData,
  type CompletionData
} from './scheduling'

// Test fixtures
const createPartData = (id: string, itemNumber: string, thickness: number | null = null): PartData => ({
  item_id: id,
  quantity: 1,
  items: {
    id,
    item_number: itemNumber,
    description: `Test part ${itemNumber}`,
    thickness
  }
})

const createRoutingData = (
  itemId: string,
  stationId: string,
  stationCode: string,
  sequence: number,
  estTime: number
): RoutingData => ({
  id: `routing-${itemId}-${stationId}`,
  item_id: itemId,
  station_id: stationId,
  sequence,
  est_time_min: estTime,
  workstations: {
    station_code: stationCode,
    station_name: `Station ${stationCode}`
  }
})

describe('buildDependencyGraph', () => {
  it('creates PartSchedule for each part', () => {
    const parts: PartData[] = [
      createPartData('p1', 'stp00001'),
      createPartData('p2', 'stp00002')
    ]
    const bom: BomData[] = []

    const result = buildDependencyGraph(parts, bom)

    expect(result.size).toBe(2)
    expect(result.get('p1')?.item_number).toBe('stp00001')
    expect(result.get('p2')?.item_number).toBe('stp00002')
  })

  it('identifies assemblies from BOM relationships', () => {
    const parts: PartData[] = [
      createPartData('assembly', 'asm00001'),
      createPartData('child1', 'stp00001'),
      createPartData('child2', 'stp00002')
    ]
    const bom: BomData[] = [
      { parent_item_id: 'assembly', child_item_id: 'child1' },
      { parent_item_id: 'assembly', child_item_id: 'child2' }
    ]

    const result = buildDependencyGraph(parts, bom)

    expect(result.get('assembly')?.is_assembly).toBe(true)
    expect(result.get('assembly')?.child_item_ids).toContain('child1')
    expect(result.get('assembly')?.child_item_ids).toContain('child2')
    expect(result.get('child1')?.is_assembly).toBe(false)
  })

  it('calculates BOM depth correctly', () => {
    // Nested structure: top_asm -> sub_asm -> part
    const parts: PartData[] = [
      createPartData('top_asm', 'asm00001'),
      createPartData('sub_asm', 'asm00002'),
      createPartData('part', 'stp00001')
    ]
    const bom: BomData[] = [
      { parent_item_id: 'top_asm', child_item_id: 'sub_asm' },
      { parent_item_id: 'sub_asm', child_item_id: 'part' }
    ]

    const result = buildDependencyGraph(parts, bom)

    expect(result.get('part')?.bom_depth).toBe(0)      // Leaf
    expect(result.get('sub_asm')?.bom_depth).toBe(1)   // One level up
    expect(result.get('top_asm')?.bom_depth).toBe(2)   // Top level
  })

  it('calculates all descendants for assemblies', () => {
    const parts: PartData[] = [
      createPartData('top_asm', 'asm00001'),
      createPartData('sub_asm', 'asm00002'),
      createPartData('part1', 'stp00001'),
      createPartData('part2', 'stp00002')
    ]
    const bom: BomData[] = [
      { parent_item_id: 'top_asm', child_item_id: 'sub_asm' },
      { parent_item_id: 'top_asm', child_item_id: 'part1' },
      { parent_item_id: 'sub_asm', child_item_id: 'part2' }
    ]

    const result = buildDependencyGraph(parts, bom)

    const topAsm = result.get('top_asm')!
    expect(topAsm.all_descendant_ids).toContain('sub_asm')
    expect(topAsm.all_descendant_ids).toContain('part1')
    expect(topAsm.all_descendant_ids).toContain('part2')
    expect(topAsm.all_descendant_ids.length).toBe(3)
  })
})

describe('createScheduledTasks', () => {
  it('creates tasks from routing data', () => {
    const parts: PartData[] = [createPartData('p1', 'stp00001')]
    const partsMap = buildDependencyGraph(parts, [])

    const routing: RoutingData[] = [
      createRoutingData('p1', 's1', '012', 1, 30),
      createRoutingData('p1', 's2', '013', 2, 15)
    ]

    const tasks = createScheduledTasks(partsMap, routing, [])

    expect(tasks.length).toBe(2)
    expect(tasks[0]!.station_code).toBe('012')
    expect(tasks[0]!.duration_min).toBe(30)
    expect(tasks[1]!.station_code).toBe('013')
    expect(tasks[1]!.sequence).toBe(2)
  })

  it('sets up predecessors for sequential operations', () => {
    const parts: PartData[] = [createPartData('p1', 'stp00001')]
    const partsMap = buildDependencyGraph(parts, [])

    const routing: RoutingData[] = [
      createRoutingData('p1', 's1', '012', 1, 30),
      createRoutingData('p1', 's2', '013', 2, 15)
    ]

    const tasks = createScheduledTasks(partsMap, routing, [])

    expect(tasks[0]!.predecessors).toEqual([])
    expect(tasks[1]!.predecessors).toContain('p1_s1')
  })

  it('marks completed tasks correctly', () => {
    const parts: PartData[] = [createPartData('p1', 'stp00001')]
    const partsMap = buildDependencyGraph(parts, [])

    const routing: RoutingData[] = [
      createRoutingData('p1', 's1', '012', 1, 30),
      createRoutingData('p1', 's2', '013', 2, 15)
    ]

    const completions: CompletionData[] = [
      { item_id: 'p1', station_id: 's1' }
    ]

    const tasks = createScheduledTasks(partsMap, routing, completions)

    expect(tasks[0]!.is_complete).toBe(true)
    expect(tasks[1]!.is_complete).toBe(false)
  })

  it('sets assembly predecessor to all descendant final operations', () => {
    const parts: PartData[] = [
      createPartData('asm', 'asm00001'),
      createPartData('part1', 'stp00001'),
      createPartData('part2', 'stp00002')
    ]
    const bom: BomData[] = [
      { parent_item_id: 'asm', child_item_id: 'part1' },
      { parent_item_id: 'asm', child_item_id: 'part2' }
    ]
    const partsMap = buildDependencyGraph(parts, bom)

    const routing: RoutingData[] = [
      createRoutingData('part1', 's1', '012', 1, 30),
      createRoutingData('part2', 's2', '012', 1, 20),
      createRoutingData('asm', 's3', '014', 1, 60)  // Assembly operation
    ]

    const tasks = createScheduledTasks(partsMap, routing, [])

    const asmTask = tasks.find(t => t.item_id === 'asm')!
    expect(asmTask.predecessors).toContain('part1_s1')
    expect(asmTask.predecessors).toContain('part2_s2')
  })
})

describe('prioritizeTasks', () => {
  it('prioritizes completed tasks highest', () => {
    const parts: PartData[] = [
      createPartData('p1', 'stp00001'),
      createPartData('p2', 'stp00002')
    ]
    const partsMap = buildDependencyGraph(parts, [])

    const routing: RoutingData[] = [
      createRoutingData('p1', 's1', '012', 1, 30),
      createRoutingData('p2', 's2', '012', 1, 30)
    ]

    const completions: CompletionData[] = [
      { item_id: 'p2', station_id: 's2' }
    ]

    const tasks = createScheduledTasks(partsMap, routing, completions)
    const prioritized = prioritizeTasks(tasks, partsMap)

    // Completed task should come first
    expect(prioritized[0]!.is_complete).toBe(true)
    expect(prioritized[0]!.item_id).toBe('p2')
  })

  it('prioritizes leaf parts over assemblies', () => {
    const parts: PartData[] = [
      createPartData('asm', 'asm00001'),
      createPartData('part', 'stp00001')
    ]
    const bom: BomData[] = [
      { parent_item_id: 'asm', child_item_id: 'part' }
    ]
    const partsMap = buildDependencyGraph(parts, bom)

    const routing: RoutingData[] = [
      createRoutingData('asm', 's1', '014', 1, 60),
      createRoutingData('part', 's2', '012', 1, 30)
    ]

    const tasks = createScheduledTasks(partsMap, routing, [])
    const prioritized = prioritizeTasks(tasks, partsMap)

    // Leaf part should come first (lower bom_depth)
    expect(prioritized[0]!.item_id).toBe('part')
  })
})

describe('calculateSchedule (integration)', () => {
  it('schedules a simple part through two stations', () => {
    const parts: PartData[] = [createPartData('p1', 'stp00001')]
    const bom: BomData[] = []
    const routing: RoutingData[] = [
      createRoutingData('p1', 's1', '012', 1, 60),
      createRoutingData('p1', 's2', '013', 2, 30)
    ]
    const completions: CompletionData[] = []

    const result = calculateSchedule(parts, bom, routing, completions)

    expect(result.tasks.length).toBe(2)
    expect(result.total_days).toBeGreaterThan(0)

    // First operation starts day 0
    const task1 = result.tasks.find(t => t.station_code === '012')!
    expect(task1.start_day).toBe(0)

    // Second operation starts after first (next day due to station change rule)
    const task2 = result.tasks.find(t => t.station_code === '013')!
    expect(task2.start_day).toBeGreaterThan(task1.end_day)
  })

  it('schedules assembly after all child parts complete', () => {
    const parts: PartData[] = [
      createPartData('asm', 'asm00001'),
      createPartData('part1', 'stp00001'),
      createPartData('part2', 'stp00002')
    ]
    const bom: BomData[] = [
      { parent_item_id: 'asm', child_item_id: 'part1' },
      { parent_item_id: 'asm', child_item_id: 'part2' }
    ]
    const routing: RoutingData[] = [
      createRoutingData('part1', 's1', '012', 1, 30),
      createRoutingData('part2', 's2', '012', 1, 45),
      createRoutingData('asm', 's3', '014', 1, 60)
    ]
    const completions: CompletionData[] = []

    const result = calculateSchedule(parts, bom, routing, completions)

    const part1Task = result.tasks.find(t => t.item_id === 'part1')!
    const part2Task = result.tasks.find(t => t.item_id === 'part2')!
    const asmTask = result.tasks.find(t => t.item_id === 'asm')!

    // Assembly should start after both parts finish
    const latestPartEnd = Math.max(part1Task.end_day, part2Task.end_day)
    expect(asmTask.start_day).toBeGreaterThan(latestPartEnd)
  })

  it('respects station capacity limits', () => {
    // Create multiple parts that exceed single-day capacity for waterjet
    // Waterjet (012) has 12 * 60 = 720 minutes capacity
    const parts: PartData[] = [
      createPartData('p1', 'stp00001'),
      createPartData('p2', 'stp00002'),
      createPartData('p3', 'stp00003')
    ]
    const bom: BomData[] = []
    const routing: RoutingData[] = [
      createRoutingData('p1', 's1', '012', 1, 400),  // 400 min
      createRoutingData('p2', 's2', '012', 1, 400),  // 400 min (exceeds day 0)
      createRoutingData('p3', 's3', '012', 1, 400)   // 400 min (exceeds day 1)
    ]
    const completions: CompletionData[] = []

    const result = calculateSchedule(parts, bom, routing, completions)

    // Should need multiple days due to capacity
    expect(result.total_days).toBeGreaterThan(1)

    // Check station days tracking
    const waterjetSlots = result.stationDays.get('012')!
    expect(waterjetSlots.length).toBeGreaterThan(1)
  })
})
