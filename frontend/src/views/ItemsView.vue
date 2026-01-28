<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useItemsStore } from '../stores/items'
import { useAuthStore } from '../stores/auth'
import { useDebounceFn } from '@vueuse/core'
import { getSignedUrlFromPath } from '../services/storage'
import type { Item, BOMTreeNode, FileInfo } from '../types'

const router = useRouter()
const itemsStore = useItemsStore()
const authStore = useAuthStore()

// Filters
const searchInput = ref('')
const lifecycleFilter = ref('')
const projectFilter = ref('')

// Sorting
const sortColumn = ref<string>('item_number')
const sortDirection = ref<'asc' | 'desc'>('asc')

// Detail panel
const selectedItem = ref<Item | null>(null)
const showPanel = ref(false)
const bomTree = ref<BOMTreeNode | null>(null)
const whereUsed = ref<{ item: Item; quantity: number }[]>([])
const loadingBom = ref(false)
const loadingWhereUsed = ref(false)

const lifecycleStates = ['Design', 'Review', 'Released', 'Obsolete']

// Get unique projects from items for filter dropdown
const projects = computed(() => {
  const projectSet = new Set<string>()
  itemsStore.items.forEach(item => {
    if (item.project_name) projectSet.add(item.project_name)
  })
  return Array.from(projectSet).sort()
})

// Client-side filtering and sorting
const filteredItems = computed(() => {
  let result = [...itemsStore.items]

  // Apply filters
  if (searchInput.value) {
    const q = searchInput.value.toLowerCase()
    result = result.filter(item =>
      item.item_number.toLowerCase().includes(q) ||
      (item.name && item.name.toLowerCase().includes(q)) ||
      (item.description && item.description.toLowerCase().includes(q)) ||
      (item.project_name && item.project_name.toLowerCase().includes(q))
    )
  }

  if (lifecycleFilter.value) {
    result = result.filter(item => item.lifecycle_state === lifecycleFilter.value)
  }

  if (projectFilter.value) {
    result = result.filter(item => item.project_name === projectFilter.value)
  }

  // Apply sorting
  result.sort((a, b) => {
    let aVal = a[sortColumn.value as keyof Item] ?? ''
    let bVal = b[sortColumn.value as keyof Item] ?? ''

    if (typeof aVal === 'string') aVal = aVal.toLowerCase()
    if (typeof bVal === 'string') bVal = bVal.toLowerCase()

    if (aVal < bVal) return sortDirection.value === 'asc' ? -1 : 1
    if (aVal > bVal) return sortDirection.value === 'asc' ? 1 : -1
    return 0
  })

  return result
})

const itemCount = computed(() => {
  const filtered = filteredItems.value.length
  const total = itemsStore.items.length
  return filtered === total ? `${total} items` : `${filtered} of ${total} items`
})

// Debounced fetch for server-side filtering (optional)
const debouncedFetch = useDebounceFn(() => {
  // Currently using client-side filtering
}, 300)

watch([searchInput, lifecycleFilter, projectFilter], () => {
  // Currently client-side, but could trigger server fetch
})

onMounted(() => {
  itemsStore.fetchItems({ limit: 1000 })
})

function sort(column: string) {
  if (sortColumn.value === column) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortColumn.value = column
    sortDirection.value = 'asc'
  }
}

function getSortIndicator(column: string) {
  if (sortColumn.value !== column) return ''
  return sortDirection.value === 'asc' ? ' ▲' : ' ▼'
}

async function selectItem(item: Item) {
  selectedItem.value = item
  showPanel.value = true
  bomTree.value = null
  whereUsed.value = []

  // Fetch full item details
  await itemsStore.fetchItem(item.item_number)
  if (itemsStore.currentItem) {
    selectedItem.value = itemsStore.currentItem
  }

  // Load BOM and Where Used
  loadBOM()
  loadWhereUsed()
}

async function loadBOM() {
  if (!selectedItem.value) return
  loadingBom.value = true
  try {
    bomTree.value = await itemsStore.getBOMTree(selectedItem.value.item_number)
  } catch (e) {
    bomTree.value = null
  } finally {
    loadingBom.value = false
  }
}

async function loadWhereUsed() {
  if (!selectedItem.value) return
  loadingWhereUsed.value = true
  try {
    whereUsed.value = await itemsStore.getWhereUsed(selectedItem.value.item_number)
  } catch (e) {
    whereUsed.value = []
  } finally {
    loadingWhereUsed.value = false
  }
}

function closePanel() {
  showPanel.value = false
  selectedItem.value = null
}

function navigateToItem(itemNumber: string) {
  const item = itemsStore.items.find(i => i.item_number === itemNumber)
  if (item) {
    selectItem(item)
  }
}

function getStateClass(state: string) {
  return `lifecycle-badge ${state.toLowerCase()}`
}

function getFileTypeClass(type: string) {
  return `file-type-badge ${type.toLowerCase()}`
}

function formatDate(date: string | undefined) {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

function formatMass(mass: number | undefined) {
  if (!mass) return '-'
  return `${mass.toFixed(2)} kg`
}

async function openFile(file: FileInfo) {
  if (!file.file_path) {
    alert('File not available in storage')
    return
  }

  const url = await getSignedUrlFromPath(file.file_path)
  if (url) {
    window.open(url, '_blank')
  } else {
    alert('Failed to generate file URL')
  }
}

// Close panel on escape
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && showPanel.value) {
    closePanel()
  }
}

function goHome() {
  router.push('/')
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="pdm-browser">
    <!-- Controls Bar -->
    <div class="controls-bar">
      <button class="home-btn" @click="goHome">
        <i class="pi pi-home"></i>
        Home
      </button>
      <input
        v-model="searchInput"
        type="text"
        placeholder="Search items..."
        class="search-input"
      />
      <select v-model="lifecycleFilter" class="filter-select">
        <option value="">All States</option>
        <option v-for="state in lifecycleStates" :key="state" :value="state">
          {{ state }}
        </option>
      </select>
      <select v-model="projectFilter" class="filter-select">
        <option value="">All Projects</option>
        <option v-for="proj in projects" :key="proj" :value="proj">
          {{ proj }}
        </option>
      </select>
      <div class="stats">{{ itemCount }}</div>
      <div class="user-info">
        <span>{{ authStore.user?.username }}</span>
        <button @click="authStore.logout()" class="logout-btn">Logout</button>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="itemsStore.loading && itemsStore.items.length === 0" class="loading-state">
      Loading items...
    </div>

    <!-- Main Content -->
    <div v-else class="main-content">
      <!-- Items Table -->
      <div class="table-container" :class="{ 'panel-open': showPanel }">
        <div class="table-header-row">
          <div class="th" @click="sort('item_number')">Item #{{ getSortIndicator('item_number') }}</div>
          <div class="th" @click="sort('description')">Description{{ getSortIndicator('description') }}</div>
          <div class="th" @click="sort('project_name')">Project{{ getSortIndicator('project_name') }}</div>
          <div class="th" @click="sort('revision')">Rev{{ getSortIndicator('revision') }}</div>
          <div class="th" @click="sort('lifecycle_state')">State{{ getSortIndicator('lifecycle_state') }}</div>
          <div class="th" @click="sort('material')">Material{{ getSortIndicator('material') }}</div>
          <div class="th" @click="sort('updated_at')">Modified{{ getSortIndicator('updated_at') }}</div>
          <div class="th" @click="sort('mass')">Mass{{ getSortIndicator('mass') }}</div>
        </div>

        <div class="table-body">
          <div
            v-for="item in filteredItems"
            :key="item.id"
            class="table-row"
            :class="{ selected: selectedItem?.id === item.id }"
            @click="selectItem(item)"
          >
            <div class="td item-number">{{ item.item_number }}</div>
            <div class="td description" :title="item.description || item.name || ''">
              {{ item.description || item.name || '-' }}
            </div>
            <div class="td" :title="item.project_name || ''">{{ item.project_name || '-' }}</div>
            <div class="td revision">{{ item.revision }}.{{ item.iteration }}</div>
            <div class="td">
              <span :class="getStateClass(item.lifecycle_state)">
                {{ item.lifecycle_state }}
              </span>
            </div>
            <div class="td" :title="item.material || ''">{{ item.material || '-' }}</div>
            <div class="td">{{ formatDate(item.updated_at) }}</div>
            <div class="td">{{ formatMass(item.mass) }}</div>
          </div>

          <div v-if="filteredItems.length === 0" class="empty-row">
            No items found
          </div>
        </div>
      </div>

      <!-- Detail Panel -->
      <div class="detail-panel" :class="{ open: showPanel }">
        <template v-if="selectedItem">
          <div class="panel-header">
            <span class="panel-title">{{ selectedItem.item_number }}</span>
            <button class="close-btn" @click="closePanel">&times;</button>
          </div>

          <div class="panel-content">
            <!-- Item Information -->
            <div class="section">
              <h3>Item Information</h3>
              <div class="info-grid">
                <div class="info-row">
                  <span class="label">Item Number</span>
                  <span class="value">{{ selectedItem.item_number }}</span>
                </div>
                <div class="info-row" v-if="selectedItem.name">
                  <span class="label">Name</span>
                  <span class="value">{{ selectedItem.name }}</span>
                </div>
                <div class="info-row" v-if="selectedItem.description">
                  <span class="label">Description</span>
                  <span class="value">{{ selectedItem.description }}</span>
                </div>
                <div class="info-row">
                  <span class="label">Revision</span>
                  <span class="value">{{ selectedItem.revision }}.{{ selectedItem.iteration }}</span>
                </div>
                <div class="info-row">
                  <span class="label">State</span>
                  <span class="value">
                    <span :class="getStateClass(selectedItem.lifecycle_state)">
                      {{ selectedItem.lifecycle_state }}
                    </span>
                  </span>
                </div>
                <div class="info-row" v-if="selectedItem.project_name">
                  <span class="label">Project</span>
                  <span class="value">{{ selectedItem.project_name }}</span>
                </div>
                <div class="info-row" v-if="selectedItem.material">
                  <span class="label">Material</span>
                  <span class="value">{{ selectedItem.material }}</span>
                </div>
                <div class="info-row" v-if="selectedItem.mass">
                  <span class="label">Mass</span>
                  <span class="value">{{ selectedItem.mass }} kg</span>
                </div>
                <div class="info-row" v-if="selectedItem.thickness">
                  <span class="label">Thickness</span>
                  <span class="value">{{ selectedItem.thickness }} mm</span>
                </div>
                <div class="info-row" v-if="selectedItem.cut_length">
                  <span class="label">Cut Length</span>
                  <span class="value">{{ selectedItem.cut_length }} mm</span>
                </div>
                <div class="info-row">
                  <span class="label">Created</span>
                  <span class="value">{{ formatDate(selectedItem.created_at) }}</span>
                </div>
                <div class="info-row">
                  <span class="label">Modified</span>
                  <span class="value">{{ formatDate(selectedItem.updated_at) }}</span>
                </div>
              </div>
            </div>

            <!-- Files Section -->
            <div class="section">
              <h3>Files ({{ selectedItem.files?.length || 0 }})</h3>
              <div v-if="selectedItem.files && selectedItem.files.length > 0" class="files-list">
                <div
                  v-for="file in selectedItem.files"
                  :key="file.id"
                  class="file-item"
                  :class="{ 'file-available': file.file_path, 'file-unavailable': !file.file_path }"
                  @click="openFile(file)"
                  :title="file.file_path ? 'Click to open' : 'File not in storage'"
                >
                  <span :class="getFileTypeClass(file.file_type)">{{ file.file_type }}</span>
                  <span class="file-name">{{ file.file_name }}</span>
                  <span v-if="file.file_path" class="file-action">Open</span>
                  <span v-else class="file-missing">Not in storage</span>
                </div>
              </div>
              <div v-else class="empty-section">No files</div>
            </div>

            <!-- BOM Section -->
            <div class="section">
              <h3>Bill of Materials ({{ bomTree?.children?.length || 0 }})</h3>
              <div v-if="loadingBom" class="loading-section">Loading...</div>
              <div v-else-if="bomTree && bomTree.children && bomTree.children.length > 0" class="bom-list">
                <div
                  v-for="child in bomTree.children"
                  :key="child.item.id"
                  class="bom-item"
                  @click="navigateToItem(child.item.item_number)"
                >
                  <span class="bom-item-number">{{ child.item.item_number }}</span>
                  <span class="bom-qty">Qty: {{ child.quantity }}</span>
                </div>
              </div>
              <div v-else class="empty-section">No child components</div>
            </div>

            <!-- Where Used Section -->
            <div class="section">
              <h3>Where Used ({{ whereUsed.length }})</h3>
              <div v-if="loadingWhereUsed" class="loading-section">Loading...</div>
              <div v-else-if="whereUsed.length > 0" class="bom-list">
                <div
                  v-for="entry in whereUsed"
                  :key="entry.item.id"
                  class="bom-item"
                  @click="navigateToItem(entry.item.item_number)"
                >
                  <span class="bom-item-number">{{ entry.item.item_number }}</span>
                  <span class="bom-qty">Qty: {{ entry.quantity }}</span>
                </div>
              </div>
              <div v-else class="empty-section">Not used in any assemblies</div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdm-browser {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #e5e5e5;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  font-size: 13px;
  color: #333;
}

/* Controls Bar */
.controls-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: #fff;
  border-bottom: 1px solid #d0d0d0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.search-input {
  flex: 1;
  max-width: 400px;
  padding: 8px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 13px;
  background: #fff;
}

.search-input:focus {
  outline: none;
  border-color: #888;
}

.filter-select {
  padding: 8px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 13px;
  background: #fff;
  min-width: 120px;
}

.stats {
  color: #666;
  font-size: 12px;
  margin-left: auto;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #666;
  font-size: 12px;
}

.logout-btn {
  padding: 6px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #fff;
  color: #666;
  cursor: pointer;
  font-size: 12px;
}

.logout-btn:hover {
  background: #f5f5f5;
  border-color: #999;
}

.home-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border: none;
  border-radius: 4px;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
}

.home-btn:hover {
  background: #1d4ed8;
}

/* Loading */
.loading-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #888;
}

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

/* Table Container */
.table-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #f8f8f8;
  transition: margin-right 0.3s ease;
}

.table-container.panel-open {
  margin-right: 0;
}

.table-header-row {
  display: grid;
  grid-template-columns: 120px 1fr 150px 70px 100px 150px 100px 80px;
  background: #e8e8e8;
  border-bottom: 1px solid #d0d0d0;
  position: sticky;
  top: 0;
  z-index: 10;
}

.th {
  padding: 10px 12px;
  font-weight: 600;
  font-size: 12px;
  color: #555;
  text-transform: uppercase;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.th:hover {
  background: #ddd;
}

.table-body {
  flex: 1;
  overflow-y: auto;
}

.table-row {
  display: grid;
  grid-template-columns: 120px 1fr 150px 70px 100px 150px 100px 80px;
  border-bottom: 1px solid #e0e0e0;
  cursor: pointer;
  background: #fff;
}

.table-row:hover {
  background: #f0f0f0;
}

.table-row.selected {
  background: #d8d8d8;
}

.td {
  padding: 8px 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #333;
}

.item-number {
  font-weight: 600;
  color: #333;
  font-family: monospace;
}

.description {
  color: #555;
}

.revision {
  font-family: monospace;
  color: #666;
}

.empty-row {
  padding: 40px;
  text-align: center;
  color: #888;
}

/* Lifecycle Badges */
.lifecycle-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.lifecycle-badge.design {
  background: #e0e0e0;
  color: #555;
}

.lifecycle-badge.review {
  background: #fff3cd;
  color: #856404;
}

.lifecycle-badge.released {
  background: #c8c8c8;
  color: #1a1a1a;
}

.lifecycle-badge.obsolete {
  background: #d8d8d8;
  color: #666;
}

/* Detail Panel */
.detail-panel {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 500px;
  background: #fff;
  border-left: 1px solid #ccc;
  box-shadow: -2px 0 8px rgba(0,0,0,0.1);
  transform: translateX(100%);
  transition: transform 0.3s ease;
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.detail-panel.open {
  transform: translateX(0);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: #4a4a4a;
  color: #fff;
}

.panel-title {
  font-size: 18px;
  font-weight: 600;
  font-family: monospace;
}

.close-btn {
  background: none;
  border: none;
  color: #fff;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #ccc;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 0;
}

/* Sections */
.section {
  padding: 16px 20px;
  border-bottom: 1px solid #e0e0e0;
}

.section h3 {
  margin: 0 0 12px 0;
  font-size: 13px;
  font-weight: 600;
  color: #333;
  text-transform: uppercase;
}

.info-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 12px;
}

.label {
  font-size: 11px;
  color: #888;
  text-transform: uppercase;
}

.value {
  color: #333;
}

/* Files */
.files-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  background: #f8f8f8;
  border-radius: 4px;
  cursor: pointer;
}

.file-item:hover {
  background: #f0f0f0;
}

.file-item.file-available:hover {
  background: #e8f4ff;
}

.file-item.file-unavailable {
  opacity: 0.6;
  cursor: not-allowed;
}

.file-action {
  font-size: 11px;
  color: #2563eb;
  font-weight: 500;
}

.file-missing {
  font-size: 10px;
  color: #999;
  font-style: italic;
}

.file-type-badge {
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  background: #d0d0d0;
  color: #555;
}

.file-type-badge.step { background: #c8c8c8; }
.file-type-badge.dxf { background: #d8d8d8; }
.file-type-badge.svg { background: #b8b8b8; }
.file-type-badge.pdf { background: #e0e0e0; }
.file-type-badge.cad { background: #d0d0d0; }

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #333;
}

.file-date {
  font-size: 11px;
  color: #888;
}

/* BOM List */
.bom-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bom-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  background: #f8f8f8;
  border-radius: 4px;
  cursor: pointer;
}

.bom-item:hover {
  background: #f0f0f0;
}

.bom-item-number {
  font-weight: 600;
  font-family: monospace;
  color: #333;
}

.bom-qty {
  font-size: 12px;
  color: #666;
}

.empty-section {
  color: #888;
  font-size: 12px;
  font-style: italic;
}

.loading-section {
  color: #888;
  font-size: 12px;
}
</style>
