<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { supabase } from '../services/supabase'
import {
  uploadSharedPdf,
  sharePrintPacket,
  shareDesignBook,
  listSharedLinks,
  revokeSharedLink,
  type SharedLink,
} from '../services/shareApi'

const router = useRouter()
const route = useRoute()

interface MrpProject {
  id: string
  project_code: string
  description: string | null
  design_book_code: string | null
}

const projects = ref<MrpProject[]>([])
const selectedDesignBook = ref<string | null>(null)
const selectedProjectCode = ref<string>((route.query.project as string) || '')
const links = ref<SharedLink[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const copiedId = ref<string | null>(null)

// Upload form state
const uploadKind = ref<SharedLink['kind']>('tracker')
const uploadTitle = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)

const KIND_LABELS: Record<string, string> = {
  build_book: 'Build Book',
  tracker: 'Tracker Sheet',
  print_packet: 'Print Packet',
  design_book: 'Design Book',
  other: 'Other',
}

async function loadProjects() {
  // Load projects with their linked design books
  const { data: projectData } = await supabase
    .from('mrp_projects')
    .select('id, project_code, description')
    .order('project_code')

  // Load design books and map by template_project_id
  const { data: bookData } = await supabase
    .from('design_books')
    .select('book_code, template_project_id')

  const bookByProject = new Map<string, string>()
  if (bookData) {
    for (const b of bookData) {
      if (b.template_project_id) bookByProject.set(b.template_project_id, b.book_code)
    }
  }

  projects.value = (projectData || []).map(p => ({
    ...p,
    design_book_code: bookByProject.get(p.id) || null,
  }))

  // Update selectedDesignBook if a project is selected
  updateSelectedDesignBook()
}

function updateSelectedDesignBook() {
  const project = projects.value.find(p => p.project_code === selectedProjectCode.value)
  selectedDesignBook.value = project?.design_book_code || null
}

async function loadLinks() {
  loading.value = true
  error.value = null
  try {
    links.value = await listSharedLinks(selectedProjectCode.value || null)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load links'
  } finally {
    loading.value = false
  }
}

async function handleFiles(files: FileList | null) {
  if (!files || !files.length || busy.value) return
  const file = files[0]
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    error.value = 'Only PDF files can be shared'
    return
  }
  busy.value = true
  error.value = null
  notice.value = null
  try {
    const link = await uploadSharedPdf(
      file,
      uploadKind.value,
      selectedProjectCode.value || null,
      uploadTitle.value || null
    )
    notice.value = `Link created for ${link.title}`
    uploadTitle.value = ''
    await loadLinks()
    await copyLink(link)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Upload failed'
  } finally {
    busy.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function onDrop(e: DragEvent) {
  dragging.value = false
  handleFiles(e.dataTransfer?.files ?? null)
}

async function sharePacket() {
  const project = projects.value.find(p => p.project_code === selectedProjectCode.value)
  if (!project || busy.value) return
  busy.value = true
  error.value = null
  notice.value = null
  try {
    const link = await sharePrintPacket(project.id)
    notice.value = `Link created for ${link.title}`
    await loadLinks()
    await copyLink(link)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to share print packet'
  } finally {
    busy.value = false
  }
}

async function shareBook() {
  if (!selectedDesignBook.value || busy.value) return
  busy.value = true
  error.value = null
  notice.value = null
  try {
    const link = await shareDesignBook(selectedDesignBook.value)
    notice.value = `Link created for ${link.title}`
    await loadLinks()
    await copyLink(link)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to share design book'
  } finally {
    busy.value = false
  }
}

async function copyLink(link: SharedLink) {
  try {
    await navigator.clipboard.writeText(link.public_url)
    copiedId.value = link.id
    setTimeout(() => {
      if (copiedId.value === link.id) copiedId.value = null
    }, 2000)
  } catch {
    // Clipboard can fail on non-HTTPS; the link is still visible to select
  }
}

async function revoke(link: SharedLink) {
  if (!confirm(`Revoke the shared link for "${link.title}"? Anyone with the link will lose access.`)) {
    return
  }
  try {
    await revokeSharedLink(link.id)
    await loadLinks()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to revoke link'
  }
}

function formatSize(bytes: number | null): string {
  if (!bytes) return '--'
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}

onMounted(async () => {
  await Promise.all([loadProjects(), loadLinks()])
})
</script>

<template>
  <div class="shares-page">
    <div class="header">
      <h1>Shared Links</h1>
      <div class="header-actions">
        <select v-model="selectedProjectCode" @change="loadLinks(); updateSelectedDesignBook()">
          <option value="">All projects</option>
          <option v-for="p in projects" :key="p.id" :value="p.project_code">
            {{ p.project_code }} - {{ p.description || '' }}
          </option>
        </select>
        <button class="btn btn-secondary" @click="router.push('/mrp/dashboard')">
          &larr; Dashboard
        </button>
      </div>
    </div>

    <p class="intro">
      Share project PDFs with a permanent public link - anyone with the link can
      view or download, no login. Print a tracker sheet or build book to PDF in the
      browser, then drop it here. Revoking a link removes the file immediately.
    </p>

    <!-- Upload zone -->
    <div class="upload-row">
      <div
        class="dropzone"
        :class="{ dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
        @click="fileInput?.click()"
      >
        <i class="pi pi-upload"></i>
        <span v-if="busy">Uploading...</span>
        <span v-else>Drop a PDF here or click to browse</span>
        <input
          ref="fileInput"
          type="file"
          accept="application/pdf"
          hidden
          @change="handleFiles(($event.target as HTMLInputElement).files)"
        />
      </div>
      <div class="upload-options">
        <label>
          Document type
          <select v-model="uploadKind">
            <option value="tracker">Tracker Sheet</option>
            <option value="build_book">Build Book</option>
            <option value="print_packet">Print Packet</option>
            <option value="design_book">Design Book</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          Title (optional)
          <input v-model="uploadTitle" type="text" placeholder="e.g. WM2121 tracker 11x17" />
        </label>
        <div class="quick-share-buttons">
          <button
            class="btn btn-secondary"
            :disabled="!selectedProjectCode || busy"
            title="Copies the project's generated print packet to a public link"
            @click="sharePacket"
          >
            <i class="pi pi-file-pdf"></i>
            Share print packet
          </button>
          <button
            class="btn btn-secondary"
            :disabled="!selectedDesignBook || busy"
            title="Copies the project's design book to a public link"
            @click="shareBook"
          >
            <i class="pi pi-book"></i>
            Share design book
          </button>
        </div>
      </div>
    </div>

    <div v-if="error" class="banner error">{{ error }}</div>
    <div v-if="notice" class="banner ok">{{ notice }} - link copied to clipboard</div>

    <!-- Links table -->
    <div class="links-table">
      <div v-if="loading" class="empty">Loading...</div>
      <div v-else-if="!links.length" class="empty">
        No shared links yet{{ selectedProjectCode ? ` for ${selectedProjectCode}` : '' }}.
      </div>
      <table v-else>
        <thead>
          <tr>
            <th>Title</th>
            <th>Type</th>
            <th>Project</th>
            <th>Size</th>
            <th>Updated</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="link in links" :key="link.id">
            <td>
              <a :href="link.public_url" target="_blank" rel="noopener">{{ link.title }}</a>
            </td>
            <td>{{ KIND_LABELS[link.kind] || link.kind }}</td>
            <td>{{ link.project_code || '--' }}</td>
            <td>{{ formatSize(link.size_bytes) }}</td>
            <td>{{ formatDate(link.updated_at) }}</td>
            <td class="row-actions">
              <button class="btn btn-small" @click="copyLink(link)">
                <i :class="copiedId === link.id ? 'pi pi-check' : 'pi pi-copy'"></i>
                {{ copiedId === link.id ? 'Copied' : 'Copy link' }}
              </button>
              <button class="btn btn-small danger" @click="revoke(link)">
                <i class="pi pi-trash"></i>
                Revoke
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }

.shares-page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  font-family: system-ui, sans-serif;
  padding: 1.25rem 1.5rem 3rem;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.header h1 {
  font-size: 1.4rem;
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.header-actions select,
.upload-options select,
.upload-options input {
  background: #0f172a;
  color: #e5e7eb;
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 0.45rem 0.6rem;
  font-size: 0.9rem;
}

.intro {
  color: #94a3b8;
  font-size: 0.9rem;
  max-width: 760px;
  margin: 0 0 1.25rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.9rem;
  border-radius: 6px;
  border: 1px solid #334155;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 0.9rem;
  cursor: pointer;
}

.btn:hover:not(:disabled) {
  background: #1e293b;
}

.btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-small {
  padding: 0.3rem 0.6rem;
  font-size: 0.8rem;
}

.btn.danger:hover:not(:disabled) {
  border-color: #ef4444;
  color: #ef4444;
}

.upload-row {
  display: flex;
  gap: 1rem;
  align-items: stretch;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.dropzone {
  flex: 1;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1.75rem 1rem;
  border: 2px dashed #334155;
  border-radius: 10px;
  color: #94a3b8;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.dropzone:hover,
.dropzone.dragging {
  border-color: #38bdf8;
  background: #0f172a;
}

.dropzone i {
  font-size: 1.4rem;
}

.upload-options {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  min-width: 260px;
}

.upload-options label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: #94a3b8;
}

.quick-share-buttons {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-top: 0.4rem;
}

.banner {
  padding: 0.6rem 0.9rem;
  border-radius: 8px;
  font-size: 0.9rem;
  margin-bottom: 1rem;
}

.banner.error {
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid #7f1d1d;
  color: #fca5a5;
}

.banner.ok {
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid #14532d;
  color: #86efac;
}

.links-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.links-table th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  color: #94a3b8;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid #1e293b;
}

.links-table td {
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid #0f172a;
}

.links-table a {
  color: #38bdf8;
  text-decoration: none;
}

.links-table a:hover {
  text-decoration: underline;
}

.row-actions {
  display: flex;
  gap: 0.4rem;
  justify-content: flex-end;
}

.empty {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}
</style>
