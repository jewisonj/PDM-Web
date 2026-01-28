<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { supabase } from '../services/supabase'
import { useAuthStore } from '../stores/auth'
import {
  uploadFileWithRecord,
  getSignedUrlFromPath,
  downloadFileToDevice,
  parseStoragePath,
  getBucketForFile
} from '../services/storage'

interface FileInfo {
  id: string
  file_name: string
  file_type: string
  file_path: string | null
  file_size: number | null
  revision: string | null
  iteration: number | null
  created_at: string
}

interface CheckoutInfo {
  user_id: string
  username: string
  checked_out_at: string
}

const props = defineProps<{
  itemId: string
  itemNumber: string
  revision: string
  iteration: number
}>()

const emit = defineEmits<{
  (e: 'fileUploaded'): void
  (e: 'iterationChanged', newIteration: number): void
}>()

const authStore = useAuthStore()

const files = ref<FileInfo[]>([])
const checkoutInfo = ref<CheckoutInfo | null>(null)
const loading = ref(true)
const uploading = ref(false)
const uploadProgress = ref(0)
const error = ref('')
const successMessage = ref('')

// Is the item checked out by the current user?
const isCheckedOutByMe = computed(() => {
  return checkoutInfo.value?.user_id === authStore.user?.id
})

// Is the item checked out by someone else?
const isCheckedOutByOther = computed(() => {
  return checkoutInfo.value && checkoutInfo.value.user_id !== authStore.user?.id
})

// Can the current user check out?
const canCheckout = computed(() => {
  return !checkoutInfo.value && (authStore.user?.role === 'admin' || authStore.user?.role === 'engineer')
})

// Can the current user upload files?
const canUpload = computed(() => {
  return isCheckedOutByMe.value
})

async function loadFiles() {
  loading.value = true
  error.value = ''

  try {
    // Load files for this item
    const { data: filesData, error: filesError } = await supabase
      .from('files')
      .select('*')
      .eq('item_id', props.itemId)
      .order('file_type')
      .order('file_name')

    if (filesError) throw filesError
    files.value = filesData || []

    // Load checkout status
    const { data: checkoutData, error: checkoutError } = await supabase
      .from('checkouts')
      .select(`
        user_id,
        checked_out_at,
        users(username)
      `)
      .eq('item_id', props.itemId)
      .single()

    if (checkoutError && checkoutError.code !== 'PGRST116') {
      // PGRST116 = no rows found, which is fine
      throw checkoutError
    }

    if (checkoutData) {
      checkoutInfo.value = {
        user_id: checkoutData.user_id,
        username: (checkoutData.users as any)?.username || 'Unknown',
        checked_out_at: checkoutData.checked_out_at
      }
    } else {
      checkoutInfo.value = null
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load files'
  } finally {
    loading.value = false
  }
}

async function checkout() {
  if (!authStore.user?.id) return

  error.value = ''
  try {
    const { error: insertError } = await supabase
      .from('checkouts')
      .insert({
        item_id: props.itemId,
        user_id: authStore.user.id
      })

    if (insertError) throw insertError

    checkoutInfo.value = {
      user_id: authStore.user.id,
      username: authStore.user.username,
      checked_out_at: new Date().toISOString()
    }

    successMessage.value = 'Item checked out successfully'
    setTimeout(() => { successMessage.value = '' }, 3000)
  } catch (e: any) {
    error.value = e.message || 'Failed to checkout item'
  }
}

async function checkin(incrementIteration: boolean = true) {
  error.value = ''

  try {
    // Remove checkout record
    const { error: deleteError } = await supabase
      .from('checkouts')
      .delete()
      .eq('item_id', props.itemId)

    if (deleteError) throw deleteError

    // Optionally increment iteration
    if (incrementIteration) {
      const newIteration = props.iteration + 1
      const { error: updateError } = await supabase
        .from('items')
        .update({ iteration: newIteration })
        .eq('id', props.itemId)

      if (updateError) throw updateError

      // Log iteration change in history
      await supabase.from('lifecycle_history').insert({
        item_id: props.itemId,
        old_iteration: props.iteration,
        new_iteration: newIteration,
        changed_by: authStore.user?.id,
        change_notes: 'Files checked in'
      })

      emit('iterationChanged', newIteration)
    }

    checkoutInfo.value = null
    successMessage.value = 'Item checked in successfully'
    setTimeout(() => { successMessage.value = '' }, 3000)
  } catch (e: any) {
    error.value = e.message || 'Failed to checkin item'
  }
}

async function undoCheckout() {
  error.value = ''

  try {
    const { error: deleteError } = await supabase
      .from('checkouts')
      .delete()
      .eq('item_id', props.itemId)

    if (deleteError) throw deleteError

    checkoutInfo.value = null
    successMessage.value = 'Checkout cancelled'
    setTimeout(() => { successMessage.value = '' }, 3000)
  } catch (e: any) {
    error.value = e.message || 'Failed to undo checkout'
  }
}

async function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  uploading.value = true
  uploadProgress.value = 0
  error.value = ''

  try {
    const result = await uploadFileWithRecord(
      file,
      props.itemId,
      props.itemNumber,
      props.revision,
      props.iteration,
      (progress) => { uploadProgress.value = progress }
    )

    if (!result) {
      throw new Error('Upload failed')
    }

    successMessage.value = `File "${file.name}" uploaded successfully`
    setTimeout(() => { successMessage.value = '' }, 3000)

    // Refresh file list
    await loadFiles()
    emit('fileUploaded')
  } catch (e: any) {
    error.value = e.message || 'Failed to upload file'
  } finally {
    uploading.value = false
    uploadProgress.value = 0
    // Reset file input
    target.value = ''
  }
}

async function downloadFile(file: FileInfo) {
  if (!file.file_path) {
    error.value = 'File not available in storage'
    return
  }

  const parsed = parseStoragePath(file.file_path)
  if (!parsed) {
    error.value = 'Invalid file path'
    return
  }

  const success = await downloadFileToDevice(parsed.bucket, parsed.path, file.file_name)
  if (!success) {
    error.value = 'Failed to download file'
  }
}

async function viewFile(file: FileInfo) {
  if (!file.file_path) {
    error.value = 'File not available in storage'
    return
  }

  const url = await getSignedUrlFromPath(file.file_path)
  if (url) {
    window.open(url, '_blank')
  } else {
    error.value = 'Failed to generate file URL'
  }
}

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

onMounted(() => {
  loadFiles()
})
</script>

<template>
  <div class="file-checkin">
    <!-- Checkout Status Bar -->
    <div class="checkout-bar" :class="{
      'checked-out-me': isCheckedOutByMe,
      'checked-out-other': isCheckedOutByOther
    }">
      <div class="checkout-status">
        <template v-if="isCheckedOutByMe">
          <i class="pi pi-lock"></i>
          <span>Checked out by you since {{ formatDate(checkoutInfo!.checked_out_at) }}</span>
        </template>
        <template v-else-if="isCheckedOutByOther">
          <i class="pi pi-lock"></i>
          <span>Checked out by <strong>{{ checkoutInfo!.username }}</strong> since {{ formatDate(checkoutInfo!.checked_out_at) }}</span>
        </template>
        <template v-else>
          <i class="pi pi-unlock"></i>
          <span>Available for checkout</span>
        </template>
      </div>
      <div class="checkout-actions">
        <button v-if="canCheckout" class="btn btn-primary" @click="checkout">
          <i class="pi pi-lock"></i> Check Out
        </button>
        <template v-if="isCheckedOutByMe">
          <button class="btn btn-success" @click="checkin(true)">
            <i class="pi pi-check"></i> Check In
          </button>
          <button class="btn btn-secondary" @click="undoCheckout">
            <i class="pi pi-times"></i> Cancel
          </button>
        </template>
      </div>
    </div>

    <!-- Messages -->
    <div v-if="error" class="message error">
      <i class="pi pi-exclamation-triangle"></i> {{ error }}
    </div>
    <div v-if="successMessage" class="message success">
      <i class="pi pi-check-circle"></i> {{ successMessage }}
    </div>

    <!-- File Upload (only when checked out) -->
    <div v-if="canUpload" class="upload-section">
      <label class="upload-area">
        <input type="file" @change="handleFileUpload" :disabled="uploading" />
        <div class="upload-content">
          <i class="pi pi-upload"></i>
          <span v-if="uploading">Uploading... {{ uploadProgress }}%</span>
          <span v-else>Drop file here or click to upload</span>
        </div>
      </label>
    </div>

    <!-- Files Table -->
    <div v-if="loading" class="loading">Loading files...</div>
    <div v-else-if="files.length === 0" class="no-files">
      <i class="pi pi-file"></i>
      <p>No files attached to this item</p>
    </div>
    <table v-else class="files-table">
      <thead>
        <tr>
          <th>Type</th>
          <th>File Name</th>
          <th>Size</th>
          <th>Rev/Iter</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="file in files" :key="file.id">
          <td class="file-type">
            <span class="type-badge" :class="file.file_type.toLowerCase()">
              {{ file.file_type }}
            </span>
          </td>
          <td class="file-name">{{ file.file_name }}</td>
          <td class="file-size">{{ formatFileSize(file.file_size) }}</td>
          <td class="file-rev">
            {{ file.revision || '-' }} / {{ file.iteration || '-' }}
          </td>
          <td class="file-actions">
            <button
              v-if="file.file_path"
              class="action-btn"
              title="View"
              @click="viewFile(file)"
            >
              <i class="pi pi-eye"></i>
            </button>
            <button
              v-if="file.file_path"
              class="action-btn"
              title="Download"
              @click="downloadFile(file)"
            >
              <i class="pi pi-download"></i>
            </button>
            <span v-if="!file.file_path" class="no-storage">
              Not in storage
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.file-checkin {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  overflow: hidden;
}

.checkout-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem 1rem;
  background: #f3f4f6;
  border-bottom: 1px solid #e5e7eb;
}

.checkout-bar.checked-out-me {
  background: #ecfdf5;
  border-bottom-color: #86efac;
}

.checkout-bar.checked-out-other {
  background: #fef3c7;
  border-bottom-color: #fcd34d;
}

.checkout-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: #374151;
}

.checkout-status i {
  font-size: 1rem;
}

.checkout-actions {
  display: flex;
  gap: 0.5rem;
}

.btn {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.4rem 0.75rem;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #2563eb;
  color: #fff;
}

.btn-primary:hover {
  background: #1d4ed8;
}

.btn-success {
  background: #059669;
  color: #fff;
}

.btn-success:hover {
  background: #047857;
}

.btn-secondary {
  background: #fff;
  border: 1px solid #d1d5db;
  color: #374151;
}

.btn-secondary:hover {
  background: #f3f4f6;
}

.message {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  font-size: 0.85rem;
}

.message.error {
  background: #fef2f2;
  color: #dc2626;
  border-bottom: 1px solid #fca5a5;
}

.message.success {
  background: #f0fdf4;
  color: #16a34a;
  border-bottom: 1px solid #86efac;
}

.upload-section {
  padding: 1rem;
  border-bottom: 1px solid #e5e7eb;
}

.upload-area {
  display: block;
  border: 2px dashed #d1d5db;
  border-radius: 0.5rem;
  padding: 1.5rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.upload-area:hover {
  border-color: #059669;
  background: #f9fafb;
}

.upload-area input {
  display: none;
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  color: #6b7280;
}

.upload-content i {
  font-size: 1.5rem;
  color: #9ca3af;
}

.loading, .no-files {
  padding: 2rem;
  text-align: center;
  color: #6b7280;
}

.no-files i {
  font-size: 2rem;
  margin-bottom: 0.5rem;
  display: block;
}

.files-table {
  width: 100%;
  border-collapse: collapse;
}

.files-table th {
  padding: 0.6rem 1rem;
  text-align: left;
  background: #f9fafb;
  font-size: 0.75rem;
  font-weight: 600;
  color: #6b7280;
  text-transform: uppercase;
  border-bottom: 1px solid #e5e7eb;
}

.files-table td {
  padding: 0.6rem 1rem;
  border-bottom: 1px solid #f3f4f6;
  font-size: 0.85rem;
}

.files-table tr:last-child td {
  border-bottom: none;
}

.type-badge {
  display: inline-block;
  padding: 0.2rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}

.type-badge.cad {
  background: #dbeafe;
  color: #1e40af;
}

.type-badge.step {
  background: #e0e7ff;
  color: #3730a3;
}

.type-badge.dxf {
  background: #fef3c7;
  color: #92400e;
}

.type-badge.svg {
  background: #d1fae5;
  color: #065f46;
}

.type-badge.pdf {
  background: #fee2e2;
  color: #991b1b;
}

.type-badge.other {
  background: #f3f4f6;
  color: #4b5563;
}

.file-name {
  font-family: monospace;
  font-size: 0.85rem;
}

.file-size, .file-rev {
  color: #6b7280;
  font-size: 0.8rem;
}

.file-actions {
  display: flex;
  gap: 0.25rem;
}

.action-btn {
  padding: 0.35rem 0.5rem;
  background: #fff;
  border: 1px solid #d1d5db;
  border-radius: 0.25rem;
  cursor: pointer;
  color: #6b7280;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.no-storage {
  font-size: 0.75rem;
  color: #9ca3af;
  font-style: italic;
}
</style>
