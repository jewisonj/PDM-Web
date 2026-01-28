<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useItemsStore } from '../stores/items'
import { useAuthStore } from '../stores/auth'
import type { BOMTreeNode, FileInfo } from '../types'

const route = useRoute()
const router = useRouter()
const itemsStore = useItemsStore()
const authStore = useAuthStore()

const itemNumber = computed(() => route.params.itemNumber as string)
const activeTab = ref<'files' | 'bom' | 'where-used' | 'history'>('files')

const bomTree = ref<BOMTreeNode | null>(null)
const whereUsed = ref<{ item: any; quantity: number }[]>([])
const history = ref<any[]>([])

onMounted(async () => {
  await itemsStore.fetchItem(itemNumber.value)
})

async function loadBOM() {
  if (!bomTree.value) {
    bomTree.value = await itemsStore.getBOMTree(itemNumber.value)
  }
}

async function loadWhereUsed() {
  if (whereUsed.value.length === 0) {
    whereUsed.value = await itemsStore.getWhereUsed(itemNumber.value)
  }
}

async function loadHistory() {
  if (history.value.length === 0) {
    history.value = await itemsStore.getItemHistory(itemNumber.value)
  }
}

function switchTab(tab: typeof activeTab.value) {
  activeTab.value = tab
  if (tab === 'bom') loadBOM()
  if (tab === 'where-used') loadWhereUsed()
  if (tab === 'history') loadHistory()
}

function getFileIcon(type: string) {
  const icons: Record<string, string> = {
    STEP: '📦',
    CAD: '📐',
    DXF: '📄',
    SVG: '🎨',
    PDF: '📕',
    IMAGE: '🖼️',
    OTHER: '📎',
  }
  return icons[type] || '📎'
}

function formatDate(date: string) {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatSize(bytes?: number) {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <div class="item-detail">
    <header class="detail-header">
      <button @click="router.push('/')" class="back-btn">&larr; Back to Items</button>
      <div class="header-actions" v-if="authStore.isEngineer">
        <button class="btn-secondary">Edit</button>
        <button class="btn-primary">Upload File</button>
      </div>
    </header>

    <div v-if="itemsStore.loading" class="loading">Loading item...</div>

    <div v-else-if="itemsStore.error" class="error">{{ itemsStore.error }}</div>

    <div v-else-if="itemsStore.currentItem" class="item-content">
      <div class="item-header">
        <div class="item-title">
          <h1>{{ itemsStore.currentItem.item_number }}</h1>
          <span class="state-badge" :class="`state-${itemsStore.currentItem.lifecycle_state.toLowerCase()}`">
            {{ itemsStore.currentItem.lifecycle_state }}
          </span>
        </div>
        <div class="item-revision">
          Rev {{ itemsStore.currentItem.revision }}.{{ itemsStore.currentItem.iteration }}
        </div>
      </div>

      <div class="item-meta">
        <div class="meta-row" v-if="itemsStore.currentItem.name">
          <span class="meta-label">Name</span>
          <span class="meta-value">{{ itemsStore.currentItem.name }}</span>
        </div>
        <div class="meta-row" v-if="itemsStore.currentItem.description">
          <span class="meta-label">Description</span>
          <span class="meta-value">{{ itemsStore.currentItem.description }}</span>
        </div>
        <div class="meta-row" v-if="itemsStore.currentItem.material">
          <span class="meta-label">Material</span>
          <span class="meta-value">{{ itemsStore.currentItem.material }}</span>
        </div>
        <div class="meta-grid">
          <div class="meta-item" v-if="itemsStore.currentItem.thickness">
            <span class="meta-label">Thickness</span>
            <span class="meta-value">{{ itemsStore.currentItem.thickness }} mm</span>
          </div>
          <div class="meta-item" v-if="itemsStore.currentItem.mass">
            <span class="meta-label">Mass</span>
            <span class="meta-value">{{ itemsStore.currentItem.mass }} kg</span>
          </div>
          <div class="meta-item" v-if="itemsStore.currentItem.cut_length">
            <span class="meta-label">Cut Length</span>
            <span class="meta-value">{{ itemsStore.currentItem.cut_length }} mm</span>
          </div>
        </div>
      </div>

      <div class="tabs">
        <button
          :class="{ active: activeTab === 'files' }"
          @click="switchTab('files')"
        >
          Files ({{ itemsStore.currentItem.files?.length || 0 }})
        </button>
        <button
          :class="{ active: activeTab === 'bom' }"
          @click="switchTab('bom')"
        >
          BOM
        </button>
        <button
          :class="{ active: activeTab === 'where-used' }"
          @click="switchTab('where-used')"
        >
          Where Used
        </button>
        <button
          :class="{ active: activeTab === 'history' }"
          @click="switchTab('history')"
        >
          History
        </button>
      </div>

      <div class="tab-content">
        <!-- Files Tab -->
        <div v-if="activeTab === 'files'" class="files-list">
          <div
            v-for="file in itemsStore.currentItem.files"
            :key="file.id"
            class="file-card"
          >
            <span class="file-icon">{{ getFileIcon(file.file_type) }}</span>
            <div class="file-info">
              <div class="file-name">{{ file.file_name }}</div>
              <div class="file-meta">
                {{ file.file_type }} &bull; {{ formatSize(file.file_size) }} &bull; {{ formatDate(file.created_at) }}
              </div>
            </div>
            <button class="btn-icon">⬇️</button>
          </div>
          <div v-if="!itemsStore.currentItem.files?.length" class="empty">
            No files uploaded yet
          </div>
        </div>

        <!-- BOM Tab -->
        <div v-if="activeTab === 'bom'" class="bom-tree">
          <div v-if="bomTree">
            <div v-if="bomTree.children.length">
              <div v-for="child in bomTree.children" :key="child.item.id" class="bom-row">
                <span class="bom-qty">{{ child.quantity }}x</span>
                <span class="bom-item" @click="router.push(`/items/${child.item.item_number}`)">
                  {{ child.item.item_number }}
                </span>
                <span class="bom-name">{{ child.item.name || '-' }}</span>
              </div>
            </div>
            <div v-else class="empty">No BOM components</div>
          </div>
          <div v-else class="loading">Loading BOM...</div>
        </div>

        <!-- Where Used Tab -->
        <div v-if="activeTab === 'where-used'" class="where-used">
          <div v-if="whereUsed.length">
            <div v-for="entry in whereUsed" :key="entry.item.id" class="bom-row">
              <span class="bom-qty">{{ entry.quantity }}x</span>
              <span class="bom-item" @click="router.push(`/items/${entry.item.item_number}`)">
                {{ entry.item.item_number }}
              </span>
              <span class="bom-name">{{ entry.item.name || '-' }}</span>
            </div>
          </div>
          <div v-else class="empty">Not used in any assemblies</div>
        </div>

        <!-- History Tab -->
        <div v-if="activeTab === 'history'" class="history-list">
          <div v-if="history.length">
            <div v-for="entry in history" :key="entry.id" class="history-entry">
              <div class="history-date">{{ formatDate(entry.changed_at) }}</div>
              <div class="history-change">
                {{ entry.old_state }} → {{ entry.new_state }}
                <span v-if="entry.old_revision !== entry.new_revision">
                  (Rev {{ entry.old_revision }} → {{ entry.new_revision }})
                </span>
              </div>
              <div v-if="entry.change_notes" class="history-notes">{{ entry.change_notes }}</div>
            </div>
          </div>
          <div v-else class="empty">No history recorded</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.item-detail {
  padding: 1rem;
  max-width: 1000px;
  margin: 0 auto;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.back-btn {
  background: transparent;
  border: none;
  color: #64b5f6;
  cursor: pointer;
  font-size: 1rem;
}

.back-btn:hover {
  text-decoration: underline;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
}

.loading, .error, .empty {
  padding: 2rem;
  text-align: center;
  color: #888;
}

.error {
  color: #ff6b6b;
}

.item-content {
  background: #16213e;
  border-radius: 8px;
  padding: 1.5rem;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #1a1a2e;
}

.item-title {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.item-title h1 {
  margin: 0;
  font-family: monospace;
  font-size: 1.75rem;
  color: #64b5f6;
}

.item-revision {
  font-family: monospace;
  color: #888;
  font-size: 1.1rem;
}

.state-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-size: 0.85rem;
}

.state-design { background: rgba(100, 181, 246, 0.2); color: #64b5f6; }
.state-review { background: rgba(255, 193, 7, 0.2); color: #ffc107; }
.state-released { background: rgba(76, 175, 80, 0.2); color: #4caf50; }
.state-obsolete { background: rgba(158, 158, 158, 0.2); color: #9e9e9e; }

.item-meta {
  margin-bottom: 1.5rem;
}

.meta-row {
  margin-bottom: 0.75rem;
}

.meta-label {
  display: block;
  color: #666;
  font-size: 0.85rem;
  margin-bottom: 0.25rem;
}

.meta-value {
  color: #e0e0e0;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #1a1a2e;
}

.tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #1a1a2e;
  margin-bottom: 1rem;
}

.tabs button {
  padding: 0.75rem 1.5rem;
  background: transparent;
  border: none;
  color: #888;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tabs button:hover {
  color: #e0e0e0;
}

.tabs button.active {
  color: #64b5f6;
  border-bottom-color: #64b5f6;
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: #0f0f1a;
  border-radius: 4px;
}

.file-icon {
  font-size: 1.5rem;
}

.file-info {
  flex: 1;
}

.file-name {
  color: #e0e0e0;
  font-weight: 500;
}

.file-meta {
  color: #666;
  font-size: 0.85rem;
}

.btn-icon {
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 1.25rem;
}

.bom-row {
  display: flex;
  gap: 1rem;
  padding: 0.5rem;
  border-bottom: 1px solid #0f0f1a;
}

.bom-qty {
  color: #888;
  min-width: 40px;
}

.bom-item {
  font-family: monospace;
  color: #64b5f6;
  cursor: pointer;
}

.bom-item:hover {
  text-decoration: underline;
}

.bom-name {
  color: #888;
}

.history-entry {
  padding: 0.75rem 0;
  border-bottom: 1px solid #0f0f1a;
}

.history-date {
  color: #666;
  font-size: 0.85rem;
}

.history-change {
  color: #e0e0e0;
}

.history-notes {
  color: #888;
  font-size: 0.9rem;
  margin-top: 0.25rem;
}

.btn-primary {
  padding: 0.5rem 1rem;
  background: #e94560;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.btn-secondary {
  padding: 0.5rem 1rem;
  background: transparent;
  color: #888;
  border: 1px solid #444;
  border-radius: 4px;
  cursor: pointer;
}
</style>
