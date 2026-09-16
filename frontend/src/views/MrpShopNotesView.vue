<script setup lang="ts">
/**
 * Shop Notes review page - /mrp/shop-notes
 * Engineering triages notes filed from the Shop Companion (/shop):
 * fix the part/assembly, add reviewer notes, mark reviewed/resolved, delete.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  listShopNotes,
  updateShopNote,
  deleteShopNote,
  listShopProjects,
  getProjectItems,
  type ShopNote,
  type ShopNoteStatus,
  type ShopProject,
  type ShopItem,
  type ShopAssembly,
} from '../services/shopNotesApi'
import { itemLabel } from '../utils/shopNotes'
import ShopItemPicker from '../components/ShopItemPicker.vue'

const router = useRouter()
const route = useRoute()

type Filter = ShopNoteStatus | 'all'
const filter = ref<Filter>(((route.query.status as string) || 'new') as Filter)
const projectFilter = ref<string>((route.query.project as string) || '')

const notes = ref<ShopNote[]>([])
const projects = ref<ShopProject[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const busyId = ref<string | null>(null)
const lightbox = ref<string | null>(null)

// Per-note edit state (only one note edits at a time)
const editingId = ref<string | null>(null)
const editProjectId = ref('')
const editAssembly = ref<ShopAssembly | null>(null)
const editAssemblyText = ref('')
const editPart = ref<ShopItem | null>(null)
const editPartText = ref('')
const editNote = ref('')
const editReviewerNotes = ref('')
const editAssemblies = ref<ShopAssembly[]>([])
const editParts = ref<ShopItem[]>([])
const editLoadingItems = ref(false)

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'new', label: 'New' },
  { key: 'reviewed', label: 'Reviewed' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'all', label: 'All' },
]

const counts = computed(() => {
  const c = { new: 0, reviewed: 0, resolved: 0 }
  for (const n of notes.value) c[n.status]++
  return c
})

async function load() {
  loading.value = true
  error.value = null
  try {
    notes.value = await listShopNotes(filter.value, projectFilter.value || null)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load notes'
  } finally {
    loading.value = false
  }
}

async function loadProjects() {
  try {
    projects.value = await listShopProjects(true)
  } catch {
    /* project filter is optional */
  }
}

onMounted(async () => {
  await Promise.all([load(), loadProjects()])
})

watch([filter, projectFilter], () => {
  router.replace({ query: { status: filter.value, ...(projectFilter.value ? { project: projectFilter.value } : {}) } })
  load()
})

function fmtDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function partDisplay(n: ShopNote) {
  return n.part ? itemLabel(n.part) : n.part_text ? `${n.part_text} (typed)` : ''
}
function assemblyDisplay(n: ShopNote) {
  return n.assembly ? itemLabel(n.assembly) : n.assembly_text ? `${n.assembly_text} (typed)` : ''
}

async function setStatus(n: ShopNote, status: ShopNoteStatus) {
  busyId.value = n.id
  try {
    const updated = await updateShopNote(n.id, { status })
    replaceNote(updated)
    if (filter.value !== 'all' && updated.status !== filter.value) {
      notes.value = notes.value.filter(x => x.id !== updated.id)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Update failed'
  } finally {
    busyId.value = null
  }
}

async function remove(n: ShopNote) {
  if (!confirm('Delete this note and its photos?')) return
  busyId.value = n.id
  try {
    await deleteShopNote(n.id)
    notes.value = notes.value.filter(x => x.id !== n.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Delete failed'
  } finally {
    busyId.value = null
  }
}

function replaceNote(updated: ShopNote) {
  const i = notes.value.findIndex(x => x.id === updated.id)
  if (i >= 0) notes.value[i] = updated
}

// --- Editing ---

async function startEdit(n: ShopNote) {
  editingId.value = n.id
  editProjectId.value = n.project_id || ''
  editAssembly.value = n.assembly ? { id: n.assembly.id, item_number: n.assembly.item_number, name: n.assembly.name || '', is_top: false } : null
  editAssemblyText.value = n.assembly?.item_number || n.assembly_text || ''
  editPart.value = n.part ? { id: n.part.id, item_number: n.part.item_number, name: n.part.name || '', parent_ids: [] } : null
  editPartText.value = n.part?.item_number || n.part_text || ''
  editNote.value = n.note
  editReviewerNotes.value = n.reviewer_notes || ''
  await loadEditItems()
}

async function loadEditItems() {
  editAssemblies.value = []
  editParts.value = []
  if (!editProjectId.value) return
  editLoadingItems.value = true
  try {
    const data = await getProjectItems(editProjectId.value, true)
    editAssemblies.value = data.assemblies
    editParts.value = data.parts
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load BOM'
  } finally {
    editLoadingItems.value = false
  }
}

function cancelEdit() {
  editingId.value = null
}

async function saveEdit(n: ShopNote) {
  busyId.value = n.id
  try {
    const patch: Parameters<typeof updateShopNote>[1] = {
      note: editNote.value,
      reviewer_notes: editReviewerNotes.value,
    }
    if (editProjectId.value && editProjectId.value !== n.project_id) patch.project_id = editProjectId.value
    if (editAssembly.value) patch.assembly_item_id = editAssembly.value.id
    else {
      patch.clear_assembly = true
      patch.assembly_text = editAssemblyText.value
    }
    if (editPart.value) patch.part_item_id = editPart.value.id
    else {
      patch.clear_part = true
      patch.part_text = editPartText.value
    }
    const updated = await updateShopNote(n.id, patch)
    replaceNote(updated)
    editingId.value = null
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Save failed'
  } finally {
    busyId.value = null
  }
}

const shopUrl = computed(() => `${window.location.origin}/shop`)
</script>

<template>
  <div class="page">
    <div class="header">
      <div>
        <h1>Shop Notes</h1>
        <p class="intro">
          Notes and photos from the shop floor. Workers open <code>{{ shopUrl }}</code> on their phone
          (PIN once, then it stays signed in). Fix the part or assembly here if they left it blank or guessed.
        </p>
      </div>
      <div class="header-actions">
        <select v-model="projectFilter">
          <option value="">All projects</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.project_code }}{{ p.description ? ' - ' + p.description : '' }}</option>
        </select>
        <button class="btn" @click="load" :disabled="loading"><i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i></button>
        <button class="btn" @click="router.push('/mrp/dashboard')">&larr; Dashboard</button>
      </div>
    </div>

    <div class="tabs">
      <button v-for="f in FILTERS" :key="f.key" class="tab" :class="{ active: filter === f.key }" @click="filter = f.key">
        {{ f.label }}<span v-if="filter === 'all' && f.key !== 'all'" class="tab-count">{{ counts[f.key] }}</span>
      </button>
    </div>

    <p v-if="error" class="error">{{ error }} <button class="link" @click="error = null">dismiss</button></p>

    <div v-if="loading && !notes.length" class="empty">Loading…</div>
    <div v-else-if="!notes.length" class="empty">No {{ filter === 'all' ? '' : filter }} notes.</div>

    <div class="list">
      <article v-for="n in notes" :key="n.id" class="card" :class="'status-' + n.status">
        <div class="card-head">
          <div class="meta">
            <span class="badge" :class="n.status">{{ n.status }}</span>
            <strong v-if="n.author_name">{{ n.author_name }}</strong>
            <span class="muted">{{ fmtDate(n.created_at) }}</span>
            <span v-if="n.project" class="proj">{{ n.project.project_code }}</span>
          </div>
          <div class="actions" v-if="editingId !== n.id">
            <button class="btn btn-small" :disabled="busyId === n.id" @click="startEdit(n)"><i class="pi pi-pencil"></i> Edit</button>
            <button v-if="n.status !== 'reviewed'" class="btn btn-small" :disabled="busyId === n.id" @click="setStatus(n, 'reviewed')">Mark reviewed</button>
            <button v-if="n.status !== 'resolved'" class="btn btn-small ok" :disabled="busyId === n.id" @click="setStatus(n, 'resolved')"><i class="pi pi-check"></i> Resolve</button>
            <button v-if="n.status !== 'new'" class="btn btn-small" :disabled="busyId === n.id" @click="setStatus(n, 'new')">Reopen</button>
            <button class="btn btn-small danger" :disabled="busyId === n.id" @click="remove(n)"><i class="pi pi-trash"></i></button>
          </div>
        </div>

        <!-- Read mode -->
        <template v-if="editingId !== n.id">
          <div class="links">
            <div class="link-row">
              <span class="lbl">Assembly</span>
              <router-link v-if="n.assembly" :to="`/items/${n.assembly.item_number}`">{{ assemblyDisplay(n) }}</router-link>
              <span v-else :class="{ muted: !n.assembly_text, typed: n.assembly_text }">{{ assemblyDisplay(n) || '—' }}</span>
            </div>
            <div class="link-row">
              <span class="lbl">Part</span>
              <router-link v-if="n.part" :to="`/items/${n.part.item_number}`">{{ partDisplay(n) }}</router-link>
              <span v-else :class="{ muted: !n.part_text, typed: n.part_text }">{{ partDisplay(n) || '—' }}</span>
            </div>
          </div>

          <p class="note-text" v-if="n.note">{{ n.note }}</p>
          <p class="note-text muted" v-else>(photo only)</p>

          <div v-if="n.photos.length" class="photos">
            <button v-for="p in n.photos" :key="p.id" class="photo" type="button" @click="p.url && (lightbox = p.url)">
              <img v-if="p.url" :src="p.url" alt="" loading="lazy" />
              <span v-else class="muted">no preview</span>
            </button>
          </div>

          <p v-if="n.reviewer_notes" class="reviewer-notes"><span class="lbl">Reviewer:</span> {{ n.reviewer_notes }}</p>
        </template>

        <!-- Edit mode -->
        <div v-else class="edit">
          <div class="edit-grid">
            <label>
              Project
              <select v-model="editProjectId" @change="editAssembly = null; editPart = null; loadEditItems()">
                <option value="">(none)</option>
                <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.project_code }}</option>
              </select>
            </label>
            <ShopItemPicker
              v-model="editAssembly"
              v-model:text="editAssemblyText"
              :items="editAssemblies"
              label="Assembly"
              :hint="editLoadingItems ? 'loading…' : ''"
            />
            <ShopItemPicker
              v-model="editPart"
              v-model:text="editPartText"
              :items="editParts"
              label="Part"
            />
          </div>
          <label>
            Note
            <textarea v-model="editNote" rows="3"></textarea>
          </label>
          <label>
            Reviewer notes
            <textarea v-model="editReviewerNotes" rows="2" placeholder="What was done about it"></textarea>
          </label>
          <div class="edit-actions">
            <button class="btn primary" :disabled="busyId === n.id" @click="saveEdit(n)">Save</button>
            <button class="btn" :disabled="busyId === n.id" @click="cancelEdit">Cancel</button>
          </div>
        </div>
      </article>
    </div>

    <div v-if="lightbox" class="lightbox" @click="lightbox = null">
      <img :src="lightbox" alt="" />
    </div>
  </div>
</template>

<style scoped>
* { box-sizing: border-box; }

.page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  font-family: system-ui, sans-serif;
  padding: 1.25rem 1.5rem 3rem;
}

.header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1rem; flex-wrap: wrap; }
.header h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
.intro { color: #94a3b8; font-size: 0.9rem; max-width: 760px; margin: 0; }
.intro code { color: #7dd3fc; }
.header-actions { display: flex; gap: 0.5rem; align-items: center; }
.header-actions select, .edit select, .edit textarea {
  background: #0f172a; color: #e5e7eb; border: 1px solid #334155; border-radius: 6px; padding: 0.45rem 0.6rem; font-size: 0.9rem;
}

.btn {
  display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.45rem 0.9rem; border-radius: 6px; border: 1px solid #334155;
  background: #0f172a; color: #e5e7eb; font-size: 0.9rem; cursor: pointer;
}
.btn:hover:not(:disabled) { background: #1e293b; }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-small { padding: 0.3rem 0.6rem; font-size: 0.8rem; }
.btn.ok:hover:not(:disabled) { border-color: #10b981; color: #6ee7b7; }
.btn.danger:hover:not(:disabled) { border-color: #ef4444; color: #ef4444; }
.btn.primary { background: #2563eb; border-color: #2563eb; }
.btn.primary:hover:not(:disabled) { background: #1d4ed8; }
.link { background: none; border: none; color: #7dd3fc; cursor: pointer; }

.tabs { display: flex; gap: 0.25rem; border-bottom: 1px solid #1e293b; margin-bottom: 1rem; }
.tab { background: none; border: none; color: #94a3b8; padding: 0.6rem 0.9rem; cursor: pointer; border-bottom: 2px solid transparent; font-size: 0.95rem; }
.tab.active { color: #f1f5f9; border-bottom-color: #38bdf8; }
.tab-count { margin-left: 0.4rem; font-size: 0.75rem; background: #1e293b; padding: 0.1rem 0.4rem; border-radius: 999px; }

.error { background: #450a0a; border: 1px solid #ef4444; color: #fecaca; padding: 0.6rem 0.8rem; border-radius: 6px; margin-bottom: 1rem; }
.empty { color: #64748b; padding: 2rem 0; text-align: center; }

.list { display: flex; flex-direction: column; gap: 0.9rem; max-width: 960px; }
.card { background: #0f172a; border: 1px solid #1e293b; border-left: 4px solid #38bdf8; border-radius: 8px; padding: 0.9rem 1rem; }
.card.status-reviewed { border-left-color: #d97706; }
.card.status-resolved { border-left-color: #059669; opacity: 0.85; }

.card-head { display: flex; justify-content: space-between; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
.meta { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; font-size: 0.9rem; }
.muted { color: #64748b; }
.proj { background: #1e3a5f; color: #bae6fd; padding: 0.1rem 0.5rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600; }
.badge { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 0.15rem 0.45rem; border-radius: 4px; font-weight: 700; }
.badge.new { background: #0c4a6e; color: #7dd3fc; }
.badge.reviewed { background: #451a03; color: #fcd34d; }
.badge.resolved { background: #052e16; color: #6ee7b7; }
.actions { display: flex; gap: 0.35rem; flex-wrap: wrap; }

.links { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 0.5rem; font-size: 0.9rem; }
.link-row { display: flex; gap: 0.5rem; align-items: baseline; }
.lbl { color: #64748b; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
.links a { color: #7dd3fc; text-decoration: none; }
.links a:hover { text-decoration: underline; }
.typed { color: #fcd34d; }

.note-text { white-space: pre-wrap; line-height: 1.45; margin: 0.25rem 0 0.6rem; font-size: 1rem; }
.reviewer-notes { color: #cbd5e1; font-size: 0.9rem; border-top: 1px dashed #1e293b; padding-top: 0.5rem; margin-top: 0.5rem; }

.photos { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.4rem; }
.photo { width: 120px; height: 120px; border-radius: 6px; overflow: hidden; border: 1px solid #334155; background: #020617; padding: 0; cursor: zoom-in; display: flex; align-items: center; justify-content: center; }
.photo img { width: 100%; height: 100%; object-fit: cover; display: block; }

.edit { display: flex; flex-direction: column; gap: 0.75rem; }
.edit-grid { display: grid; grid-template-columns: 160px 1fr 1fr; gap: 0.75rem; align-items: start; }
.edit label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; }
.edit textarea { font-family: inherit; font-size: 0.95rem; text-transform: none; letter-spacing: 0; font-weight: 400; color: #e5e7eb; }
.edit-actions { display: flex; gap: 0.5rem; }

.lightbox { position: fixed; inset: 0; background: rgba(2,6,23,0.92); display: flex; align-items: center; justify-content: center; z-index: 100; cursor: zoom-out; }
.lightbox img { max-width: 95vw; max-height: 95vh; object-fit: contain; border-radius: 6px; }

@media (max-width: 800px) {
  .edit-grid { grid-template-columns: 1fr; }
}
</style>
