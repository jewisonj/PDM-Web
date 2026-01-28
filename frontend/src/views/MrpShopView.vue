<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../services/supabase'

const router = useRouter()

interface Workstation {
  id: string
  station_code: string
  station_name: string
  sort_order: number
}

interface MrpProject {
  id: string
  project_code: string
  description: string
  customer: string
  due_date: string
  status: string
}

interface QueueItem {
  item_id: string
  item_number: string
  item_name: string
  description: string
  est_time_min: number
  qty_complete: number
  qty_total: number
  has_pdf: boolean
  pdf_url: string | null
}

// Station icon mapping based on station name keywords
function getStationIcon(stationName: string): string {
  const name = stationName.toLowerCase()

  if (name.includes('deburr') || name.includes('grind') || name.includes('file')) {
    return 'deburr'
  }
  if (name.includes('saw') || name.includes('band') || name.includes('cut')) {
    return 'bandsaw'
  }
  if (name.includes('water') || name.includes('jet') || name.includes('laser')) {
    return 'waterjet'
  }
  if (name.includes('brake') || name.includes('bend') || name.includes('press') || name.includes('form')) {
    return 'pressbrake'
  }
  if (name.includes('weld')) {
    return 'weld'
  }
  if (name.includes('drill') || name.includes('tap') || name.includes('mill')) {
    return 'drill'
  }
  if (name.includes('paint') || name.includes('coat') || name.includes('finish')) {
    return 'paint'
  }
  if (name.includes('assem') || name.includes('pack')) {
    return 'assembly'
  }
  return 'generic'
}

const workstations = ref<Workstation[]>([])
const selectedStation = ref<Workstation | null>(null)
const projects = ref<MrpProject[]>([])
const selectedProject = ref<MrpProject | null>(null)
const queueItems = ref<QueueItem[]>([])
const loading = ref(true)
const loadingQueue = ref(false)
const error = ref('')
const workerName = ref('')

// Time logging
const selectedItems = ref<Set<string>>(new Set())
const timeToLog = ref(0)

// PDF Panel
const showPdfPanel = ref(false)
const selectedPartForPdf = ref<QueueItem | null>(null)
const pdfPanelWidth = ref(500)
const isResizing = ref(false)

async function loadWorkstations() {
  loading.value = true
  error.value = ''

  try {
    const { data, error: queryError } = await supabase
      .from('workstations')
      .select('*')
      .order('sort_order')

    if (queryError) throw queryError
    workstations.value = data || []
  } catch (e: any) {
    error.value = e.message || 'Failed to load workstations'
  } finally {
    loading.value = false
  }
}

async function selectStation(station: Workstation) {
  selectedStation.value = station
  selectedProject.value = null
  queueItems.value = []
  closePdfPanel()

  try {
    // Load projects that have parts routed through this station
    const { data, error: queryError } = await supabase
      .from('mrp_projects')
      .select('*')
      .in('status', ['Released', 'Setup'])
      .order('due_date')

    if (queryError) throw queryError
    projects.value = data || []
  } catch (e: any) {
    error.value = e.message || 'Failed to load projects'
  }
}

async function selectProject(project: MrpProject) {
  selectedProject.value = project
  loadingQueue.value = true
  selectedItems.value = new Set()
  closePdfPanel()

  try {
    // Get all items in this project that have routing through the selected station
    const { data: routingData, error: routingError } = await supabase
      .from('routing')
      .select(`
        item_id,
        est_time_min,
        items(item_number, name, description)
      `)
      .eq('station_id', selectedStation.value!.id)

    if (routingError) throw routingError

    // Get project parts
    const { data: partsData, error: partsError } = await supabase
      .from('mrp_project_parts')
      .select('item_id, quantity')
      .eq('project_id', project.id)

    if (partsError) throw partsError

    // Get completion status
    const { data: completionData, error: completionError } = await supabase
      .from('part_completion')
      .select('item_id, qty_complete')
      .eq('project_id', project.id)
      .eq('station_id', selectedStation.value!.id)

    if (completionError) throw completionError

    // Get item IDs that will be in the queue
    const itemIds = (routingData || [])
      .filter(r => partsData?.some(p => p.item_id === r.item_id))
      .map(r => r.item_id)

    // Get PDF files for these items
    const { data: filesData, error: filesError } = await supabase
      .from('files')
      .select('item_id, file_path, storage_path')
      .in('item_id', itemIds)
      .eq('file_type', 'PDF')

    if (filesError) console.warn('Failed to load PDF files:', filesError)

    const completionMap = new Map(completionData?.map(c => [c.item_id, c.qty_complete]) || [])
    const partsMap = new Map(partsData?.map(p => [p.item_id, p.quantity]) || [])
    const filesMap = new Map(filesData?.map(f => [f.item_id, f.storage_path || f.file_path]) || [])

    // Build queue items
    queueItems.value = (routingData || [])
      .filter(r => partsMap.has(r.item_id))
      .map(r => ({
        item_id: r.item_id,
        item_number: (r.items as any)?.item_number || '',
        item_name: (r.items as any)?.name || '',
        description: (r.items as any)?.description || '',
        est_time_min: r.est_time_min,
        qty_complete: completionMap.get(r.item_id) || 0,
        qty_total: partsMap.get(r.item_id) || 1,
        has_pdf: filesMap.has(r.item_id),
        pdf_url: filesMap.get(r.item_id) || null
      }))

  } catch (e: any) {
    error.value = e.message || 'Failed to load queue'
  } finally {
    loadingQueue.value = false
  }
}

function toggleItemSelection(itemId: string) {
  if (selectedItems.value.has(itemId)) {
    selectedItems.value.delete(itemId)
  } else {
    selectedItems.value.add(itemId)
  }
  // Trigger reactivity
  selectedItems.value = new Set(selectedItems.value)
}

function selectAllItems() {
  if (selectedItems.value.size === queueItems.value.length) {
    selectedItems.value = new Set()
  } else {
    selectedItems.value = new Set(queueItems.value.map(i => i.item_id))
  }
}

async function logTime() {
  if (selectedItems.value.size === 0 || timeToLog.value <= 0) return

  try {
    const logs = Array.from(selectedItems.value).map(item_id => ({
      project_id: selectedProject.value!.id,
      item_id,
      station_id: selectedStation.value!.id,
      worker: workerName.value || 'Unknown',
      time_min: timeToLog.value
    }))

    const { error: insertError } = await supabase
      .from('time_logs')
      .insert(logs)

    if (insertError) throw insertError

    timeToLog.value = 0
    alert(`Logged ${timeToLog.value} minutes for ${selectedItems.value.size} items`)
  } catch (e: any) {
    error.value = e.message || 'Failed to log time'
  }
}

async function markComplete() {
  if (selectedItems.value.size === 0) return

  try {
    // Upsert completion records
    for (const item_id of selectedItems.value) {
      const item = queueItems.value.find(i => i.item_id === item_id)
      if (!item) continue

      const { error: upsertError } = await supabase
        .from('part_completion')
        .upsert({
          project_id: selectedProject.value!.id,
          item_id,
          station_id: selectedStation.value!.id,
          qty_complete: item.qty_total,
          completed_by: workerName.value || 'Unknown'
        }, {
          onConflict: 'project_id,item_id,station_id'
        })

      if (upsertError) throw upsertError
    }

    // Refresh queue
    await selectProject(selectedProject.value!)
    selectedItems.value = new Set()
  } catch (e: any) {
    error.value = e.message || 'Failed to mark complete'
  }
}

function backToStations() {
  selectedStation.value = null
  selectedProject.value = null
  queueItems.value = []
  closePdfPanel()
}

function backToProjects() {
  selectedProject.value = null
  queueItems.value = []
  closePdfPanel()
}

function goHome() {
  router.push('/')
}

// PDF Panel functions
function openPdfPanel(item: QueueItem) {
  selectedPartForPdf.value = item
  showPdfPanel.value = true
}

function closePdfPanel() {
  showPdfPanel.value = false
  selectedPartForPdf.value = null
}

async function getPdfUrl(storagePath: string | null): Promise<string | null> {
  if (!storagePath) return null
  try {
    const { data } = await supabase.storage.from('files').getPublicUrl(storagePath)
    return data?.publicUrl || null
  } catch {
    return null
  }
}

// Panel resize handlers
function startResize(e: MouseEvent | TouchEvent) {
  isResizing.value = true
  const startX = 'touches' in e ? e.touches[0].clientX : e.clientX
  const startWidth = pdfPanelWidth.value

  const handleMove = (moveEvent: MouseEvent | TouchEvent) => {
    if (!isResizing.value) return
    const currentX = 'touches' in moveEvent ? moveEvent.touches[0].clientX : moveEvent.clientX
    const diff = startX - currentX
    pdfPanelWidth.value = Math.min(Math.max(startWidth + diff, 300), window.innerWidth - 400)
  }

  const handleEnd = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', handleMove)
    document.removeEventListener('mouseup', handleEnd)
    document.removeEventListener('touchmove', handleMove)
    document.removeEventListener('touchend', handleEnd)
  }

  document.addEventListener('mousemove', handleMove)
  document.addEventListener('mouseup', handleEnd)
  document.addEventListener('touchmove', handleMove)
  document.addEventListener('touchend', handleEnd)
}

onMounted(() => {
  loadWorkstations()
})
</script>

<template>
  <div class="shop-terminal">
    <!-- Station Selection -->
    <div v-if="!selectedStation" class="station-selection">
      <header class="terminal-header">
        <button class="back-btn" @click="goHome">
          <i class="pi pi-arrow-left"></i>
          Home
        </button>
        <h1>Shop Terminal</h1>
        <p>Select your workstation</p>
      </header>

      <div v-if="loading" class="loading">
        <i class="pi pi-spin pi-spinner"></i>
        Loading stations...
      </div>

      <div v-else class="stations-grid">
        <div
          v-for="station in workstations"
          :key="station.id"
          class="station-card"
          @click="selectStation(station)"
        >
          <!-- Custom SVG icons based on station type -->
          <div class="station-icon">
            <!-- Deburr Icon -->
            <svg v-if="getStationIcon(station.station_name) === 'deburr'" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 52 L28 36 L32 32 L48 16" />
              <path d="M28 36 L26 42 L32 40 L28 36" />
              <ellipse cx="48" cy="16" rx="6" ry="3" transform="rotate(-45 48 16)" />
              <path d="M52 12 L56 8" />
              <path d="M54 16 C56 14, 58 16, 56 18" />
              <path d="M50 20 C52 18, 54 20, 52 22" />
            </svg>
            <!-- Bandsaw Icon -->
            <svg v-else-if="getStationIcon(station.station_name) === 'bandsaw'" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="14" y="38" width="36" height="18" rx="2" />
              <path d="M20 38 L20 28 L44 28 L44 38" />
              <path d="M32 28 L32 12" />
              <path d="M26 16 L38 16" />
              <path d="M18 16 L12 22 L18 28" />
              <path d="M46 16 L52 22 L46 28" />
              <path d="M24 22 L28 18 L32 22 L36 18 L40 22" />
            </svg>
            <!-- Waterjet Icon -->
            <svg v-else-if="getStationIcon(station.station_name) === 'waterjet'" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="22" y="8" width="20" height="24" rx="2" />
              <path d="M26 16 L38 16" />
              <path d="M26 22 L38 22" />
              <path d="M32 32 L32 44" />
              <path d="M28 32 L36 32 L34 36 L30 36 Z" />
              <ellipse cx="12" cy="14" rx="4" ry="6" />
              <path d="M32 48 L32 56" stroke-dasharray="2 2" />
              <path d="M20 52 L44 52" />
            </svg>
            <!-- Press Brake Icon -->
            <svg v-else-if="getStationIcon(station.station_name) === 'pressbrake'" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="12" y="8" width="40" height="12" rx="2" />
              <path d="M32 20 L32 30" />
              <path d="M24 30 L40 30 L36 38 L28 38 Z" />
              <path d="M16 44 L48 44" />
              <path d="M24 44 L32 38 L40 44" />
              <rect x="12" y="48" width="40" height="8" rx="2" />
            </svg>
            <!-- Weld Icon -->
            <svg v-else-if="getStationIcon(station.station_name) === 'weld'" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M32 12 L32 28" />
              <path d="M26 16 L38 16" />
              <path d="M28 28 L36 28 L38 34 L26 34 Z" />
              <path d="M32 34 L32 44" />
              <circle cx="32" cy="48" r="6" />
              <path d="M26 48 L20 54" />
              <path d="M38 48 L44 54" />
              <path d="M16 42 L20 38" />
              <path d="M48 42 L44 38" />
            </svg>
            <!-- Drill Icon -->
            <svg v-else-if="getStationIcon(station.station_name) === 'drill'" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="26" y="8" width="12" height="20" rx="2" />
              <path d="M32 28 L32 42" />
              <path d="M28 32 L36 32" />
              <path d="M30 42 L34 42 L32 52 Z" />
              <path d="M20 56 L44 56" />
              <rect x="16" y="56" width="32" height="4" />
            </svg>
            <!-- Paint Icon -->
            <svg v-else-if="getStationIcon(station.station_name) === 'paint'" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="20" y="8" width="24" height="16" rx="3" />
              <path d="M32 24 L32 32" />
              <path d="M24 32 L40 32 L38 40 L26 40 Z" />
              <path d="M28 40 L28 56" />
              <path d="M36 40 L36 56" />
              <path d="M24 56 L40 56" />
              <ellipse cx="16" cy="48" rx="4" ry="6" />
              <ellipse cx="48" cy="48" rx="4" ry="6" />
            </svg>
            <!-- Assembly Icon -->
            <svg v-else-if="getStationIcon(station.station_name) === 'assembly'" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="12" y="20" width="16" height="16" rx="2" />
              <rect x="36" y="20" width="16" height="16" rx="2" />
              <rect x="24" y="40" width="16" height="16" rx="2" />
              <path d="M28 20 L36 20" />
              <path d="M20 36 L32 40" />
              <path d="M44 36 L32 40" />
            </svg>
            <!-- Generic/Default Icon -->
            <svg v-else viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="32" cy="32" r="20" />
              <circle cx="32" cy="32" r="8" />
              <path d="M32 12 L32 8" />
              <path d="M32 56 L32 52" />
              <path d="M12 32 L8 32" />
              <path d="M56 32 L52 32" />
            </svg>
          </div>
          <h2>{{ station.station_name }}</h2>
          <span class="station-code">{{ station.station_code }}</span>
        </div>
      </div>
    </div>

    <!-- Project Selection -->
    <div v-else-if="!selectedProject" class="project-selection">
      <header class="terminal-header">
        <button class="back-btn" @click="backToStations">
          <i class="pi pi-arrow-left"></i>
          Stations
        </button>
        <div class="header-info">
          <h1>{{ selectedStation.station_name }}</h1>
          <p>Select a project</p>
        </div>
      </header>

      <div class="projects-list">
        <div v-if="projects.length === 0" class="empty-state">
          <i class="pi pi-inbox"></i>
          <p>No active projects</p>
        </div>

        <div
          v-for="project in projects"
          :key="project.id"
          class="project-row"
          @click="selectProject(project)"
        >
          <div class="project-info">
            <span class="project-code">{{ project.project_code }}</span>
            <span class="project-desc">{{ project.description }}</span>
          </div>
          <span class="project-status" :class="project.status.toLowerCase().replace(' ', '-')">
            {{ project.status }}
          </span>
        </div>
      </div>
    </div>

    <!-- Work Queue -->
    <div v-else class="work-queue" :class="{ 'panel-open': showPdfPanel }">
      <div class="queue-main-area">
        <header class="terminal-header">
          <button class="back-btn" @click="backToProjects">
            <i class="pi pi-arrow-left"></i>
            Projects
          </button>
          <div class="header-info">
            <h1>Shop Floor Terminal - <span class="station-highlight">{{ selectedStation.station_code }} - {{ selectedStation.station_name }}</span></h1>
          </div>
          <div class="header-actions">
            <input v-model="workerName" type="text" placeholder="Your name..." class="worker-input" />
            <button class="back-btn" @click="backToStations">Change Station</button>
          </div>
        </header>

        <div class="project-bar">
          <label>Project:</label>
          <span class="project-name">{{ selectedProject.project_code }} - {{ selectedProject.description }}</span>
          <span class="project-meta">Due: {{ selectedProject.due_date || 'N/A' }} | Customer: {{ selectedProject.customer || 'N/A' }}</span>
        </div>

        <div v-if="error" class="error-message">{{ error }}</div>

        <div v-if="loadingQueue" class="loading">
          <i class="pi pi-spin pi-spinner"></i>
          Loading queue...
        </div>

        <div v-else class="queue-container">
          <div class="queue-header">
            <h2>Parts Queue</h2>
            <div class="selection-info">
              <span>{{ selectedItems.size }} selected</span> |
              <strong>{{ queueItems.filter(i => selectedItems.has(i.item_id)).reduce((sum, i) => sum + i.qty_total, 0) }} total qty</strong>
            </div>
          </div>

          <div v-if="queueItems.length === 0" class="empty-state">
            <i class="pi pi-check-circle"></i>
            <p>No items in queue for this station</p>
          </div>

          <table v-else class="parts-table">
            <thead>
              <tr>
                <th style="width: 50px">
                  <input
                    type="checkbox"
                    class="select-check"
                    :checked="selectedItems.size === queueItems.length && queueItems.length > 0"
                    @change="selectAllItems"
                  />
                </th>
                <th>Part Number</th>
                <th>Description</th>
                <th style="width: 80px">Qty</th>
                <th style="width: 90px">Est Time</th>
                <th style="width: 100px">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in queueItems"
                :key="item.item_id"
                :class="{
                  selected: selectedItems.has(item.item_id),
                  completed: item.qty_complete >= item.qty_total
                }"
                @click="toggleItemSelection(item.item_id)"
              >
                <td @click.stop>
                  <input
                    type="checkbox"
                    class="select-check"
                    :checked="selectedItems.has(item.item_id)"
                    @change="toggleItemSelection(item.item_id)"
                  />
                </td>
                <td>
                  <div class="part-num">
                    {{ item.item_number }}
                    <span
                      v-if="item.has_pdf"
                      class="pdf-icon"
                      @click.stop="openPdfPanel(item)"
                      title="View PDF"
                    >
                      <i class="pi pi-file-pdf"></i>
                    </span>
                  </div>
                  <div class="part-type">{{ item.item_name }}</div>
                </td>
                <td>{{ item.description || '-' }}</td>
                <td><span class="qty-badge">{{ item.qty_total }}</span></td>
                <td class="est-time">{{ item.est_time_min * item.qty_total }} min</td>
                <td :class="item.qty_complete >= item.qty_total ? 'status-complete' : 'status-pending'">
                  {{ item.qty_complete >= item.qty_total ? 'Complete' : `${item.qty_complete}/${item.qty_total}` }}
                </td>
              </tr>
            </tbody>
          </table>

          <div class="action-bar">
            <div class="time-input-group">
              <label>Time (min):</label>
              <input v-model.number="timeToLog" type="number" min="0" step="0.5" />
            </div>
            <button class="btn btn-warning" @click="logTime" :disabled="selectedItems.size === 0 || timeToLog <= 0">
              <i class="pi pi-stopwatch"></i> Log Time
            </button>
            <button class="btn btn-success" @click="markComplete" :disabled="selectedItems.size === 0">
              <i class="pi pi-check"></i> Mark Complete
            </button>
            <div class="spacer"></div>
            <button class="btn btn-secondary" @click="selectedItems = new Set()">Clear Selection</button>
          </div>
        </div>
      </div>

      <!-- PDF Panel -->
      <div v-if="showPdfPanel" class="pdf-panel" :style="{ width: pdfPanelWidth + 'px' }">
        <div
          class="panel-resize-handle"
          @mousedown="startResize"
          @touchstart="startResize"
        ></div>
        <div class="panel-header">
          <h2>{{ selectedPartForPdf?.item_number }}</h2>
          <button class="panel-close" @click="closePdfPanel">&times;</button>
        </div>
        <div class="panel-content">
          <div class="panel-info">
            <div class="info-row">
              <span class="label">Description</span>
              <span class="value">{{ selectedPartForPdf?.description || selectedPartForPdf?.item_name || '-' }}</span>
            </div>
            <div class="info-row">
              <span class="label">Project Qty</span>
              <span class="value">{{ selectedPartForPdf?.qty_total }}</span>
            </div>
            <div class="info-row">
              <span class="label">Routing Time</span>
              <span class="value">{{ selectedPartForPdf?.est_time_min }} min</span>
            </div>
          </div>
          <div class="pdf-viewer">
            <iframe
              v-if="selectedPartForPdf?.pdf_url"
              :src="selectedPartForPdf.pdf_url"
            ></iframe>
            <div v-else class="no-pdf">No PDF available</div>
          </div>
        </div>
        <div class="panel-footer">
          <a
            v-if="selectedPartForPdf?.pdf_url"
            :href="selectedPartForPdf.pdf_url"
            target="_blank"
            class="pdf-download-btn"
          >
            <i class="pi pi-file-pdf"></i>
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }

.shop-terminal {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  font-family: system-ui, sans-serif;
}

.terminal-header {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1rem 1.5rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
}

.terminal-header h1 {
  font-size: 1.5rem;
  margin: 0;
  color: #fff;
}

.station-highlight {
  color: #38bdf8;
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

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 4rem;
  color: #9ca3af;
  font-size: 1.25rem;
}

/* Station Selection */
.station-selection {
  min-height: 100vh;
  overflow-y: auto;
}

.stations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 1rem;
  padding: 2rem;
  max-width: 900px;
  margin: 0 auto;
}

.station-card {
  background: #1e293b;
  border: 2px solid #334155;
  border-radius: 0.75rem;
  padding: 1.5rem 1rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.station-card:hover {
  background: #334155;
  border-color: #38bdf8;
}

.station-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto 1rem;
  color: #38bdf8;
}

.station-icon svg {
  width: 100%;
  height: 100%;
}

.station-card h2 {
  margin: 0 0 0.25rem 0;
  font-size: 1rem;
  color: #fff;
}

.station-code {
  font-size: 1.75rem;
  font-weight: 700;
  color: #38bdf8;
}

/* Project Selection */
.project-selection {
  min-height: 100vh;
  overflow-y: auto;
}

.projects-list {
  padding: 1.5rem 2rem;
  max-width: 800px;
  margin: 0 auto;
}

.project-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 0.5rem;
  margin-bottom: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.project-row:hover {
  background: #334155;
  border-color: #38bdf8;
}

.project-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.project-code {
  font-weight: 600;
  font-size: 1.1rem;
  color: #fff;
}

.project-desc {
  color: #9ca3af;
  font-size: 0.9rem;
}

.project-status {
  padding: 0.35rem 0.75rem;
  border-radius: 0.25rem;
  font-size: 0.8rem;
  font-weight: 500;
}

.project-status.released {
  background: #065f46;
  color: #a7f3d0;
}

.project-status.setup {
  background: #374151;
  color: #d1d5db;
}

.project-status.on-hold {
  background: #92400e;
  color: #fde68a;
}

/* Work Queue */
.work-queue {
  display: grid;
  grid-template-columns: 1fr;
  height: 100vh;
  overflow: hidden;
}

.work-queue.panel-open {
  grid-template-columns: 1fr auto;
}

.queue-main-area {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.project-bar {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  padding: 0.75rem 1.5rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
}

.project-bar label {
  font-size: 0.9rem;
  color: #9ca3af;
}

.project-name {
  font-weight: 600;
  color: #e5e7eb;
}

.project-meta {
  margin-left: 1rem;
  color: #9ca3af;
  font-size: 0.9rem;
}

.worker-input {
  padding: 0.6rem 1rem;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 0.375rem;
  color: #e5e7eb;
  font-size: 0.9rem;
  width: 150px;
}

.error-message {
  margin: 1rem 1.5rem;
  padding: 0.75rem 1rem;
  background: #7f1d1d;
  border-radius: 0.5rem;
  color: #fca5a5;
}

.queue-container {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.5rem;
  display: flex;
  flex-direction: column;
}

.queue-container::-webkit-scrollbar { width: 8px; }
.queue-container::-webkit-scrollbar-track { background: #0f172a; }
.queue-container::-webkit-scrollbar-thumb { background: #374151; border-radius: 4px; }
.queue-container::-webkit-scrollbar-thumb:hover { background: #4b5563; }

.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.queue-header h2 {
  margin: 0;
  font-size: 1.125rem;
}

.selection-info {
  font-size: 0.875rem;
  color: #9ca3af;
}

.selection-info strong {
  color: #38bdf8;
}

/* Parts Table */
.parts-table {
  width: 100%;
  border-collapse: collapse;
  flex: 1;
}

.parts-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  background: #1e293b;
  font-size: 0.75rem;
  color: #9ca3af;
  text-transform: uppercase;
  position: sticky;
  top: 0;
  z-index: 1;
}

.parts-table td {
  padding: 1rem;
  border-bottom: 1px solid #1e293b;
}

.parts-table tbody tr {
  cursor: pointer;
  transition: background 0.1s;
}

.parts-table tbody tr:hover {
  background: #1e293b;
}

.parts-table tbody tr.selected {
  background: #1e3a5f;
}

.parts-table tbody tr.completed {
  opacity: 0.5;
}

.parts-table tbody tr.completed td {
  text-decoration: line-through;
}

.part-num {
  font-weight: 600;
  font-size: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.part-type {
  font-size: 0.8rem;
  color: #9ca3af;
}

.pdf-icon {
  color: #f87171;
  cursor: pointer;
  font-size: 0.9rem;
}

.pdf-icon:hover {
  color: #fca5a5;
}

.qty-badge {
  background: #374151;
  padding: 0.375rem 0.75rem;
  border-radius: 0.375rem;
  font-weight: 600;
  font-size: 1rem;
}

.est-time {
  text-align: right;
  color: #9ca3af;
}

.status-complete {
  color: #6ee7b7;
}

.status-pending {
  color: #fcd34d;
}

.select-check {
  width: 1.25rem;
  height: 1.25rem;
  cursor: pointer;
  accent-color: #2563eb;
}

/* Action Bar */
.action-bar {
  display: flex;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  background: #0f172a;
  border-top: 1px solid #1e293b;
  flex-wrap: wrap;
  align-items: center;
  margin-top: auto;
}

.action-bar .spacer {
  flex: 1;
}

.time-input-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.time-input-group label {
  font-size: 0.875rem;
  color: #9ca3af;
}

.time-input-group input {
  width: 70px;
  padding: 0.75rem;
  border-radius: 0.375rem;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e5e7eb;
  font-size: 1rem;
  text-align: center;
}

.btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.25rem;
  border-radius: 0.5rem;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 600;
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

.btn-success:hover:not(:disabled) {
  background: #047857;
}

.btn-warning {
  background: #d97706;
  color: white;
}

.btn-warning:hover:not(:disabled) {
  background: #b45309;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* PDF Panel */
.pdf-panel {
  background: #0f172a;
  border-left: 1px solid #1e293b;
  display: flex;
  flex-direction: column;
  height: 100vh;
  position: relative;
  min-width: 300px;
  max-width: calc(100vw - 400px);
}

.panel-resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
  background: transparent;
  z-index: 10;
}

.panel-resize-handle:hover {
  background: #38bdf8;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid #1e293b;
}

.panel-header h2 {
  margin: 0;
  font-size: 1.125rem;
}

.panel-close {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 1.75rem;
  cursor: pointer;
  padding: 0.25rem 0.75rem;
  line-height: 1;
}

.panel-close:hover {
  color: #e5e7eb;
}

.panel-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-info {
  padding: 1rem;
  border-bottom: 1px solid #1e293b;
}

.info-row {
  margin-bottom: 0.75rem;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-row .label {
  display: block;
  font-size: 0.7rem;
  color: #9ca3af;
  text-transform: uppercase;
  margin-bottom: 0.125rem;
}

.info-row .value {
  font-size: 0.9rem;
  color: #e5e7eb;
}

.pdf-viewer {
  flex: 1;
  background: #fff;
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
  height: 100%;
  color: #6b7280;
  font-size: 0.875rem;
  background: #1e293b;
}

.panel-footer {
  padding: 0.75rem 1rem;
  border-top: 1px solid #1e293b;
  display: flex;
  justify-content: flex-end;
}

.pdf-download-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2.5rem;
  height: 2.5rem;
  background: #dc2626;
  border-radius: 50%;
  color: white;
  text-decoration: none;
  font-size: 1.25rem;
}

.pdf-download-btn:hover {
  background: #b91c1c;
}

.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #6b7280;
}

.empty-state i {
  font-size: 3rem;
  margin-bottom: 1rem;
  display: block;
}
</style>
