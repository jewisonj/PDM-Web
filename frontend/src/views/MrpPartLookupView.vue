<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { supabase, API_BASE_URL } from '../services/supabase'
import { getSignedUrlFromPath } from '../services/storage'
import PdfMeasure from '../components/PdfMeasure.vue'

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
  has_pdf: boolean
  has_step: boolean
  has_dxf: boolean
  routing_count: number
  material: string | null
  thickness: string | null
}

interface RoutingOp {
  id: string
  station_id: string
  station_code: string
  station_name: string
  sequence: number
  est_time_min: number | null
  time_basis?: 'per_unit' | 'per_line_item'
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
  [key: string]: any // Allow other columns from database
}

const router = useRouter()
const route = useRoute()

// State
const loading = ref(true)
const projects = ref<Project[]>([])
const parts = ref<Part[]>([])
const files = ref<FileRecord[]>([])
const searchQuery = ref('')
const projectFilter = ref<string>('')
const selectedPart = ref<Part | null>(null)
const currentRouting = ref<RoutingOp[]>([])
const partCompletion = ref<PartCompletion[]>([])
const pdfUrl = ref<string | null>(null)
const activeTab = ref<'pdf' | 'details'>('pdf')

// File availability sets (like Routing Editor)
const itemsWithPdf = ref(new Set<string>())
const itemsWithStep = ref(new Set<string>())
const itemsWithDxf = ref(new Set<string>())
const itemsWithSvg = ref(new Set<string>())
const itemsWithCad = ref(new Set<string>())

// File download/generate state
const generatingDxf = ref(false)
const itemFiles = ref<FileRecord[]>([])

// Measure mode
const showMeasureMode = ref(false)

// Computed
const projectOptions = computed(() => {
  const codes = new Set(projects.value.map(p => p.project_code))
  return Array.from(codes).sort()
})

const filteredParts = computed(() => {
  let filtered = parts.value

  // Project filter
  if (projectFilter.value !== 'all') {
    filtered = filtered.filter(_p => {
      // For now, we'll need to add project info to parts or filter by selected project
      return true
    })
  }

  // Search filter
  const search = searchQuery.value.toLowerCase()
  if (search) {
    filtered = filtered.filter(p =>
      p.item_number.toLowerCase().includes(search) ||
      (p.description || '').toLowerCase().includes(search)
    )
  }

  return filtered
})

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

async function loadFiles() {
  // Load all files and build availability sets (like Routing Editor)

  // Load all file types with full data
  const { data: allFiles, error: filesError } = await supabase
    .from('files')
    .select('*')
    .not('file_path', 'is', null)

  if (filesError) {
    console.error('[Files] Query error:', filesError)
    return
  }

  // Store all files
  files.value = allFiles || []

  // Create sets for fast lookups by file type
  itemsWithPdf.value = new Set((allFiles || []).filter(f => f.file_type === 'PDF').map(f => f.item_id))
  itemsWithStep.value = new Set((allFiles || []).filter(f => f.file_type === 'STEP').map(f => f.item_id))
  itemsWithDxf.value = new Set((allFiles || []).filter(f => f.file_type === 'DXF').map(f => f.item_id))
  itemsWithSvg.value = new Set((allFiles || []).filter(f => f.file_type === 'SVG').map(f => f.item_id))
  itemsWithCad.value = new Set((allFiles || []).filter(f => f.file_type === 'CAD').map(f => f.item_id))

  console.log('[Files] Loaded files:', {
    total: files.value.length,
    pdfs: itemsWithPdf.value.size,
    steps: itemsWithStep.value.size,
    dxfs: itemsWithDxf.value.size,
    svgs: itemsWithSvg.value.size
  })
}

async function loadParts() {
  loading.value = true

  // If "All Parts" is selected, load all items from items table
  if (projectFilter.value === 'all') {
    const { data: itemsData, error: itemsError } = await supabase
      .from('items')
      .select('id, item_number, name, description, material, thickness')
      .order('item_number')

    if (itemsError) {
      console.error('Failed to load all items:', itemsError)
      loading.value = false
      return
    }

    console.log('[Parts] Loaded all items from database:', itemsData?.length || 0)

    // Get all item IDs for batch queries
    const itemIds = (itemsData || []).map(i => i.id)

    // Load routing counts for all items in one query
    const { data: routingData } = await supabase
      .from('routing')
      .select('item_id, id')
      .in('item_id', itemIds)

    // Create routing count map
    const routingCountMap = new Map<string, number>()
    for (const r of routingData || []) {
      const count = routingCountMap.get(r.item_id) || 0
      routingCountMap.set(r.item_id, count + 1)
    }

    // Process all items
    const processedParts: Part[] = (itemsData || []).map(item => {
      const has_pdf = itemsWithPdf.value.has(item.id)
      const has_step = itemsWithStep.value.has(item.id)
      const has_dxf = itemsWithDxf.value.has(item.id)

      console.log(`[Parts] Item ${item.item_number}: has_pdf=${has_pdf}, item.id=${item.id}`)

      return {
        id: item.id,
        item_id: item.id,
        item_number: item.item_number,
        description: item.name || item.description,
        quantity: 1,
        has_pdf,
        has_step,
        has_dxf,
        routing_count: routingCountMap.get(item.id) || 0,
        material: item.material,
        thickness: item.thickness
      }
    })

    // Sort alphabetically by item number
    processedParts.sort((a, b) => a.item_number.localeCompare(b.item_number))

    const partsWithPdf = processedParts.filter(p => p.has_pdf).length
    console.log('[Parts] Processed all parts:', {
      total: processedParts.length,
      withPdf: partsWithPdf,
      withRouting: processedParts.filter(p => p.routing_count > 0).length
    })

    // Show sample of itemsWithPdf Set
    const sampleIds = Array.from(itemsWithPdf.value).slice(0, 5)
    console.log('[Parts] Sample PDF item IDs in Set:', sampleIds)

    parts.value = processedParts
    loading.value = false
    return
  }

  // Load parts for specific project
  if (!projectFilter.value) {
    parts.value = []
    loading.value = false
    return
  }

  const project = projects.value.find(p => p.project_code === projectFilter.value)
  if (!project) {
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
        name,
        description,
        material,
        thickness
      )
    `)
    .eq('project_id', project.id)

  if (partsError) {
    console.error('Failed to load parts:', partsError)
    loading.value = false
    return
  }

  console.log('[Parts] Loaded project parts:', partsData?.length || 0)

  // Load completion for this project
  const { data: completionData } = await supabase
    .from('part_completion')
    .select('*')
    .eq('project_id', project.id)

  partCompletion.value = completionData || []

  // Get all item IDs for batch queries
  const itemIds = (partsData || [])
    .map(p => (p as any).items?.id)
    .filter(id => id)

  // Load routing counts for all items in one query
  const { data: routingData } = await supabase
    .from('routing')
    .select('item_id, id')
    .in('item_id', itemIds)

  // Create routing count map
  const routingCountMap = new Map<string, number>()
  for (const r of routingData || []) {
    const count = routingCountMap.get(r.item_id) || 0
    routingCountMap.set(r.item_id, count + 1)
  }

  // Process parts with file availability (using Sets like Routing Editor)
  const processedParts: Part[] = []
  for (const p of partsData || []) {
    const item = (p as any).items
    if (!item) {
      console.warn('[Parts] Skipping part with no item data:', p)
      continue
    }

    // Check file availability using Sets
    const has_pdf = itemsWithPdf.value.has(item.id)
    const has_step = itemsWithStep.value.has(item.id)
    const has_dxf = itemsWithDxf.value.has(item.id)

    console.log(`[Parts] Item ${item.item_number}: has_pdf=${has_pdf}, item.id=${item.id}`)

    processedParts.push({
      id: p.id,
      item_id: item.id,
      item_number: item.item_number,
      description: item.name || item.description,
      quantity: p.quantity,
      has_pdf,
      has_step,
      has_dxf,
      routing_count: routingCountMap.get(item.id) || 0,
      material: item.material,
      thickness: item.thickness
    })
  }

  // Sort alphabetically by item number
  processedParts.sort((a, b) => a.item_number.localeCompare(b.item_number))

  const partsWithPdf = processedParts.filter(p => p.has_pdf).length
  console.log('[Parts] Processed project parts:', {
    total: processedParts.length,
    withPdf: partsWithPdf,
    withRouting: processedParts.filter(p => p.routing_count > 0).length
  })

  // Show sample of itemsWithPdf Set
  const sampleIds = Array.from(itemsWithPdf.value).slice(0, 5)
  console.log('[Parts] Sample PDF item IDs in Set:', sampleIds)

  parts.value = processedParts
  loading.value = false
}

async function selectPart(part: Part) {
  // Set selected part immediately for UI feedback
  selectedPart.value = part
  activeTab.value = 'pdf'
  pdfUrl.value = null
  itemFiles.value = []

  // Ensure files are loaded
  if (files.value.length === 0) {
    await loadFiles()
  }

  // Load all files for this part
  itemFiles.value = files.value.filter(f => f.item_id === part.item_id)

  // Load PDF
  const pdfFile = itemFiles.value.find(f => f.file_type === 'PDF')
  if (pdfFile?.file_path) {
    const url = await getSignedUrlFromPath(pdfFile.file_path)
    // Only set if this is still the selected part (handles rapid clicking)
    if (selectedPart.value?.item_id === part.item_id && url) {
      pdfUrl.value = url
    }
  }

  // Load routing (only if still selected)
  if (selectedPart.value?.item_id === part.item_id) {
    const { data: routingData } = await supabase
      .from('routing')
      .select(`
        id,
        station_id,
        sequence,
        est_time_min,
        time_basis,
        workstations (
          id,
          station_code,
          station_name
        )
      `)
      .eq('item_id', part.item_id)
      .order('sequence')

    if (selectedPart.value?.item_id === part.item_id) {
      currentRouting.value = (routingData || []).map(r => ({
        id: r.id,
        station_id: r.station_id,
        station_code: (r as any).workstations?.station_code || '',
        station_name: (r as any).workstations?.station_name || '',
        sequence: r.sequence,
        est_time_min: r.est_time_min,
        time_basis: r.time_basis as 'per_unit' | 'per_line_item' | undefined
      }))
    }
  }

  // Update URL (only if still selected)
  if (selectedPart.value?.item_id === part.item_id) {
    router.replace({
      query: {
        project: projectFilter.value,
        part: part.item_number
      }
    })
  }
}

function goToDashboard() {
  router.push('/mrp/dashboard')
}

function goToShop() {
  router.push('/mrp/shop')
}

function isStationComplete(stationId: string): boolean {
  if (!selectedPart.value) return false
  const project = projects.value.find(p => p.project_code === projectFilter.value)
  if (!project) return false

  return partCompletion.value.some(
    c => c.item_id === selectedPart.value!.item_id && c.station_id === stationId
  )
}

// File operations
async function openFile(file: FileRecord) {
  if (!file.file_path) {
    console.warn('[File] No file_path for file:', file)
    return
  }

  try {
    const url = await getSignedUrlFromPath(file.file_path)
    if (url) {
      window.open(url, '_blank')
    }
  } catch (e) {
    console.error('[File] Error opening file:', e)
  }
}

async function generateDxf() {
  if (!selectedPart.value) return

  generatingDxf.value = true

  try {
    const response = await fetch(`${API_BASE_URL}/items/${selectedPart.value.item_id}/generate-dxf`, {
      method: 'POST'
    })

    const data = await response.json()

    if (response.ok && data.queued) {
      // Refresh files after a delay to pick up the new DXF
      setTimeout(async () => {
        await loadFiles()
        // Refresh selected part files
        itemFiles.value = files.value.filter(f => f.item_id === selectedPart.value?.item_id)
      }, 2000)
    } else if (data.dxf_exists) {
      console.log('[DXF] Already exists')
    } else {
      console.error('[DXF] Generation failed:', data)
    }
  } catch (e) {
    console.error('[DXF] Error:', e)
  } finally {
    generatingDxf.value = false
  }
}

// Computed for file badges
const hasDxf = computed(() => itemFiles.value.some(f => f.file_type === 'DXF'))
const hasStep = computed(() => itemFiles.value.some(f => f.file_type === 'STEP'))

// Watch for project changes
watch(projectFilter, () => {
  selectedPart.value = null
  pdfUrl.value = null
  loadParts()
})

onMounted(async () => {
  await loadProjects()
  await loadFiles()

  // Check URL params
  const projectParam = route.query.project as string
  const partParam = route.query.part as string

  if (projectParam) {
    projectFilter.value = projectParam
    await loadParts()

    if (partParam) {
      const part = parts.value.find(p =>
        p.item_number === partParam ||
        p.item_number.toLowerCase() === partParam.toLowerCase()
      )
      if (part) {
        await selectPart(part)
      }
    }
  }

  loading.value = false
})
</script>

<template>
  <div class="part-lookup-view">
    <header class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="goToDashboard">
          <i class="pi pi-arrow-left"></i>
          Dashboard
        </button>
        <div>
          <h1>Part Lookup</h1>
        </div>
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
      </div>
    </header>

    <div class="lookup-layout">
      <!-- Left Sidebar - Part List -->
      <div class="sidebar">
        <div class="sidebar-header">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search parts..."
            class="search-input"
          />
          <div class="filter-row">
            <select v-model="projectFilter" class="filter-select">
              <option value="">Select Project...</option>
              <option value="all">All Parts</option>
              <option v-for="proj in projectOptions" :key="proj" :value="proj">
                {{ proj }}
              </option>
            </select>
          </div>
          <div class="filter-stats">
            {{ filteredParts.length }} parts
          </div>
        </div>

        <div v-if="loading" class="loading-small">Loading...</div>
        <div v-else-if="!projectFilter" class="no-selection-sidebar">
          <i class="pi pi-arrow-up"></i>
          <p>Select a project or view all parts</p>
        </div>
        <div v-else class="parts-list">
          <div
            v-for="part in filteredParts"
            :key="part.id"
            class="part-row"
            :class="{ selected: selectedPart?.id === part.id }"
            @click="selectPart(part)"
          >
            <div class="part-row-main">
              <span v-if="part.has_pdf" class="pdf-icon" title="Has PDF">
                <i class="pi pi-file-pdf"></i>
              </span>
              <span class="part-number">{{ part.item_number }}</span>
              <span v-if="part.material" class="mat-badge" title="Material assigned">Mat</span>
              <span v-if="part.routing_count > 0" class="ops-badge" :title="`${part.routing_count} operations`">
                {{ part.routing_count }} ops
              </span>
              <span v-else class="no-routing-badge">No routing</span>
            </div>
            <span class="part-name">{{ part.description || '-' }}</span>
          </div>
        </div>
      </div>

      <!-- Main Panel - PDF Viewer & Details -->
      <div class="main-panel">
        <div v-if="!selectedPart" class="no-selection">
          <i class="pi pi-arrow-left"></i>
          <p>Select a part to view</p>
        </div>

        <template v-else>
          <!-- Part Header -->
          <div class="part-header">
            <div class="part-info">
              <span class="part-number-large">{{ selectedPart.item_number }}</span>
              <span class="part-desc">{{ selectedPart.description || '-' }}</span>
            </div>
            <div class="file-tiles">
              <!-- File type badges -->
              <button
                v-for="file in itemFiles.filter(f => f.file_path)"
                :key="file.id"
                class="file-tile"
                :class="file.file_type.toLowerCase()"
                @click="openFile(file)"
                :title="`Open ${file.file_name}`"
              >
                {{ file.file_type }}
              </button>

              <!-- Generate DXF button (if has STEP but no DXF) -->
              <button
                v-if="!hasDxf && hasStep"
                class="file-tile generate-dxf"
                @click="generateDxf"
                :disabled="generatingDxf"
                title="Generate DXF flat pattern"
              >
                <i :class="generatingDxf ? 'pi pi-spin pi-spinner' : 'pi pi-plus'"></i>
                DXF
              </button>
            </div>
          </div>

          <!-- Tabs -->
          <div class="tabs">
            <button
              class="tab"
              :class="{ active: activeTab === 'pdf' }"
              @click="activeTab = 'pdf'"
            >
              <i class="pi pi-file-pdf"></i>
              Drawing
            </button>
            <button
              class="tab"
              :class="{ active: activeTab === 'details' }"
              @click="activeTab = 'details'"
            >
              <i class="pi pi-info-circle"></i>
              Details
            </button>
          </div>

          <!-- PDF Tab -->
          <div v-if="activeTab === 'pdf'" class="tab-content">
            <div class="pdf-toolbar" v-if="pdfUrl">
              <button class="measure-btn" @click="showMeasureMode = true" title="Measure distances on the drawing">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18">
                  <path d="M4 20L20 4M4 20l3-1M4 20l1-3M20 4l-3 1M20 4l-1 3"/>
                </svg>
                Measure
              </button>
            </div>
            <div class="pdf-viewer">
              <iframe v-if="pdfUrl" :src="pdfUrl" />
              <div v-else class="no-pdf">
                <i class="pi pi-file"></i>
                <p>No PDF available for this part</p>
              </div>
            </div>
          </div>

          <!-- Details Tab -->
          <div v-if="activeTab === 'details'" class="tab-content">
            <div class="details-section">
              <h3>Part Information</h3>
              <div class="info-grid">
                <div class="info-item">
                  <span class="info-label">Part Number:</span>
                  <span class="info-value">{{ selectedPart.item_number }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">Description:</span>
                  <span class="info-value">{{ selectedPart.description || '-' }}</span>
                </div>
                <div class="info-item">
                  <span class="info-label">Quantity:</span>
                  <span class="info-value">{{ selectedPart.quantity }}</span>
                </div>
                <div class="info-item" v-if="selectedPart.material">
                  <span class="info-label">Material:</span>
                  <span class="info-value">{{ selectedPart.material }}</span>
                </div>
                <div class="info-item" v-if="selectedPart.thickness">
                  <span class="info-label">Thickness:</span>
                  <span class="info-value">{{ selectedPart.thickness }}"</span>
                </div>
              </div>

              <h3 v-if="currentRouting.length > 0">Routing Operations</h3>
              <div v-if="currentRouting.length === 0" class="empty-routing">
                No routing defined
              </div>
              <div v-else class="routing-list">
                <div
                  v-for="r in currentRouting"
                  :key="r.id"
                  class="routing-item"
                  :class="{ completed: isStationComplete(r.station_id) }"
                >
                  <div class="routing-seq">{{ r.sequence }}</div>
                  <div class="routing-info">
                    <div class="routing-station">
                      <strong>{{ r.station_code }}</strong> - {{ r.station_name }}
                    </div>
                    <div class="routing-time">
                      <template v-if="r.time_basis === 'per_line_item'">
                        Est: {{ r.est_time_min || 0 }} min (fixed per line item)
                      </template>
                      <template v-else>
                        Est: {{ r.est_time_min || 0 }} min/ea × {{ selectedPart.quantity }} =
                        {{ (r.est_time_min || 0) * selectedPart.quantity }} min total
                      </template>
                    </div>
                  </div>
                  <div class="routing-status">
                    <i v-if="isStationComplete(r.station_id)" class="pi pi-check-circle complete-icon"></i>
                    <i v-else class="pi pi-circle pending-icon"></i>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- PDF Measure Mode -->
    <PdfMeasure
      v-if="showMeasureMode && pdfUrl"
      :pdf-url="pdfUrl"
      :part-number="selectedPart?.item_number"
      @close="showMeasureMode = false"
    />
  </div>
</template>

<style scoped>
.part-lookup-view {
  height: 100vh;
  background: #020617;
  color: #e5e7eb;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.header-left h1 {
  font-size: 1.5rem;
  margin: 0;
  color: #fff;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #374151;
  border: none;
  color: #e5e7eb;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.875rem;
  transition: background 0.15s;
}

.back-btn:hover {
  background: #4b5563;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.nav-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #374151;
  border: none;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.875rem;
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

/* Layout */
.lookup-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  width: 320px;
  background: #0f172a;
  border-right: 1px solid #1e293b;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

.sidebar-header {
  padding: 1rem;
  border-bottom: 1px solid #1e293b;
  flex-shrink: 0;
}

.search-input {
  width: 100%;
  padding: 0.5rem;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 0.375rem;
  color: #e5e7eb;
  font-size: 0.875rem;
  margin-bottom: 0.75rem;
}

.search-input:focus {
  outline: none;
  border-color: #38bdf8;
}

.filter-row {
  margin-bottom: 0.75rem;
}

.filter-select {
  width: 100%;
  padding: 0.5rem;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 0.375rem;
  color: #e5e7eb;
  font-size: 0.875rem;
}

.filter-select:focus {
  outline: none;
  border-color: #38bdf8;
}

.filter-stats {
  font-size: 0.75rem;
  color: #9ca3af;
  text-align: right;
}

.loading-small {
  padding: 2rem;
  text-align: center;
  color: #6b7280;
  font-size: 0.875rem;
}

.no-selection-sidebar {
  padding: 3rem 1rem;
  text-align: center;
  color: #6b7280;
}

.no-selection-sidebar i {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  display: block;
}

.no-selection-sidebar p {
  font-size: 0.875rem;
  margin: 0;
}

.parts-list {
  flex: 1;
  overflow-y: auto;
}

.part-row {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #1e293b;
  cursor: pointer;
  transition: background 0.15s;
}

.part-row:hover {
  background: #1e293b;
}

.part-row.selected {
  background: #1e3a5f;
  border-left: 3px solid #38bdf8;
}

.part-row-main {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pdf-icon {
  color: #f87171;
  font-size: 12px;
}

.part-number {
  font-size: 13px;
  font-weight: 600;
  color: #e5e7eb;
}

.mat-badge {
  padding: 1px 5px;
  border-radius: 3px;
  border: 1px solid #b8860b;
  color: #fbbf24;
  font-size: 9px;
  font-weight: 600;
}

.ops-badge {
  margin-left: auto;
  padding: 2px 6px;
  border-radius: 4px;
  background: #065f46;
  color: #6ee7b7;
  font-size: 10px;
  font-weight: 600;
}

.no-routing-badge {
  margin-left: auto;
  padding: 2px 6px;
  border-radius: 4px;
  background: #7f1d1d;
  color: #fca5a5;
  font-size: 10px;
}

.part-name {
  display: block;
  font-size: 11px;
  color: #9ca3af;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Main Panel */
.main-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #020617;
}

.no-selection {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #6b7280;
}

.no-selection i {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.no-selection p {
  font-size: 1.125rem;
}

.part-header {
  padding: 1rem 1.5rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.part-info {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.part-number-large {
  font-size: 1.5rem;
  font-weight: 700;
  color: #38bdf8;
}

.part-desc {
  font-size: 0.875rem;
  color: #9ca3af;
}

.part-qty {
  font-size: 0.875rem;
  color: #e5e7eb;
  background: #374151;
  padding: 0.25rem 0.75rem;
  border-radius: 0.375rem;
}

.part-meta-badges {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.info-chip {
  background: #1e3a8a;
  color: #93c5fd;
  padding: 0.25rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  font-weight: 600;
}

/* File Tiles (badges) */
.file-tiles {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.file-tile {
  padding: 4px 10px;
  border: none;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.file-tile.pdf {
  background: #7f1d1d;
  color: #fca5a5;
}
.file-tile.pdf:hover { background: #991b1b; }

.file-tile.svg {
  background: #365314;
  color: #bef264;
}
.file-tile.svg:hover { background: #3f6212; }

.file-tile.dxf {
  background: #3f3f46;
  color: #a1a1aa;
}
.file-tile.dxf:hover { background: #52525b; }

.file-tile.step, .file-tile.cad {
  background: #1e3a5f;
  color: #93c5fd;
}
.file-tile.step:hover, .file-tile.cad:hover { background: #1e40af; }

.file-tile.generate-dxf {
  background: #065f46;
  color: #6ee7b7;
  border: 1px dashed #6ee7b7;
}
.file-tile.generate-dxf:hover { background: #047857; }
.file-tile.generate-dxf:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Tabs */
.tabs {
  display: flex;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
}

.tab {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  background: transparent;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}

.tab:hover {
  background: #1e293b;
  color: #e5e7eb;
}

.tab.active {
  color: #38bdf8;
  border-bottom-color: #38bdf8;
}

/* Tab Content */
.tab-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* PDF Toolbar */
.pdf-toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
}

.measure-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: #2563eb;
  border: none;
  border-radius: 0.375rem;
  color: #fff;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.measure-btn:hover {
  background: #1d4ed8;
}

/* PDF Viewer */
.pdf-viewer {
  flex: 1;
  background: white;
  display: flex;
  flex-direction: column;
}

.pdf-viewer iframe {
  flex: 1;
  width: 100%;
  border: none;
}

.no-pdf {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #0f172a;
  color: #6b7280;
}

.no-pdf i {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.no-pdf p {
  font-size: 1rem;
}

/* Details Section */
.details-section {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
}

.details-section h3 {
  font-size: 1rem;
  margin: 0 0 1rem 0;
  color: #e5e7eb;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.info-label {
  font-size: 0.75rem;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-value {
  font-size: 0.875rem;
  color: #e5e7eb;
  font-weight: 500;
}

.empty-routing {
  padding: 2rem;
  text-align: center;
  color: #6b7280;
  font-size: 0.875rem;
}

.routing-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.routing-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: #1e293b;
  border-radius: 0.5rem;
  border: 1px solid #334155;
}

.routing-item.completed {
  opacity: 0.6;
}

.routing-seq {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #374151;
  border-radius: 0.375rem;
  font-weight: 700;
  color: #e5e7eb;
  flex-shrink: 0;
}

.routing-info {
  flex: 1;
}

.routing-station {
  font-size: 0.875rem;
  color: #e5e7eb;
  margin-bottom: 0.25rem;
}

.routing-station strong {
  color: #38bdf8;
}

.routing-time {
  font-size: 0.75rem;
  color: #9ca3af;
}

.routing-status {
  flex-shrink: 0;
}

.complete-icon {
  color: #6ee7b7;
  font-size: 1.25rem;
}

.pending-icon {
  color: #374151;
  font-size: 1.25rem;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .sidebar {
    width: 280px;
  }

  .part-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .tabs {
    overflow-x: auto;
  }

  .tab {
    white-space: nowrap;
  }
}

@media (max-width: 640px) {
  .lookup-layout {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    max-height: 40vh;
    border-right: none;
    border-bottom: 1px solid #1e293b;
  }

  .main-panel {
    flex: 1;
  }
}
</style>
