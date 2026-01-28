<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../services/supabase'

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

// Computed
const hierarchy = computed(() => buildHierarchy())

const projectInfo = computed(() => {
  if (!currentProject.value) return null

  const totalMinutes = parts.value.reduce((sum, p) => {
    const routingTime = p.routing.reduce((t, r) => t + (r.est_time_min || 0), 0)
    return sum + (routingTime * p.quantity)
  }, 0)

  const workDays = Math.ceil(totalMinutes / 480)
  let startDate = '-'
  if (currentProject.value.due_date) {
    const due = new Date(currentProject.value.due_date)
    due.setDate(due.getDate() - workDays)
    startDate = due.toISOString().split('T')[0]
  }

  return {
    customer: currentProject.value.customer || '-',
    dueDate: currentProject.value.due_date || '-',
    startDate,
    partCount: parts.value.length,
    hours: (totalMinutes / 60).toFixed(1) + 'h'
  }
})

const days = computed(() => {
  if (!currentProject.value) return []

  const today = new Date()
  let startDate = new Date()
  let endDate = new Date()

  if (currentProject.value.due_date) {
    endDate = new Date(currentProject.value.due_date)
    endDate.setDate(endDate.getDate() + 7)

    const totalMinutes = parts.value.reduce((sum, p) => {
      const routingTime = p.routing.reduce((t, r) => t + (r.est_time_min || 0), 0)
      return sum + (routingTime * p.quantity)
    }, 0)
    const workDays = Math.ceil(totalMinutes / 480)
    startDate = new Date(currentProject.value.due_date)
    startDate.setDate(startDate.getDate() - workDays - 7)
  } else {
    startDate.setDate(startDate.getDate() - 7)
    endDate.setDate(endDate.getDate() + 30)
  }

  const result: Date[] = []
  const d = new Date(startDate)
  while (d <= endDate) {
    result.push(new Date(d))
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
  if (!selectedProjectCode.value) {
    currentProject.value = null
    parts.value = []
    return
  }

  loading.value = true
  currentProject.value = projects.value.find(p => p.project_code === selectedProjectCode.value) || null
  if (!currentProject.value) {
    loading.value = false
    return
  }

  // Load parts for this project
  const { data: partsData, error: partsError } = await supabase
    .from('mrp_project_parts')
    .select(`
      id,
      item_id,
      quantity,
      items (
        id,
        item_number,
        description
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
    .select('*')
    .eq('project_id', currentProject.value.id)

  completion.value = completionData || []

  // Load BOM for hierarchy
  const itemIds = (partsData || []).map(p => (p as any).items?.id).filter(Boolean)
  const { data: bomData } = await supabase
    .from('bom')
    .select('parent_item_id, child_item_id')
    .in('parent_item_id', itemIds)

  const bomMap = new Map<string, string>()
  for (const b of bomData || []) {
    bomMap.set(b.child_item_id, b.parent_item_id)
  }

  // Process parts
  const processedParts: Part[] = []
  for (const p of partsData || []) {
    const item = (p as any).items
    if (!item) continue

    // Load routing for this item
    const { data: routingData } = await supabase
      .from('routing')
      .select('id, est_time_min')
      .eq('item_id', item.id)

    const routing = routingData || []
    const completedStations = completion.value.filter(c => c.item_id === item.id).length
    const totalStations = routing.length
    const status = completedStations === 0 ? 'not-started' :
      completedStations >= totalStations ? 'complete' : 'in-progress'
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
      routing,
      completedStations,
      totalStations,
      status,
      progress
    })
  }

  parts.value = processedParts
  loading.value = false
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

function isWeekend(date: Date): boolean {
  const day = date.getDay()
  return day === 0 || day === 6
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

  const totalTime = part.routing.reduce((t, r) => t + (r.est_time_min || 0), 0) * part.quantity
  const barDays = Math.max(1, Math.ceil(totalTime / 480))

  const dayWidth = 100 / days.value.length
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

onMounted(async () => {
  await loadProjects()
  loading.value = false
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
