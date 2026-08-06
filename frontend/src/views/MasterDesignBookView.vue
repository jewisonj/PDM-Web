<script setup lang="ts">
/**
 * Master Design Book — rev-controlled section booklets for a product.
 *
 * Reads the book state from GET /api/mrp/design-books/{code} (sections, revs,
 * stale-print badge, change history). "Check & Update" builds the master model
 * client-side (utils/masterDesignBook.ts — the single source of truth), dry-runs
 * it against /check, and the diff modal is the confirmation for /update.
 * See Documentation/36-MASTER-DESIGN-BOOK-PLAN.md.
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { supabase } from '../services/supabase'
import DesignBookUpdateModal from '../components/DesignBookUpdateModal.vue'
import {
  buildMasterModel,
  toPayload,
  getDesignBook,
  checkDesignBook,
  updateDesignBook,
  syncQuantities,
  getSectionUrl,
  getNoticeUrl,
  downloadFullBook,
  downloadPurchaseList,
  type BookDetail,
  type BookSectionRow,
  type CheckResult,
  type DesignBookPayload,
} from '../services/designBook'

const route = useRoute()
const router = useRouter()
const bookCode = String(route.params.bookCode || 'spa-standard')

// New-book defaults come from the index's create form (query params); the
// spa-standard code keeps its convenience defaults so the first book is one click.
const isSpaDefault = bookCode === 'spa-standard'
const loading = ref(true)
const error = ref('')
const success = ref('')
const book = ref<BookDetail | null>(null)
const templateProjectCode = ref(
  String(route.query.template || (isSpaDefault ? 'SPA0030' : ''))
)
const newTitle = ref(
  String(route.query.title || (isSpaDefault ? 'Standard Spa Master Design Book' : ''))
)

const checking = ref(false)
const updating = ref(false)
const buildingFull = ref(false)
const downloadingList = ref(false)
const allowQtyMismatch = ref(false)
const showModal = ref(false)
const pendingDiff = ref<CheckResult | null>(null)
const pendingPayload = ref<DesignBookPayload | null>(null)

const isFirstGen = computed(() => !book.value || book.value.book_rev === 0)

// ============================================================================
// Load
// ============================================================================

async function load() {
  loading.value = true
  error.value = ''
  try {
    book.value = await getDesignBook(bookCode)
    if (book.value?.template_project_id) {
      const { data } = await supabase
        .from('mrp_projects')
        .select('project_code')
        .eq('id', book.value.template_project_id)
        .single()
      if (data?.project_code) templateProjectCode.value = data.project_code
    }
    if (book.value?.title) newTitle.value = book.value.title
  } catch (e: any) {
    error.value = e?.message || 'Failed to load design book'
  } finally {
    loading.value = false
  }
}

onMounted(load)

// ============================================================================
// Sections table
// ============================================================================

const staleBySection = computed(() => {
  const map = new Map<string, string[]>()
  for (const s of book.value?.stale_prints || []) {
    if (!map.has(s.section_code)) map.set(s.section_code, [])
    map.get(s.section_code)!.push(
      `${s.item_number} print ${s.bound_revision ?? '?'}→${s.newest_revision ?? '?'}`
    )
  }
  return map
})

interface SectionGroup {
  label: string
  rows: BookSectionRow[]
}

const groups = computed<SectionGroup[]>(() => {
  const rows = (book.value?.sections || []).filter(s => s.status !== 'superseded')
  const by = (kinds: string[]) =>
    rows.filter(s => kinds.includes(s.kind)).sort((a, b) => a.sort_order - b.sort_order)
  const out: SectionGroup[] = []
  const spine = by(['spine'])
  if (spine.length) out.push({ label: 'Spine (Buy List + TOC)', rows: spine })
  const pkgs = by(['work_package'])
  if (pkgs.length) out.push({ label: 'Section I — Work Packages', rows: pkgs })
  const asms = by(['assembly', 'design_reference'])
  if (asms.length) out.push({ label: 'Section II — Assemblies + Reference', rows: asms })
  const gen = by(['general_reference'])
  if (gen.length) out.push({ label: 'Section III — General Reference', rows: gen })
  return out
})

function sectionState(s: BookSectionRow): { label: string; cls: string; reason: string } {
  if (s.status === 'retired') return { label: 'RETIRED', cls: 'state-retired', reason: '' }
  const stale = staleBySection.value.get(s.section_code)
  if (stale?.length) return { label: 'OUT OF DATE', cls: 'state-stale', reason: stale.join(' · ') }
  return { label: 'CURRENT', cls: 'state-current', reason: '' }
}

function sectionSubtitle(s: BookSectionRow): string {
  switch (s.kind) {
    case 'spine':
      return 'Cover + Buy List + Checklist + TOC'
    case 'general_reference':
      return 'Reference documents, specs, standards'
    case 'design_reference':
      return 'Overall design prints (CSD items)'
    default:
      return ''
  }
}

const staleCount = computed(() => book.value?.stale_prints.length ?? 0)
const currentSections = computed(
  () => (book.value?.sections || []).filter(s => s.status === 'current').length
)
const latestNotice = computed(() =>
  (book.value?.changes || []).find(c => c.notice_path)
)

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return iso.slice(0, 10)
}

// ============================================================================
// Actions
// ============================================================================

async function checkAndUpdate() {
  if (checking.value || updating.value) return
  checking.value = true
  error.value = ''
  success.value = ''
  try {
    let master = await buildMasterModel(templateProjectCode.value)

    // Auto-sync quantities from BOM if there are mismatches
    // Skip sync for new books that don't exist yet - sync will happen on first update
    if (!master.qtyCheck.ok && !allowQtyMismatch.value && book.value) {
      const syncResult = await syncQuantities(bookCode)
      if (syncResult.updated.length > 0) {
        // Show what was synced
        const synced = syncResult.updated.map(u => `${u.item_number}: ${u.old_qty}->${u.new_qty}`).join('; ')
        success.value = `Synced ${syncResult.updated.length} quantities from BOM: ${synced}`
        // Rebuild model with updated quantities
        master = await buildMasterModel(templateProjectCode.value)
      }
      // If still mismatched after sync, show error
      if (!master.qtyCheck.ok) {
        const list = master.qtyCheck.mismatches
          .slice(0, 6)
          .map(m => `${m.item_number}: flat ${m.project_qty} vs BOM ${m.bom_rollup_qty}`)
          .join('; ')
        throw new Error(`Template quantities do not match the BOM rollup — ${list}. Enable "Allow qty mismatch" to override.`)
      }
    }

    const payload = toPayload(master, {
      title: newTitle.value,
      create: isFirstGen.value && !book.value,
      expectedBookRev: book.value ? book.value.book_rev : null,
      allowQtyMismatch: allowQtyMismatch.value,
    })
    pendingDiff.value = await checkDesignBook(bookCode, payload)
    pendingPayload.value = payload
    showModal.value = true
  } catch (e: any) {
    error.value = e?.message || 'Check failed'
  } finally {
    checking.value = false
  }
}

async function commitUpdate() {
  if (!pendingPayload.value || updating.value) return
  updating.value = true
  error.value = ''
  try {
    const result = await updateDesignBook(bookCode, pendingPayload.value)
    showModal.value = false
    pendingDiff.value = null
    pendingPayload.value = null
    const parts: string[] = []
    if (result.changed.length) parts.push(`${result.changed.length} replaced`)
    if (result.added.length) parts.push(`${result.added.length} added`)
    if (result.retired.length) parts.push(`${result.retired.length} removed`)
    success.value =
      `Book published at rev ${result.book_rev}` +
      (parts.length ? ` — ${parts.join(', ')}` : '') +
      (result.change_notice_path ? ' · change notice ready' : '')
    await load()
  } catch (e: any) {
    error.value = e?.message || 'Update failed'
  } finally {
    updating.value = false
  }
}

async function downloadSection(s: BookSectionRow) {
  error.value = ''
  try {
    const url = await getSectionUrl(bookCode, s.section_code)
    window.open(url, '_blank')
  } catch (e: any) {
    error.value = e?.message || 'Download failed'
  }
}

async function openNotice(toRev: number) {
  error.value = ''
  try {
    const url = await getNoticeUrl(bookCode, toRev)
    window.open(url, '_blank')
  } catch (e: any) {
    error.value = e?.message || 'Download failed'
  }
}

async function downloadNotice() {
  if (!latestNotice.value) return
  await openNotice(latestNotice.value.to_rev)
}

async function fullPdf() {
  if (buildingFull.value) return
  buildingFull.value = true
  error.value = ''
  try {
    const info = await downloadFullBook(bookCode)
    success.value = `Full book downloaded — ${info.pages ?? '?'} pages, ${info.sections ?? '?'} sections`
  } catch (e: any) {
    error.value = e?.message || 'Full book failed'
  } finally {
    buildingFull.value = false
  }
}

async function purchaseListCsv() {
  if (downloadingList.value) return
  downloadingList.value = true
  error.value = ''
  try {
    const info = await downloadPurchaseList(bookCode)
    success.value = `Purchase list downloaded — ${info.items} items`
  } catch (e: any) {
    error.value = e?.message || 'Purchase list failed'
  } finally {
    downloadingList.value = false
  }
}
</script>

<template>
  <div class="design-book">
    <header class="page-header">
      <div class="header-left">
        <button class="secondary-btn" @click="router.push('/mrp/design-books')">
          <i class="pi pi-arrow-left"></i> Design Books
        </button>
        <h1>Master Design Book</h1>
        <span class="mono book-code">{{ bookCode }}</span>
        <span v-if="book" class="rev-badge">REV {{ book.book_rev }}</span>
      </div>
      <div class="header-actions">
        <label class="qty-override" title="Bypass quantity mismatch check (use when BOM differs intentionally)">
          <input type="checkbox" v-model="allowQtyMismatch" />
          Allow qty mismatch
        </label>
        <button
          class="primary-btn"
          :disabled="checking || updating || (isFirstGen && !templateProjectCode.trim())"
          :title="isFirstGen && !templateProjectCode.trim() ? 'Set a template project first' : ''"
          @click="checkAndUpdate"
        >
          <i :class="checking ? 'pi pi-spin pi-spinner' : 'pi pi-sync'"></i>
          {{ checking ? 'Checking…' : isFirstGen ? 'Generate Book…' : 'Check & Update…' }}
        </button>
        <button class="success-btn" :disabled="buildingFull || isFirstGen" @click="fullPdf">
          <i :class="buildingFull ? 'pi pi-spin pi-spinner' : 'pi pi-file-pdf'"></i>
          {{ buildingFull ? 'Merging…' : 'Full PDF' }}
        </button>
        <button class="secondary-btn" :disabled="!latestNotice" @click="downloadNotice">
          <i class="pi pi-history"></i> Change Notice
        </button>
        <button class="secondary-btn" :disabled="downloadingList || isFirstGen" @click="purchaseListCsv">
          <i :class="downloadingList ? 'pi pi-spin pi-spinner' : 'pi pi-list'"></i>
          {{ downloadingList ? 'Downloading…' : 'Purchase List' }}
        </button>
        <button class="secondary-btn" @click="router.push(`/mrp/design-book/${bookCode}/images`)">
          <i class="pi pi-images"></i> Images
        </button>
      </div>
    </header>

    <div v-if="error" class="error-message">
      <i class="pi pi-exclamation-triangle"></i>
      <span>{{ error }}</span>
      <button class="dismiss" @click="error = ''">&times;</button>
    </div>
    <div v-if="success" class="success-message">
      <i class="pi pi-check-circle"></i>
      <span>{{ success }}</span>
      <button class="dismiss" @click="success = ''">&times;</button>
    </div>

    <div v-if="loading" class="loading-msg">Loading design book…</div>

    <!-- ============ first generation ============ -->
    <div v-else-if="!book || isFirstGen" class="create-panel">
      <h2>No published book yet</h2>
      <p>
        The Master Design Book is the product-level, date-free (D1..Dn) build document —
        swap-able section booklets with revision letters and change notices.
        Generate rev 1 from the template project's current model, routing, and prints.
      </p>
      <div class="create-form">
        <label>
          <span>Title</span>
          <input v-model="newTitle" type="text" />
        </label>
        <label>
          <span>Template project</span>
          <input v-model="templateProjectCode" type="text" class="mono" />
        </label>
      </div>
      <p class="muted">
        "Generate Book…" runs a dry-run first — you review the full section list
        (and acknowledge any missing prints) before anything publishes.
      </p>
    </div>

    <!-- ============ book state ============ -->
    <template v-else>
      <div class="stats-row">
        <div class="stat-box">
          <div class="stat-value">{{ book.book_rev }}</div>
          <div class="stat-label">Book Rev</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">{{ currentSections }}</div>
          <div class="stat-label">Sections</div>
        </div>
        <div class="stat-box">
          <div class="stat-value">{{ fmtDate(book.generated_at) }}</div>
          <div class="stat-label">Last Published</div>
        </div>
        <div class="stat-box">
          <div class="stat-value mono">{{ book.product_item_number }}</div>
          <div class="stat-label">Product</div>
        </div>
        <div class="stat-box">
          <div class="stat-value mono">{{ templateProjectCode }}</div>
          <div class="stat-label">Template</div>
        </div>
        <div class="stat-box" :class="{ 'stat-warn': staleCount > 0 }">
          <div class="stat-value">{{ staleCount }}</div>
          <div class="stat-label">Stale Prints</div>
        </div>
      </div>

      <div class="sections-card">
        <table class="sections-table">
          <thead>
            <tr>
              <th style="width: 120px">Code</th>
              <th>Title</th>
              <th style="width: 52px">Rev</th>
              <th style="width: 60px">Pages</th>
              <th style="width: 220px">Status</th>
              <th style="width: 100px">Updated</th>
              <th style="width: 80px"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in groups" :key="g.label">
              <tr class="group-row">
                <td colspan="7">{{ g.label }}</td>
              </tr>
              <tr v-for="s in g.rows" :key="s.section_code" :class="{ retired: s.status === 'retired' }">
                <td class="mono">{{ s.section_code }}</td>
                <td>
                  <div>{{ s.title }}</div>
                  <div v-if="sectionSubtitle(s)" class="section-subtitle">{{ sectionSubtitle(s) }}</div>
                </td>
                <td class="mono">{{ s.rev }}</td>
                <td>{{ s.page_count ?? '—' }}</td>
                <td>
                  <span class="state-chip" :class="sectionState(s).cls">{{ sectionState(s).label }}</span>
                  <div v-if="sectionState(s).reason" class="state-reason">{{ sectionState(s).reason }}</div>
                </td>
                <td class="muted">{{ fmtDate(s.updated_at) }}</td>
                <td>
                  <button
                    v-if="s.status === 'current'"
                    class="row-btn"
                    title="Download booklet PDF"
                    @click="downloadSection(s)"
                  >
                    <i class="pi pi-download"></i> PDF
                  </button>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div v-if="book.changes.length" class="history-card">
        <h3>Revision History</h3>
        <table class="sections-table">
          <thead>
            <tr>
              <th style="width: 80px">Rev</th>
              <th style="width: 120px">Issued</th>
              <th>Change Notice</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in book.changes" :key="c.to_rev">
              <td class="mono">{{ c.from_rev }} → {{ c.to_rev }}</td>
              <td class="muted">{{ fmtDate(c.created_at) }}</td>
              <td>
                <button v-if="c.notice_path" class="row-btn" @click="openNotice(c.to_rev)">
                  <i class="pi pi-file-pdf"></i> CHANGE-NOTICE-rev{{ String(c.to_rev).padStart(3, '0') }}
                </button>
                <span v-else class="muted">initial issue — no notice</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <DesignBookUpdateModal
      v-if="showModal && pendingDiff"
      :diff="pendingDiff"
      :committing="updating"
      :first-gen="isFirstGen"
      @close="showModal = false"
      @commit="commitUpdate"
    />
  </div>
</template>

<style scoped>
.design-book {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  padding-bottom: 40px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  background: #020617;
  border-bottom: 1px solid #1e293b;
  flex-wrap: wrap;
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-left h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.book-code {
  color: #9ca3af;
  font-size: 13px;
}

.rev-badge {
  background: #059669;
  color: white;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.qty-override {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #9ca3af;
  cursor: pointer;
  padding: 6px 10px;
  border: 1px solid #374151;
  border-radius: 6px;
  background: #0f172a;
}
.qty-override:hover {
  border-color: #4b5563;
}
.qty-override input {
  cursor: pointer;
}

.mono { font-family: 'Consolas', 'Monaco', monospace; }
.muted { color: #9ca3af; font-size: 12px; }

/* buttons */
.primary-btn,
.secondary-btn,
.success-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}
.primary-btn { background: #2563eb; }
.primary-btn:hover:not(:disabled) { background: #1d4ed8; }
.secondary-btn { background: #374151; }
.secondary-btn:hover:not(:disabled) { background: #4b5563; }
.success-btn { background: #059669; }
.success-btn:hover:not(:disabled) { background: #047857; }
.primary-btn:disabled,
.secondary-btn:disabled,
.success-btn:disabled {
  background: #374151;
  color: #6b7280;
  cursor: not-allowed;
}

/* banners */
.error-message,
.success-message {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 20px 0;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}
.error-message { background: #7f1d1d; color: #fca5a5; }
.success-message { background: #065f46; color: #6ee7b7; }
.dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  font-size: 18px;
  cursor: pointer;
  line-height: 1;
}

.loading-msg {
  padding: 40px 20px;
  color: #9ca3af;
}

/* first generation panel */
.create-panel {
  margin: 24px 20px;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 24px;
  max-width: 720px;
}
.create-panel h2 {
  margin: 0 0 8px;
  font-size: 16px;
}
.create-panel p {
  color: #9ca3af;
  font-size: 13px;
  line-height: 1.5;
}
.create-form {
  display: flex;
  gap: 16px;
  margin: 16px 0;
  flex-wrap: wrap;
}
.create-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.create-form input {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 8px 10px;
  font-size: 13px;
  min-width: 260px;
}
.create-form input:focus {
  outline: none;
  border-color: #38bdf8;
}

/* stats */
.stats-row {
  display: flex;
  gap: 12px;
  margin: 20px;
  flex-wrap: wrap;
}
.stat-box {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 12px 18px;
  min-width: 110px;
}
.stat-box.stat-warn { border-color: #d97706; }
.stat-box.stat-warn .stat-value { color: #fbbf24; }
.stat-value {
  font-size: 22px;
  font-weight: 700;
}
.stat-label {
  font-size: 11px;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-top: 2px;
}

/* sections table */
.sections-card,
.history-card {
  margin: 0 20px 20px;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  overflow: hidden;
}
.history-card { padding-top: 4px; }
.history-card h3 {
  margin: 12px 16px 4px;
  font-size: 13px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.sections-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.sections-table th {
  text-align: left;
  padding: 10px 12px;
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.sections-table td {
  padding: 9px 12px;
  border-bottom: 1px solid #1e293b;
}
.sections-table tbody tr:hover { background: #1e293b; }
.sections-table tr.retired td { color: #6b7280; }

.group-row td {
  background: #020617;
  color: #9ca3af;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 8px 12px;
}

.state-chip {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  color: white;
}
.state-current { background: #059669; }
.state-stale { background: #d97706; }
.state-retired { background: #374151; color: #9ca3af; }
.state-reason {
  color: #9ca3af;
  font-size: 11px;
  margin-top: 4px;
}

.row-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: #374151;
  border: none;
  color: white;
  padding: 5px 10px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
}
.row-btn:hover { background: #4b5563; }

.section-subtitle {
  font-size: 11px;
  color: #6b7280;
  margin-top: 2px;
  font-style: italic;
}
</style>
