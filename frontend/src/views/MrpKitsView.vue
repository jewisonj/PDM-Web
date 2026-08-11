<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../services/supabase'

interface Project {
  id: string
  project_code: string
  description: string | null
}

interface Kit {
  id: string
  project_id: string
  kit_number: string
  kit_name: string
  vendor: string | null
  price: number
  use_kit: boolean
  notes: string | null
  created_at: string
  part_count?: number
  total_pieces?: number
}

interface KitItem {
  id: string
  kit_id: string
  item_id: string
  quantity: number
  unit_price: number | null
  notes: string | null
  item_number?: string
  description?: string
  material?: string
  thickness?: string
}

interface AvailableItem {
  id: string
  item_number: string
  name: string
  material: string | null
  thickness: string | null
}

const router = useRouter()

// State
const loading = ref(true)
const projects = ref<Project[]>([])
const selectedProjectId = ref('')
const kits = ref<Kit[]>([])
const selectedKit = ref<Kit | null>(null)
const kitItems = ref<KitItem[]>([])
const availableItems = ref<AvailableItem[]>([])

// Modal state
const showKitModal = ref(false)
const showAddPartsModal = ref(false)
const editingKit = ref<Partial<Kit>>({})
const selectedItemsToAdd = ref<Set<string>>(new Set())
const newItemQty = ref<Record<string, number>>({})
const newItemPrice = ref<Record<string, string>>({})

// Computed
const itemsNotInKit = computed(() => {
  const inKitIds = new Set(kitItems.value.map(ki => ki.item_id))
  return availableItems.value.filter(item => !inKitIds.has(item.id))
})

const kitTotalFromItems = computed(() => {
  return kitItems.value.reduce((sum, ki) => {
    const price = ki.unit_price || 0
    return sum + (price * ki.quantity)
  }, 0)
})

// Methods
async function loadProjects() {
  const { data, error } = await supabase
    .from('mrp_projects')
    .select('id, project_code, description')
    .order('project_code')

  if (error) {
    console.error('Failed to load projects:', error)
    return
  }
  projects.value = data || []
}

async function loadKits() {
  if (!selectedProjectId.value) {
    kits.value = []
    return
  }

  loading.value = true

  // Load kits with part counts
  const { data, error } = await supabase
    .from('project_kits')
    .select(`
      *,
      kit_items (
        quantity
      )
    `)
    .eq('project_id', selectedProjectId.value)
    .order('kit_number')

  if (error) {
    console.error('Failed to load kits:', error)
    loading.value = false
    return
  }

  kits.value = (data || []).map(k => ({
    ...k,
    part_count: k.kit_items?.length || 0,
    total_pieces: k.kit_items?.reduce((sum: number, ki: any) => sum + (ki.quantity || 0), 0) || 0
  }))

  loading.value = false
}

async function loadKitItems(kitId: string) {
  const { data, error } = await supabase
    .from('kit_items')
    .select(`
      *,
      items (
        item_number,
        description,
        material,
        thickness
      )
    `)
    .eq('kit_id', kitId)
    .order('items(item_number)')

  if (error) {
    console.error('Failed to load kit items:', error)
    return
  }

  kitItems.value = (data || []).map(ki => ({
    ...ki,
    item_number: ki.items?.item_number,
    description: ki.items?.description,
    material: ki.items?.material,
    thickness: ki.items?.thickness
  }))
}

async function loadAvailableItems() {
  if (!selectedProjectId.value) return

  // Get items from mrp_project_parts for this project
  const { data, error } = await supabase
    .from('mrp_project_parts')
    .select(`
      items (
        id,
        item_number,
        name,
        material,
        thickness
      )
    `)
    .eq('project_id', selectedProjectId.value)

  if (error) {
    console.error('Failed to load available items:', error)
    return
  }

  const items: AvailableItem[] = []
  for (const p of data || []) {
    const item = p.items as any
    if (item && item.id) {
      items.push({
        id: item.id,
        item_number: item.item_number,
        name: item.name,
        material: item.material,
        thickness: item.thickness
      })
    }
  }
  items.sort((a, b) => a.item_number.localeCompare(b.item_number))
  availableItems.value = items
}

async function selectKit(kit: Kit) {
  selectedKit.value = kit
  await loadKitItems(kit.id)
}

function openNewKitModal() {
  editingKit.value = {
    kit_number: '',
    kit_name: '',
    vendor: '',
    price: 0,
    use_kit: false,
    notes: ''
  }
  showKitModal.value = true
}

function openEditKitModal(kit: Kit) {
  editingKit.value = { ...kit }
  showKitModal.value = true
}

async function saveKit() {
  if (!selectedProjectId.value) return

  const kitData = {
    project_id: selectedProjectId.value,
    kit_number: editingKit.value.kit_number,
    kit_name: editingKit.value.kit_name,
    vendor: editingKit.value.vendor || null,
    price: editingKit.value.price || 0,
    use_kit: editingKit.value.use_kit || false,
    notes: editingKit.value.notes || null
  }

  if (editingKit.value.id) {
    // Update
    const { error } = await supabase
      .from('project_kits')
      .update(kitData)
      .eq('id', editingKit.value.id)

    if (error) {
      console.error('Failed to update kit:', error)
      alert('Failed to update kit: ' + error.message)
      return
    }
  } else {
    // Insert
    const { error } = await supabase
      .from('project_kits')
      .insert(kitData)

    if (error) {
      console.error('Failed to create kit:', error)
      alert('Failed to create kit: ' + error.message)
      return
    }
  }

  showKitModal.value = false
  await loadKits()
}

async function deleteKit(kit: Kit) {
  if (!confirm(`Delete kit "${kit.kit_number}"? This will remove all part assignments.`)) return

  const { error } = await supabase
    .from('project_kits')
    .delete()
    .eq('id', kit.id)

  if (error) {
    console.error('Failed to delete kit:', error)
    alert('Failed to delete kit: ' + error.message)
    return
  }

  if (selectedKit.value?.id === kit.id) {
    selectedKit.value = null
    kitItems.value = []
  }
  await loadKits()
}

async function setActiveKit(kit: Kit) {
  // First, set all other kits to use_kit = false
  await supabase
    .from('project_kits')
    .update({ use_kit: false })
    .eq('project_id', selectedProjectId.value)

  // Then set this kit to use_kit = true
  await supabase
    .from('project_kits')
    .update({ use_kit: true })
    .eq('id', kit.id)

  await loadKits()
}

function openAddPartsModal() {
  selectedItemsToAdd.value = new Set()
  newItemQty.value = {}
  newItemPrice.value = {}
  showAddPartsModal.value = true
}

function toggleItemSelection(itemId: string) {
  if (selectedItemsToAdd.value.has(itemId)) {
    selectedItemsToAdd.value.delete(itemId)
  } else {
    selectedItemsToAdd.value.add(itemId)
    newItemQty.value[itemId] = 1
    newItemPrice.value[itemId] = ''
  }
  // Trigger reactivity
  selectedItemsToAdd.value = new Set(selectedItemsToAdd.value)
}

async function addSelectedParts() {
  if (!selectedKit.value || selectedItemsToAdd.value.size === 0) return

  const inserts = Array.from(selectedItemsToAdd.value).map(itemId => ({
    kit_id: selectedKit.value!.id,
    item_id: itemId,
    quantity: newItemQty.value[itemId] || 1,
    unit_price: newItemPrice.value[itemId] ? parseFloat(newItemPrice.value[itemId]) : null
  }))

  const { error } = await supabase
    .from('kit_items')
    .insert(inserts)

  if (error) {
    console.error('Failed to add parts:', error)
    alert('Failed to add parts: ' + error.message)
    return
  }

  showAddPartsModal.value = false
  await loadKitItems(selectedKit.value.id)
  await loadKits()
}

async function removeKitItem(kitItem: KitItem) {
  if (!confirm(`Remove ${kitItem.item_number} from this kit?`)) return

  const { error } = await supabase
    .from('kit_items')
    .delete()
    .eq('id', kitItem.id)

  if (error) {
    console.error('Failed to remove item:', error)
    return
  }

  if (selectedKit.value) {
    await loadKitItems(selectedKit.value.id)
    await loadKits()
  }
}

async function updateKitItemQty(kitItem: KitItem, newQty: number) {
  const { error } = await supabase
    .from('kit_items')
    .update({ quantity: newQty })
    .eq('id', kitItem.id)

  if (error) {
    console.error('Failed to update quantity:', error)
    return
  }

  kitItem.quantity = newQty
  await loadKits()
}

async function updateKitItemPrice(kitItem: KitItem, newPrice: string) {
  const price = newPrice ? parseFloat(newPrice) : null
  const { error } = await supabase
    .from('kit_items')
    .update({ unit_price: price })
    .eq('id', kitItem.id)

  if (error) {
    console.error('Failed to update price:', error)
    return
  }

  kitItem.unit_price = price
}

function formatPrice(price: number | null): string {
  if (price === null || price === undefined) return '-'
  return '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function goToDashboard() {
  router.push('/mrp/dashboard')
}

// Watchers
watch(selectedProjectId, async () => {
  selectedKit.value = null
  kitItems.value = []
  await loadKits()
  await loadAvailableItems()
})

onMounted(async () => {
  await loadProjects()
  loading.value = false
})
</script>

<template>
  <div class="kits-page">
    <!-- Header -->
    <div class="header">
      <h1>Kit Management</h1>
      <div class="header-actions">
        <select v-model="selectedProjectId">
          <option value="">-- Select Project --</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">
            {{ p.project_code }} - {{ p.description || '' }}
          </option>
        </select>
        <button v-if="selectedProjectId" class="btn btn-primary" @click="openNewKitModal">
          + New Kit
        </button>
        <button class="btn btn-secondary" @click="goToDashboard">
          &larr; Dashboard
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="content">
      <div v-if="!selectedProjectId" class="no-selection">
        Select a project to manage kits
      </div>

      <div v-else-if="loading" class="loading">
        Loading...
      </div>

      <div v-else class="main-layout">
        <!-- Kits List -->
        <div class="kits-panel">
          <h2>Vendor Kits</h2>
          <div v-if="kits.length === 0" class="empty-state">
            No kits defined. Create one to get started.
          </div>
          <div
            v-for="kit in kits"
            :key="kit.id"
            :class="['kit-card', { selected: selectedKit?.id === kit.id, active: kit.use_kit }]"
            @click="selectKit(kit)"
          >
            <div class="kit-header">
              <div class="kit-number">{{ kit.kit_number }}</div>
              <div v-if="kit.use_kit" class="active-badge">ACTIVE</div>
            </div>
            <div class="kit-name">{{ kit.kit_name }}</div>
            <div class="kit-vendor">{{ kit.vendor || 'No vendor' }}</div>
            <div class="kit-stats">
              <span>{{ kit.part_count }} parts</span>
              <span>{{ kit.total_pieces }} pcs</span>
              <span class="kit-price">{{ formatPrice(kit.price) }}</span>
            </div>
            <div class="kit-actions">
              <button class="btn-icon" @click.stop="openEditKitModal(kit)" title="Edit">
                &#9998;
              </button>
              <button
                v-if="!kit.use_kit"
                class="btn-icon"
                @click.stop="setActiveKit(kit)"
                title="Set as Active"
              >
                &#10003;
              </button>
              <button class="btn-icon danger" @click.stop="deleteKit(kit)" title="Delete">
                &#10005;
              </button>
            </div>
          </div>
        </div>

        <!-- Kit Details -->
        <div class="details-panel">
          <div v-if="!selectedKit" class="no-selection">
            Select a kit to view parts
          </div>
          <template v-else>
            <div class="details-header">
              <div>
                <h2>{{ selectedKit.kit_number }} - {{ selectedKit.kit_name }}</h2>
                <div class="details-meta">
                  <span>Vendor: {{ selectedKit.vendor || 'N/A' }}</span>
                  <span>Kit Price: {{ formatPrice(selectedKit.price) }}</span>
                  <span>Calculated Total: {{ formatPrice(kitTotalFromItems) }}</span>
                </div>
              </div>
              <button class="btn btn-primary" @click="openAddPartsModal">
                + Add Parts
              </button>
            </div>

            <div v-if="selectedKit.notes" class="kit-notes">
              <strong>Notes:</strong>
              <pre>{{ selectedKit.notes }}</pre>
            </div>

            <table class="parts-table">
              <thead>
                <tr>
                  <th>Part Number</th>
                  <th>Description</th>
                  <th>Material</th>
                  <th>Thickness</th>
                  <th>Qty</th>
                  <th>Unit Price</th>
                  <th>Line Total</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in kitItems" :key="item.id">
                  <td class="part-number">{{ item.item_number }}</td>
                  <td>{{ item.description || '-' }}</td>
                  <td>{{ item.material || '-' }}</td>
                  <td>{{ item.thickness || '-' }}</td>
                  <td>
                    <input
                      type="number"
                      :value="item.quantity"
                      min="1"
                      class="qty-input"
                      @change="updateKitItemQty(item, parseInt(($event.target as HTMLInputElement).value))"
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      :value="item.unit_price || ''"
                      step="0.01"
                      class="price-input"
                      placeholder="-"
                      @change="updateKitItemPrice(item, ($event.target as HTMLInputElement).value)"
                    />
                  </td>
                  <td>{{ item.unit_price ? formatPrice(item.unit_price * item.quantity) : '-' }}</td>
                  <td>
                    <button class="btn-icon danger" @click="removeKitItem(item)" title="Remove">
                      &#10005;
                    </button>
                  </td>
                </tr>
                <tr v-if="kitItems.length === 0">
                  <td colspan="8" class="empty-row">No parts in this kit</td>
                </tr>
              </tbody>
              <tfoot v-if="kitItems.length > 0">
                <tr>
                  <td colspan="5"></td>
                  <td><strong>Total:</strong></td>
                  <td><strong>{{ formatPrice(kitTotalFromItems) }}</strong></td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </template>
        </div>
      </div>
    </div>

    <!-- Kit Modal -->
    <div v-if="showKitModal" class="modal-overlay" @click.self="showKitModal = false">
      <div class="modal">
        <h3>{{ editingKit.id ? 'Edit Kit' : 'New Kit' }}</h3>
        <div class="form-group">
          <label>Kit Number</label>
          <input v-model="editingKit.kit_number" type="text" placeholder="e.g., KIT-001" />
        </div>
        <div class="form-group">
          <label>Kit Name</label>
          <input v-model="editingKit.kit_name" type="text" placeholder="e.g., PTL Tube Kit" />
        </div>
        <div class="form-group">
          <label>Vendor</label>
          <input v-model="editingKit.vendor" type="text" placeholder="e.g., Precision Tube Laser" />
        </div>
        <div class="form-group">
          <label>Kit Price (per unit)</label>
          <input v-model.number="editingKit.price" type="number" step="0.01" />
        </div>
        <div class="form-group">
          <label>Notes</label>
          <textarea v-model="editingKit.notes" rows="4" placeholder="Quote number, lead time, etc."></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showKitModal = false">Cancel</button>
          <button class="btn btn-primary" @click="saveKit">Save</button>
        </div>
      </div>
    </div>

    <!-- Add Parts Modal -->
    <div v-if="showAddPartsModal" class="modal-overlay" @click.self="showAddPartsModal = false">
      <div class="modal modal-wide">
        <h3>Add Parts to {{ selectedKit?.kit_number }}</h3>
        <div class="parts-list">
          <div v-if="itemsNotInKit.length === 0" class="empty-state">
            All project parts are already in this kit
          </div>
          <div
            v-for="item in itemsNotInKit"
            :key="item.id"
            :class="['part-row', { selected: selectedItemsToAdd.has(item.id) }]"
            @click="toggleItemSelection(item.id)"
          >
            <input
              type="checkbox"
              :checked="selectedItemsToAdd.has(item.id)"
              @click.stop
              @change="toggleItemSelection(item.id)"
            />
            <span class="part-number">{{ item.item_number }}</span>
            <span class="part-name">{{ item.name }}</span>
            <span class="part-material">{{ item.material || '-' }}</span>
            <template v-if="selectedItemsToAdd.has(item.id)">
              <input
                type="number"
                v-model.number="newItemQty[item.id]"
                min="1"
                class="qty-input"
                placeholder="Qty"
                @click.stop
              />
              <input
                type="number"
                v-model="newItemPrice[item.id]"
                step="0.01"
                class="price-input"
                placeholder="Unit $"
                @click.stop
              />
            </template>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showAddPartsModal = false">Cancel</button>
          <button
            class="btn btn-primary"
            :disabled="selectedItemsToAdd.size === 0"
            @click="addSelectedParts"
          >
            Add {{ selectedItemsToAdd.size }} Part(s)
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kits-page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
}

.header h1 {
  margin: 0;
  font-size: 20px;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.btn-primary {
  background: #2563eb;
  color: white;
}

.btn-primary:hover {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #374151;
  cursor: not-allowed;
}

.btn-secondary {
  background: #374151;
  color: white;
}

.btn-secondary:hover {
  background: #4b5563;
}

.btn-icon {
  background: none;
  border: none;
  color: #9ca3af;
  cursor: pointer;
  padding: 4px 8px;
  font-size: 14px;
}

.btn-icon:hover {
  color: #e5e7eb;
}

.btn-icon.danger:hover {
  color: #ef4444;
}

select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #334155;
  background: #1e293b;
  color: #e5e7eb;
  font-size: 13px;
  min-width: 200px;
}

.content {
  padding: 24px;
}

.no-selection,
.loading,
.empty-state {
  text-align: center;
  padding: 40px;
  color: #6b7280;
}

.main-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 24px;
}

.kits-panel {
  background: #0f172a;
  border-radius: 8px;
  padding: 16px;
}

.kits-panel h2 {
  margin: 0 0 16px 0;
  font-size: 14px;
  color: #9ca3af;
  text-transform: uppercase;
}

.kit-card {
  background: #1e293b;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: border-color 0.15s;
}

.kit-card:hover {
  border-color: #334155;
}

.kit-card.selected {
  border-color: #2563eb;
}

.kit-card.active {
  background: #1e3a5f;
}

.kit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.kit-number {
  font-weight: 600;
  font-size: 15px;
}

.active-badge {
  background: #059669;
  color: white;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.kit-name {
  font-size: 13px;
  color: #e5e7eb;
}

.kit-vendor {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 8px;
}

.kit-stats {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #9ca3af;
}

.kit-price {
  color: #34d399;
  font-weight: 500;
}

.kit-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #334155;
}

.details-panel {
  background: #0f172a;
  border-radius: 8px;
  padding: 16px;
}

.details-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.details-header h2 {
  margin: 0 0 4px 0;
  font-size: 18px;
}

.details-meta {
  display: flex;
  gap: 16px;
  font-size: 13px;
  color: #9ca3af;
}

.kit-notes {
  background: #1e293b;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 13px;
}

.kit-notes pre {
  margin: 8px 0 0 0;
  white-space: pre-wrap;
  font-family: inherit;
  color: #9ca3af;
}

.parts-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.parts-table th,
.parts-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid #1e293b;
}

.parts-table th {
  background: #1e293b;
  color: #9ca3af;
  font-weight: 500;
  font-size: 11px;
  text-transform: uppercase;
}

.parts-table .part-number {
  font-family: monospace;
  font-weight: 500;
}

.parts-table .empty-row {
  text-align: center;
  color: #6b7280;
  padding: 24px;
}

.parts-table tfoot td {
  border-top: 2px solid #334155;
  border-bottom: none;
}

.qty-input,
.price-input {
  width: 70px;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid #334155;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 13px;
}

.price-input {
  width: 80px;
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
  background: #1e293b;
  border-radius: 12px;
  padding: 24px;
  width: 400px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-wide {
  width: 700px;
}

.modal h3 {
  margin: 0 0 20px 0;
  font-size: 18px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: #9ca3af;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #334155;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 14px;
  box-sizing: border-box;
}

.form-group textarea {
  resize: vertical;
  font-family: inherit;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 20px;
}

.parts-list {
  max-height: 400px;
  overflow-y: auto;
  margin-bottom: 16px;
}

.part-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  border-radius: 6px;
  cursor: pointer;
  background: #0f172a;
  margin-bottom: 6px;
}

.part-row:hover {
  background: #1e3a5f;
}

.part-row.selected {
  background: #1e3a5f;
  border: 1px solid #2563eb;
}

.part-row .part-number {
  font-family: monospace;
  font-weight: 500;
  min-width: 100px;
}

.part-row .part-name {
  flex: 1;
  color: #9ca3af;
}

.part-row .part-material {
  color: #6b7280;
  font-size: 12px;
  min-width: 60px;
}

.part-row input[type="checkbox"] {
  width: 18px;
  height: 18px;
}
</style>
