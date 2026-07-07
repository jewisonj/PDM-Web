<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../services/supabase'
import {
  calculateSchedule,
  type ScheduleResult,
  type PartData,
  type BomData,
  type RoutingData
} from '../utils/scheduling'

interface Project {
  id: string
  project_code: string
  description: string | null
  customer: string | null
  due_date: string | null
  top_assembly: string | null
  status: string
}

interface Part {
  id: string
  item_id: string
  item_number: string
  description: string | null
  quantity: number
  parent_assembly: string | null
  part_type: string | null
  routing: RoutingOp[]
  completedStations: number
  totalStations: number
  status: 'not-started' | 'in-progress' | 'complete'
  progress: number
  level?: number
}

interface RoutingOp {
  id: string
  est_time_min: number | null
}

const router = useRouter()

// State
const loading = ref(true)
const projects = ref<Project[]>([])
const selectedProjectCode = ref('')
const currentProject = ref<Project | null>(null)
const parts = ref<Part[]>([])
const completion = ref<any[]>([])

// Scheduling state
const schedule = ref<ScheduleResult | null>(null)
const completionChannel = ref<any>(null)

// Raw data for re-scheduling
const rawPartsData = ref<PartData[]>([])
const rawBomData = ref<BomData[]>([])
const rawRoutingData = ref<RoutingData[]>([])

// Helper: Check if a date is a weekend (Saturday=6, Sunday=0)
function isWeekend(date: Date): boolean {
  const day = date.getDay()
  return day === 0 || day === 6
}

// Helper: Add working days to a date (skipping weekends)
function addWorkingDays(date: Date, numDays: number): Date {
  const result = new Date(date)
  let remaining = numDays
  while (remaining > 0) {
    result.setDate(result.getDate() + 1)
    if (!isWeekend(result)) {
      remaining--
    }
  }
  return result
}

// Helper: Subtract working days from a date (skipping weekends)
function subtractWorkingDays(date: Date, numDays: number): Date {
  const result = new Date(date)
  let remaining = numDays
  while (remaining > 0) {
    result.setDate(result.getDate() - 1)
    if (!isWeekend(result)) {
      remaining--
    }
  }
  return result
}

// Computed
const hierarchy = computed(() => buildHierarchy())

const projectInfo = computed(() => {
  if (!currentProject.value) return null

  const totalMinutes = parts.value.reduce((sum, p) => {
    const routingTime = p.routing.reduce((t, r) => t + (r.est_time_min || 0), 0)
    return sum + (routingTime * p.quantity)
  }, 0)

  // Use schedule-based days if available, otherwise fall back to simple calculation
  const scheduledDays = schedule.value?.total_days || Math.ceil(totalMinutes / 480)
  let startDate = '-'
  if (currentProject.value.due_date) {
    const due = new Date(currentProject.value.due_date)
    // Subtract working days (skip weekends)
    const start = subtractWorkingDays(due, scheduledDays)
    startDate = start.toISOString().split('T')[0] ?? ''
  }

  return {
    customer: currentProject.value.customer || '-',
    dueDate: currentProject.value.due_date || '-',
    startDate,
    partCount: parts.value.length,
    hours: (totalMinutes / 60).toFixed(1) + 'h',
    scheduledDays
  }
})

const days = computed(() => {
  if (!currentProject.value) return []

  let startDate = new Date()
  let endDate = new Date()

  // Use schedule-based days if available
  const scheduledDays = schedule.value?.total_days || 14

  if (currentProject.value.due_date) {
    endDate = new Date(currentProject.value.due_date)
    endDate = addWorkingDays(endDate, 5) // Buffer after due date (working days)

    startDate = subtractWorkingDays(new Date(currentProject.value.due_date), scheduledDays + 2) // Buffer before start
  } else {
    // No due date - show from today
    startDate = subtractWorkingDays(startDate, 2)
    endDate = addWorkingDays(endDate, scheduledDays + 5)
  }

  // Generate only working days (skip weekends)
  const result: Date[] = []
  const d = new Date(startDate)
  while (d <= endDate) {
    if (!isWeekend(d)) {
      result.push(new Date(d))
    }
    d.setDate(d.getDate() + 1)
  }
  return result
})

const summary = computed(() => {
  const complete = parts.value.filter(p => p.status === 'complete').length
  const inProgress = parts.value.filter(p => p.status === 'in-progress').length
  const notStarted = parts.value.filter(p => p.status === 'not-started').length
  const total = parts.value.length || 1

  return {
    complete,
    inProgress,
    notStarted,
    completePercent: (complete / total * 100),
    inProgressPercent: (inProgress / total * 100),
    notStartedPercent: (notStarted / total * 100)
  }
})

// Methods
async function loadProjects() {
  const { data, error } = await supabase
    .from('mrp_projects')
    .select('*')
    .order('project_code')

  if (error) {
    console.error('Failed to load projects:', error)
    return
  }
  projects.value = data || []
}

async function loadProject() {
  // Unsubscribe from previous project's completion channel
  if (completionChannel.value) {
    supabase.removeChannel(completionChannel.value)
    completionChannel.value = null
  }

  if (!selectedProjectCode.value) {
    currentProject.value = null
    parts.value = []
    schedule.value = null
    return
  }

  loading.value = true
  currentProject.value = projects.value.find(p => p.project_code === selectedProjectCode.value) || null
  if (!currentProject.value) {
    loading.value = false
    return
  }

  // Load parts for this project (with thickness for scheduling)
  const { data: partsData, error: partsError } = await supabase
    .from('mrp_project_parts')
    .select(`
      id,
      item_id,
      quantity,
      items (
        id,
        item_number,
        description,
        thickness
      )
    `)
    .eq('project_id', currentProject.value.id)

  if (partsError) {
    console.error('Failed to load parts:', partsError)
    loading.value = false
    return
  }

  // Load completion data
  const { data: completionData } = await supabase
    .from('part_completion')
    .select('item_id, station_id')
    .eq('project_id', currentProject.value.id)

  completion.value = completionData || []

  // Load BOM for hierarchy and scheduling
  const itemIds = (partsData || []).map(p => (p as any).items?.id).filter(Boolean)

  // Get all BOM relationships where items in this project are involved
  const { data: bomData, error: bomError } = await supabase
    .from('bom')
    .select('parent_item_id, child_item_id')
    .or(`parent_item_id.in.(${itemIds.join(',')}),child_item_id.in.(${itemIds.join(',')})`)

  console.log('BOM query result:', { count: bomData?.length, error: bomError })

  const bomMap = new Map<string, string>()
  for (const b of bomData || []) {
    bomMap.set(b.child_item_id, b.parent_item_id)
  }

  // Load ALL routing at once (with workstation info for scheduling)
  const { data: routingData, error: routingError } = await supabase
    .from('routing')
    .select(`
      id,
      item_id,
      station_id,
      sequence,
      est_time_min,
      workstations (
        station_code,
        station_name
      )
    `)
    .in('item_id', itemIds)
    .order('sequence')

  console.log('Routing query result:', {
    count: routingData?.length,
    error: routingError,
    sampleWithWorkstation: routingData?.slice(0, 3).map(r => ({
      item_id: r.item_id,
      station_code: (r as any).workstations?.station_code
    }))
  })

  // Group routing by item for quick lookup
  const routingByItem = new Map<string, any[]>()
  for (const r of routingData || []) {
    if (!routingByItem.has(r.item_id)) {
      routingByItem.set(r.item_id, [])
    }
    routingByItem.get(r.item_id)!.push(r)
  }

  // Store raw data for re-scheduling
  rawPartsData.value = (partsData || []).map(p => ({
    item_id: p.item_id,
    quantity: p.quantity,
    items: (p as any).items
  }))
  rawBomData.value = (bomData || []).map(b => ({
    parent_item_id: b.parent_item_id,
    child_item_id: b.child_item_id
  }))
  rawRoutingData.value = (routingData || []).map(r => ({
    id: r.id,
    item_id: r.item_id,
    station_id: r.station_id,
    sequence: r.sequence,
    est_time_min: r.est_time_min,
    workstations: (r as any).workstations
  }))

  // Calculate schedule
  schedule.value = calculateSchedule(
    rawPartsData.value,
    rawBomData.value,
    rawRoutingData.value,
    completionData || []
  )

  console.log('Schedule calculated:', {
    totalDays: schedule.value.total_days,
    partsCount: schedule.value.parts.size,
    tasksCount: schedule.value.tasks.length
  })

  // Process parts for display (using schedule data for status)
  const processedParts: Part[] = []
  for (const p of partsData || []) {
    const item = (p as any).items
    if (!item) continue

    const routing = routingByItem.get(item.id) || []
    const partSchedule = schedule.value.parts.get(p.item_id)

    const completedStations = partSchedule?.completed_stations.size || 0
    const totalStations = routing.length
    const status = partSchedule?.status || (
      completedStations === 0 ? 'not-started' :
      completedStations >= totalStations ? 'complete' : 'in-progress'
    )
    const progress = totalStations > 0 ? (completedStations / totalStations * 100) : 0

    // Find parent assembly from BOM
    const parentId = bomMap.get(item.id)
    const parentPart = (partsData || []).find(pp => (pp as any).items?.id === parentId)
    const parentAssembly = parentPart ? (parentPart as any).items?.item_number : null

    processedParts.push({
      id: p.id,
      item_id: item.id,
      item_number: item.item_number,
      description: item.description,
      quantity: p.quantity,
      parent_assembly: parentAssembly,
      part_type: null,
      routing: routing.map((r: any) => ({ id: r.id, est_time_min: r.est_time_min })),
      completedStations,
      totalStations,
      status,
      progress
    })
  }

  parts.value = processedParts

  // Subscribe to completion changes for real-time updates
  completionChannel.value = supabase
    .channel(`completion-${currentProject.value.id}`)
    .on('postgres_changes', {
      event: '*',
      schema: 'public',
      table: 'part_completion',
      filter: `project_id=eq.${currentProject.value.id}`
    }, () => {
      refreshSchedule()
    })
    .subscribe()

  loading.value = false
}

async function refreshSchedule() {
  if (!currentProject.value) return

  // Reload completion data
  const { data: completionData } = await supabase
    .from('part_completion')
    .select('item_id, station_id')
    .eq('project_id', currentProject.value.id)

  completion.value = completionData || []

  // Recalculate schedule with fresh completion data
  schedule.value = calculateSchedule(
    rawPartsData.value,
    rawBomData.value,
    rawRoutingData.value,
    completionData || []
  )

  // Update parts status from new schedule
  for (const part of parts.value) {
    const partSchedule = schedule.value.parts.get(part.item_id)
    if (partSchedule) {
      part.completedStations = partSchedule.completed_stations.size
      part.status = partSchedule.status
      part.progress = part.totalStations > 0
        ? (part.completedStations / part.totalStations * 100)
        : 0
    }
  }

  console.log('Schedule refreshed:', {
    totalDays: schedule.value.total_days,
    completedParts: [...schedule.value.parts.values()].filter(p => p.status === 'complete').length
  })
}

function buildHierarchy(): (Part & { level: number })[] {
  const result: (Part & { level: number })[] = []
  const topAssembly = currentProject.value?.top_assembly

  const topLevel = parts.value.filter(p =>
    !p.parent_assembly || p.parent_assembly === topAssembly
  )

  function addPart(part: Part, level: number) {
    result.push({ ...part, level })
    const children = parts.value.filter(p => p.parent_assembly === part.item_number)
    children.forEach(child => addPart(child, level + 1))
  }

  // Sort: assemblies first (check item_number patterns)
  topLevel.sort((a, b) => {
    const aIsAsm = a.item_number.toLowerCase().includes('asm') ? 0 : 1
    const bIsAsm = b.item_number.toLowerCase().includes('asm') ? 0 : 1
    return aIsAsm - bIsAsm || a.item_number.localeCompare(b.item_number)
  })

  topLevel.forEach(p => addPart(p, 0))
  return result
}

function getLevelClass(level: number): string {
  if (level === 0) return 'assembly'
  if (level === 1) return 'sub-assembly'
  return 'part'
}

function isToday(date: Date): boolean {
  const today = new Date()
  return date.toDateString() === today.toDateString()
}

function formatDay(date: Date): string {
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function getBarStyle(part: Part): { left: string; width: string; progress?: string } | null {
  if (!part.routing || part.routing.length === 0) return null

  const partSchedule = schedule.value?.parts.get(part.item_id)
  const dayWidth = 100 / days.value.length

  if (partSchedule && partSchedule.tasks.length > 0) {
    // Use scheduled start/end days
    const firstTask = partSchedule.tasks[0]!
    const lastTask = partSchedule.tasks[partSchedule.tasks.length - 1]!

    const startDay = firstTask.start_day
    const endDay = lastTask.end_day + (lastTask.end_hour / 24)
    const durationDays = Math.max(endDay - startDay, 0.5)

    const left = (startDay * dayWidth) + '%'
    const width = Math.max(durationDays * dayWidth, dayWidth * 0.5) + '%'

    return {
      left,
      width,
      progress: part.status === 'in-progress' ? `${part.progress}%` : undefined
    }
  }

  // Fallback to simple calculation if no schedule
  const totalTime = part.routing.reduce((t, r) => t + (r.est_time_min || 0), 0) * part.quantity
  const barDays = Math.max(1, Math.ceil(totalTime / 480))

  const startOffset = 2
  const left = (startOffset * dayWidth) + '%'
  const width = (barDays * dayWidth) + '%'

  return {
    left,
    width,
    progress: part.status === 'in-progress' ? `${part.progress}%` : undefined
  }
}

function goToDashboard() {
  router.push('/mrp/dashboard')
}

function openBuildTracker() {
  if (!selectedProjectCode.value) return
  router.push(`/mrp/tracker/${selectedProjectCode.value}`)
}

function openBuildBook() {
  if (!selectedProjectCode.value) return
  router.push(`/mrp/book/${selectedProjectCode.value}`)
}

onMounted(async () => {
  await loadProjects()
  loading.value = false
})

onUnmounted(() => {
  // Clean up subscription
  if (completionChannel.value) {
    supabase.removeChannel(completionChannel.value)
    completionChannel.value = null
  }
})
</script>

<template>
  <div class="project-tracking-page">
    <!-- Header -->
    <div class="header">
      <h1>Project Tracking</h1>
      <div class="header-actions">
        <select v-model="selectedProjectCode" @change="loadProject">
          <option value="">-- Select Project --</option>
          <option v-for="p in projects" :key="p.id" :value="p.project_code">
            {{ p.project_code }} - {{ p.description || p.customer || '' }}
          </option>
        </select>
        <button
          v-if="selectedProjectCode"
          class="btn btn-secondary"
          @click="openBuildTracker"
        >
          🖨 Build Tracker Sheet
        </button>
        <button
          v-if="selectedProjectCode"
          class="btn btn-secondary"
          @click="openBuildBook"
        >
          📖 Build Book
        </button>
        <button class="btn btn-secondary" @click="goToDashboard">
          &larr; Dashboard
        </button>
      </div>
    </div>

    <!-- Project Info -->
    <div v-if="projectInfo" class="project-info">
      <div class="info-item">
        <div class="info-label">Customer</div>
        <div class="info-value">{{ projectInfo.customer }}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Due Date</div>
        <div class="info-value">{{ projectInfo.dueDate }}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Start Date</div>
        <div class="info-value">{{ projectInfo.startDate }}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Total Parts</div>
        <div class="info-value">{{ projectInfo.partCount }}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Est. Hours</div>
        <div class="info-value">{{ projectInfo.hours }}</div>
      </div>
      <div class="info-item">
        <div class="info-label">Scheduled Days</div>
        <div class="info-value">{{ projectInfo.scheduledDays }} days</div>
      </div>
    </div>

    <!-- Legend -->
    <div class="legend">
      <div class="legend-item">
        <div class="legend-box complete"></div>
        Complete
      </div>
      <div class="legend-item">
        <div class="legend-box in-progress"></div>
        In Progress
      </div>
      <div class="legend-item">
        <div class="legend-box not-started"></div>
        Not Started
      </div>
    </div>

    <!-- Content -->
    <div class="content">
      <div v-if="!currentProject" class="no-project">
        Select a project to view tracking
      </div>

      <div v-else-if="loading" class="loading">
        Loading project data...
      </div>

      <div v-else class="gantt-container">
        <div class="gantt">
          <!-- Labels Column -->
          <div class="gantt-labels">
            <div class="gantt-label assembly header-label">Part / Assembly</div>
            <div
              v-for="item in hierarchy"
              :key="item.id"
              :class="['gantt-label', getLevelClass(item.level)]"
              :title="item.item_number"
            >
              {{ item.item_number }}
              {{ item.description ? '- ' + item.description.substring(0, 20) : '' }}
            </div>
          </div>

          <!-- Chart Column -->
          <div class="gantt-chart">
            <!-- Date Header -->
            <div class="gantt-header">
              <div
                v-for="(day, idx) in days"
                :key="idx"
                :class="['gantt-day', { weekend: isWeekend(day), today: isToday(day) }]"
              >
                {{ formatDay(day) }}
              </div>
            </div>

            <!-- Rows -->
            <div v-for="item in hierarchy" :key="item.id" class="gantt-row">
              <div
                v-for="(day, idx) in days"
                :key="idx"
                :class="['gantt-cell', { weekend: isWeekend(day) }]"
              ></div>
              <div
                v-if="getBarStyle(item)"
                :class="['gantt-bar', item.status]"
                :style="{
                  left: getBarStyle(item)!.left,
                  width: getBarStyle(item)!.width,
                  '--progress': getBarStyle(item)!.progress
                }"
              >
                <span class="gantt-bar-text">
                  {{ item.quantity }}&times;
                  {{ Math.round(item.routing.reduce((t, r) => t + (r.est_time_min || 0), 0) * item.quantity) }}min
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- Summary Bar -->
        <div class="summary-bar">
          <div class="summary-title">Overall Progress</div>
          <div class="progress-bar-container">
            <div
              class="progress-segment complete"
              :style="{ width: summary.completePercent + '%' }"
            >
              {{ summary.complete > 0 ? summary.complete : '' }}
            </div>
            <div
              class="progress-segment in-progress"
              :style="{ width: summary.inProgressPercent + '%' }"
            >
              {{ summary.inProgress > 0 ? summary.inProgress : '' }}
            </div>
            <div
              class="progress-segment not-started"
              :style="{ width: summary.notStartedPercent + '%' }"
            >
              {{ summary.notStarted > 0 ? summary.notStarted : '' }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.project-tracking-page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
}

.header h1 {
  margin: 0;
  font-size: 20px;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.btn-secondary {
  background: #374151;
  color: white;
}

.btn-secondary:hover {
  background: #4b5563;
}

select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e5e7eb;
  font-size: 13px;
}

.project-info {
  padding: 16px 24px;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  display: flex;
  gap: 32px;
}

.info-item {
}

.info-label {
  font-size: 11px;
  color: #9ca3af;
}

.info-value {
  font-size: 14px;
  font-weight: 500;
}

.legend {
  padding: 12px 24px;
  display: flex;
  gap: 20px;
  font-size: 12px;
  border-bottom: 1px solid #1e293b;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-box {
  width: 16px;
  height: 16px;
  border-radius: 3px;
}

.legend-box.complete {
  background: #059669;
}

.legend-box.in-progress {
  background: #2563eb;
}

.legend-box.not-started {
  background: #374151;
}

.content {
}

.no-project,
.loading {
  text-align: center;
  padding: 60px;
  color: #6b7280;
}

.gantt-container {
  padding: 16px 24px;
  overflow-x: auto;
}

.gantt {
  display: grid;
  grid-template-columns: 280px 1fr;
  min-width: 1000px;
}

.gantt-labels {
  border-right: 1px solid #1e293b;
}

.gantt-label {
  height: 36px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border-bottom: 1px solid #1e293b;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gantt-label.header-label {
  font-weight: 700;
}

.gantt-label.assembly {
  background: #1e293b;
  font-weight: 600;
}

.gantt-label.sub-assembly {
  padding-left: 24px;
  background: #0f172a;
}

.gantt-label.part {
  padding-left: 36px;
  color: #9ca3af;
}

.gantt-chart {
  position: relative;
}

.gantt-header {
  display: flex;
  height: 36px;
  border-bottom: 1px solid #1e293b;
  background: #0f172a;
}

.gantt-day {
  flex: 1;
  min-width: 30px;
  text-align: center;
  font-size: 10px;
  color: #9ca3af;
  display: flex;
  align-items: center;
  justify-content: center;
  border-right: 1px solid #1e293b;
}

.gantt-day.weekend {
  background: #0c1222;
}

.gantt-day.today {
  background: #1e3a5f;
  color: #38bdf8;
  font-weight: 600;
}

.gantt-row {
  height: 36px;
  display: flex;
  border-bottom: 1px solid #1e293b;
  position: relative;
}

.gantt-cell {
  flex: 1;
  min-width: 30px;
  border-right: 1px solid #0f172a;
}

.gantt-cell.weekend {
  background: #0c1222;
}

.gantt-bar {
  position: absolute;
  height: 20px;
  top: 8px;
  border-radius: 3px;
  min-width: 8px;
}

.gantt-bar.complete {
  background: #059669;
}

.gantt-bar.in-progress {
  background: linear-gradient(90deg, #059669 var(--progress, 50%), #2563eb var(--progress, 50%));
}

.gantt-bar.not-started {
  background: #374151;
}

.gantt-bar-text {
  position: absolute;
  left: 4px;
  top: 2px;
  font-size: 10px;
  color: white;
  white-space: nowrap;
}

.summary-bar {
  margin-top: 16px;
  padding: 16px 24px;
  background: #0f172a;
  border-radius: 8px;
}

.summary-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
}

.progress-bar-container {
  height: 24px;
  background: #1e293b;
  border-radius: 4px;
  overflow: hidden;
  display: flex;
}

.progress-segment {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 500;
}

.progress-segment.complete {
  background: #059669;
}

.progress-segment.in-progress {
  background: #2563eb;
}

.progress-segment.not-started {
  background: #374151;
}
</style>
