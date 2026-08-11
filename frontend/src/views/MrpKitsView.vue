<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { supabase } from '../services/supabase'

interface Project {
  id: string
  project_code: string
  description: string | null
}

interface Kit {
  id: string
  kit_number: string
  kit_name: string
  vendor: string | null
  price: number
  notes: string | null
  created_at: string
  part_count?: number
  total_pieces?: number
  items_total?: number
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

interface KitUsage {
  id: string
  project_id: string
  kit_id: string
  is_active: boolean
  project_code?: string
}

interface AvailableItem {
  id: string
  item_number: string
  name: string
  material: string | null
  thickness: string | null
}

const router = useRouter()
const route = useRoute()

// State
const loading = ref(true)
const kits = ref<Kit[]>([])
const selectedKit = ref<Kit | null>(null)
const kitItems = ref<KitItem[]>([])
const kitUsages = ref<KitUsage[]>([])
const projects = ref<Project[]>([])
const allItems = ref<AvailableItem[]>([])

// Modal state
const showKitModal = ref(false)
const showAddPartsModal = ref(false)
const showLinkProjectModal = ref(false)
const editingKit = ref<Partial<Kit>>({})
const selectedItemsToAdd = ref<Set<string>>(new Set())
const newItemQty = ref<Record<string, number>>({})
const newItemPrice = ref<Record<string, string>>({})
const selectedProjectToLink = ref('')

// Computed
const itemsNotInKit = computed(() => {
  const inKitIds = new Set(kitItems.value.map(ki => ki.item_id))
  let items = allItems.value.filter(item => !inKitIds.has(item.id))

  // If filtering by project, only show items from that project
  // For now, show all items
  return items
})

const kitTotalFromItems = computed(() => {
  return kitItems.value.reduce((sum, ki) => {
    const price = ki.unit_price || 0
    return sum + (price * ki.quantity)
  }, 0)
})

const projectsNotLinked = computed(() => {
  const linkedProjectIds = new Set(kitUsages.value.map(ku => ku.project_id))
  return projects.value.filter(p => !linkedProjectIds.has(p.id))
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

async function loadAllItems() {
  // Load all items for adding to kits
  const { data, error } = await supabase
    .from('items')
    .select('id, item_number, name, material, thickness')
    .order('item_number')
    .limit(1000)

  if (error) {
    console.error('Failed to load items:', error)
    return
  }
  allItems.value = data || []
}

async function loadKits() {
  loading.value = true

  // Load all kits (global, not project-specific)
  const { data, error } = await supabase
    .from('project_kits')
    .select(`
      *,
      kit_items (
        quantity,
        unit_price
      )
    `)
    .order('kit_number')

  if (error) {
    console.error('Failed to load kits:', error)
    loading.value = false
    return
  }

  kits.value = (data || []).map(k => {
    const items = k.kit_items || []
    return {
      ...k,
      part_count: items.length,
      total_pieces: items.reduce((sum: number, ki: any) => sum + (ki.quantity || 0), 0),
      items_total: items.reduce((sum: number, ki: any) => {
        const price = ki.unit_price || 0
        const qty = ki.quantity || 1
        return sum + (price * qty)
      }, 0)
    }
  })

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

async function loadKitUsages(kitId: string) {
  const { data, error } = await supabase
    .from('project_kit_usage')
    .select(`
      *,
      mrp_projects (
        project_code
      )
    `)
    .eq('kit_id', kitId)

  if (error) {
    console.error('Failed to load kit usages:', error)
    return
  }

  kitUsages.value = (data || []).map(ku => ({
    ...ku,
    project_code: ku.mrp_projects?.project_code
  }))
}

async function selectKit(kit: Kit) {
  selectedKit.value = kit
  await Promise.all([
    loadKitItems(kit.id),
    loadKitUsages(kit.id)
  ])
}

function openNewKitModal() {
  editingKit.value = {
    kit_number: '',
    kit_name: '',
    vendor: '',
    price: 0,
    notes: ''
  }
  showKitModal.value = true
}

function openEditKitModal(kit: Kit) {
  editingKit.value = { ...kit }
  showKitModal.value = true
}

async function saveKit() {
  const kitData = {
    kit_number: editingKit.value.kit_number,
    kit_name: editingKit.value.kit_name,
    vendor: editingKit.value.vendor || null,
    price: editingKit.value.price || 0,
    notes: editingKit.value.notes || null,
    project_id: null,  // Global kit
    use_kit: false     // Deprecated field, use project_kit_usage instead
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

  // Refresh selected kit if it was edited
  if (selectedKit.value && editingKit.value.id === selectedKit.value.id) {
    const updated = kits.value.find(k => k.id === selectedKit.value!.id)
    if (updated) selectedKit.value = updated
  }
}

async function deleteKit(kit: Kit) {
  if (!confirm(`Delete kit "${kit.kit_number}"? This will remove all part assignments and project links.`)) return

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
    kitUsages.value = []
  }
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
  await loadKits()
}

function openLinkProjectModal() {
  selectedProjectToLink.value = ''
  showLinkProjectModal.value = true
}

async function linkProject() {
  if (!selectedKit.value || !selectedProjectToLink.value) return

  const { error } = await supabase
    .from('project_kit_usage')
    .insert({
      project_id: selectedProjectToLink.value,
      kit_id: selectedKit.value.id,
      is_active: false
    })

  if (error) {
    console.error('Failed to link project:', error)
    alert('Failed to link project: ' + error.message)
    return
  }

  showLinkProjectModal.value = false
  await loadKitUsages(selectedKit.value.id)
}

async function unlinkProject(usage: KitUsage) {
  if (!confirm(`Unlink this kit from project ${usage.project_code}?`)) return

  const { error } = await supabase
    .from('project_kit_usage')
    .delete()
    .eq('id', usage.id)

  if (error) {
    console.error('Failed to unlink project:', error)
    return
  }

  if (selectedKit.value) {
    await loadKitUsages(selectedKit.value.id)
  }
}

async function toggleKitActive(usage: KitUsage) {
  const newActive = !usage.is_active

  const { error } = await supabase
    .from('project_kit_usage')
    .update({ is_active: newActive })
    .eq('id', usage.id)

  if (error) {
    console.error('Failed to toggle active:', error)
    return
  }

  usage.is_active = newActive
}

function formatPrice(price: number | null | undefined): string {
  if (price === null || price === undefined) return '-'
  return '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function goToDashboard() {
  router.push('/mrp/dashboard')
}

onMounted(async () => {
  await Promise.all([
    loadProjects(),
    loadKits(),
    loadAllItems()
  ])
  loading.value = false

  // If kit ID in URL, select it
  const kitId = route.query.kit as string
  if (kitId) {
    const kit = kits.value.find(k => k.id === kitId)
    if (kit) selectKit(kit)
  }
})
</script>

<template>
  <div class="kits-page">
    <!-- Header -->
    <div class="header">
      <h1>Vendor Kit Management</h1>
      <div class="header-actions">
        <button class="btn btn-primary" @click="openNewKitModal">
          + New Kit
        </button>
        <button class="btn btn-secondary" @click="goToDashboard">
          &larr; Dashboard
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="content">
      <div v-if="loading" class="loading">
        Loading...
      </div>

      <div v-else class="main-layout">
        <!-- Kits List -->
        <div class="kits-panel">
          <h2>Vendor Kits (Global)</h2>
          <div v-if="kits.length === 0" class="empty-state">
            No kits defined. Create one to get started.
          </div>
          <div
            v-for="kit in kits"
            :key="kit.id"
            :class="['kit-card', { selected: selectedKit?.id === kit.id }]"
            @click="selectKit(kit)"
          >
            <div class="kit-header">
              <div class="kit-number">{{ kit.kit_number }}</div>
            </div>
            <div class="kit-name">{{ kit.kit_name }}</div>
            <div class="kit-vendor">{{ kit.vendor || 'No vendor' }}</div>
            <div class="kit-stats">
              <span>{{ kit.part_count }} parts</span>
              <span>{{ kit.total_pieces }} pcs</span>
            </div>
            <div class="kit-pricing">
              <div v-if="kit.price > 0" class="bundle-price">
                <span class="label">Bundle:</span>
                <span class="price">{{ formatPrice(kit.price) }}</span>
              </div>
              <div v-if="kit.items_total && kit.items_total > 0" class="items-price">
                <span class="label">Items:</span>
                <span class="price">{{ formatPrice(kit.items_total) }}</span>
              </div>
            </div>
            <div class="kit-actions">
              <button class="btn-icon" @click.stop="openEditKitModal(kit)" title="Edit">
                &#9998;
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
            Select a kit to view details
          </div>
          <template v-else>
            <div class="details-header">
              <div>
                <h2>{{ selectedKit.kit_number }} - {{ selectedKit.kit_name }}</h2>
                <div class="details-meta">
                  <span>Vendor: {{ selectedKit.vendor || 'N/A' }}</span>
                </div>
              </div>
              <div class="header-buttons">
                <button class="btn btn-secondary" @click="openEditKitModal(selectedKit)">
                  Edit Kit
                </button>
                <button class="btn btn-primary" @click="openAddPartsModal">
                  + Add Parts
                </button>
              </div>
            </div>

            <!-- Prominent Price Section -->
            <div class="price-section">
              <div class="price-box bundle">
                <div class="price-label">Kit Bundle Price</div>
                <div class="price-value">{{ formatPrice(selectedKit.price) }}</div>
                <div class="price-note">Use this for vendor quotes with fixed total</div>
              </div>
              <div class="price-box calculated">
                <div class="price-label">Calculated from Items</div>
                <div class="price-value">{{ formatPrice(kitTotalFromItems) }}</div>
                <div class="price-note">Sum of (unit price x qty) for all parts</div>
              </div>
              <div class="price-box effective">
                <div class="price-label">Effective Price</div>
                <div class="price-value highlight">
                  {{ formatPrice(selectedKit.price > 0 ? selectedKit.price : kitTotalFromItems) }}
                </div>
                <div class="price-note">Bundle price used if set, otherwise items total</div>
              </div>
            </div>

            <!-- Project Usage Section -->
            <div class="usage-section">
              <div class="section-header">
                <h3>Project Usage</h3>
                <button class="btn btn-sm" @click="openLinkProjectModal">
                  + Link to Project
                </button>
              </div>
              <div v-if="kitUsages.length === 0" class="empty-state small">
                Not linked to any projects
              </div>
              <div v-else class="usage-list">
                <div v-for="usage in kitUsages" :key="usage.id" class="usage-item">
                  <span class="project-code">{{ usage.project_code }}</span>
                  <label class="active-toggle">
                    <input
                      type="checkbox"
                      :checked="usage.is_active"
                      @change="toggleKitActive(usage)"
                    />
                    <span>Active</span>
                  </label>
                  <button class="btn-icon danger" @click="unlinkProject(usage)" title="Unlink">
                    &#10005;
                  </button>
                </div>
              </div>
            </div>

            <div v-if="selectedKit.notes" class="kit-notes">
              <strong>Notes:</strong>
              <pre>{{ selectedKit.notes }}</pre>
            </div>

            <!-- Parts Table -->
            <h3 class="section-title">Parts in Kit</h3>
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
                      :value="item.unit_price ?? ''"
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
          <input v-model="editingKit.kit_number" type="text" placeholder="e.g., KIT-001_PTL" />
        </div>
        <div class="form-group">
          <label>Kit Name</label>
          <input v-model="editingKit.kit_name" type="text" placeholder="e.g., PTL Tube & Sheet Kit" />
        </div>
        <div class="form-group">
          <label>Vendor</label>
          <input v-model="editingKit.vendor" type="text" placeholder="e.g., Precision Tube Laser" />
        </div>
        <div class="form-group highlight">
          <label>Bundle Price (Total for all parts)</label>
          <input v-model.number="editingKit.price" type="number" step="0.01" placeholder="0.00" />
          <div class="form-hint">
            Enter the vendor's total quoted price for all parts in this kit.
            If individual part prices are entered, leave this at 0 to use calculated total.
          </div>
        </div>
        <div class="form-group">
          <label>Notes</label>
          <textarea v-model="editingKit.notes" rows="4" placeholder="Quote number, lead time, special terms..."></textarea>
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
            All parts are already in this kit
          </div>
          <div
            v-for="item in itemsNotInKit.slice(0, 100)"
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
          <div v-if="itemsNotInKit.length > 100" class="more-items">
            Showing first 100 items. {{ itemsNotInKit.length - 100 }} more available.
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

    <!-- Link Project Modal -->
    <div v-if="showLinkProjectModal" class="modal-overlay" @click.self="showLinkProjectModal = false">
      <div class="modal">
        <h3>Link Kit to Project</h3>
        <div class="form-group">
          <label>Select Project</label>
          <select v-model="selectedProjectToLink">
            <option value="">-- Select --</option>
            <option v-for="p in projectsNotLinked" :key="p.id" :value="p.id">
              {{ p.project_code }} - {{ p.description || '' }}
            </option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="showLinkProjectModal = false">Cancel</button>
          <button
            class="btn btn-primary"
            :disabled="!selectedProjectToLink"
            @click="linkProject"
          >
            Link
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

.btn-sm {
  padding: 4px 10px;
  font-size: 12px;
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

.empty-state.small {
  padding: 16px;
  font-size: 13px;
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
  max-height: calc(100vh - 150px);
  overflow-y: auto;
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
  margin-bottom: 6px;
}

.kit-pricing {
  display: flex;
  gap: 16px;
  font-size: 12px;
  margin-bottom: 8px;
}

.kit-pricing .label {
  color: #6b7280;
}

.kit-pricing .price {
  color: #34d399;
  font-weight: 500;
}

.kit-actions {
  display: flex;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px solid #334155;
}

.details-panel {
  background: #0f172a;
  border-radius: 8px;
  padding: 16px;
  max-height: calc(100vh - 150px);
  overflow-y: auto;
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
  font-size: 13px;
  color: #9ca3af;
}

.header-buttons {
  display: flex;
  gap: 8px;
}

/* Price Section */
.price-section {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.price-box {
  background: #1e293b;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}

.price-box.bundle {
  border-left: 4px solid #f97316;
}

.price-box.calculated {
  border-left: 4px solid #3b82f6;
}

.price-box.effective {
  border-left: 4px solid #22c55e;
}

.price-label {
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.price-value {
  font-size: 24px;
  font-weight: 600;
  color: #e5e7eb;
}

.price-value.highlight {
  color: #34d399;
}

.price-note {
  font-size: 11px;
  color: #6b7280;
  margin-top: 8px;
}

/* Usage Section */
.usage-section {
  background: #1e293b;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 14px;
  color: #e5e7eb;
}

.usage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.usage-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #0f172a;
  border-radius: 6px;
}

.project-code {
  font-weight: 500;
  flex: 1;
}

.active-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #9ca3af;
  cursor: pointer;
}

.active-toggle input:checked + span {
  color: #34d399;
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

.section-title {
  font-size: 14px;
  color: #e5e7eb;
  margin: 0 0 12px 0;
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
  width: 450px;
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

.form-group.highlight {
  background: #0f172a;
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid #f97316;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: #9ca3af;
}

.form-group input,
.form-group textarea,
.form-group select {
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

.form-hint {
  font-size: 11px;
  color: #6b7280;
  margin-top: 6px;
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

.more-items {
  text-align: center;
  color: #6b7280;
  font-size: 12px;
  padding: 12px;
}
</style>
