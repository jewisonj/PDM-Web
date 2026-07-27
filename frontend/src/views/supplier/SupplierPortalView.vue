<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useSupplierAuthStore } from '../../stores/supplierAuth'
import type { SupplierItemView } from '../../types/supplier'

const router = useRouter()
const supplierAuth = useSupplierAuthStore()

const items = ref<SupplierItemView[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const searchQuery = ref('')
const thumbnailUrls = ref<Map<string, string>>(new Map())

const filteredItems = computed(() => {
  if (!searchQuery.value) return items.value
  const q = searchQuery.value.toLowerCase()
  return items.value.filter(item =>
    item.item_number.toLowerCase().includes(q) ||
    (item.name && item.name.toLowerCase().includes(q)) ||
    (item.material && item.material.toLowerCase().includes(q))
  )
})

/**
 * Fetch thumbnail URL for an item and cache it
 */
async function fetchThumbnailUrl(item: SupplierItemView) {
  const imageFile = item.files.find(f => f.file_type === 'IMAGE')
  if (!imageFile) return

  try {
    const response = await supplierAuth.getDownloadUrl(item.item_number, imageFile.id)
    thumbnailUrls.value.set(item.id, response.url)
  } catch (e) {
    console.warn(`Failed to load thumbnail for ${item.item_number}:`, e)
  }
}

/**
 * Load thumbnails for all items with IMAGE files
 */
async function loadThumbnails() {
  const promises = items.value
    .filter(item => item.files.some(f => f.file_type === 'IMAGE'))
    .map(item => fetchThumbnailUrl(item))

  await Promise.allSettled(promises)
}

onMounted(async () => {
  try {
    items.value = await supplierAuth.getItems()
    // Load thumbnails after items are loaded
    await loadThumbnails()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load items'
  } finally {
    loading.value = false
  }
})

function logout() {
  supplierAuth.logout()
  router.push('/supplier-login')
}

function viewItem(itemNumber: string) {
  router.push(`/supplier/item/${itemNumber}`)
}

function formatFileTypes(types: string[]): string {
  return types.join(', ')
}

function exportToCsv() {
  const headers = ['Part Number', 'Name', 'Revision', 'Material', 'Thickness', 'Weight (lb)', 'Lifecycle', 'File Types']
  const rows = filteredItems.value.map(item => [
    item.item_number,
    item.name || '',
    item.revision,
    item.material || '',
    item.thickness?.toString() || '',
    item.mass?.toString() || '',
    item.lifecycle_state,
    formatFileTypes(item.allowed_file_types)
  ])

  const csvContent = [
    headers.join(','),
    ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
  ].join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `supplier-items-${new Date().toISOString().split('T')[0]}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

function getThumbnailUrl(item: SupplierItemView): string | null {
  return thumbnailUrls.value.get(item.id) || null
}
</script>

<template>
  <div class="portal-container">
    <header class="portal-header">
      <div class="header-content">
        <h1>Supplier Portal</h1>
        <p class="company-name" v-if="supplierAuth.supplier">
          {{ supplierAuth.supplier.company_name }}
        </p>
      </div>
      <button class="logout-btn" @click="logout">
        Logout
      </button>
    </header>

    <main class="portal-main">
      <div class="controls-bar">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search items..."
          class="search-input"
        />
        <span class="item-count">{{ filteredItems.length }} items</span>
        <button class="export-btn" @click="exportToCsv">
          <i class="pi pi-download"></i>
          Export CSV
        </button>
      </div>

      <div v-if="loading" class="loading-state">
        Loading your items...
      </div>

      <div v-else-if="error" class="error-state">
        {{ error }}
      </div>

      <div v-else-if="items.length === 0" class="empty-state">
        <h3>No Items Assigned</h3>
        <p>Contact your account manager to request access to items.</p>
      </div>

      <div v-else class="table-container">
        <table class="items-table">
          <thead>
            <tr>
              <th style="width: 60px;">Thumb</th>
              <th style="width: 140px;">Part Number</th>
              <th>Name</th>
              <th style="width: 60px;">Rev</th>
              <th style="width: 120px;">Material</th>
              <th class="hide-below-1200" style="width: 80px;">Thick</th>
              <th class="hide-below-1200" style="width: 90px;">Weight</th>
              <th style="width: 100px;">Status</th>
              <th style="width: 150px;">Files</th>
              <th style="width: 80px;">Comments</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in filteredItems"
              :key="item.id"
              @click="viewItem(item.item_number)"
              class="item-row"
            >
              <td>
                <img
                  v-if="getThumbnailUrl(item)"
                  :src="getThumbnailUrl(item)!"
                  alt="Thumbnail"
                  class="thumbnail"
                />
                <div v-else class="thumbnail-placeholder">
                  <i class="pi pi-image"></i>
                </div>
              </td>
              <td>
                <span class="item-number">{{ item.item_number }}</span>
              </td>
              <td>{{ item.name || 'Untitled Part' }}</td>
              <td>{{ item.revision }}</td>
              <td>{{ item.material || '-' }}</td>
              <td class="hide-below-1200">{{ item.thickness || '-' }}</td>
              <td class="hide-below-1200">{{ item.mass || '-' }}</td>
              <td>
                <span :class="['lifecycle-badge', item.lifecycle_state.toLowerCase()]">
                  {{ item.lifecycle_state }}
                </span>
              </td>
              <td>
                <span class="file-types">{{ formatFileTypes(item.allowed_file_types) }}</span>
              </td>
              <td>
                <span v-if="item.unread_comments > 0" class="unread-badge">
                  {{ item.unread_comments }} new
                </span>
                <span v-else class="no-comments">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </main>
  </div>
</template>

<style scoped>
.portal-container {
  min-height: 100vh;
  background: #f8fafc;
}

.portal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 2rem;
  background: #1e40af;
  color: white;
}

.header-content h1 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
}

.company-name {
  margin: 0.25rem 0 0;
  opacity: 0.85;
  font-size: 0.9rem;
}

.logout-btn {
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  padding: 0.5rem 1.25rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.logout-btn:hover {
  background: rgba(255, 255, 255, 0.25);
}

.portal-main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem;
}

.controls-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.search-input {
  flex: 1;
  max-width: 400px;
  padding: 10px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
}

.search-input:focus {
  outline: none;
  border-color: #1e40af;
  box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1);
}

.item-count {
  color: #64748b;
  font-size: 14px;
}

.export-btn {
  margin-left: auto;
  background: #059669;
  color: white;
  border: none;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.2s;
}

.export-btn:hover {
  background: #047857;
}

.loading-state,
.error-state,
.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #64748b;
}

.error-state {
  color: #dc2626;
}

.empty-state h3 {
  margin: 0 0 0.5rem;
  color: #334155;
}

.empty-state p {
  margin: 0;
}

.table-container {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
}

.items-table {
  width: 100%;
  border-collapse: collapse;
}

.items-table thead {
  background: #f8fafc;
  border-bottom: 2px solid #e2e8f0;
}

.items-table th {
  padding: 12px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
}

.items-table tbody tr {
  border-bottom: 1px solid #f1f5f9;
}

.items-table tbody tr:last-child {
  border-bottom: none;
}

.item-row {
  cursor: pointer;
  transition: background 0.15s;
}

.item-row:hover {
  background: #f8fafc;
}

.items-table td {
  padding: 12px;
  font-size: 14px;
  color: #334155;
}

.thumbnail {
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
}

.thumbnail-placeholder {
  width: 44px;
  height: 44px;
  background: #f1f5f9;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 18px;
}

.item-number {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-weight: 600;
  color: #1e40af;
}

.lifecycle-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 12px;
  font-weight: 500;
  text-transform: uppercase;
  font-size: 10px;
}

.lifecycle-badge.design { background: #e0e7ff; color: #3730a3; }
.lifecycle-badge.review { background: #fef3c7; color: #92400e; }
.lifecycle-badge.released { background: #d1fae5; color: #065f46; }
.lifecycle-badge.obsolete { background: #f3f4f6; color: #6b7280; }

.file-types {
  color: #64748b;
  font-size: 12px;
}

.unread-badge {
  background: #dc2626;
  color: white;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 12px;
}

.no-comments {
  color: #cbd5e1;
}

@media (max-width: 1200px) {
  .hide-below-1200 {
    display: none;
  }
}
</style>
