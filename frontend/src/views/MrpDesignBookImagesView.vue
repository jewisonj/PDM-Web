<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { supabase } from '../services/supabase'

const API_BASE = '/api'
const route = useRoute()
const router = useRouter()

// Get bookCode from route if present
const bookCode = ref<string | null>(route.params.bookCode as string || null)

interface Category {
  id: string
  name: string
  description: string | null
  icon: string | null
  sort_order: number
  is_system: boolean
}

interface MrpProject {
  id: string
  project_code: string
  name: string | null
}

interface Item {
  id: string
  item_number: string
  name: string | null
}

interface DesignBook {
  id: string
  book_code: string
  title: string | null
  template_project_id: string | null
}

interface DesignBookImage {
  id: string
  file_name: string
  file_path: string
  file_size: number | null
  mime_type: string | null
  caption: string | null
  notes: string | null
  category_id: string | null
  item_id: string | null
  project_id: string | null
  width_pct: number
  created_at: string
  category: Category | null
  item: Item | null
  project: MrpProject | null
  _signedUrl?: string
}

// State
const images = ref<DesignBookImage[]>([])
const categories = ref<Category[]>([])
const mrpProjects = ref<MrpProject[]>([])
const designBook = ref<DesignBook | null>(null)
const loading = ref(true)
const searchInput = ref('')
const categoryFilter = ref('')
const projectFilter = ref('')

// Upload state
const showUploadModal = ref(false)
const uploadFile = ref<File | null>(null)
const uploadPreview = ref<string | null>(null)
const uploadCaption = ref('')
const uploadNotes = ref('')
const uploadCategoryId = ref('')
const uploadProjectId = ref('')
const uploadItemSearch = ref('')
const uploadItemId = ref('')
const uploadWidthPct = ref(100)
const uploading = ref(false)

// Edit state
const editingImage = ref<DesignBookImage | null>(null)
const showEditModal = ref(false)

// Category management state
const showCategoryModal = ref(false)
const newCategoryName = ref('')
const newCategoryDescription = ref('')
const newCategoryIcon = ref('pi pi-image')

// Status message
const statusMessage = ref('')
const statusType = ref<'success' | 'error' | ''>('')

// Computed
const displayedImages = computed(() => {
  return images.value.filter(img => {
    const search = searchInput.value.toLowerCase()
    const matchSearch = !search ||
      (img.caption || '').toLowerCase().includes(search) ||
      (img.notes || '').toLowerCase().includes(search) ||
      (img.file_name || '').toLowerCase().includes(search)

    const matchCategory = !categoryFilter.value || img.category_id === categoryFilter.value
    const matchProject = !projectFilter.value || img.project_id === projectFilter.value

    return matchSearch && matchCategory && matchProject
  })
})

const totalCount = computed(() => images.value.length)
const displayedCount = computed(() => displayedImages.value.length)

// Computed
const pageTitle = computed(() => {
  if (designBook.value?.title) {
    return `Images: ${designBook.value.title}`
  }
  return 'Design Book Images'
})

// Methods
async function loadCategories() {
  try {
    const res = await fetch(`${API_BASE}/design-book-images/categories`)
    if (!res.ok) throw new Error('Failed to load categories')
    categories.value = await res.json()
    console.log('Loaded categories:', categories.value.length)
  } catch (err) {
    console.error('Failed to load categories:', err)
    showStatus('Failed to load categories', 'error')
  }
}

async function loadMrpProjects() {
  try {
    const { data, error } = await supabase
      .from('mrp_projects')
      .select('id, project_code, name')
      .order('project_code')

    if (error) throw error
    mrpProjects.value = data || []
    console.log('Loaded MRP projects:', mrpProjects.value.length)
  } catch (err) {
    console.error('Failed to load MRP projects:', err)
  }
}

async function loadDesignBook() {
  if (!bookCode.value) return

  try {
    const { data, error } = await supabase
      .from('design_books')
      .select('id, book_code, title, template_project_id')
      .eq('book_code', bookCode.value)
      .single()

    if (error) throw error
    designBook.value = data

    // Auto-select the project filter based on the design book's template project
    if (data?.template_project_id) {
      projectFilter.value = data.template_project_id
      uploadProjectId.value = data.template_project_id
    }
    console.log('Loaded design book:', data?.title, 'project:', data?.template_project_id)
  } catch (err) {
    console.error('Failed to load design book:', err)
  }
}

async function loadImages() {
  loading.value = true
  try {
    let url = `${API_BASE}/design-book-images/list`
    // If we have a project filter set, use it
    if (projectFilter.value) {
      url += `?project_id=${projectFilter.value}`
    }
    const res = await fetch(url)
    if (!res.ok) throw new Error('Failed to load images')
    const data = await res.json()
    images.value = data

    // Load signed URLs for thumbnails
    for (const img of images.value) {
      loadImageUrl(img)
    }
  } catch (err) {
    console.error('Failed to load images:', err)
    showStatus('Failed to load images', 'error')
  } finally {
    loading.value = false
  }
}

async function loadImageUrl(img: DesignBookImage) {
  try {
    const res = await fetch(`${API_BASE}/design-book-images/${img.id}/url`)
    if (res.ok) {
      const data = await res.json()
      img._signedUrl = data.url
    }
  } catch (err) {
    console.error('Failed to load image URL:', err)
  }
}

function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    uploadFile.value = file
    // Create preview
    const reader = new FileReader()
    reader.onload = (e) => {
      uploadPreview.value = e.target?.result as string
    }
    reader.readAsDataURL(file)
  }
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  const file = event.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) {
    uploadFile.value = file
    const reader = new FileReader()
    reader.onload = (e) => {
      uploadPreview.value = e.target?.result as string
    }
    reader.readAsDataURL(file)
  }
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
}

async function uploadImage() {
  if (!uploadFile.value) {
    showStatus('Please select a file', 'error')
    return
  }

  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', uploadFile.value)
    formData.append('caption', uploadCaption.value)
    formData.append('notes', uploadNotes.value)
    formData.append('width_pct', uploadWidthPct.value.toString())

    if (uploadCategoryId.value) {
      formData.append('category_id', uploadCategoryId.value)
    }
    if (uploadProjectId.value) {
      formData.append('project_id', uploadProjectId.value)
    }
    if (uploadItemId.value) {
      formData.append('item_id', uploadItemId.value)
    }

    const res = await fetch(`${API_BASE}/design-book-images/upload`, {
      method: 'POST',
      body: formData
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Upload failed')
    }

    const newImage = await res.json()
    images.value.unshift(newImage)
    loadImageUrl(newImage)

    resetUploadForm()
    showUploadModal.value = false
    showStatus('Image uploaded successfully', 'success')
  } catch (err: any) {
    console.error('Upload failed:', err)
    showStatus(err.message || 'Upload failed', 'error')
  } finally {
    uploading.value = false
  }
}

function resetUploadForm() {
  uploadFile.value = null
  uploadPreview.value = null
  uploadCaption.value = ''
  uploadNotes.value = ''
  uploadCategoryId.value = ''
  // Keep uploadProjectId if we're in a design book context
  if (!bookCode.value) {
    uploadProjectId.value = ''
  }
  uploadItemSearch.value = ''
  uploadItemId.value = ''
  uploadWidthPct.value = 100
}

function openEditModal(img: DesignBookImage) {
  editingImage.value = { ...img }
  showEditModal.value = true
}

async function saveEdit() {
  if (!editingImage.value) return

  try {
    const res = await fetch(`${API_BASE}/design-book-images/${editingImage.value.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        caption: editingImage.value.caption,
        notes: editingImage.value.notes,
        category_id: editingImage.value.category_id,
        width_pct: editingImage.value.width_pct
      })
    })

    if (!res.ok) throw new Error('Failed to update image')

    // Update local state
    const idx = images.value.findIndex(i => i.id === editingImage.value!.id)
    if (idx >= 0) {
      const updated = await res.json()
      // Preserve signed URL
      updated._signedUrl = images.value[idx]._signedUrl
      // Update category reference
      updated.category = categories.value.find(c => c.id === updated.category_id) || null
      images.value[idx] = updated
    }

    showEditModal.value = false
    editingImage.value = null
    showStatus('Image updated', 'success')
  } catch (err) {
    console.error('Failed to update image:', err)
    showStatus('Failed to update image', 'error')
  }
}

async function deleteImage(img: DesignBookImage) {
  if (!confirm(`Delete image "${img.caption || img.file_name}"?`)) return

  try {
    const res = await fetch(`${API_BASE}/design-book-images/${img.id}`, {
      method: 'DELETE'
    })

    if (!res.ok) throw new Error('Failed to delete image')

    images.value = images.value.filter(i => i.id !== img.id)
    showStatus('Image deleted', 'success')
  } catch (err) {
    console.error('Failed to delete image:', err)
    showStatus('Failed to delete image', 'error')
  }
}

async function createCategory() {
  if (!newCategoryName.value.trim()) {
    showStatus('Category name is required', 'error')
    return
  }

  try {
    const res = await fetch(`${API_BASE}/design-book-images/categories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newCategoryName.value.trim(),
        description: newCategoryDescription.value.trim() || null,
        icon: newCategoryIcon.value || 'pi pi-image'
      })
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to create category')
    }

    const newCat = await res.json()
    categories.value.push(newCat)

    newCategoryName.value = ''
    newCategoryDescription.value = ''
    newCategoryIcon.value = 'pi pi-image'
    showCategoryModal.value = false
    showStatus('Category created', 'success')
  } catch (err: any) {
    console.error('Failed to create category:', err)
    showStatus(err.message || 'Failed to create category', 'error')
  }
}

async function deleteCategory(cat: Category) {
  if (cat.is_system) {
    showStatus('System categories cannot be deleted', 'error')
    return
  }

  if (!confirm(`Delete category "${cat.name}"?`)) return

  try {
    const res = await fetch(`${API_BASE}/design-book-images/categories/${cat.id}`, {
      method: 'DELETE'
    })

    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to delete category')
    }

    categories.value = categories.value.filter(c => c.id !== cat.id)
    showStatus('Category deleted', 'success')
  } catch (err: any) {
    console.error('Failed to delete category:', err)
    showStatus(err.message || 'Failed to delete category', 'error')
  }
}

function getCategoryName(id: string | null): string {
  if (!id) return 'Uncategorized'
  return categories.value.find(c => c.id === id)?.name || 'Unknown'
}

function getCategoryIcon(id: string | null): string {
  if (!id) return 'pi pi-image'
  return categories.value.find(c => c.id === id)?.icon || 'pi pi-image'
}

function formatFileSize(bytes: number | null): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString()
}

function showStatus(msg: string, type: 'success' | 'error') {
  statusMessage.value = msg
  statusType.value = type
  setTimeout(() => {
    statusMessage.value = ''
    statusType.value = ''
  }, 3000)
}

function goBack() {
  if (bookCode.value) {
    router.push(`/mrp/design-book/${bookCode.value}`)
  } else {
    router.push('/mrp/dashboard')
  }
}

onMounted(async () => {
  // Load categories and projects first (these are quick)
  await Promise.all([loadCategories(), loadMrpProjects()])

  // If we have a bookCode, load the design book to get the project filter
  if (bookCode.value) {
    await loadDesignBook()
  }

  // Then load images (filtered by project if set)
  loadImages()
})

// Watch for project filter changes to reload images
watch(projectFilter, () => {
  loadImages()
})
</script>

<template>
  <div class="images-page">
    <!-- Status Message -->
    <div v-if="statusMessage" :class="['status-msg', statusType]">
      {{ statusMessage }}
    </div>

    <!-- Header -->
    <div class="header">
      <h1>{{ pageTitle }}</h1>
      <div class="header-actions">
        <button class="btn btn-primary" @click="showCategoryModal = true">
          <i class="pi pi-tags"></i> Categories
        </button>
        <button class="btn btn-success" @click="goBack">
          <span class="back-arrow">&larr;</span> {{ bookCode ? 'Back to Book' : 'Back to MRP' }}
        </button>
      </div>
    </div>

    <!-- Summary Bar -->
    <div class="summary-bar">
      <div class="summary-item">Total Images: <strong>{{ totalCount }}</strong></div>
      <div class="summary-item">Showing: <strong>{{ displayedCount }}</strong></div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <input
        v-model="searchInput"
        type="text"
        placeholder="Search by caption, notes, filename..."
        class="search-input"
      />
      <select v-model="categoryFilter">
        <option value="">All Categories</option>
        <option v-for="cat in categories" :key="cat.id" :value="cat.id">
          {{ cat.name }}
        </option>
      </select>
      <select v-model="projectFilter" :disabled="!!bookCode">
        <option value="">All Projects</option>
        <option v-for="proj in mrpProjects" :key="proj.id" :value="proj.id">
          {{ proj.project_code }}{{ proj.name ? ' - ' + proj.name : '' }}
        </option>
      </select>
      <button class="btn btn-primary" @click="showUploadModal = true">
        <i class="pi pi-upload"></i> Upload Image
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      Loading images...
    </div>

    <!-- Empty State -->
    <div v-else-if="displayedImages.length === 0" class="empty-state">
      <i class="pi pi-images" style="font-size: 48px; margin-bottom: 16px; opacity: 0.5;"></i>
      <p>No images found</p>
      <button class="btn btn-primary" @click="showUploadModal = true">
        Upload your first image
      </button>
    </div>

    <!-- Images Grid -->
    <div v-else class="images-grid">
      <div
        v-for="img in displayedImages"
        :key="img.id"
        class="image-card"
      >
        <div class="image-preview">
          <img
            v-if="img._signedUrl"
            :src="img._signedUrl"
            :alt="img.caption || img.file_name"
            loading="lazy"
          />
          <div v-else class="image-placeholder">
            <i class="pi pi-image"></i>
          </div>
        </div>
        <div class="image-info">
          <div class="image-caption">{{ img.caption || img.file_name }}</div>
          <div class="image-meta">
            <span :class="['badge', 'badge-category']">
              <i :class="getCategoryIcon(img.category_id)"></i>
              {{ getCategoryName(img.category_id) }}
            </span>
          </div>
          <div v-if="img.notes" class="image-notes">{{ img.notes }}</div>
          <div class="image-details">
            <span v-if="img.project">{{ img.project.name }}</span>
            <span v-if="img.item">{{ img.item.item_number }}</span>
            <span>{{ formatFileSize(img.file_size) }}</span>
            <span>{{ formatDate(img.created_at) }}</span>
          </div>
        </div>
        <div class="image-actions">
          <button class="btn-icon" @click="openEditModal(img)" title="Edit">
            <i class="pi pi-pencil"></i>
          </button>
          <button class="btn-icon btn-danger" @click="deleteImage(img)" title="Delete">
            <i class="pi pi-trash"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Upload Modal -->
    <div v-if="showUploadModal" class="modal-overlay" @click.self="showUploadModal = false">
      <div class="modal">
        <div class="modal-header">
          <h2>Upload Image</h2>
          <button class="btn-close" @click="showUploadModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <!-- Drop Zone -->
          <div
            class="drop-zone"
            :class="{ 'has-file': uploadFile }"
            @drop="handleDrop"
            @dragover="handleDragOver"
            @click="($refs.fileInput as HTMLInputElement).click()"
          >
            <input
              ref="fileInput"
              type="file"
              accept="image/png,image/jpeg,image/webp"
              style="display: none"
              @change="handleFileSelect"
            />
            <div v-if="uploadPreview" class="preview-container">
              <img :src="uploadPreview" alt="Preview" />
            </div>
            <div v-else class="drop-hint">
              <i class="pi pi-cloud-upload"></i>
              <p>Drag & drop an image or click to browse</p>
              <small>PNG, JPEG, WebP - Max 10MB</small>
            </div>
          </div>

          <!-- Form Fields -->
          <div class="form-grid">
            <div class="form-group">
              <label>Caption</label>
              <input v-model="uploadCaption" type="text" placeholder="e.g., Assembly photo" />
            </div>
            <div class="form-group">
              <label>Category</label>
              <select v-model="uploadCategoryId">
                <option value="">Select category...</option>
                <option v-for="cat in categories" :key="cat.id" :value="cat.id">
                  {{ cat.name }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label>Project</label>
              <select v-model="uploadProjectId" :disabled="!!bookCode">
                <option value="">Select project (optional)...</option>
                <option v-for="proj in mrpProjects" :key="proj.id" :value="proj.id">
                  {{ proj.project_code }}{{ proj.name ? ' - ' + proj.name : '' }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label>Display Width</label>
              <select v-model="uploadWidthPct">
                <option :value="100">100% (Full width)</option>
                <option :value="75">75%</option>
                <option :value="50">50%</option>
                <option :value="25">25%</option>
              </select>
            </div>
            <div class="form-group full-width">
              <label>Notes</label>
              <textarea v-model="uploadNotes" placeholder="Additional notes..." rows="3"></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showUploadModal = false">Cancel</button>
          <button class="btn btn-primary" @click="uploadImage" :disabled="uploading || !uploadFile">
            {{ uploading ? 'Uploading...' : 'Upload' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Edit Modal -->
    <div v-if="showEditModal && editingImage" class="modal-overlay" @click.self="showEditModal = false">
      <div class="modal">
        <div class="modal-header">
          <h2>Edit Image</h2>
          <button class="btn-close" @click="showEditModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <div v-if="editingImage._signedUrl" class="edit-preview">
            <img :src="editingImage._signedUrl" :alt="editingImage.caption || editingImage.file_name" />
          </div>
          <div class="form-grid">
            <div class="form-group">
              <label>Caption</label>
              <input v-model="editingImage.caption" type="text" />
            </div>
            <div class="form-group">
              <label>Category</label>
              <select v-model="editingImage.category_id">
                <option value="">Select category...</option>
                <option v-for="cat in categories" :key="cat.id" :value="cat.id">
                  {{ cat.name }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label>Display Width</label>
              <select v-model="editingImage.width_pct">
                <option :value="100">100% (Full width)</option>
                <option :value="75">75%</option>
                <option :value="50">50%</option>
                <option :value="25">25%</option>
              </select>
            </div>
            <div class="form-group full-width">
              <label>Notes</label>
              <textarea v-model="editingImage.notes" rows="3"></textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showEditModal = false">Cancel</button>
          <button class="btn btn-primary" @click="saveEdit">Save Changes</button>
        </div>
      </div>
    </div>

    <!-- Category Management Modal -->
    <div v-if="showCategoryModal" class="modal-overlay" @click.self="showCategoryModal = false">
      <div class="modal modal-lg">
        <div class="modal-header">
          <h2>Manage Categories</h2>
          <button class="btn-close" @click="showCategoryModal = false">&times;</button>
        </div>
        <div class="modal-body">
          <!-- Existing Categories -->
          <div class="categories-list">
            <div
              v-for="cat in categories"
              :key="cat.id"
              class="category-item"
            >
              <div class="category-info">
                <i :class="cat.icon || 'pi pi-image'"></i>
                <div>
                  <div class="category-name">
                    {{ cat.name }}
                    <span v-if="cat.is_system" class="system-badge">System</span>
                  </div>
                  <div class="category-desc">{{ cat.description }}</div>
                </div>
              </div>
              <button
                v-if="!cat.is_system"
                class="btn-icon btn-danger"
                @click="deleteCategory(cat)"
                title="Delete"
              >
                <i class="pi pi-trash"></i>
              </button>
            </div>
          </div>

          <!-- Add New Category -->
          <div class="add-category-form">
            <h3>Add New Category</h3>
            <div class="form-grid">
              <div class="form-group">
                <label>Name</label>
                <input v-model="newCategoryName" type="text" placeholder="Category name" />
              </div>
              <div class="form-group">
                <label>Icon</label>
                <select v-model="newCategoryIcon">
                  <option value="pi pi-image">Image</option>
                  <option value="pi pi-box">Box</option>
                  <option value="pi pi-wrench">Wrench</option>
                  <option value="pi pi-cog">Cog</option>
                  <option value="pi pi-list">List</option>
                  <option value="pi pi-check-circle">Check</option>
                  <option value="pi pi-camera">Camera</option>
                  <option value="pi pi-file">File</option>
                </select>
              </div>
              <div class="form-group full-width">
                <label>Description</label>
                <input v-model="newCategoryDescription" type="text" placeholder="Optional description" />
              </div>
            </div>
            <button class="btn btn-primary" @click="createCategory">
              <i class="pi pi-plus"></i> Add Category
            </button>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showCategoryModal = false">Close</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.images-page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-actions {
  display: flex;
  gap: 10px;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-primary {
  background: #1d4ed8;
  color: white;
}

.btn-primary:hover {
  background: #1e40af;
}

.btn-primary:disabled {
  background: #374151;
  cursor: not-allowed;
}

.btn-secondary {
  background: #374151;
  color: #e5e7eb;
}

.btn-secondary:hover {
  background: #4b5563;
}

.btn-success {
  background: #065f46;
  color: #6ee7b7;
}

.btn-success:hover {
  background: #064e3b;
}

.btn-icon {
  padding: 6px 8px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
}

.btn-icon:hover {
  background: #1f2937;
  color: #e5e7eb;
}

.btn-icon.btn-danger:hover {
  background: #7f1d1d;
  color: #fca5a5;
}

.back-arrow {
  font-size: 16px;
}

.summary-bar {
  display: flex;
  gap: 20px;
  margin-bottom: 16px;
  padding: 12px;
  background: #0f172a;
  border-radius: 8px;
}

.summary-item {
  font-size: 13px;
}

.summary-item strong {
  color: #38bdf8;
}

.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.filter-bar select,
.search-input {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #1f2937;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 14px;
}

.search-input {
  flex: 1;
  min-width: 200px;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 60px;
  color: #9ca3af;
  font-size: 14px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* Images Grid */
.images-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.image-card {
  background: #0f172a;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #1e293b;
  transition: border-color 0.2s;
}

.image-card:hover {
  border-color: #3b82f6;
}

.image-preview {
  aspect-ratio: 4/3;
  background: #020617;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-placeholder {
  color: #4b5563;
  font-size: 48px;
}

.image-info {
  padding: 12px;
}

.image-caption {
  font-weight: 500;
  margin-bottom: 8px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.image-meta {
  margin-bottom: 8px;
}

.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.badge-category {
  background: #1e3a8a;
  color: #93c5fd;
}

.image-notes {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.image-details {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 11px;
  color: #6b7280;
}

.image-details span::after {
  content: '|';
  margin-left: 8px;
  color: #374151;
}

.image-details span:last-child::after {
  display: none;
}

.image-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding: 8px 12px;
  background: #020617;
  border-top: 1px solid #1e293b;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #0f172a;
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-lg {
  max-width: 700px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #1e293b;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
}

.btn-close {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 24px;
  cursor: pointer;
}

.btn-close:hover {
  color: #e5e7eb;
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid #1e293b;
}

/* Drop Zone */
.drop-zone {
  border: 2px dashed #374151;
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  cursor: pointer;
  margin-bottom: 20px;
  transition: border-color 0.2s, background 0.2s;
}

.drop-zone:hover {
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.05);
}

.drop-zone.has-file {
  border-color: #22c55e;
  padding: 10px;
}

.drop-hint i {
  font-size: 48px;
  color: #4b5563;
  margin-bottom: 12px;
}

.drop-hint p {
  margin: 0 0 4px;
  color: #9ca3af;
}

.drop-hint small {
  color: #6b7280;
}

.preview-container {
  max-height: 200px;
  overflow: hidden;
  border-radius: 4px;
}

.preview-container img {
  width: 100%;
  height: auto;
  max-height: 200px;
  object-fit: contain;
}

.edit-preview {
  margin-bottom: 20px;
  border-radius: 8px;
  overflow: hidden;
  max-height: 200px;
}

.edit-preview img {
  width: 100%;
  height: auto;
  max-height: 200px;
  object-fit: contain;
}

/* Form */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group.full-width {
  grid-column: 1 / -1;
}

.form-group label {
  font-size: 12px;
  font-weight: 500;
  color: #9ca3af;
}

.form-group input,
.form-group select,
.form-group textarea {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #1f2937;
  background: #020617;
  color: #e5e7eb;
  font-size: 14px;
}

.form-group textarea {
  resize: vertical;
}

/* Category Management */
.categories-list {
  margin-bottom: 24px;
}

.category-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: #020617;
  border-radius: 6px;
  margin-bottom: 8px;
}

.category-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.category-info > i {
  font-size: 20px;
  color: #3b82f6;
}

.category-name {
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
}

.system-badge {
  font-size: 10px;
  background: #4b5563;
  padding: 2px 6px;
  border-radius: 4px;
  color: #d1d5db;
}

.category-desc {
  font-size: 12px;
  color: #6b7280;
}

.add-category-form {
  border-top: 1px solid #1e293b;
  padding-top: 20px;
}

.add-category-form h3 {
  margin: 0 0 16px;
  font-size: 14px;
  color: #9ca3af;
}

.add-category-form .btn {
  margin-top: 16px;
}

/* Status Message */
.status-msg {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  z-index: 1001;
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
