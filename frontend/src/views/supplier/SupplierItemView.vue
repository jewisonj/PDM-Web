<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useSupplierAuthStore } from '../../stores/supplierAuth'
import type { SupplierItemView, SupplierComment, SupplierFileView } from '../../types/supplier'
import StlViewer from '../../components/StlViewer.vue'

const router = useRouter()
const route = useRoute()
const supplierAuth = useSupplierAuthStore()

const itemNumber = computed(() => route.params.itemNumber as string)
const item = ref<SupplierItemView | null>(null)
const comments = ref<SupplierComment[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const newComment = ref('')
const postingComment = ref(false)
const downloadingFile = ref<string | null>(null)

// 3D Viewer state
const showStlViewer = ref(false)
const selectedStlFile = ref<SupplierFileView | null>(null)
const stlViewerUrl = ref('')

onMounted(async () => {
  await loadData()
})

async function loadData() {
  loading.value = true
  error.value = null

  try {
    const [itemData, commentsData] = await Promise.all([
      supplierAuth.getItem(itemNumber.value),
      supplierAuth.getComments(itemNumber.value),
    ])
    item.value = itemData
    comments.value = commentsData
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load item'
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/supplier/portal')
}

function logout() {
  supplierAuth.logout()
  router.push('/supplier-login')
}

async function downloadFile(fileId: string, fileName: string) {
  downloadingFile.value = fileId
  try {
    const result = await supplierAuth.getDownloadUrl(itemNumber.value, fileId)
    // Open in new tab
    window.open(result.url, '_blank')
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Download failed')
  } finally {
    downloadingFile.value = null
  }
}

async function openStlViewer(file: SupplierFileView) {
  try {
    const result = await supplierAuth.getDownloadUrl(itemNumber.value, file.id)
    stlViewerUrl.value = result.url
    selectedStlFile.value = file
    showStlViewer.value = true
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to load 3D model')
  }
}

function closeStlViewer() {
  showStlViewer.value = false
  selectedStlFile.value = null
  stlViewerUrl.value = ''
}

async function postComment() {
  if (!newComment.value.trim()) return

  postingComment.value = true
  try {
    const comment = await supplierAuth.postComment(itemNumber.value, newComment.value.trim())
    comments.value.push(comment)
    newComment.value = ''
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to post comment')
  } finally {
    postingComment.value = false
  }
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getFileTypeClass(type: string): string {
  return type.toLowerCase()
}
</script>

<template>
  <div class="item-view-container">
    <header class="view-header">
      <div class="header-left">
        <button class="back-btn" @click="goBack">
          &larr; Back to Items
        </button>
        <h1 v-if="item">{{ item.item_number }}</h1>
      </div>
      <div class="header-right">
        <span class="company-name" v-if="supplierAuth.supplier">
          {{ supplierAuth.supplier.company_name }}
        </span>
        <button class="logout-btn" @click="logout">Logout</button>
      </div>
    </header>

    <main class="view-main">
      <div v-if="loading" class="loading-state">Loading item details...</div>
      <div v-else-if="error" class="error-state">{{ error }}</div>

      <template v-else-if="item">
        <!-- Item Info Section -->
        <section class="info-section">
          <div class="info-header">
            <div>
              <h2 class="item-name">{{ item.name || 'Untitled Part' }}</h2>
              <div class="item-meta">
                <span class="revision">Revision {{ item.revision }}</span>
                <span :class="['lifecycle', item.lifecycle_state.toLowerCase()]">
                  {{ item.lifecycle_state }}
                </span>
                <span v-if="item.material" class="material">{{ item.material }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- Files Section -->
        <section class="files-section">
          <h3>Available Documents</h3>

          <div v-if="item.files.length === 0" class="empty-files">
            No files available for download.
          </div>

          <div v-else class="files-list">
            <div v-for="file in item.files" :key="file.id" class="file-row">
              <div class="file-info">
                <span :class="['file-type-badge', getFileTypeClass(file.file_type)]">
                  {{ file.file_type }}
                </span>
                <span class="file-name">{{ file.file_name }}</span>
                <span class="file-size">{{ formatFileSize(file.file_size) }}</span>
                <span v-if="file.revision" class="file-rev">Rev {{ file.revision }}</span>
              </div>
              <div class="file-actions">
                <button
                  v-if="file.file_type === 'STL'"
                  class="view-3d-btn"
                  @click.stop="openStlViewer(file)"
                >
                  View 3D
                </button>
                <button
                  class="download-btn"
                  @click="downloadFile(file.id, file.file_name)"
                  :disabled="downloadingFile === file.id"
                >
                  {{ downloadingFile === file.id ? 'Opening...' : 'Download' }}
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- Comments Section -->
        <section class="comments-section">
          <h3>Questions & Comments</h3>

          <div class="comments-list">
            <div
              v-for="comment in comments"
              :key="comment.id"
              :class="['comment', comment.author_type]"
            >
              <div class="comment-header">
                <span class="comment-author">{{ comment.author_name }}</span>
                <span class="comment-date">{{ formatDate(comment.created_at) }}</span>
              </div>
              <div class="comment-content">{{ comment.content }}</div>
            </div>

            <div v-if="comments.length === 0" class="no-comments">
              No comments yet. Ask a question below.
            </div>
          </div>

          <form @submit.prevent="postComment" class="comment-form">
            <textarea
              v-model="newComment"
              placeholder="Ask a question or leave a comment..."
              rows="3"
              :disabled="postingComment"
            ></textarea>
            <button
              type="submit"
              class="post-btn"
              :disabled="!newComment.trim() || postingComment"
            >
              {{ postingComment ? 'Posting...' : 'Post Comment' }}
            </button>
          </form>
        </section>
      </template>
    </main>

    <!-- 3D STL Viewer -->
    <StlViewer
      v-if="showStlViewer && selectedStlFile && item"
      :stl-url="stlViewerUrl"
      :file-id="selectedStlFile.id"
      :item-id="item.id"
      :item-number="item.item_number"
      :author-info="{
        type: 'supplier',
        id: supplierAuth.supplier?.id || '',
        name: supplierAuth.supplier?.company_name || 'Supplier'
      }"
      api-base="/api/supplier"
      @close="closeStlViewer"
    />
  </div>
</template>

<style scoped>
.item-view-container {
  min-height: 100vh;
  background: #f8fafc;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: #1e40af;
  color: white;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.back-btn {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.back-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

h1 {
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 1.5rem;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.company-name {
  opacity: 0.85;
  font-size: 14px;
}

.logout-btn {
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
  padding: 0.4rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.logout-btn:hover {
  background: rgba(255, 255, 255, 0.25);
}

.view-main {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem;
}

.loading-state,
.error-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #64748b;
}

.error-state {
  color: #dc2626;
}

section {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

h3 {
  margin: 0 0 1rem;
  color: #334155;
  font-size: 1rem;
  font-weight: 600;
}

/* Info Section */
.info-section {
  background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%);
  color: white;
}

.item-name {
  margin: 0 0 0.5rem;
  font-size: 1.25rem;
  color: white;
}

.item-meta {
  display: flex;
  gap: 1rem;
  font-size: 14px;
}

.revision {
  opacity: 0.9;
}

.lifecycle {
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.lifecycle.design { background: rgba(255,255,255,0.2); }
.lifecycle.review { background: #fef3c7; color: #92400e; }
.lifecycle.released { background: #d1fae5; color: #065f46; }
.lifecycle.obsolete { background: #f3f4f6; color: #6b7280; }

.material {
  opacity: 0.85;
}

/* Files Section */
.files-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.file-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.file-type-badge {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.file-type-badge.pdf { background: #fee2e2; color: #b91c1c; }
.file-type-badge.step { background: #dbeafe; color: #1e40af; }
.file-type-badge.dxf { background: #fef3c7; color: #92400e; }
.file-type-badge.svg { background: #d1fae5; color: #065f46; }
.file-type-badge.stl { background: #ede9fe; color: #7c3aed; }

.file-name {
  color: #334155;
  font-size: 14px;
}

.file-size {
  color: #94a3b8;
  font-size: 12px;
}

.file-rev {
  color: #64748b;
  font-size: 12px;
  background: #f1f5f9;
  padding: 2px 6px;
  border-radius: 4px;
}

.file-actions {
  display: flex;
  gap: 8px;
}

.view-3d-btn {
  background: #7c3aed;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.view-3d-btn:hover {
  background: #6d28d9;
}

.download-btn {
  background: #1e40af;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.download-btn:hover:not(:disabled) {
  background: #1e3a8a;
}

.download-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.empty-files {
  color: #94a3b8;
  text-align: center;
  padding: 2rem;
}

/* Comments Section */
.comments-list {
  margin-bottom: 1.5rem;
  max-height: 400px;
  overflow-y: auto;
}

.comment {
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 0.75rem;
}

.comment.supplier {
  background: #eff6ff;
  margin-right: 2rem;
}

.comment.admin {
  background: #f0fdf4;
  margin-left: 2rem;
}

.comment-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 12px;
}

.comment-author {
  font-weight: 600;
  color: #334155;
}

.comment-date {
  color: #94a3b8;
}

.comment-content {
  color: #475569;
  font-size: 14px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.no-comments {
  color: #94a3b8;
  text-align: center;
  padding: 2rem;
  font-style: italic;
}

.comment-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.comment-form textarea {
  padding: 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
}

.comment-form textarea:focus {
  outline: none;
  border-color: #1e40af;
  box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1);
}

.post-btn {
  align-self: flex-end;
  background: #1e40af;
  color: white;
  border: none;
  padding: 0.6rem 1.5rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.post-btn:hover:not(:disabled) {
  background: #1e3a8a;
}

.post-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
