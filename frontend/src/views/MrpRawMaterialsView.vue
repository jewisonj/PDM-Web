<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../services/supabase'

interface RawMaterial {
  id: string
  part_number: string
  type: string
  material: string
  material_code: string
  profile: string | null
  dim1_in: number | null
  dim2_in: number | null
  wall_or_thk_in: number | null
  wall_or_thk_code: string | null
  stock_length_ft: number | null
  qty_on_hand: number
  qty_on_order: number
  reorder_point: number
  price_per_unit: number | null
  material_type: string
}

const router = useRouter()

// State
const allMaterials = ref<RawMaterial[]>([])
const loading = ref(true)
const searchInput = ref('')
const typeFilter = ref('')
const materialFilter = ref('')
const stockFilter = ref('')
const changes = ref<Map<string, Partial<RawMaterial>>>(new Map())
const statusMessage = ref('')
const statusType = ref<'success' | 'error' | ''>('')

// Computed
const displayedMaterials = computed(() => {
  return allMaterials.value.filter(m => {
    const search = searchInput.value.toLowerCase()
    const matchSearch = !search ||
      (m.part_number || '').toLowerCase().includes(search) ||
      (m.material || '').toLowerCase().includes(search) ||
      (m.profile || '').toLowerCase().includes(search)

    const matchType = !typeFilter.value || m.type === typeFilter.value
    const matchMaterial = !materialFilter.value || m.material_code === materialFilter.value

    let matchStock = true
    if (stockFilter.value === 'low') {
      matchStock = m.qty_on_hand > 0 && m.qty_on_hand <= m.reorder_point
    } else if (stockFilter.value === 'out') {
      matchStock = m.qty_on_hand === 0
    }

    return matchSearch && matchType && matchMaterial && matchStock
  })
})

const totalCount = computed(() => allMaterials.value.length)
const lowCount = computed(() => allMaterials.value.filter(m => m.qty_on_hand > 0 && m.qty_on_hand <= m.reorder_point).length)
const outCount = computed(() => allMaterials.value.filter(m => m.qty_on_hand === 0).length)
const changesCount = computed(() => changes.value.size)

// Methods
async function loadMaterials() {
  loading.value = true
  try {
    const { data, error } = await supabase
      .from('raw_materials')
      .select('*')
      .order('part_number')

    if (error) throw error
    allMaterials.value = data || []
  } catch (err) {
    console.error('Failed to load materials:', err)
    showStatus('Failed to load materials', 'error')
  } finally {
    loading.value = false
  }
}

function getDimensions(m: RawMaterial): string {
  if (m.type === 'SM') {
    return `${m.wall_or_thk_code || ''} (${m.wall_or_thk_in || 0}")`
  }
  if (m.dim2_in) {
    return `${m.dim1_in}" x ${m.dim2_in}" x ${m.wall_or_thk_in}"`
  }
  return `${m.dim1_in}" OD x ${m.wall_or_thk_in}" wall`
}

function getStockClass(m: RawMaterial): string {
  if (m.qty_on_hand === 0) return 'stock-out'
  if (m.qty_on_hand <= m.reorder_point) return 'stock-low'
  return 'stock-ok'
}

function hasChanges(id: string): boolean {
  return changes.value.has(id)
}

function trackChange(id: string, field: keyof RawMaterial, value: string) {
  const current = changes.value.get(id) || {}
  const newChanges = new Map(changes.value)
  newChanges.set(id, { ...current, [field]: parseInt(value) || 0 })
  changes.value = newChanges

  // Also update local display value
  const material = allMaterials.value.find(m => m.id === id)
  if (material) {
    (material as any)[field] = parseInt(value) || 0
  }
}

function trackPriceChange(id: string, value: string) {
  const current = changes.value.get(id) || {}
  const newChanges = new Map(changes.value)
  const numVal = value === '' ? null : parseFloat(value) || null
  newChanges.set(id, { ...current, price_per_unit: numVal })
  changes.value = newChanges

  const material = allMaterials.value.find(m => m.id === id)
  if (material) {
    material.price_per_unit = numVal
  }
}

function getPriceUnit(m: RawMaterial): string {
  return m.material_type === 'SM' ? '$/lb' : '$/ft'
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
        .from('raw_materials')
        .update(updates)
        .eq('id', id)

      if (error) throw error
      saved++
    } catch (err) {
      console.error(`Failed to save material ${id}:`, err)
    }
  }

  changes.value = new Map()
  showStatus(`Saved ${saved} material${saved !== 1 ? 's' : ''}`, 'success')
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
  loadMaterials()
})
</script>

<template>
  <div class="raw-materials-page">
    <!-- Status Message -->
    <div v-if="statusMessage" :class="['status-msg', statusType]">
      {{ statusMessage }}
    </div>

    <!-- Header -->
    <div class="header">
      <h1>Raw Materials Inventory</h1>
      <button class="btn btn-success" @click="goBack">
        <span class="back-arrow">&larr;</span> Back to MRP
      </button>
    </div>

    <!-- Summary Bar -->
    <div class="summary-bar">
      <div class="summary-item">Total: <strong>{{ totalCount }}</strong></div>
      <div class="summary-item">Low Stock: <strong class="low">{{ lowCount }}</strong></div>
      <div class="summary-item">Out of Stock: <strong class="out">{{ outCount }}</strong></div>
      <div class="summary-item">Unsaved Changes: <strong class="changes">{{ changesCount }}</strong></div>
    </div>

    <!-- Filter Bar -->
    <div class="filter-bar">
      <input
        v-model="searchInput"
        type="text"
        placeholder="Search by part number, material..."
        class="search-input"
      />
      <select v-model="typeFilter">
        <option value="">All Types</option>
        <option value="SQ">Square/Rect Tube</option>
        <option value="OT">Round Tube</option>
        <option value="SM">Sheet Metal</option>
      </select>
      <select v-model="materialFilter">
        <option value="">All Materials</option>
        <option value="SS">Stainless Steel</option>
        <option value="CS">Carbon Steel</option>
      </select>
      <select v-model="stockFilter">
        <option value="">All Stock Levels</option>
        <option value="low">Low Stock</option>
        <option value="out">Out of Stock</option>
      </select>
      <button class="btn btn-primary" @click="saveAll">
        Save All Changes
      </button>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="loading-state">
      Loading materials...
    </div>

    <!-- Empty State -->
    <div v-else-if="displayedMaterials.length === 0" class="empty-state">
      No materials found matching filters
    </div>

    <!-- Materials Table -->
    <table v-else class="material-table">
      <thead>
        <tr>
          <th>Part Number</th>
          <th>Type</th>
          <th>Dimensions</th>
          <th>Material</th>
          <th>Stock Length</th>
          <th>Price/Unit</th>
          <th>On Hand</th>
          <th>On Order</th>
          <th>Reorder Point</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="m in displayedMaterials"
          :key="m.id"
          :class="{ 'has-changes': hasChanges(m.id) }"
        >
          <td>{{ m.part_number }}</td>
          <td>
            <span :class="['badge', `badge-${(m.type || '').toLowerCase()}`]">{{ m.type }}</span>
          </td>
          <td>{{ getDimensions(m) }}</td>
          <td>
            <span :class="['badge', `badge-${(m.material_code || '').toLowerCase()}`]">{{ m.material_code }}</span>
            {{ m.material }}
          </td>
          <td>{{ m.stock_length_ft ? m.stock_length_ft + ' ft' : 'Sheet' }}</td>
          <td class="price-cell">
            <input
              type="number"
              :value="m.price_per_unit ?? ''"
              step="0.01"
              min="0"
              placeholder="default"
              @change="trackPriceChange(m.id, ($event.target as HTMLInputElement).value)"
            />
            <span class="price-unit">{{ getPriceUnit(m) }}</span>
          </td>
          <td :class="getStockClass(m)">
            <input
              type="number"
              :value="m.qty_on_hand || 0"
              @change="trackChange(m.id, 'qty_on_hand', ($event.target as HTMLInputElement).value)"
            />
          </td>
          <td>
            <input
              type="number"
              :value="m.qty_on_order || 0"
              @change="trackChange(m.id, 'qty_on_order', ($event.target as HTMLInputElement).value)"
            />
          </td>
          <td>
            <input
              type="number"
              :value="m.reorder_point || 0"
              @change="trackChange(m.id, 'reorder_point', ($event.target as HTMLInputElement).value)"
            />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.raw-materials-page {
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

.btn-primary {
  background: #1d4ed8;
  color: white;
}

.btn-primary:hover {
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
}

.summary-item {
  font-size: 13px;
}

.summary-item strong {
  color: #38bdf8;
}

.summary-item strong.low {
  color: #fca5a5;
}

.summary-item strong.out {
  color: #f87171;
}

.summary-item strong.changes {
  color: #fde68a;
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
  padding: 40px;
  color: #9ca3af;
  font-size: 14px;
}

.material-table {
  width: 100%;
  border-collapse: collapse;
  background: #0f172a;
  border-radius: 8px;
  overflow: hidden;
}

.material-table th {
  background: #1e293b;
  padding: 12px;
  text-align: left;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: #9ca3af;
}

.material-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #1e293b;
  font-size: 13px;
}

.material-table tr:hover {
  background: #020617;
}

.material-table input[type="number"] {
  width: 80px;
  padding: 4px 6px;
  border-radius: 4px;
  border: 1px solid #1f2937;
  background: #020617;
  color: #e5e7eb;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.badge-sq {
  background: #1e3a8a;
  color: #93c5fd;
}

.badge-ot {
  background: #065f46;
  color: #6ee7b7;
}

.badge-sm {
  background: #713f12;
  color: #fde68a;
}

.badge-ss {
  background: #4c1d95;
  color: #ddd6fe;
}

.badge-cs {
  background: #7f1d1d;
  color: #fca5a5;
}

.stock-low {
  color: #fca5a5;
  font-weight: 600;
}

.stock-out {
  color: #f87171;
  font-weight: 600;
}

.stock-ok {
  color: #6ee7b7;
}

.has-changes {
  background: #1e3a5c !important;
}

.price-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

.price-cell input[type="number"] {
  width: 80px;
  padding: 4px 6px;
  border-radius: 4px;
  border: 1px solid #1f2937;
  background: #020617;
  color: #e5e7eb;
}

.price-cell input::placeholder {
  color: #6b7280;
  font-style: italic;
}

.price-unit {
  color: #9ca3af;
  font-size: 11px;
  white-space: nowrap;
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
