<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase, API_BASE_URL } from '../services/supabase'

const router = useRouter()

// Search state
const searchQuery = ref('')
const searchType = ref<'part' | 'project'>('part')
const searching = ref(false)
const error = ref('')

// Autocomplete state
interface AutocompleteSuggestion {
  id: string
  label: string
  sublabel: string
  has_pdf: boolean
}

const suggestions = ref<AutocompleteSuggestion[]>([])
const showSuggestions = ref(false)
const loadingSuggestions = ref(false)
const selectedSuggestionIndex = ref(-1)
const searchInputRef = ref<HTMLInputElement | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// Part search results
interface PartResult {
  id: string
  item_number: string
  name: string
  has_pdf: boolean
  pdf_path: string | null
}

interface ProjectResult {
  id: string
  project_code: string
  description: string
  customer: string
  has_print_packet: boolean
  print_packet_path: string | null
}

const partResults = ref<PartResult[]>([])
const projectResults = ref<ProjectResult[]>([])

// PDF Panel
const showPdfPanel = ref(false)
const pdfTitle = ref('')
const pdfUrl = ref<string | null>(null)
const loadingPdf = ref(false)
const pdfPanelWidth = ref(600)
const isResizing = ref(false)

async function search() {
  if (!searchQuery.value.trim()) return

  searching.value = true
  error.value = ''
  partResults.value = []
  projectResults.value = []
  closePdfPanel()

  try {
    if (searchType.value === 'part') {
      await searchParts()
    } else {
      await searchProjects()
    }
  } catch (e: any) {
    error.value = e.message || 'Search failed'
  } finally {
    searching.value = false
  }
}

async function searchParts() {
  const query = searchQuery.value.trim().toLowerCase()

  const { data, error: queryError } = await supabase
    .from('items')
    .select('id, item_number, name')
    .ilike('item_number', `%${query}%`)
    .limit(50)

  if (queryError) throw queryError

  // Get PDF info for each item
  const itemIds = (data || []).map(i => i.id)

  const { data: filesData } = await supabase
    .from('files')
    .select('item_id, file_path')
    .in('item_id', itemIds)
    .eq('file_type', 'PDF')
    .not('file_path', 'is', null)

  const pdfMap = new Map((filesData || []).map(f => [f.item_id, f.file_path]))

  partResults.value = (data || []).map(item => ({
    id: item.id,
    item_number: item.item_number,
    name: item.name || '',
    has_pdf: pdfMap.has(item.id),
    pdf_path: pdfMap.get(item.id) || null
  }))
}

async function searchProjects() {
  const query = searchQuery.value.trim()

  const { data, error: queryError } = await supabase
    .from('mrp_projects')
    .select('id, project_code, description, customer, print_packet_path')
    .or(`project_code.ilike.%${query}%,description.ilike.%${query}%,customer.ilike.%${query}%`)
    .limit(50)

  if (queryError) throw queryError

  projectResults.value = (data || []).map(p => ({
    id: p.id,
    project_code: p.project_code,
    description: p.description || '',
    customer: p.customer || '',
    has_print_packet: !!p.print_packet_path,
    print_packet_path: p.print_packet_path
  }))
}

// Autocomplete functions
async function fetchSuggestions() {
  const query = searchQuery.value.trim().toLowerCase()
  if (query.length < 2) {
    suggestions.value = []
    showSuggestions.value = false
    return
  }

  loadingSuggestions.value = true

  try {
    if (searchType.value === 'part') {
      await fetchPartSuggestions(query)
    } else {
      await fetchProjectSuggestions(query)
    }
    showSuggestions.value = suggestions.value.length > 0
    selectedSuggestionIndex.value = -1
  } catch (e) {
    console.error('Failed to fetch suggestions:', e)
  } finally {
    loadingSuggestions.value = false
  }
}

async function fetchPartSuggestions(query: string) {
  const { data, error: queryError } = await supabase
    .from('items')
    .select('id, item_number, name')
    .ilike('item_number', `%${query}%`)
    .order('item_number')
    .limit(10)

  if (queryError) throw queryError

  // Get PDF info for suggestions
  const itemIds = (data || []).map(i => i.id)
  const { data: filesData } = await supabase
    .from('files')
    .select('item_id')
    .in('item_id', itemIds)
    .eq('file_type', 'PDF')
    .not('file_path', 'is', null)

  const pdfSet = new Set((filesData || []).map(f => f.item_id))

  suggestions.value = (data || []).map(item => ({
    id: item.id,
    label: item.item_number,
    sublabel: item.name || '',
    has_pdf: pdfSet.has(item.id)
  }))
}

async function fetchProjectSuggestions(query: string) {
  const { data, error: queryError } = await supabase
    .from('mrp_projects')
    .select('id, project_code, description, customer, print_packet_path')
    .or(`project_code.ilike.%${query}%,description.ilike.%${query}%,customer.ilike.%${query}%`)
    .order('project_code')
    .limit(10)

  if (queryError) throw queryError

  suggestions.value = (data || []).map(p => ({
    id: p.id,
    label: p.project_code,
    sublabel: p.description || p.customer || '',
    has_pdf: !!p.print_packet_path
  }))
}

function onSearchInput() {
  // Debounce the autocomplete fetch
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
  debounceTimer = setTimeout(() => {
    fetchSuggestions()
  }, 200)
}

function selectSuggestion(suggestion: AutocompleteSuggestion) {
  searchQuery.value = suggestion.label
  showSuggestions.value = false
  selectedSuggestionIndex.value = -1
  search()
}

function handleKeydown(e: KeyboardEvent) {
  if (!showSuggestions.value || suggestions.value.length === 0) {
    return
  }

  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      selectedSuggestionIndex.value = Math.min(
        selectedSuggestionIndex.value + 1,
        suggestions.value.length - 1
      )
      break
    case 'ArrowUp':
      e.preventDefault()
      selectedSuggestionIndex.value = Math.max(selectedSuggestionIndex.value - 1, -1)
      break
    case 'Enter':
      if (selectedSuggestionIndex.value >= 0) {
        e.preventDefault()
        selectSuggestion(suggestions.value[selectedSuggestionIndex.value])
      }
      break
    case 'Escape':
      showSuggestions.value = false
      selectedSuggestionIndex.value = -1
      break
  }
}

function hideSuggestionsOnClickOutside(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.search-input-wrapper')) {
    showSuggestions.value = false
  }
}

// Clear suggestions when search type changes
watch(searchType, () => {
  suggestions.value = []
  showSuggestions.value = false
  partResults.value = []
  projectResults.value = []
})

onMounted(() => {
  document.addEventListener('click', hideSuggestionsOnClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', hideSuggestionsOnClickOutside)
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }
})

async function openPartPdf(part: PartResult) {
  if (!part.pdf_path) return

  pdfTitle.value = part.item_number
  showPdfPanel.value = true
  pdfUrl.value = null
  loadingPdf.value = true

  try {
    // Parse bucket and path from file_path (e.g., "pdm-drawings/csp00025/A/1/csp00025.pdf")
    const parts = part.pdf_path.split('/')
    const bucket = parts[0]
    const filePath = parts.slice(1).join('/')

    const { data, error } = await supabase.storage
      .from(bucket)
      .createSignedUrl(filePath, 3600)

    if (error) {
      console.warn('Signed URL failed:', error)
      const { data: publicData } = supabase.storage.from(bucket).getPublicUrl(filePath)
      pdfUrl.value = publicData?.publicUrl || null
    } else {
      pdfUrl.value = data?.signedUrl || null
    }
  } catch (e) {
    console.error('Failed to load PDF:', e)
  } finally {
    loadingPdf.value = false
  }
}

async function openProjectPrintPacket(project: ProjectResult) {
  pdfTitle.value = `${project.project_code} Print Packet`
  showPdfPanel.value = true
  pdfUrl.value = null
  loadingPdf.value = true

  try {
    const response = await fetch(`${API_BASE_URL}/mrp/projects/${project.id}/print-packet`)

    if (response.ok) {
      const data = await response.json()
      pdfUrl.value = data.url || null
    } else {
      error.value = 'Print packet not available'
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load print packet'
  } finally {
    loadingPdf.value = false
  }
}

function closePdfPanel() {
  showPdfPanel.value = false
  pdfTitle.value = ''
  pdfUrl.value = null
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

// Navigation
function goHome() {
  router.push('/')
}

function goToShop() {
  router.push('/mrp/shop')
}

function goToPartLookup() {
  router.push('/mrp/parts')
}
</script>

<template>
  <div class="print-lookup">
    <header class="terminal-header">
      <button class="back-btn" @click="goHome">
        <i class="pi pi-arrow-left"></i>
        Home
      </button>
      <div class="header-info">
        <h1>Print Lookup</h1>
        <p>Search for drawings and print packets</p>
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

    <div class="main-content" :class="{ 'panel-open': showPdfPanel }">
      <div class="search-area">
        <!-- Search Controls -->
        <div class="search-box">
          <div class="search-type-toggle">
            <button
              :class="['toggle-btn', { active: searchType === 'part' }]"
              @click="searchType = 'part'"
            >
              Part Number
            </button>
            <button
              :class="['toggle-btn', { active: searchType === 'project' }]"
              @click="searchType = 'project'"
            >
              Project
            </button>
          </div>
          <div class="search-input-row">
            <div class="search-input-wrapper">
              <input
                ref="searchInputRef"
                v-model="searchQuery"
                type="text"
                :placeholder="searchType === 'part' ? 'Enter part number...' : 'Enter project code or name...'"
                class="search-input"
                autocomplete="off"
                @input="onSearchInput"
                @keydown="handleKeydown"
                @keyup.enter="!showSuggestions || selectedSuggestionIndex < 0 ? search() : null"
                @focus="searchQuery.length >= 2 && suggestions.length > 0 && (showSuggestions = true)"
              />
              <!-- Autocomplete Dropdown -->
              <div v-if="showSuggestions" class="autocomplete-dropdown">
                <div v-if="loadingSuggestions" class="autocomplete-loading">
                  <i class="pi pi-spin pi-spinner"></i>
                  Loading...
                </div>
                <div
                  v-else
                  v-for="(suggestion, index) in suggestions"
                  :key="suggestion.id"
                  :class="['autocomplete-item', { selected: index === selectedSuggestionIndex, 'has-pdf': suggestion.has_pdf }]"
                  @click="selectSuggestion(suggestion)"
                  @mouseenter="selectedSuggestionIndex = index"
                >
                  <div class="suggestion-main">
                    <span class="suggestion-label">{{ suggestion.label }}</span>
                    <span v-if="suggestion.sublabel" class="suggestion-sublabel">{{ suggestion.sublabel }}</span>
                  </div>
                  <span v-if="suggestion.has_pdf" class="suggestion-pdf-badge">
                    <i class="pi pi-file-pdf"></i>
                  </span>
                </div>
              </div>
            </div>
            <button class="search-btn" @click="search" :disabled="searching || !searchQuery.trim()">
              <i :class="searching ? 'pi pi-spin pi-spinner' : 'pi pi-search'"></i>
              {{ searching ? 'Searching...' : 'Search' }}
            </button>
          </div>
        </div>

        <div v-if="error" class="error-message">
          <i class="pi pi-exclamation-triangle"></i>
          {{ error }}
          <button class="dismiss-btn" @click="error = ''">&times;</button>
        </div>

        <!-- Part Results -->
        <div v-if="searchType === 'part' && partResults.length > 0" class="results-section">
          <h2>Parts ({{ partResults.length }})</h2>
          <div class="results-grid">
            <div
              v-for="part in partResults"
              :key="part.id"
              class="result-card"
              :class="{ 'has-pdf': part.has_pdf }"
              @click="part.has_pdf && openPartPdf(part)"
            >
              <div class="result-main">
                <span class="result-number">{{ part.item_number }}</span>
                <span class="result-name">{{ part.name || '-' }}</span>
              </div>
              <div class="result-actions">
                <span v-if="part.has_pdf" class="pdf-indicator">
                  <i class="pi pi-file-pdf"></i>
                  PDF
                </span>
                <span v-else class="no-pdf">No PDF</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Project Results -->
        <div v-if="searchType === 'project' && projectResults.length > 0" class="results-section">
          <h2>Projects ({{ projectResults.length }})</h2>
          <div class="results-grid">
            <div
              v-for="project in projectResults"
              :key="project.id"
              class="result-card project-card"
              :class="{ 'has-pdf': project.has_print_packet }"
              @click="project.has_print_packet && openProjectPrintPacket(project)"
            >
              <div class="result-main">
                <span class="result-number">{{ project.project_code }}</span>
                <span class="result-name">{{ project.description || '-' }}</span>
                <span class="result-customer">{{ project.customer }}</span>
              </div>
              <div class="result-actions">
                <span v-if="project.has_print_packet" class="pdf-indicator">
                  <i class="pi pi-file-pdf"></i>
                  Print Packet
                </span>
                <span v-else class="no-pdf">No Print Packet</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="!searching && partResults.length === 0 && projectResults.length === 0 && searchQuery" class="empty-state">
          <i class="pi pi-search"></i>
          <p>No results found for "{{ searchQuery }}"</p>
        </div>

        <div v-if="!searchQuery && partResults.length === 0 && projectResults.length === 0" class="empty-state initial">
          <i class="pi pi-file-pdf"></i>
          <p>Search for part numbers or projects to view their drawings</p>
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
          <h2>{{ pdfTitle }}</h2>
          <button class="panel-close" @click="closePdfPanel">&times;</button>
        </div>
        <div class="panel-content">
          <div class="pdf-viewer">
            <div v-if="loadingPdf" class="pdf-loading">
              <i class="pi pi-spin pi-spinner"></i>
              Loading PDF...
            </div>
            <iframe
              v-else-if="pdfUrl"
              :src="pdfUrl"
            ></iframe>
            <div v-else class="no-pdf">PDF not available</div>
          </div>
        </div>
        <div class="panel-footer">
          <a
            v-if="pdfUrl"
            :href="pdfUrl"
            target="_blank"
            class="pdf-open-btn"
            title="Open in new tab"
          >
            <i class="pi pi-external-link"></i>
            Open Full Screen
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }

.print-lookup {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  font-family: system-ui, sans-serif;
  display: flex;
  flex-direction: column;
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

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.main-content.panel-open .search-area {
  flex: 1;
}

.search-area {
  flex: 1;
  padding: 2rem;
  overflow-y: auto;
}

/* Search Box */
.search-box {
  max-width: 700px;
  margin: 0 auto 2rem;
}

.search-type-toggle {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.toggle-btn {
  flex: 1;
  padding: 0.75rem 1rem;
  background: #1e293b;
  border: 2px solid #334155;
  color: #9ca3af;
  border-radius: 0.5rem;
  cursor: pointer;
  font-size: 1rem;
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

.search-input-row {
  display: flex;
  gap: 0.75rem;
}

.search-input-wrapper {
  flex: 1;
  position: relative;
}

.search-input {
  width: 100%;
  padding: 1rem 1.25rem;
  background: #1e293b;
  border: 2px solid #334155;
  border-radius: 0.5rem;
  color: #e5e7eb;
  font-size: 1.25rem;
}

.search-input:focus {
  outline: none;
  border-color: #38bdf8;
}

/* Autocomplete Dropdown */
.autocomplete-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: #1e293b;
  border: 2px solid #38bdf8;
  border-top: none;
  border-radius: 0 0 0.5rem 0.5rem;
  max-height: 350px;
  overflow-y: auto;
  z-index: 100;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}

.autocomplete-loading {
  padding: 1rem;
  text-align: center;
  color: #9ca3af;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.autocomplete-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  cursor: pointer;
  border-bottom: 1px solid #334155;
  transition: background 0.1s;
}

.autocomplete-item:last-child {
  border-bottom: none;
}

.autocomplete-item:hover,
.autocomplete-item.selected {
  background: #334155;
}

.autocomplete-item.has-pdf {
  border-left: 3px solid #dc2626;
}

.suggestion-main {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
  flex: 1;
}

.suggestion-label {
  font-size: 1rem;
  font-weight: 600;
  font-family: monospace;
  color: #fff;
}

.suggestion-sublabel {
  font-size: 0.8rem;
  color: #9ca3af;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.suggestion-pdf-badge {
  color: #dc2626;
  font-size: 1.125rem;
  margin-left: 0.5rem;
}

.search-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem 2rem;
  background: #2563eb;
  border: none;
  border-radius: 0.5rem;
  color: white;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
}

.search-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Results */
.results-section {
  max-width: 900px;
  margin: 0 auto;
}

.results-section h2 {
  font-size: 1.125rem;
  margin: 0 0 1rem;
  color: #9ca3af;
}

.results-grid {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.result-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 0.5rem;
  cursor: default;
}

.result-card.has-pdf {
  cursor: pointer;
  transition: all 0.15s;
}

.result-card.has-pdf:hover {
  background: #334155;
  border-color: #38bdf8;
}

.result-main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.result-number {
  font-size: 1.125rem;
  font-weight: 600;
  font-family: monospace;
  color: #fff;
}

.result-name {
  font-size: 0.875rem;
  color: #9ca3af;
}

.result-customer {
  font-size: 0.75rem;
  color: #6b7280;
}

.pdf-indicator {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: #dc2626;
  color: white;
  padding: 0.35rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 600;
}

.no-pdf {
  color: #6b7280;
  font-size: 0.875rem;
}

/* Error Message */
.error-message {
  max-width: 700px;
  margin: 0 auto 1rem;
  padding: 0.75rem 1rem;
  background: #7f1d1d;
  border-radius: 0.5rem;
  color: #fca5a5;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.dismiss-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: #fca5a5;
  font-size: 1.25rem;
  cursor: pointer;
}

/* Empty State */
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

.empty-state.initial i {
  color: #38bdf8;
}

/* PDF Panel */
.pdf-panel {
  background: #0f172a;
  border-left: 1px solid #1e293b;
  display: flex;
  flex-direction: column;
  height: 100%;
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
}

.pdf-viewer {
  height: 100%;
  background: #fff;
}

.pdf-viewer iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.pdf-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  height: 100%;
  color: #9ca3af;
  background: #1e293b;
}

.pdf-loading i {
  font-size: 2rem;
}

.panel-footer {
  padding: 0.75rem 1rem;
  border-top: 1px solid #1e293b;
  display: flex;
  justify-content: center;
}

.pdf-open-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 1.25rem;
  background: #374151;
  border-radius: 0.5rem;
  color: #e5e7eb;
  text-decoration: none;
  font-size: 0.875rem;
  font-weight: 500;
  transition: background 0.15s;
}

.pdf-open-btn:hover {
  background: #4b5563;
}
</style>
