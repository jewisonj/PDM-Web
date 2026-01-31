<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../services/supabase'

interface CostSetting {
  id: string
  setting_key: string
  setting_value: number
  description: string
  updated_at: string
}

interface Workstation {
  id: string
  station_code: string
  station_name: string
  sort_order: number
  hourly_rate: number | null
  is_outsourced: boolean
  outsourced_cost_default: number | null
}

interface RawMaterial {
  id: string
  part_number: string
  material_type: string
  material_code: string
  profile: string | null
  dim1_in: number | null
  dim2_in: number | null
  wall_or_thk_in: number | null
  wall_or_thk_code: string | null
  stock_length_ft: number | null
  price_per_unit: number | null
}

const router = useRouter()

// State
const costSettings = ref<CostSetting[]>([])
const workstations = ref<Workstation[]>([])
const rawMaterials = ref<RawMaterial[]>([])
const loading = ref(true)
const settingChanges = ref<Map<string, Partial<CostSetting>>>(new Map())
const stationChanges = ref<Map<string, Partial<Workstation>>>(new Map())
const materialChanges = ref<Map<string, Partial<RawMaterial>>>(new Map())
const statusMessage = ref('')
const statusType = ref<'success' | 'error' | ''>('')
const materialSearch = ref('')
const materialTypeFilter = ref('')

// Display labels for setting keys
const settingLabels: Record<string, string> = {
  default_labor_rate: 'Default Labor Rate',
  default_sm_price_per_lb: 'Default Sheet Metal Price',
  default_tube_price_per_ft: 'Default Tubing Price',
  overhead_multiplier: 'Overhead Multiplier'
}

const settingUnits: Record<string, string> = {
  default_labor_rate: '$/hr',
  default_sm_price_per_lb: '$/lb',
  default_tube_price_per_ft: '$/ft',
  overhead_multiplier: 'x'
}

// Computed
const totalChanges = computed(() =>
  settingChanges.value.size + stationChanges.value.size + materialChanges.value.size
)

const filteredMaterials = computed(() => {
  return rawMaterials.value.filter(m => {
    const search = materialSearch.value.toLowerCase()
    const matchSearch = !search ||
      (m.part_number || '').toLowerCase().includes(search) ||
      (m.material_code || '').toLowerCase().includes(search) ||
      (m.profile || '').toLowerCase().includes(search)
    const matchType = !materialTypeFilter.value || m.material_type === materialTypeFilter.value
    return matchSearch && matchType
  })
})

// Methods
async function loadAll() {
  loading.value = true
  try {
    const [settingsRes, stationsRes, materialsRes] = await Promise.all([
      supabase.from('cost_settings').select('*').order('setting_key'),
      supabase.from('workstations').select('*').order('sort_order'),
      supabase.from('raw_materials').select('*').order('part_number')
    ])

    if (settingsRes.error) throw settingsRes.error
    if (stationsRes.error) throw stationsRes.error
    if (materialsRes.error) throw materialsRes.error

    costSettings.value = settingsRes.data || []
    workstations.value = stationsRes.data || []
    rawMaterials.value = materialsRes.data || []
  } catch (err) {
    console.error('Failed to load settings:', err)
    showStatus('Failed to load settings', 'error')
  } finally {
    loading.value = false
  }
}

function trackSettingChange(id: string, value: string) {
  const newChanges = new Map(settingChanges.value)
  newChanges.set(id, { setting_value: parseFloat(value) || 0 })
  settingChanges.value = newChanges

  const setting = costSettings.value.find(s => s.id === id)
  if (setting) setting.setting_value = parseFloat(value) || 0
}

function trackStationChange(id: string, field: keyof Workstation, value: any) {
  const current = stationChanges.value.get(id) || {}
  const newChanges = new Map(stationChanges.value)

  if (field === 'is_outsourced') {
    newChanges.set(id, { ...current, [field]: value })
    const station = workstations.value.find(s => s.id === id)
    if (station) station.is_outsourced = value
  } else if (field === 'hourly_rate' || field === 'outsourced_cost_default') {
    const numVal = value === '' ? null : parseFloat(value) || null
    newChanges.set(id, { ...current, [field]: numVal })
    const station = workstations.value.find(s => s.id === id)
    if (station) (station as any)[field] = numVal
  }

  stationChanges.value = newChanges
}

function trackMaterialChange(id: string, value: string) {
  const newChanges = new Map(materialChanges.value)
  const numVal = value === '' ? null : parseFloat(value) || null
  newChanges.set(id, { price_per_unit: numVal })
  materialChanges.value = newChanges

  const material = rawMaterials.value.find(m => m.id === id)
  if (material) material.price_per_unit = numVal
}

function getMaterialDimensions(m: RawMaterial): string {
  if (m.material_type === 'SM') {
    return `${m.wall_or_thk_code || ''} (${m.wall_or_thk_in || 0}")`
  }
  if (m.dim2_in) {
    return `${m.dim1_in}" x ${m.dim2_in}" x ${m.wall_or_thk_in}"`
  }
  return `${m.dim1_in}" OD x ${m.wall_or_thk_in}" wall`
}

function getPriceUnit(m: RawMaterial): string {
  return m.material_type === 'SM' ? '$/lb' : '$/ft'
}

function getDefaultPrice(m: RawMaterial): number | null {
  const key = m.material_type === 'SM' ? 'default_sm_price_per_lb' : 'default_tube_price_per_ft'
  const setting = costSettings.value.find(s => s.setting_key === key)
  return setting ? setting.setting_value : null
}

function getDefaultRate(): number | null {
  const setting = costSettings.value.find(s => s.setting_key === 'default_labor_rate')
  return setting ? setting.setting_value : null
}

async function saveAll() {
  if (totalChanges.value === 0) {
    showStatus('No changes to save', 'error')
    return
  }

  let saved = 0

  // Save cost settings
  for (const [id, updates] of settingChanges.value.entries()) {
    try {
      const { error } = await supabase
        .from('cost_settings')
        .update({ ...updates, updated_at: new Date().toISOString() })
        .eq('id', id)
      if (error) throw error
      saved++
    } catch (err) {
      console.error(`Failed to save setting ${id}:`, err)
    }
  }

  // Save station changes
  for (const [id, updates] of stationChanges.value.entries()) {
    try {
      const { error } = await supabase
        .from('workstations')
        .update(updates)
        .eq('id', id)
      if (error) throw error
      saved++
    } catch (err) {
      console.error(`Failed to save station ${id}:`, err)
    }
  }

  // Save material changes
  for (const [id, updates] of materialChanges.value.entries()) {
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

  settingChanges.value = new Map()
  stationChanges.value = new Map()
  materialChanges.value = new Map()
  showStatus(`Saved ${saved} change${saved !== 1 ? 's' : ''}`, 'success')
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
  loadAll()
})
</script>

<template>
  <div class="settings-page">
    <!-- Status Message -->
    <div v-if="statusMessage" :class="['status-msg', statusType]">
      {{ statusMessage }}
    </div>

    <!-- Header -->
    <div class="header">
      <h1>Cost Settings</h1>
      <div class="header-actions">
        <span v-if="totalChanges > 0" class="changes-badge">{{ totalChanges }} unsaved</span>
        <button class="btn btn-primary" @click="saveAll" :disabled="totalChanges === 0">
          Save All Changes
        </button>
        <button class="btn btn-back" @click="goBack">
          <span class="back-arrow">&larr;</span> Back to MRP
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">Loading settings...</div>

    <template v-else>
      <!-- Section 1: Global Defaults -->
      <div class="section">
        <h2>Global Defaults</h2>
        <p class="section-desc">Fallback values used when stations or materials don't have specific rates set.</p>
        <table class="settings-table compact">
          <thead>
            <tr>
              <th>Setting</th>
              <th>Value</th>
              <th>Unit</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in costSettings"
              :key="s.id"
              :class="{ 'has-changes': settingChanges.has(s.id) }"
            >
              <td class="setting-name">{{ settingLabels[s.setting_key] || s.setting_key }}</td>
              <td>
                <input
                  type="number"
                  :value="s.setting_value"
                  step="0.01"
                  min="0"
                  class="value-input"
                  @change="trackSettingChange(s.id, ($event.target as HTMLInputElement).value)"
                />
              </td>
              <td class="unit-label">{{ settingUnits[s.setting_key] || '' }}</td>
              <td class="desc-col">{{ s.description }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Section 2: Workstation Rates -->
      <div class="section">
        <h2>Workstation Rates</h2>
        <p class="section-desc">Set hourly rates for in-house stations, or mark stations as outsourced with a default flat cost.</p>
        <table class="settings-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Station Name</th>
              <th>Outsourced</th>
              <th>Hourly Rate</th>
              <th>Outsource Default</th>
              <th>Effective Rate</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="ws in workstations"
              :key="ws.id"
              :class="{
                'has-changes': stationChanges.has(ws.id),
                'outsourced-row': ws.is_outsourced
              }"
            >
              <td class="station-code">{{ ws.station_code }}</td>
              <td>{{ ws.station_name }}</td>
              <td>
                <label class="toggle-label">
                  <input
                    type="checkbox"
                    :checked="ws.is_outsourced"
                    @change="trackStationChange(ws.id, 'is_outsourced', ($event.target as HTMLInputElement).checked)"
                  />
                  <span class="toggle-text">{{ ws.is_outsourced ? 'Yes' : 'No' }}</span>
                </label>
              </td>
              <td>
                <input
                  type="number"
                  :value="ws.hourly_rate ?? ''"
                  step="0.5"
                  min="0"
                  placeholder="default"
                  class="value-input"
                  :class="{ 'input-disabled': ws.is_outsourced }"
                  :disabled="ws.is_outsourced"
                  @change="trackStationChange(ws.id, 'hourly_rate', ($event.target as HTMLInputElement).value)"
                />
              </td>
              <td>
                <input
                  type="number"
                  :value="ws.outsourced_cost_default ?? ''"
                  step="0.5"
                  min="0"
                  placeholder="per part"
                  class="value-input"
                  :class="{ 'input-disabled': !ws.is_outsourced }"
                  :disabled="!ws.is_outsourced"
                  @change="trackStationChange(ws.id, 'outsourced_cost_default', ($event.target as HTMLInputElement).value)"
                />
              </td>
              <td class="effective-rate">
                <template v-if="ws.is_outsourced">
                  <span class="outsourced-badge">{{ ws.outsourced_cost_default != null ? `$${ws.outsourced_cost_default}/part` : 'per item' }}</span>
                </template>
                <template v-else>
                  {{ ws.hourly_rate != null ? `$${ws.hourly_rate}/hr` : '' }}
                  <span v-if="ws.hourly_rate == null" class="default-badge">${{ getDefaultRate() }}/hr</span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Section 3: Material Pricing -->
      <div class="section">
        <h2>Material Pricing</h2>
        <p class="section-desc">Set specific prices per raw material. Materials without a price use the global default.</p>
        <div class="material-filters">
          <input
            v-model="materialSearch"
            type="text"
            placeholder="Search by part number, material..."
            class="search-input"
          />
          <select v-model="materialTypeFilter">
            <option value="">All Types</option>
            <option value="SM">Sheet Metal</option>
            <option value="SQ">Square/Rect Tube</option>
            <option value="OT">Round Tube</option>
          </select>
        </div>
        <table class="settings-table">
          <thead>
            <tr>
              <th>Part Number</th>
              <th>Type</th>
              <th>Material</th>
              <th>Dimensions</th>
              <th>Price/Unit</th>
              <th>Unit</th>
              <th>Effective Price</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="m in filteredMaterials"
              :key="m.id"
              :class="{ 'has-changes': materialChanges.has(m.id) }"
            >
              <td>{{ m.part_number }}</td>
              <td>
                <span :class="['badge', `badge-${(m.material_type || '').toLowerCase()}`]">{{ m.material_type }}</span>
              </td>
              <td>
                <span :class="['badge', `badge-${(m.material_code || '').toLowerCase()}`]">{{ m.material_code }}</span>
              </td>
              <td>{{ getMaterialDimensions(m) }}</td>
              <td>
                <input
                  type="number"
                  :value="m.price_per_unit ?? ''"
                  step="0.01"
                  min="0"
                  placeholder="default"
                  class="value-input"
                  @change="trackMaterialChange(m.id, ($event.target as HTMLInputElement).value)"
                />
              </td>
              <td class="unit-label">{{ getPriceUnit(m) }}</td>
              <td class="effective-rate">
                <template v-if="m.price_per_unit != null">
                  ${{ m.price_per_unit }}{{ getPriceUnit(m).replace('$', '') }}
                </template>
                <template v-else>
                  <span class="default-badge">${{ getDefaultPrice(m) }}{{ getPriceUnit(m).replace('$', '') }}</span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.settings-page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.changes-badge {
  background: #92400e;
  color: #fde68a;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
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
  cursor: default;
}

.btn-primary {
  background: #1d4ed8;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1e40af;
}

.btn-back {
  background: #065f46;
  color: #6ee7b7;
}

.btn-back:hover {
  background: #064e3b;
}

.back-arrow {
  font-size: 16px;
}

.loading-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
  font-size: 14px;
}

/* Sections */
.section {
  margin-bottom: 32px;
}

h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 4px 0;
}

.section-desc {
  color: #9ca3af;
  font-size: 13px;
  margin: 0 0 12px 0;
}

/* Tables */
.settings-table {
  width: 100%;
  border-collapse: collapse;
  background: #0f172a;
  border-radius: 8px;
  overflow: hidden;
}

.settings-table.compact {
  max-width: 900px;
}

.settings-table th {
  background: #1e293b;
  padding: 10px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: #9ca3af;
}

.settings-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #1e293b;
  font-size: 13px;
}

.settings-table tr:hover {
  background: #020617;
}

.setting-name {
  font-weight: 500;
  color: #e5e7eb;
}

.desc-col {
  color: #9ca3af;
  font-size: 12px;
}

.station-code {
  font-family: monospace;
  font-weight: 600;
  color: #38bdf8;
}

/* Inputs */
.value-input {
  width: 100px;
  padding: 5px 8px;
  border-radius: 4px;
  border: 1px solid #1f2937;
  background: #020617;
  color: #e5e7eb;
  font-size: 13px;
}

.value-input::placeholder {
  color: #6b7280;
  font-style: italic;
}

.value-input:focus {
  border-color: #3b82f6;
  outline: none;
}

.input-disabled {
  opacity: 0.3;
  background: #0f172a;
}

.unit-label {
  color: #9ca3af;
  font-size: 12px;
  white-space: nowrap;
}

/* Toggle */
.toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.toggle-label input[type="checkbox"] {
  accent-color: #f59e0b;
  width: 16px;
  height: 16px;
}

.toggle-text {
  font-size: 12px;
  color: #9ca3af;
}

/* Badges */
.effective-rate {
  white-space: nowrap;
}

.default-badge {
  color: #9ca3af;
  font-style: italic;
  font-size: 12px;
}

.outsourced-badge {
  background: #92400e;
  color: #fde68a;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
}

.outsourced-row {
  background: rgba(146, 64, 14, 0.1);
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.badge-sq { background: #1e3a8a; color: #93c5fd; }
.badge-ot { background: #065f46; color: #6ee7b7; }
.badge-sm { background: #713f12; color: #fde68a; }
.badge-ss { background: #4c1d95; color: #ddd6fe; }
.badge-cs { background: #7f1d1d; color: #fca5a5; }

.has-changes {
  background: #1e3a5c !important;
}

/* Material Filters */
.material-filters {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.material-filters select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #1f2937;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 14px;
}

.search-input {
  flex: 1;
  max-width: 300px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #1f2937;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 14px;
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
