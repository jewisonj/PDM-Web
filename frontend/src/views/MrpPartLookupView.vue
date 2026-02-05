<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { supabase, API_BASE_URL } from '../services/supabase'

interface Project {
  id: string
  project_code: string
  description: string | null
  customer: string | null
  status: string
}

interface Part {
  id: string
  item_id: string
  item_number: string
  description: string | null
  quantity: number
  routing?: RoutingOp[]
  completedStations: number
  status: 'not-started' | 'in-progress' | 'complete'
}

interface RoutingOp {
  id: string
  station_id: string
  station_code: string
  station_name: string
  sequence: number
  est_time_min: number | null
}

interface PartCompletion {
  id: string
  project_id: string
  item_id: string
  station_id: string
  qty_complete: number
}

interface FileRecord {
  id: string
  item_id: string
  file_type: string
  file_path: string
  storage_path: string | null
}

const router = useRouter()
const route = useRoute()

// State
const loading = ref(true)
const projects = ref<Project[]>([])
const parts = ref<Part[]>([])
const completion = ref<PartCompletion[]>([])
const files = ref<FileRecord[]>([])

const selectedProjectCode = ref('')
const searchBox = ref('')
const currentPart = ref<Part | null>(null)
const currentRouting = ref<RoutingOp[]>([])
const partCompletion = ref<PartCompletion[]>([])
const workerName = ref('')
const timeEntries = ref<Map<string, number>>(new Map())

const statusMessage = ref('')
const statusType = ref<'success' | 'error' | ''>('')

// PDF state
const pdfUrl = ref<string | null>(null)

// Computed
const filteredParts = computed(() => {
  const search = searchBox.value.toLowerCase()
  return parts.value.filter(p =>
    p.item_number.toLowerCase().includes(search) ||
    (p.description || '').toLowerCase().includes(search)
  )
})

const selectedProject = computed(() =>
  projects.value.find(p => p.project_code === selectedProjectCode.value)
)

// Methods
async function loadProjects() {
  const { data, error } = await supabase
    .from('mrp_projects')
    .select('*')
    .in('status', ['Released', 'Setup'])
    .order('project_code')

  if (error) {
    console.error('Failed to load projects:', error)
    return
  }
  projects.value = data || []
}

async function loadParts() {
  if (!selectedProjectCode.value) {
    parts.value = []
    return
  }

  const project = projects.value.find(p => p.project_code === selectedProjectCode.value)
  if (!project) return

  loading.value = true

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
    .eq('project_id', project.id)

  if (partsError) {
    console.error('Failed to load parts:', partsError)
    loading.value = false
    return
  }

  // Load completion for this project
  const { data: completionData } = await supabase
    .from('part_completion')
    .select('*')
    .eq('project_id', project.id)

  completion.value = completionData || []

  // Process parts and load routing for each
  const processedParts: Part[] = []
  for (const p of partsData || []) {
    const item = (p as any).items
    if (!item) continue

    // Load routing for this item
    const { data: routingData } = await supabase
      .from('routing')
      .select(`
        id,
        station_id,
        sequence,
        est_time_min,
        workstations (
          id,
          station_code,
          station_name
        )
      `)
      .eq('item_id', item.id)
      .order('sequence')

    const routing = (routingData || []).map(r => ({
      id: r.id,
      station_id: r.station_id,
      station_code: (r as any).workstations?.station_code || '',
      station_name: (r as any).workstations?.station_name || '',
      sequence: r.sequence,
      est_time_min: r.est_time_min
    }))

    const completedStations = completion.value.filter(
      c => c.item_id === item.id
    ).length

    const status = completedStations === 0 ? 'not-started' :
      completedStations >= routing.length ? 'complete' : 'in-progress'

    processedParts.push({
      id: p.id,
      item_id: item.id,
      item_number: item.item_number,
      description: item.description,
      quantity: p.quantity,
      routing,
      completedStations,
      status
    })
  }

  parts.value = processedParts
  loading.value = false
}

async function loadFiles() {
  const { data } = await supabase
    .from('files')
    .select('id, item_id, file_type, file_path, storage_path')
    .eq('file_type', 'PDF')

  files.value = data || []
}

async function openPart(part: Part) {
  currentPart.value = part
  timeEntries.value = new Map()

  // Get routing
  const { data: routingData } = await supabase
    .from('routing')
    .select(`
      id,
      station_id,
      sequence,
      est_time_min,
      workstations (
        id,
        station_code,
        station_name
      )
    `)
    .eq('item_id', part.item_id)
    .order('sequence')

  currentRouting.value = (routingData || []).map(r => ({
    id: r.id,
    station_id: r.station_id,
    station_code: (r as any).workstations?.station_code || '',
    station_name: (r as any).workstations?.station_name || '',
    sequence: r.sequence,
    est_time_min: r.est_time_min
  }))

  // Get completion for this part
  const project = projects.value.find(p => p.project_code === selectedProjectCode.value)
  if (project) {
    partCompletion.value = completion.value.filter(c => c.item_id === part.item_id)
  }

  // Load PDF
  const pdfFile = files.value.find(f => f.item_id === part.item_id)
  if (pdfFile && pdfFile.storage_path) {
    const { data } = supabase.storage.from('files').getPublicUrl(pdfFile.storage_path)
    pdfUrl.value = data.publicUrl
  } else if (pdfFile && pdfFile.file_path) {
    // Fall back to API endpoint for local files
    pdfUrl.value = `${API_BASE_URL}/api/pdf?path=${encodeURIComponent(pdfFile.file_path)}`
  } else {
    pdfUrl.value = null
  }

  // Update URL
  router.replace({
    query: {
      project: selectedProjectCode.value,
      part: part.item_number
    }
  })
}

function backToList() {
  currentPart.value = null
  pdfUrl.value = null
  router.replace({
    query: {
      project: selectedProjectCode.value
    }
  })
}

function isStationComplete(stationId: string): boolean {
  return partCompletion.value.some(c => c.station_id === stationId)
}

function setTimeEntry(stationId: string, value: string) {
  const time = parseFloat(value) || 0
  if (time > 0) {
    timeEntries.value.set(stationId, time)
  } else {
    timeEntries.value.delete(stationId)
  }
}

async function saveAllTime() {
  if (!currentPart.value || timeEntries.value.size === 0) {
    showStatus('No time entries to save', 'error')
    return
  }

  const project = projects.value.find(p => p.project_code === selectedProjectCode.value)
  if (!project) return

  let saved = 0
  for (const [stationId, time] of timeEntries.value.entries()) {
    const { error } = await supabase.from('time_logs').insert({
      project_id: project.id,
      item_id: currentPart.value.item_id,
      station_id: stationId,
      worker: workerName.value || 'Unknown',
      time_min: time
    })

    if (!error) saved++
  }

  if (saved > 0) {
    timeEntries.value = new Map()
    showStatus(`Saved ${saved} time entries`, 'success')
  }
}

async function markAllComplete() {
  if (!currentPart.value) return

  const project = projects.value.find(p => p.project_code === selectedProjectCode.value)
  if (!project) return

  const incompleteStations = currentRouting.value.filter(
    r => !isStationComplete(r.station_id)
  )

  if (incompleteStations.length === 0) {
    showStatus('All stations already complete', 'error')
    return
  }

  let marked = 0
  for (const station of incompleteStations) {
    const { error } = await supabase.from('part_completion').insert({
      project_id: project.id,
      item_id: currentPart.value.item_id,
      station_id: station.station_id,
      qty_complete: currentPart.value.quantity,
      completed_by: workerName.value || 'Unknown'
    })

    if (!error) marked++
  }

  showStatus(`Marked ${marked} stations complete`, 'success')

  // Refresh
  await loadParts()
  const part = parts.value.find(p => p.item_number === currentPart.value?.item_number)
  if (part) {
    await openPart(part)
  }
}

function showStatus(msg: string, type: 'success' | 'error') {
  statusMessage.value = msg
  statusType.value = type
  setTimeout(() => {
    statusMessage.value = ''
    statusType.value = ''
  }, 3000)
}

function goToDashboard() {
  router.push('/mrp/dashboard')
}

function goToShop() {
  router.push('/mrp/shop')
}

function goToPrintLookup() {
  router.push('/mrp/print-lookup')
}

// Watch for project changes
watch(selectedProjectCode, () => {
  currentPart.value = null
  loadParts()
})

onMounted(async () => {
  await loadProjects()
  await loadFiles()

  // Check URL params
  const projectParam = route.query.project as string
  const partParam = route.query.part as string

  if (projectParam) {
    selectedProjectCode.value = projectParam
    await loadParts()

    if (partParam) {
      const part = parts.value.find(p =>
        p.item_number === partParam ||
        p.item_number.toLowerCase() === partParam.toLowerCase()
      )
      if (part) {
        await openPart(part)
      }
    }
  }

  loading.value = false
})
</script>

<template>
  <div class="part-lookup-page">
    <!-- Status Message -->
    <div v-if="statusMessage" :class="['status-msg', statusType]">
      {{ statusMessage }}
    </div>

    <!-- Landing View -->
    <div v-if="!currentPart" class="landing">
      <header class="terminal-header">
        <button class="back-btn" @click="goToDashboard">
          <i class="pi pi-arrow-left"></i>
          Dashboard
        </button>
        <div class="header-info">
          <h1>Part Lookup</h1>
          <p>Search parts and log time</p>
        </div>
        <div class="header-actions">
          <button class="nav-btn shop" @click="goToShop">
            <span class="nav-dot shop"></span>
            Shop Terminal
          </button>
          <button class="nav-btn lookup active">
            <span class="nav-dot lookup"></span>
            Part Lookup
          </button>
          <button class="nav-btn print" @click="goToPrintLookup">
            <span class="nav-dot print"></span>
            Print Lookup
          </button>
        </div>
      </header>

      <select v-model="selectedProjectCode" class="project-select-large">
        <option value="">-- Select Project --</option>
        <option v-for="p in projects" :key="p.id" :value="p.project_code">
          {{ p.project_code }} - {{ p.description || p.customer || '' }}
        </option>
      </select>

      <input
        v-model="searchBox"
        type="text"
        class="search-box"
        placeholder="Search parts..."
      />

      <div v-if="loading" class="loading-state">Loading parts...</div>

      <div v-else-if="filteredParts.length === 0 && selectedProjectCode" class="empty-state">
        No parts found
      </div>

      <div v-else class="parts-grid">
        <div
          v-for="p in filteredParts"
          :key="p.id"
          class="part-card"
          @click="openPart(p)"
        >
          <div class="part-num">{{ p.item_number }}</div>
          <div class="part-desc">{{ p.description || '-' }}</div>
          <div class="part-qty">Qty: {{ p.quantity }}</div>
          <div :class="['part-status', p.status]">
            {{ p.status.replace('-', ' ') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Part Detail View -->
    <div v-else class="part-page">
      <div class="part-header">
        <div>
          <h1><span class="part-number">{{ currentPart.item_number }}</span></h1>
          <div class="part-meta">
            {{ currentPart.description || '-' }} | Qty: {{ currentPart.quantity }}
          </div>
        </div>
        <button class="btn btn-secondary" @click="backToList">
          &larr; Back to Parts
        </button>
      </div>

      <div class="worker-section">
        <label>Your Name:</label>
        <input
          v-model="workerName"
          type="text"
          placeholder="Enter your name..."
        />
      </div>

      <div class="routing-section">
        <h2>Routing Operations</h2>
        <div v-if="currentRouting.length === 0" class="empty-routing">
          No routing defined
        </div>
        <div
          v-for="r in currentRouting"
          :key="r.id"
          :class="['routing-card', { completed: isStationComplete(r.station_id) }]"
        >
          <div class="station-code">{{ r.station_code }}</div>
          <div class="station-info">
            <h3>{{ r.station_name }}</h3>
            <div class="est-time">
              Est: {{ r.est_time_min || 0 }} min x {{ currentPart.quantity }} =
              {{ (r.est_time_min || 0) * currentPart.quantity }} min total
            </div>
          </div>
          <div class="time-input-group">
            <label>Actual:</label>
            <input
              type="number"
              placeholder="min"
              min="0"
              step="0.5"
              :disabled="isStationComplete(r.station_id)"
              @change="setTimeEntry(r.station_id, ($event.target as HTMLInputElement).value)"
            />
          </div>
          <div class="station-status">
            <div :class="['status-check', isStationComplete(r.station_id) ? 'done' : 'pending']">
              {{ isStationComplete(r.station_id) ? '&#x2714;' : '&#x25CB;' }}
            </div>
          </div>
        </div>
      </div>

      <div class="save-bar">
        <button class="btn btn-lg btn-success" @click="saveAllTime">
          Save Time Entries
        </button>
        <button class="btn btn-lg btn-success" @click="markAllComplete">
          Mark All Complete
        </button>
      </div>

      <div class="pdf-section">
        <h2>Drawing / Documentation</h2>
        <div class="pdf-viewer">
          <iframe v-if="pdfUrl" :src="pdfUrl" />
          <div v-else class="no-pdf">No PDF available for this part</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.part-lookup-page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
}

/* Terminal Header */
.terminal-header {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1rem 1.5rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  width: 100%;
}

.terminal-header h1 {
  font-size: 1.5rem;
  margin: 0;
  color: #fff;
}

.header-info {
  flex: 1;
}

.header-info h1 {
  margin: 0;
}

.header-info p {
  margin: 0.25rem 0 0 0;
  color: #9ca3af;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #374151;
  border: none;
  color: #e5e7eb;
  padding: 0.75rem 1.25rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-size: 0.9rem;
}

.back-btn:hover {
  background: #4b5563;
}

/* Navigation Buttons */
.nav-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #374151;
  border: none;
  color: white;
  padding: 0.6rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  transition: background 0.15s;
}

.nav-btn:hover {
  background: #4b5563;
}

.nav-btn.active {
  background: #1e3a5f;
  border: 1px solid #38bdf8;
}

.nav-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.nav-dot.shop { background: #eab308; }
.nav-dot.lookup { background: #22d3ee; }
.nav-dot.print { background: #f472b6; }

/* Landing Page */
.landing {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.landing > select,
.landing > input,
.landing > .parts-grid,
.landing > .loading-state,
.landing > .empty-state {
  padding-left: 20px;
  padding-right: 20px;
}

.landing > select:first-of-type {
  margin-top: 40px;
}

.project-select-large {
  width: 100%;
  max-width: 500px;
  padding: 16px 20px;
  font-size: 18px;
  border-radius: 8px;
  border: 2px solid #334155;
  background: #1e293b;
  color: #e5e7eb;
  margin-bottom: 24px;
}

.search-box {
  width: 100%;
  max-width: 500px;
  padding: 12px 16px;
  font-size: 16px;
  border-radius: 8px;
  border: 1px solid #334155;
  background: #0f172a;
  color: #e5e7eb;
  margin-bottom: 16px;
}

.loading-state,
.empty-state,
.empty-routing {
  color: #6b7280;
  text-align: center;
  padding: 40px;
}

.parts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  width: 100%;
  max-width: 900px;
}

.part-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.part-card:hover {
  border-color: #38bdf8;
  background: #0f172a;
}

.part-num {
  font-size: 18px;
  font-weight: 600;
  color: #38bdf8;
}

.part-desc {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 4px;
}

.part-qty {
  font-size: 14px;
  margin-top: 8px;
}

.part-status {
  font-size: 11px;
  margin-top: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  display: inline-block;
  text-transform: capitalize;
}

.part-status.complete {
  background: #065f46;
  color: #6ee7b7;
}

.part-status.in-progress {
  background: #1e3a8a;
  color: #93c5fd;
}

.part-status.not-started {
  background: #374151;
  color: #9ca3af;
}

/* Part Detail Page */
.part-page {
  min-height: 100vh;
}

.part-header {
  background: #0f172a;
  padding: 16px 24px;
  border-bottom: 1px solid #1e293b;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.part-header h1 {
  margin: 0;
  font-size: 24px;
}

.part-number {
  color: #38bdf8;
}

.part-meta {
  font-size: 13px;
  color: #9ca3af;
}

.btn {
  padding: 10px 20px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.btn-secondary {
  background: #374151;
  color: white;
}

.btn-secondary:hover {
  background: #4b5563;
}

.btn-success {
  background: #059669;
  color: white;
}

.btn-success:hover {
  background: #047857;
}

.btn-lg {
  padding: 14px 28px;
  font-size: 16px;
}

.worker-section {
  background: #0f172a;
  padding: 16px 24px;
  border-bottom: 1px solid #1e293b;
  display: flex;
  gap: 16px;
  align-items: center;
}

.worker-section label {
  font-size: 14px;
  color: #9ca3af;
}

.worker-section input {
  padding: 10px 16px;
  border-radius: 6px;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e5e7eb;
  font-size: 14px;
  width: 200px;
}

.routing-section {
  padding: 24px;
}

.routing-section h2 {
  margin: 0 0 16px;
  font-size: 18px;
}

.routing-card {
  background: #1e293b;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  gap: 16px;
  align-items: center;
}

.routing-card.completed {
  opacity: 0.6;
}

.station-code {
  font-size: 24px;
  font-weight: 700;
  color: #38bdf8;
  width: 60px;
  text-align: center;
}

.station-info h3 {
  margin: 0;
  font-size: 16px;
}

.station-info .est-time {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}

.time-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.time-input-group label {
  font-size: 12px;
  color: #9ca3af;
}

.time-input-group input {
  width: 80px;
  padding: 10px;
  border-radius: 6px;
  border: 1px solid #334155;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 16px;
  text-align: center;
}

.time-input-group input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.station-status {
  text-align: center;
}

.status-check {
  font-size: 28px;
}

.status-check.done {
  color: #6ee7b7;
}

.status-check.pending {
  color: #374151;
}

.save-bar {
  background: #0f172a;
  padding: 16px 24px;
  border-top: 1px solid #1e293b;
  position: sticky;
  bottom: 0;
  display: flex;
  gap: 12px;
  justify-content: center;
}

.pdf-section {
  padding: 24px;
  border-top: 1px solid #1e293b;
}

.pdf-section h2 {
  margin: 0 0 16px;
  font-size: 18px;
}

.pdf-viewer {
  background: white;
  border-radius: 8px;
  overflow: hidden;
  height: 800px;
}

.pdf-viewer iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.no-pdf {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  background: #1e293b;
  border-radius: 8px;
  color: #6b7280;
}

.status-msg {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 14px;
  z-index: 100;
}

.status-msg.success {
  background: #065f46;
  color: #6ee7b7;
}

.status-msg.error {
  background: #7f1d1d;
  color: #fca5a5;
}
</style>
