/**
 * Project Scheduling Algorithm
 *
 * Calculates realistic shop floor schedules with:
 * - BOM-based assembly dependencies (assemblies wait for all child parts)
 * - Per-station capacity limits (waterjet, press brake, etc.)
 * - Priority scoring (leaf parts first, smaller assemblies, thickness grouping)
 * - Task splitting across days when capacity exceeded
 */

// ============================================================================
// INTERFACES
// ============================================================================

export interface ScheduledTask {
  id: string                    // `${item_id}_${station_id}`
  item_id: string
  item_number: string
  station_id: string
  station_code: string
  sequence: number
  duration_min: number          // est_time_min * quantity
  quantity: number
  start_day: number
  start_hour: number
  end_day: number
  end_hour: number
  predecessors: string[]
  is_complete: boolean
}

export interface PartSchedule {
  item_id: string
  item_number: string
  description: string | null
  thickness: number | null
  quantity: number
  is_assembly: boolean
  child_item_ids: string[]
  all_descendant_ids: string[]
  bom_depth: number             // 0 = leaf, higher = nested assembly
  tasks: ScheduledTask[]
  earliest_start_day: number
  status: 'not-started' | 'in-progress' | 'complete'
  completed_stations: Set<string>
}

export interface StationDaySlot {
  station_code: string
  day: number
  total_minutes: number
  used_minutes: number
  remaining_minutes: number
  tasks: ScheduledTask[]
}

export interface ScheduleResult {
  parts: Map<string, PartSchedule>
  tasks: ScheduledTask[]
  stationDays: Map<string, StationDaySlot[]>  // station_code -> day slots
  total_days: number
}

// Input data types (from Supabase queries)
export interface PartData {
  item_id: string
  quantity: number
  items: {
    id: string
    item_number: string
    description: string | null
    thickness: number | null
  }
}

export interface BomData {
  parent_item_id: string
  child_item_id: string
}

export interface RoutingData {
  id: string
  item_id: string
  station_id: string
  sequence: number
  est_time_min: number | null
  time_basis?: 'per_unit' | 'per_line_item'  // per_unit = multiply by qty, per_line_item = fixed time
  workstations: {
    station_code: string
    station_name: string
  }
}

export interface CompletionData {
  item_id: string
  station_id: string
}

// ============================================================================
// STATION CAPACITY CONFIGURATION
// ============================================================================

interface StationCapacityConfig {
  daily_minutes: number
  max_parallel: number
}

// Hardcoded station capacities (can be made configurable later)
// NOTE: total daily capacity = daily_minutes * max_parallel
const STATION_CAPACITIES: Record<string, StationCapacityConfig> = {
  // Single-machine bottleneck stations
  '012': { daily_minutes: 12 * 60, max_parallel: 1 },  // Waterjet - runs overnight, 1 machine (720 min)
  '013': { daily_minutes: 8 * 60, max_parallel: 1 },   // Press Brake - 1 machine (480 min)
  '010': { daily_minutes: 8 * 60, max_parallel: 1 },   // Saw - 1 machine (480 min)

  // Assembly stations - 3 parallel stations
  '014': { daily_minutes: 8 * 60, max_parallel: 3 },   // Weld Jigging/Pre-assembly (1440 min)
  '025': { daily_minutes: 8 * 60, max_parallel: 3 },   // Mech Assembly (1440 min)

  // Welding pool - shared welders (treat as single pool)
  '015': { daily_minutes: 8 * 60, max_parallel: 2 },   // Tig Welding (960 min)
  '016': { daily_minutes: 8 * 60, max_parallel: 2 },   // Dual Shield Weld (960 min)
  '017': { daily_minutes: 8 * 60, max_parallel: 2 },   // Weld Cleanup (960 min)

  // Finishing/support operations
  '011': { daily_minutes: 8 * 60, max_parallel: 2 },   // Deburr (960 min)
  '050': { daily_minutes: 8 * 60, max_parallel: 2 },   // Inspection (960 min)
  '005': { daily_minutes: 8 * 60, max_parallel: 1 },   // Receiving (480 min)
}

// Default for unlisted stations: 8 hours with 2 parallel workers = 16 man-hours
const DEFAULT_CAPACITY: StationCapacityConfig = {
  daily_minutes: 8 * 60,   // 8 hours per worker
  max_parallel: 2          // 2 workers (960 min = 16 man-hours total)
}

function getStationCapacity(stationCode: string): StationCapacityConfig {
  return STATION_CAPACITIES[stationCode] || DEFAULT_CAPACITY
}

// ============================================================================
// STEP 1: BUILD DEPENDENCY GRAPH
// ============================================================================

export function buildDependencyGraph(
  partsData: PartData[],
  bomData: BomData[]
): Map<string, PartSchedule> {
  const parts = new Map<string, PartSchedule>()

  // Create PartSchedule for each project part
  for (const p of partsData) {
    const item = p.items
    if (!item) {
      continue
    }

    parts.set(p.item_id, {
      item_id: p.item_id,
      item_number: item.item_number,
      description: item.description,
      thickness: item.thickness,
      quantity: p.quantity,
      is_assembly: false,
      child_item_ids: [],
      all_descendant_ids: [],
      bom_depth: 0,
      tasks: [],
      earliest_start_day: 0,
      status: 'not-started',
      completed_stations: new Set()
    })
  }

  // Build parent-child relationships from BOM
  // Only consider relationships where both parent and child are in the project
  let bomMatchCount = 0
  for (const bom of bomData) {
    const parent = parts.get(bom.parent_item_id)
    const child = parts.get(bom.child_item_id)
    if (parent && child) {
      bomMatchCount++
      parent.is_assembly = true
      if (!parent.child_item_ids.includes(bom.child_item_id)) {
        parent.child_item_ids.push(bom.child_item_id)
      }
    }
  }

  // Recursively calculate all descendants for each assembly
  function getDescendants(itemId: string, visited: Set<string> = new Set()): string[] {
    if (visited.has(itemId)) return [] // Circular reference protection
    visited.add(itemId)

    const part = parts.get(itemId)
    if (!part) return []

    const descendants: string[] = []
    for (const childId of part.child_item_ids) {
      descendants.push(childId)
      descendants.push(...getDescendants(childId, new Set(visited)))
    }
    return [...new Set(descendants)] // Deduplicate
  }

  // Calculate BOM depth (0 = leaf, higher = more nested assembly)
  function calculateDepth(itemId: string, memo: Map<string, number> = new Map()): number {
    if (memo.has(itemId)) return memo.get(itemId)!

    const part = parts.get(itemId)
    if (!part || part.child_item_ids.length === 0) {
      memo.set(itemId, 0)
      return 0
    }

    const maxChildDepth = Math.max(
      ...part.child_item_ids.map(cid => calculateDepth(cid, memo))
    )
    const depth = maxChildDepth + 1
    memo.set(itemId, depth)
    return depth
  }

  const depthMemo = new Map<string, number>()
  for (const [itemId, part] of parts) {
    part.all_descendant_ids = getDescendants(itemId)
    part.bom_depth = calculateDepth(itemId, depthMemo)
  }

  return parts
}

// ============================================================================
// STEP 2: CREATE SCHEDULED TASKS WITH PREDECESSORS
// ============================================================================

export function createScheduledTasks(
  parts: Map<string, PartSchedule>,
  routingData: RoutingData[],
  completionData: CompletionData[]
): ScheduledTask[] {
  const tasks: ScheduledTask[] = []

  // Build completion lookup: item_id -> Set of completed station_ids
  const completionMap = new Map<string, Set<string>>()
  for (const c of completionData) {
    if (!completionMap.has(c.item_id)) {
      completionMap.set(c.item_id, new Set())
    }
    completionMap.get(c.item_id)!.add(c.station_id)
  }

  // Group routing by item_id
  const routingByItem = new Map<string, RoutingData[]>()
  for (const r of routingData) {
    if (!routingByItem.has(r.item_id)) {
      routingByItem.set(r.item_id, [])
    }
    routingByItem.get(r.item_id)!.push(r)
  }

  // Sort each item's routing by sequence
  for (const [, routing] of routingByItem) {
    routing.sort((a, b) => a.sequence - b.sequence)
  }

  // Create tasks for each part
  for (const [itemId, part] of parts) {
    const routing = routingByItem.get(itemId) || []
    const completedStations = completionMap.get(itemId) || new Set()
    part.completed_stations = completedStations

    let prevTaskId: string | null = null

    for (let i = 0; i < routing.length; i++) {
      const r = routing[i]!
      const taskId = `${itemId}_${r.station_id}`
      const isComplete = completedStations.has(r.station_id)
      const isFirstOperation = i === 0

      const predecessors: string[] = []

      // Predecessor 1: Previous operation in same part's routing
      if (prevTaskId) {
        predecessors.push(prevTaskId)
      }

      // Predecessor 2: For assembly's first operation, all descendant parts' LAST operations
      if (part.is_assembly && isFirstOperation) {
        for (const descendantId of part.all_descendant_ids) {
          const descendantRouting = routingByItem.get(descendantId) || []
          if (descendantRouting.length > 0) {
            const lastOp = descendantRouting[descendantRouting.length - 1]!
            const depTaskId = `${descendantId}_${lastOp.station_id}`
            predecessors.push(depTaskId)
          }
        }
      }

      // Respect time_basis: per_line_item = fixed time, per_unit = multiply by qty
      const timeBasis = r.time_basis || 'per_unit'
      const durationMin = timeBasis === 'per_line_item'
        ? (r.est_time_min || 0)           // Fixed time regardless of quantity
        : (r.est_time_min || 0) * part.quantity  // Traditional: multiply by quantity

      const task: ScheduledTask = {
        id: taskId,
        item_id: itemId,
        item_number: part.item_number,
        station_id: r.station_id,
        station_code: r.workstations?.station_code || '',
        sequence: r.sequence,
        duration_min: durationMin,
        quantity: part.quantity,
        start_day: 0,
        start_hour: 0,
        end_day: 0,
        end_hour: 0,
        predecessors,
        is_complete: isComplete
      }

      tasks.push(task)
      part.tasks.push(task)
      prevTaskId = taskId
    }

    // Calculate part status
    const totalOps = part.tasks.length
    const completedOps = part.tasks.filter(t => t.is_complete).length
    part.status = completedOps === 0 ? 'not-started' :
                  completedOps >= totalOps ? 'complete' : 'in-progress'
  }

  return tasks
}

// ============================================================================
// STEP 3: PRIORITY SCORING
// ============================================================================

interface TaskWithPriority {
  task: ScheduledTask
  score: number
  thickness: number | null
}

export function prioritizeTasks(
  tasks: ScheduledTask[],
  parts: Map<string, PartSchedule>
): ScheduledTask[] {
  const scored: TaskWithPriority[] = tasks.map(task => {
    const part = parts.get(task.item_id)!
    let score = 0

    // Priority 1: Already completed tasks get highest priority (lock position early)
    if (task.is_complete) {
      score += 10000
    }

    // Priority 2: Leaf parts before assemblies (lower bom_depth = higher priority)
    score += (10 - part.bom_depth) * 100

    // Priority 3: Parts from smaller assemblies first (fewer descendants = higher priority)
    const descendantCount = part.all_descendant_ids.length
    score += Math.max(0, 50 - descendantCount)

    // Priority 4: Earlier routing sequence = higher priority
    score += (1000 - task.sequence)

    return { task, score, thickness: part.thickness }
  })

  // Sort by score descending, then by thickness to group similar thicknesses
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score
    // Secondary: group by thickness (nulls last)
    const thkA = a.thickness ?? 9999
    const thkB = b.thickness ?? 9999
    return thkA - thkB
  })

  return scored.map(s => s.task)
}

// ============================================================================
// STEP 4: CAPACITY-CONSTRAINED SCHEDULING
// ============================================================================

export function scheduleWithCapacity(
  tasks: ScheduledTask[],
  parts: Map<string, PartSchedule>
): ScheduleResult {
  // Prioritize tasks
  const prioritizedTasks = prioritizeTasks(tasks, parts)

  // Task lookup by ID
  const taskMap = new Map(tasks.map(t => [t.id, t]))

  // Track which tasks are scheduled
  const scheduled = new Set<string>()

  // Per-station day slots
  const stationDays = new Map<string, StationDaySlot[]>()

  // Helper: Get or create a day slot for a station
  function getStationSlot(stationCode: string, day: number): StationDaySlot {
    if (!stationDays.has(stationCode)) {
      stationDays.set(stationCode, [])
    }
    const slots = stationDays.get(stationCode)!

    while (slots.length <= day) {
      const config = getStationCapacity(stationCode)
      const totalMin = config.daily_minutes * config.max_parallel
      slots.push({
        station_code: stationCode,
        day: slots.length,
        total_minutes: totalMin,
        used_minutes: 0,
        remaining_minutes: totalMin,
        tasks: []
      })
    }
    return slots[day]!
  }

  // Helper: Check if all predecessors are scheduled
  function predecessorsScheduled(task: ScheduledTask): boolean {
    return task.predecessors.every(predId => scheduled.has(predId))
  }

  // Helper: Get earliest start day based on predecessors
  // Rule: If a part finishes an operation on Day N, it goes to the next station on Day N+1
  // This reflects real shop floor behavior - parts don't move between stations same-day
  function getEarliestStart(task: ScheduledTask): number {
    let maxStartDay = 0

    for (const predId of task.predecessors) {
      const pred = taskMap.get(predId)
      if (pred && scheduled.has(predId)) {
        // Check if this is a same-part dependency (sequential routing)
        const isSamePartDep = pred.item_id === task.item_id

        if (isSamePartDep) {
          // Same part, next operation: starts the day AFTER previous op ends
          const nextDay = pred.end_day + 1
          if (nextDay > maxStartDay) {
            maxStartDay = nextDay
          }
        } else {
          // Different part (assembly dep): can start once all parts are done
          // Assembly can start the day after last part finishes
          const nextDay = pred.end_day + 1
          if (nextDay > maxStartDay) {
            maxStartDay = nextDay
          }
        }
      }
    }

    return maxStartDay
  }

  // Helper: Find first day with available capacity starting from given day
  function findAvailableDay(stationCode: string, startDay: number, minMinutes: number = 1): number {
    let day = startDay
    const maxDays = 1000 // Safety limit

    while (day < maxDays) {
      const slot = getStationSlot(stationCode, day)
      if (slot.remaining_minutes >= minMinutes) {
        return day
      }
      day++
    }
    return startDay // Fallback
  }

  // Helper: Schedule a task, splitting across days if needed
  function scheduleTask(task: ScheduledTask, startDay: number) {
    let remainingDuration = task.duration_min
    let currentDay = startDay

    // Find first day with available capacity (starting from startDay)
    currentDay = findAvailableDay(task.station_code, startDay, Math.min(remainingDuration, 1))

    task.start_day = currentDay
    const startSlot = getStationSlot(task.station_code, currentDay)
    task.start_hour = startSlot.used_minutes / 60

    // Allocate across days
    while (remainingDuration > 0) {
      const daySlot = getStationSlot(task.station_code, currentDay)
      const availableInDay = daySlot.remaining_minutes

      if (availableInDay <= 0) {
        currentDay++
        continue
      }

      const useMinutes = Math.min(remainingDuration, availableInDay)
      daySlot.used_minutes += useMinutes
      daySlot.remaining_minutes -= useMinutes
      daySlot.tasks.push(task)

      remainingDuration -= useMinutes

      if (remainingDuration > 0) {
        currentDay++
      }
    }

    // Set end time
    const finalSlot = getStationSlot(task.station_code, currentDay)
    task.end_day = currentDay
    task.end_hour = finalSlot.used_minutes / 60

    scheduled.add(task.id)
  }

  // Main scheduling loop
  const pending = [...prioritizedTasks]
  let iterations = 0
  const maxIterations = pending.length * 100 // Safety limit

  while (pending.length > 0 && iterations < maxIterations) {
    iterations++

    // Find tasks ready to schedule (all predecessors done)
    const readyIndex = pending.findIndex(t => predecessorsScheduled(t))

    if (readyIndex === -1) {
      // No ready tasks - might have circular dependencies or missing predecessors
      // Force schedule the first pending task to break deadlock
      const task = pending.shift()!
      scheduleTask(task, 0)
      continue
    }

    const task = pending.splice(readyIndex, 1)[0]!
    const earliestDay = getEarliestStart(task)

    // Schedule starting from the earliest possible day (based on predecessors)
    // The scheduleTask function will find available capacity
    scheduleTask(task, earliestDay)
  }

  // Calculate total days
  let totalDays = 0
  for (const task of tasks) {
    if (task.end_day > totalDays) {
      totalDays = task.end_day
    }
  }
  totalDays++ // Convert from 0-indexed to count

  return {
    parts,
    tasks,
    stationDays,
    total_days: totalDays
  }
}

// ============================================================================
// MAIN ENTRY POINT
// ============================================================================

export function calculateSchedule(
  partsData: PartData[],
  bomData: BomData[],
  routingData: RoutingData[],
  completionData: CompletionData[]
): ScheduleResult {
  // Step 1: Build dependency graph
  const parts = buildDependencyGraph(partsData, bomData)

  // Step 2: Create tasks with predecessors
  const tasks = createScheduledTasks(parts, routingData, completionData)

  // Step 3 & 4: Prioritize and schedule with capacity
  const result = scheduleWithCapacity(tasks, parts)

  return result
}
