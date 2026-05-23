<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase, API_BASE_URL } from '../services/supabase'

const router = useRouter()

// State
const loading = ref(false)
const searchQuery = ref('')
const searchType = ref<'part' | 'project'>('part')
const partResults = ref<PartResult[]>([])
const projectResults = ref<ProjectResult[]>([])
const selectedItem = ref<PartResult | ProjectResult | null>(null)
const pdfUrl = ref<string | null>(null)
const loadingPdf = ref(false)

interface PartResult {
  id: string
  item_number: string
  name: string
  has_pdf: boolean
  pdf_path: string | null
  material: string | null
  description: string | null
}

interface ProjectResult {
  id: string
  project_code: string
  description: string
  customer: string
  has_print_packet: boolean
  print_packet_path: string | null
}

// Computed
const filteredResults = computed(() => {
  const search = searchQuery.value.toLowerCase()

  if (searchType.value === 'part') {
    return partResults.value.filter(p =>
      p.item_number.toLowerCase().includes(search) ||
      (p.name || '').toLowerCase().includes(search) ||
      (p.description || '').toLowerCase().includes(search)
    )
  } else {
    return projectResults.value.filter(p =>
      p.project_code.toLowerCase().includes(search) ||
      (p.description || '').toLowerCase().includes(search) ||
      (p.customer || '').toLowerCase().includes(search)
    )
  }
})

// Methods
async function loadParts() {
  loading.value = true

  try {
    const { data: itemsData, error: itemsError } = await supabase
      .from('items')
      .select('id, item_number, name, description, material')
      .order('item_number')
      .limit(200)

    if (itemsError) throw itemsError

    // Get PDF info for all items
    const itemIds = (itemsData || []).map(i => i.id)
    const { data: filesData } = await supabase
      .from('files')
      .select('item_id, file_path, storage_path')
      .in('item_id', itemIds)
      .eq('file_type', 'PDF')
      .not('file_path', 'is', null)

    const pdfMap = new Map(
      (filesData || []).map(f => [f.item_id, f.file_path || f.storage_path])
    )

    partResults.value = (itemsData || []).map(item => ({
      id: item.id,
      item_number: item.item_number,
      name: item.name || '',
      description: item.description,
      material: item.material,
      has_pdf: pdfMap.has(item.id),
      pdf_path: pdfMap.get(item.id) || null
    }))
  } catch (e) {
    console.error('Failed to load parts:', e)
  } finally {
    loading.value = false
  }
}

async function loadProjects() {
  loading.value = true

  try {
    const { data, error: queryError } = await supabase
      .from('mrp_projects')
      .select('id, project_code, description, customer, print_packet_path')
      .order('project_code')
      .limit(200)

    if (queryError) throw queryError

    projectResults.value = (data || []).map(p => ({
      id: p.id,
      project_code: p.project_code,
      description: p.description || '',
      customer: p.customer || '',
      has_print_packet: !!p.print_packet_path,
      print_packet_path: p.print_packet_path
    }))
  } catch (e) {
    console.error('Failed to load projects:', e)
  } finally {
    loading.value = false
  }
}

async function selectPart(part: PartResult) {
  if (!part.has_pdf) return

  selectedItem.value = part
  pdfUrl.value = null
  loadingPdf.value = true

  try {
    // Check if it's a storage path
    if (part.pdf_path) {
      if (part.pdf_path.includes('/')) {
        // Parse bucket and path from file_path (e.g., "pdm-drawings/csp00025/A/1/csp00025.pdf")
        const parts = part.pdf_path.split('/')
        const bucket = parts[0] ?? 'pdm-files'
        const filePath = parts.slice(1).join('/')

        const { data, error } = await supabase.storage
          .from(bucket)
          .createSignedUrl(filePath, 3600)

        if (error) {
          const { data: publicData } = supabase.storage.from(bucket).getPublicUrl(filePath)
          pdfUrl.value = publicData?.publicUrl || null
        } else {
          pdfUrl.value = data?.signedUrl || null
        }
      } else {
        // Local file path - use API endpoint
        pdfUrl.value = `${API_BASE_URL}/api/pdf?path=${encodeURIComponent(part.pdf_path)}`
      }
    }
  } catch (e) {
    console.error('Failed to load PDF:', e)
  } finally {
    loadingPdf.value = false
  }
}

async function selectProject(project: ProjectResult) {
  if (!project.has_print_packet) return

  selectedItem.value = project
  pdfUrl.value = null
  loadingPdf.value = true

  try {
    const response = await fetch(`${API_BASE_URL}/mrp/projects/${project.id}/print-packet`)

    if (response.ok) {
      const data = await response.json()
      pdfUrl.value = data.url || null
    }
  } catch (e) {
    console.error('Failed to load print packet:', e)
  } finally {
    loadingPdf.value = false
  }
}

function _selectItem(item: any) {
  if ('item_number' in item) {
    selectPart(item as PartResult)
  } else {
    selectProject(item as ProjectResult)
  }
}

function isPart(item: any): item is PartResult {
  return 'item_number' in item
}

function _isProject(item: any): item is ProjectResult {
  return 'project_code' in item
}

// Export for potential future use
void _selectItem
void _isProject

function goHome() {
  router.push('/')
}

function goToShop() {
  router.push('/mrp/shop')
}

function goToPartLookup() {
  router.push('/mrp/parts')
}

// Watch for search type changes
watch(searchType, (newType) => {
  selectedItem.value = null
  pdfUrl.value = null
  searchQuery.value = ''

  if (newType === 'part' && partResults.value.length === 0) {
    loadParts()
  } else if (newType === 'project' && projectResults.value.length === 0) {
    loadProjects()
  }
})

onMounted(() => {
  loadParts()
})
</script>

<template>
  <div class="print-lookup-view">
    <header class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="goHome">
          <i class="pi pi-arrow-left"></i>
          Home
        </button>
        <div>
          <h1>Print Lookup</h1>
        </div>
      </div>
      <div class="header-actions">
        <button class="nav-btn shop" @click="goToShop">
          <span class="nav-dot shop"></span>
          Shop Terminal
        </button>
        <button class="nav-btn lookup" @click="goToPartLookup">
          <span class="nav-dot lookup"></span>
          Part Lookup
        </button>
        <button class="nav-btn print active">
          <span class="nav-dot print"></span>
          Print Lookup
        </button>
      </div>
    </header>

    <div class="lookup-layout">
      <!-- Left Sidebar - Parts/Projects List -->
      <div class="sidebar">
        <div class="sidebar-header">
          <div class="type-toggle">
            <button
              :class="['toggle-btn', { active: searchType === 'part' }]"
              @click="searchType = 'part'"
            >
              <i class="pi pi-box"></i>
              Parts
            </button>
            <button
              :class="['toggle-btn', { active: searchType === 'project' }]"
              @click="searchType = 'project'"
            >
              <i class="pi pi-folder"></i>
              Projects
            </button>
          </div>
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="searchType === 'part' ? 'Search parts...' : 'Search projects...'"
            class="search-input"
          />
          <div class="filter-stats">
            {{ filteredResults.length }} {{ searchType === 'part' ? 'parts' : 'projects' }}
          </div>
        </div>

        <div v-if="loading" class="loading-small">Loading...</div>
        <div v-else class="items-list">
          <!-- Part Results -->
          <template v-if="searchType === 'part'">
            <div
              v-for="part in filteredResults"
              :key="part.id"
              class="item-row"
              :class="{
                selected: selectedItem?.id === part.id,
                'has-pdf': (part as PartResult).has_pdf,
                disabled: !(part as PartResult).has_pdf
              }"
              @click="(part as PartResult).has_pdf && selectPart(part as PartResult)"
            >
              <div class="item-row-main">
                <span v-if="(part as PartResult).has_pdf" class="pdf-icon" title="Has PDF">
                  <i class="pi pi-file-pdf"></i>
                </span>
                <span v-else class="no-pdf-icon" title="No PDF">
                  <i class="pi pi-file"></i>
                </span>
                <span class="item-number">{{ (part as PartResult).item_number }}</span>
                <span v-if="(part as PartResult).material" class="material-badge">
                  {{ (part as PartResult).material }}
                </span>
              </div>
              <span class="item-name">{{ (part as PartResult).name || (part as PartResult).description || '-' }}</span>
            </div>
          </template>

          <!-- Project Results -->
          <template v-else>
            <div
              v-for="project in filteredResults"
              :key="project.id"
              class="item-row"
              :class="{
                selected: selectedItem?.id === project.id,
                'has-pdf': (project as ProjectResult).has_print_packet,
                disabled: !(project as ProjectResult).has_print_packet
              }"
              @click="(project as ProjectResult).has_print_packet && selectProject(project as ProjectResult)"
            >
              <div class="item-row-main">
                <span v-if="(project as ProjectResult).has_print_packet" class="pdf-icon" title="Has Print Packet">
                  <i class="pi pi-file-pdf"></i>
                </span>
                <span v-else class="no-pdf-icon" title="No Print Packet">
                  <i class="pi pi-file"></i>
                </span>
                <span class="item-number">{{ (project as ProjectResult).project_code }}</span>
              </div>
              <span class="item-name">{{ (project as ProjectResult).description || '-' }}</span>
              <span v-if="(project as ProjectResult).customer" class="item-customer">
                {{ (project as ProjectResult).customer }}
              </span>
            </div>
          </template>
        </div>
      </div>

      <!-- Main Panel - PDF Viewer -->
      <div class="main-panel">
        <div v-if="!selectedItem" class="no-selection">
          <i class="pi pi-arrow-left"></i>
          <p>Select {{ searchType === 'part' ? 'a part' : 'a project' }} to view PDF</p>
        </div>

        <template v-else>
          <!-- Header -->
          <div class="pdf-header">
            <div class="pdf-info">
              <span class="pdf-title">
                {{ isPart(selectedItem) ? selectedItem.item_number : (selectedItem as ProjectResult).project_code }}
              </span>
              <span class="pdf-subtitle">
                {{ isPart(selectedItem) ? (selectedItem.name || selectedItem.description) : (selectedItem as ProjectResult).description }}
              </span>
            </div>
            <a
              v-if="pdfUrl"
              :href="pdfUrl"
              target="_blank"
              class="open-new-btn"
              title="Open in new tab"
            >
              <i class="pi pi-external-link"></i>
              Open Full Screen
            </a>
          </div>

          <!-- PDF Viewer -->
          <div class="pdf-content">
            <div v-if="loadingPdf" class="pdf-loading">
              <i class="pi pi-spin pi-spinner"></i>
              <p>Loading PDF...</p>
            </div>
            <div v-else-if="!pdfUrl" class="no-pdf">
              <i class="pi pi-file"></i>
              <p>PDF not available</p>
            </div>
            <iframe v-else :src="pdfUrl"></iframe>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.print-lookup-view {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  display: flex;
  flex-direction: column;
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
}

.sidebar-header {
  padding: 1rem;
  border-bottom: 1px solid #1e293b;
}

.type-toggle {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.toggle-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 0.375rem;
  color: #9ca3af;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.15s;
}

.toggle-btn:hover {
  background: #334155;
  color: #e5e7eb;
}

.toggle-btn.active {
  background: #1e3a5f;
  border-color: #38bdf8;
  color: #fff;
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

.items-list {
  flex: 1;
  overflow-y: auto;
}

.item-row {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #1e293b;
  cursor: pointer;
  transition: background 0.15s;
}

.item-row:hover:not(.disabled) {
  background: #1e293b;
}

.item-row.selected {
  background: #1e3a5f;
  border-left: 3px solid #38bdf8;
}

.item-row.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.item-row-main {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
  flex-wrap: wrap;
}

.pdf-icon {
  color: #ef4444;
  font-size: 1rem;
}

.no-pdf-icon {
  color: #6b7280;
  font-size: 1rem;
}

.item-number {
  font-weight: 600;
  color: #38bdf8;
  font-size: 0.875rem;
}

.material-badge {
  font-size: 0.625rem;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  background: #1e3a8a;
  color: #93c5fd;
  font-weight: 600;
}

.item-name {
  font-size: 0.75rem;
  color: #9ca3af;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-customer {
  font-size: 0.7rem;
  color: #6b7280;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.pdf-header {
  padding: 1rem 1.5rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.pdf-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  min-width: 0;
  flex: 1;
}

.pdf-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: #38bdf8;
}

.pdf-subtitle {
  font-size: 0.875rem;
  color: #9ca3af;
}

.open-new-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: #374151;
  border-radius: 0.375rem;
  color: #e5e7eb;
  text-decoration: none;
  font-size: 0.875rem;
  font-weight: 500;
  transition: background 0.15s;
  white-space: nowrap;
}

.open-new-btn:hover {
  background: #4b5563;
}

.pdf-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
}

.pdf-content iframe {
  flex: 1;
  width: 100%;
  border: none;
}

.pdf-loading,
.no-pdf {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #0f172a;
  color: #6b7280;
  gap: 1rem;
}

.pdf-loading i,
.no-pdf i {
  font-size: 3rem;
}

.pdf-loading p,
.no-pdf p {
  font-size: 1rem;
  margin: 0;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .sidebar {
    width: 280px;
  }

  .pdf-header {
    flex-direction: column;
    align-items: flex-start;
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
