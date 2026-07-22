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

const filteredItems = computed(() => {
  if (!searchQuery.value) return items.value
  const q = searchQuery.value.toLowerCase()
  return items.value.filter(item =>
    item.item_number.toLowerCase().includes(q) ||
    (item.name && item.name.toLowerCase().includes(q)) ||
    (item.material && item.material.toLowerCase().includes(q))
  )
})

onMounted(async () => {
  try {
    items.value = await supplierAuth.getItems()
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

function formatFileSize(bytes?: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
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

      <div v-else class="items-grid">
        <div
          v-for="item in filteredItems"
          :key="item.id"
          class="item-card"
          @click="viewItem(item.item_number)"
        >
          <div class="item-header">
            <span class="item-number">{{ item.item_number }}</span>
            <span class="item-revision">Rev {{ item.revision }}</span>
          </div>

          <div class="item-name">{{ item.name || 'Untitled Part' }}</div>

          <div class="item-meta">
            <span v-if="item.material" class="material">{{ item.material }}</span>
            <span :class="['lifecycle', item.lifecycle_state.toLowerCase()]">
              {{ item.lifecycle_state }}
            </span>
          </div>

          <div class="item-footer">
            <span class="file-count">
              {{ item.files.length }} file{{ item.files.length !== 1 ? 's' : '' }}
            </span>
            <span class="file-types">
              {{ formatFileTypes(item.allowed_file_types) }}
            </span>
          </div>

          <div v-if="item.unread_comments > 0" class="unread-badge">
            {{ item.unread_comments }} new
          </div>
        </div>
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

.items-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.item-card {
  position: relative;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1.25rem;
  cursor: pointer;
  transition: all 0.2s;
}

.item-card:hover {
  border-color: #1e40af;
  box-shadow: 0 4px 16px rgba(30, 64, 175, 0.12);
  transform: translateY(-2px);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.item-number {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 1.1rem;
  font-weight: 600;
  color: #1e40af;
}

.item-revision {
  color: #64748b;
  font-size: 0.85rem;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
}

.item-name {
  color: #334155;
  margin-bottom: 0.75rem;
  font-size: 14px;
  line-height: 1.4;
}

.item-meta {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  font-size: 12px;
}

.material {
  color: #64748b;
}

.lifecycle {
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
  text-transform: uppercase;
  font-size: 10px;
}

.lifecycle.design { background: #e0e7ff; color: #3730a3; }
.lifecycle.review { background: #fef3c7; color: #92400e; }
.lifecycle.released { background: #d1fae5; color: #065f46; }
.lifecycle.obsolete { background: #f3f4f6; color: #6b7280; }

.item-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 0.75rem;
  border-top: 1px solid #f1f5f9;
  font-size: 12px;
}

.file-count {
  color: #1e40af;
  font-weight: 500;
}

.file-types {
  color: #94a3b8;
  background: #f8fafc;
  padding: 2px 8px;
  border-radius: 4px;
}

.unread-badge {
  position: absolute;
  top: -8px;
  right: -8px;
  background: #dc2626;
  color: white;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 12px;
}
</style>
