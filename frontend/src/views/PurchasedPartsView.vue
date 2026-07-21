<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../services/supabase'

interface PurchasedPart {
  id: string
  item_number: string
  name: string | null
  supplier_name: string | null
  supplier_pn: string | null
  unit_price: number | null
  reference_url: string | null
  is_supplier_part: boolean
  has_pdf: boolean
}

const router = useRouter()

// State
const allParts = ref<PurchasedPart[]>([])
const loading = ref(true)
const searchInput = ref('')
const supplierFilter = ref('')
const typeFilter = ref('')
const showAllParts = ref(false)
const changes = ref<Map<string, Partial<PurchasedPart>>>(new Map())
const statusMessage = ref('')
const statusType = ref<'success' | 'error' | ''>('')

// Computed
const suppliers = computed(() => {
  const set = new Set<string>()
  allParts.value.forEach(p => {
    if (p.supplier_name) set.add(p.supplier_name)
  })
  return Array.from(set).sort()
})

const displayedParts = computed(() => {
  return allParts.value.filter(p => {
    // If not showing all, only show mmc/spn or flagged as supplier part
    if (!showAllParts.value) {
      const num = p.item_number.toLowerCase()
      const isPurchased = num.startsWith('mmc') || num.startsWith('spn') || p.is_supplier_part
      if (!isPurchased) return false
    }

    const search = searchInput.value.toLowerCase()
    const matchSearch = !search ||
      p.item_number.toLowerCase().includes(search) ||
      (p.name || '').toLowerCase().includes(search) ||
      (p.supplier_name || '').toLowerCase().includes(search) ||
      (p.supplier_pn || '').toLowerCase().includes(search)

    const matchSupplier = !supplierFilter.value || p.supplier_name === supplierFilter.value

    let matchType = true
    if (typeFilter.value === 'mmc') matchType = p.item_number.toLowerCase().startsWith('mmc')
    else if (typeFilter.value === 'spn') matchType = p.item_number.toLowerCase().startsWith('spn')
    else if (typeFilter.value === 'other') {
      const num = p.item_number.toLowerCase()
      matchType = !num.startsWith('mmc') && !num.startsWith('spn') && p.is_supplier_part
    }

    return matchSearch && matchSupplier && matchType
  })
})

const totalCount = computed(() => {
  const num = (p: PurchasedPart) => p.item_number.toLowerCase()
  return allParts.value.filter(p =>
    num(p).startsWith('mmc') || num(p).startsWith('spn') || p.is_supplier_part
  ).length
})

const mmcCount = computed(() =>
  allParts.value.filter(p => p.item_number.toLowerCase().startsWith('mmc')).length
)

const spnCount = computed(() =>
  allParts.value.filter(p => p.item_number.toLowerCase().startsWith('spn')).length
)

const missingInfoCount = computed(() =>
  displayedParts.value.filter(p => !p.supplier_name || !p.unit_price).length
)

const changesCount = computed(() => changes.value.size)

// Methods
async function loadParts() {
  loading.value = true
  try {
    // Get items with file info
    const { data, error } = await supabase
      .from('items')
      .select(`
        id,
        item_number,
        name,
        supplier_name,
        supplier_pn,
        unit_price,
        reference_url,
        is_supplier_part,
        files!left(id, file_type)
      `)
      .order('item_number')

    if (error) throw error

    allParts.value = (data || []).map(item => ({
      ...item,
      is_supplier_part: item.is_supplier_part || false,
      has_pdf: (item.files || []).some((f: any) => f.file_type === 'PDF')
    }))
  } catch (err) {
    console.error('Failed to load parts:', err)
    showStatus('Failed to load parts', 'error')
  } finally {
    loading.value = false
  }
}

function getPartType(itemNumber: string): string {
  const num = itemNumber.toLowerCase()
  if (num.startsWith('mmc')) return 'McMaster'
  if (num.startsWith('spn')) return 'Supplier'
  return 'Other'
}

function getDisplayNumber(p: PurchasedPart): string {
  // Show supplier PN if available, else strip prefix
  if (p.supplier_pn) return p.supplier_pn.toUpperCase()
  const num = p.item_number.toLowerCase()
  if (num.startsWith('mmc')) return p.item_number.slice(3).toUpperCase()
  if (num.startsWith('spn')) return p.item_number.slice(3).toUpperCase()
  return p.item_number.toUpperCase()
}

function hasChanges(id: string): boolean {
  return changes.value.has(id)
}

function trackChange(id: string, field: keyof PurchasedPart, value: string | boolean | number | null) {
  const current = changes.value.get(id) || {}
  const newChanges = new Map(changes.value)
  newChanges.set(id, { ...current, [field]: value })
  changes.value = newChanges

  // Update local display
  const part = allParts.value.find(p => p.id === id)
  if (part) {
    (part as any)[field] = value
  }
}

function trackTextChange(id: string, field: keyof PurchasedPart, event: Event) {
  const value = (event.target as HTMLInputElement).value || null
  trackChange(id, field, value)
}

function trackPriceChange(id: string, event: Event) {
  const value = (event.target as HTMLInputElement).value
  const numVal = value === '' ? null : parseFloat(value) || null
  trackChange(id, 'unit_price', numVal)
}

function trackSupplierToggle(id: string, event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  trackChange(id, 'is_supplier_part', checked)
}

function openLink(url: string | null) {
  if (url) window.open(url, '_blank')
}

function goToItem(itemNumber: string) {
  router.push(`/items/${itemNumber}`)
}

async function saveAll() {
  if (changes.value.size === 0) {
    showStatus('No changes to save', 'error')
    return
  }

  let saved = 0
  for (const [id, updates] of changes.value.entries()) {
    try {
      const { error } = await supabase
        .from('items')
        .update(updates)
        .eq('id', id)

      if (error) throw error
      saved++
    } catch (err) {
      console.error(`Failed to save item ${id}:`, err)
    }
  }

  changes.value = new Map()
  showStatus(`Saved ${saved} item${saved !== 1 ? 's' : ''}`, 'success')
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
  router.push('/mrp/dashboard')
}

onMounted(() => {
  loadParts()
})
</script>

<template>
  <div class="purchased-parts-page">
    <!-- Status Message -->
    <div v-if="statusMessage" :class="['status-msg', statusType]">
      {{ statusMessage }}
    </div>

    <!-- Header -->
    <div class="header">
      <h1>Purchased Parts</h1>
      <button class="btn btn-success" @click="goBack">
        <span class="back-arrow">&larr;</span> Back to MRP
      </button>
    </div>

    <!-- Summary Bar -->
    <div class="summary-bar">
      <div class="summary-item">Total Purchased: <strong>{{ totalCount }}</strong></div>
      <div class="summary-item">McMaster: <strong class="mmc">{{ mmcCount }}</strong></div>
      <div class="summary-item">Supplier: <strong class="spn">{{ spnCount }}</strong></div>
      <div class="summary-item">Missing Info: <strong class="missing">{{ missingInfoCount }}</strong></div>
      <div class="summary-item">Unsaved: <strong class="changes">{{ changesCount }}</strong></div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <input
        v-model="searchInput"
        type="text"
        placeholder="Search by part number, name, supplier..."
        class="search-input"
      />
      <select v-model="typeFilter">
        <option value="">All Types</option>
        <option value="mmc">McMaster (mmc)</option>
        <option value="spn">Supplier (spn)</option>
        <option value="other">Other Purchased</option>
      </select>
      <select v-model="supplierFilter">
        <option value="">All Suppliers</option>
        <option v-for="s in suppliers" :key="s" :value="s">{{ s }}</option>
      </select>
      <label class="checkbox-label">
        <input type="checkbox" v-model="showAllParts" />
        Show all parts (to flag as purchased)
      </label>
      <button class="btn btn-primary" @click="saveAll" :disabled="changesCount === 0">
        Save All Changes
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      Loading parts...
    </div>

    <!-- Empty State -->
    <div v-else-if="displayedParts.length === 0" class="empty-state">
      No parts found matching filters
    </div>

    <!-- Parts Table -->
    <table v-else class="parts-table">
      <thead>
        <tr>
          <th class="col-checkbox" v-if="showAllParts">Purchased</th>
          <th class="col-part">Part Number</th>
          <th class="col-type">Type</th>
          <th class="col-display">Display #</th>
          <th class="col-name">Name</th>
          <th class="col-supplier">Supplier Name</th>
          <th class="col-suppn">Supplier PN</th>
          <th class="col-price">Unit Price</th>
          <th class="col-link">Link</th>
          <th class="col-pdf">PDF</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="p in displayedParts"
          :key="p.id"
          :class="{ 'has-changes': hasChanges(p.id), 'missing-info': !p.supplier_name || !p.unit_price }"
        >
          <td v-if="showAllParts" class="col-checkbox">
            <input
              type="checkbox"
              :checked="p.is_supplier_part || p.item_number.toLowerCase().startsWith('mmc') || p.item_number.toLowerCase().startsWith('spn')"
              :disabled="p.item_number.toLowerCase().startsWith('mmc') || p.item_number.toLowerCase().startsWith('spn')"
              @change="trackSupplierToggle(p.id, $event)"
              title="Flag as purchased part"
            />
          </td>
          <td class="col-part">
            <a href="#" @click.prevent="goToItem(p.item_number)" class="part-link">
              {{ p.item_number }}
            </a>
          </td>
          <td class="col-type">
            <span :class="['badge', `badge-${getPartType(p.item_number).toLowerCase()}`]">
              {{ getPartType(p.item_number) }}
            </span>
          </td>
          <td class="col-display">{{ getDisplayNumber(p) }}</td>
          <td class="col-name">{{ p.name || '—' }}</td>
          <td class="col-supplier">
            <input
              type="text"
              :value="p.supplier_name || ''"
              placeholder="Enter supplier"
              @change="trackTextChange(p.id, 'supplier_name', $event)"
            />
          </td>
          <td class="col-suppn">
            <input
              type="text"
              :value="p.supplier_pn || ''"
              placeholder="Supplier PN"
              @change="trackTextChange(p.id, 'supplier_pn', $event)"
            />
          </td>
          <td class="col-price">
            <div class="price-cell">
              <span class="currency">$</span>
              <input
                type="number"
                :value="p.unit_price ?? ''"
                step="0.01"
                min="0"
                placeholder="0.00"
                @change="trackPriceChange(p.id, $event)"
              />
            </div>
          </td>
          <td class="col-link">
            <input
              type="url"
              :value="p.reference_url || ''"
              placeholder="https://..."
              @change="trackTextChange(p.id, 'reference_url', $event)"
              class="url-input"
            />
            <button
              v-if="p.reference_url"
              class="btn-icon"
              @click="openLink(p.reference_url)"
              title="Open link"
            >
              &#x2197;
            </button>
          </td>
          <td class="col-pdf">
            <span v-if="p.has_pdf" class="pdf-yes" title="Has PDF">&#x2713;</span>
            <a v-else href="#" @click.prevent="goToItem(p.item_number)" class="pdf-upload" title="Upload PDF">
              +
            </a>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.purchased-parts-page {
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

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #1d4ed8;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1e40af;
}

.btn-success {
  background: #065f46;
  color: #6ee7b7;
}

.btn-success:hover {
  background: #064e3b;
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
  flex-wrap: wrap;
}

.summary-item {
  font-size: 13px;
}

.summary-item strong {
  color: #38bdf8;
}

.summary-item strong.mmc {
  color: #fde68a;
}

.summary-item strong.spn {
  color: #a5b4fc;
}

.summary-item strong.missing {
  color: #fca5a5;
}

.summary-item strong.changes {
  color: #6ee7b7;
}

.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  align-items: center;
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

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #9ca3af;
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  cursor: pointer;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
  font-size: 14px;
}

.parts-table {
  width: 100%;
  border-collapse: collapse;
  background: #0f172a;
  border-radius: 8px;
  overflow: hidden;
}

.parts-table th {
  background: #1e293b;
  padding: 12px 8px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: #9ca3af;
  white-space: nowrap;
}

.parts-table td {
  padding: 8px;
  border-bottom: 1px solid #1e293b;
  font-size: 13px;
}

.parts-table tr:hover {
  background: #1e293b;
}

.parts-table input[type="text"],
.parts-table input[type="url"],
.parts-table input[type="number"] {
  width: 100%;
  padding: 4px 6px;
  border-radius: 4px;
  border: 1px solid #374151;
  background: #020617;
  color: #e5e7eb;
  font-size: 12px;
}

.parts-table input::placeholder {
  color: #6b7280;
}

.col-checkbox { width: 60px; text-align: center; }
.col-part { width: 120px; }
.col-type { width: 80px; }
.col-display { width: 100px; }
.col-name { width: 180px; }
.col-supplier { width: 140px; }
.col-suppn { width: 120px; }
.col-price { width: 100px; }
.col-link { width: 180px; }
.col-pdf { width: 50px; text-align: center; }

.part-link {
  color: #38bdf8;
  text-decoration: none;
  font-family: monospace;
}

.part-link:hover {
  text-decoration: underline;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
}

.badge-mcmaster {
  background: #713f12;
  color: #fde68a;
}

.badge-supplier {
  background: #312e81;
  color: #a5b4fc;
}

.badge-other {
  background: #374151;
  color: #9ca3af;
}

.price-cell {
  display: flex;
  align-items: center;
  gap: 2px;
}

.price-cell .currency {
  color: #6b7280;
  font-size: 12px;
}

.price-cell input[type="number"] {
  width: 70px;
}

.url-input {
  width: calc(100% - 30px) !important;
}

.btn-icon {
  background: none;
  border: none;
  color: #38bdf8;
  cursor: pointer;
  font-size: 14px;
  padding: 2px 6px;
}

.btn-icon:hover {
  color: #7dd3fc;
}

.pdf-yes {
  color: #6ee7b7;
  font-weight: bold;
}

.pdf-upload {
  color: #9ca3af;
  text-decoration: none;
  font-size: 16px;
  font-weight: bold;
}

.pdf-upload:hover {
  color: #38bdf8;
}

.has-changes {
  background: #1e3a5c !important;
}

.missing-info {
  border-left: 3px solid #f87171;
}

.status-msg {
  position: fixed;
  top: 20px;
  right: 20px;
  padding: 12px 20px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  z-index: 1000;
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
