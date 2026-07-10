<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'

interface Kit {
  id: string
  kit_number: string
  kit_name: string
  vendor: string | null
  price: number
  use_kit: boolean
  notes: string | null
  part_count?: number
  inhouse_cost?: number
  savings?: number
  savings_percent?: number
}

interface KitPart {
  item_id: string
  item_number: string
  name: string
}

const props = defineProps<{
  projectId: string
  projectCode: string
}>()

const emit = defineEmits<{
  close: []
  updated: []
}>()

const loading = ref(true)
const saving = ref(false)
const kits = ref<Kit[]>([])
const selectedKitId = ref<string | null>(null)
const selectedKitParts = ref<KitPart[]>([])
const loadingParts = ref(false)
const showAddForm = ref(false)
const editingKit = ref<Kit | null>(null)

// Form fields for add/edit
const formKitNumber = ref('')
const formKitName = ref('')
const formVendor = ref('')
const formPrice = ref<number>(0)
const formNotes = ref('')

async function loadKits() {
  loading.value = true
  try {
    const response = await fetch(`/api/mrp/projects/${props.projectId}/kits`)
    if (response.ok) {
      kits.value = await response.json()
    }
  } catch (error) {
    console.error('Failed to load kits:', error)
  } finally {
    loading.value = false
  }
}

async function loadKitParts(kitId: string) {
  loadingParts.value = true
  try {
    const response = await fetch(`/api/mrp/projects/${props.projectId}/kits/${kitId}`)
    if (response.ok) {
      const data = await response.json()
      selectedKitParts.value = data.parts || []
    }
  } catch (error) {
    console.error('Failed to load kit parts:', error)
  } finally {
    loadingParts.value = false
  }
}

watch(selectedKitId, (newId) => {
  if (newId) {
    loadKitParts(newId)
  } else {
    selectedKitParts.value = []
  }
})

function openAddForm() {
  editingKit.value = null
  formKitNumber.value = `KIT-${String(kits.value.length + 1).padStart(3, '0')}`
  formKitName.value = ''
  formVendor.value = ''
  formPrice.value = 0
  formNotes.value = ''
  showAddForm.value = true
}

function openEditForm(kit: Kit) {
  editingKit.value = kit
  formKitNumber.value = kit.kit_number
  formKitName.value = kit.kit_name
  formVendor.value = kit.vendor || ''
  formPrice.value = kit.price
  formNotes.value = kit.notes || ''
  showAddForm.value = true
}

function cancelForm() {
  showAddForm.value = false
  editingKit.value = null
}

async function saveKit() {
  saving.value = true
  try {
    const body = {
      kit_number: formKitNumber.value,
      kit_name: formKitName.value,
      vendor: formVendor.value || null,
      price: formPrice.value,
      notes: formNotes.value || null,
    }

    let response: Response
    if (editingKit.value) {
      response = await fetch(`/api/mrp/projects/${props.projectId}/kits/${editingKit.value.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } else {
      response = await fetch(`/api/mrp/projects/${props.projectId}/kits`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    }

    if (response.ok) {
      await loadKits()
      showAddForm.value = false
      editingKit.value = null
      emit('updated')
    }
  } catch (error) {
    console.error('Failed to save kit:', error)
  } finally {
    saving.value = false
  }
}

async function toggleUseKit(kit: Kit) {
  try {
    const response = await fetch(`/api/mrp/projects/${props.projectId}/kits/${kit.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ use_kit: !kit.use_kit }),
    })
    if (response.ok) {
      kit.use_kit = !kit.use_kit
      emit('updated')
    }
  } catch (error) {
    console.error('Failed to toggle kit:', error)
  }
}

async function deleteKit(kit: Kit) {
  if (!confirm(`Delete kit "${kit.kit_name}"? Parts in this kit will revert to in-house routing.`)) {
    return
  }

  try {
    const response = await fetch(`/api/mrp/projects/${props.projectId}/kits/${kit.id}`, {
      method: 'DELETE',
    })
    if (response.ok) {
      if (selectedKitId.value === kit.id) {
        selectedKitId.value = null
      }
      await loadKits()
      emit('updated')
    }
  } catch (error) {
    console.error('Failed to delete kit:', error)
  }
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

onMounted(() => {
  loadKits()
})
</script>

<template>
  <div class="slideout-overlay" @click.self="emit('close')">
    <div class="kit-slideout">
      <div class="slideout-header">
        <div>
          <h2>Kit Management</h2>
          <p class="project-code">{{ projectCode }}</p>
        </div>
        <button class="close-btn" @click="emit('close')">&times;</button>
      </div>

      <div class="slideout-body">
        <!-- Loading State -->
        <div v-if="loading" class="loading-state">
          <i class="pi pi-spin pi-spinner"></i>
          Loading kits...
        </div>

        <template v-else>
          <!-- Add/Edit Form -->
          <div v-if="showAddForm" class="kit-form">
            <h3>{{ editingKit ? 'Edit Kit' : 'Add New Kit' }}</h3>

            <div class="form-grid">
              <div class="form-field">
                <label>Kit Number</label>
                <input v-model="formKitNumber" type="text" placeholder="KIT-001" />
              </div>
              <div class="form-field">
                <label>Kit Name</label>
                <input v-model="formKitName" type="text" placeholder="Tube Bundle" />
              </div>
              <div class="form-field">
                <label>Vendor</label>
                <input v-model="formVendor" type="text" placeholder="ABC Fabrication" />
              </div>
              <div class="form-field">
                <label>Price ($)</label>
                <input v-model.number="formPrice" type="number" min="0" step="0.01" />
              </div>
              <div class="form-field full-width">
                <label>Notes</label>
                <textarea v-model="formNotes" rows="2" placeholder="Optional notes..."></textarea>
              </div>
            </div>

            <div class="form-actions">
              <button class="secondary-btn" @click="cancelForm">Cancel</button>
              <button
                class="primary-btn"
                :disabled="!formKitNumber || !formKitName || saving"
                @click="saveKit"
              >
                {{ saving ? 'Saving...' : (editingKit ? 'Update Kit' : 'Add Kit') }}
              </button>
            </div>
          </div>

          <!-- Kit List -->
          <div v-else class="kit-list-section">
            <div class="section-header">
              <span class="section-label">Project Kits</span>
              <button class="add-btn" @click="openAddForm">
                <i class="pi pi-plus"></i>
                Add Kit
              </button>
            </div>

            <div v-if="kits.length === 0" class="empty-state">
              <i class="pi pi-box"></i>
              <p>No kits defined for this project.</p>
              <p class="hint">Add a kit to group parts purchased as a bundle.</p>
            </div>

            <div v-else class="kit-cards">
              <div
                v-for="kit in kits"
                :key="kit.id"
                class="kit-card"
                :class="{ selected: selectedKitId === kit.id, disabled: !kit.use_kit }"
                @click="selectedKitId = selectedKitId === kit.id ? null : kit.id"
              >
                <div class="kit-header">
                  <div class="kit-info">
                    <span class="kit-number">{{ kit.kit_number }}</span>
                    <span class="kit-name">{{ kit.kit_name }}</span>
                  </div>
                  <div class="kit-actions" @click.stop>
                    <button
                      class="toggle-btn"
                      :class="{ active: kit.use_kit }"
                      :title="kit.use_kit ? 'Kit pricing active' : 'Kit pricing disabled'"
                      @click="toggleUseKit(kit)"
                    >
                      <i :class="kit.use_kit ? 'pi pi-check-circle' : 'pi pi-circle'"></i>
                    </button>
                    <button class="icon-btn" title="Edit" @click="openEditForm(kit)">
                      <i class="pi pi-pencil"></i>
                    </button>
                    <button class="icon-btn danger" title="Delete" @click="deleteKit(kit)">
                      <i class="pi pi-trash"></i>
                    </button>
                  </div>
                </div>

                <div class="kit-meta">
                  <span v-if="kit.vendor" class="vendor">{{ kit.vendor }}</span>
                  <span class="part-count">{{ kit.part_count || 0 }} parts</span>
                </div>

                <div class="kit-pricing">
                  <div class="price-row">
                    <span class="label">Kit Price:</span>
                    <span class="value kit-price">{{ formatCurrency(kit.price) }}</span>
                  </div>
                  <div v-if="kit.inhouse_cost && kit.inhouse_cost > 0" class="price-row">
                    <span class="label">In-House Cost:</span>
                    <span class="value inhouse">{{ formatCurrency(kit.inhouse_cost) }}</span>
                  </div>
                  <div v-if="kit.savings && kit.savings !== 0" class="price-row savings">
                    <span class="label">{{ kit.savings > 0 ? 'Savings:' : 'Extra Cost:' }}</span>
                    <span
                      class="value"
                      :class="{ positive: kit.savings > 0, negative: kit.savings < 0 }"
                    >
                      {{ formatCurrency(Math.abs(kit.savings)) }}
                      <span class="percent">({{ kit.savings_percent?.toFixed(0) }}%)</span>
                    </span>
                  </div>
                </div>

                <div v-if="!kit.use_kit" class="disabled-warning">
                  <i class="pi pi-exclamation-triangle"></i>
                  Kit pricing disabled - parts use in-house routing
                </div>

                <!-- Expanded Parts List -->
                <div v-if="selectedKitId === kit.id" class="parts-section">
                  <div class="parts-header">
                    <span>Parts in Kit</span>
                  </div>
                  <div v-if="loadingParts" class="loading-parts">
                    <i class="pi pi-spin pi-spinner"></i>
                    Loading...
                  </div>
                  <div v-else-if="selectedKitParts.length === 0" class="no-parts">
                    No parts assigned to this kit yet.
                    <br />
                    <span class="hint">Assign parts from the Routing page.</span>
                  </div>
                  <div v-else class="parts-list">
                    <div v-for="part in selectedKitParts" :key="part.item_id" class="part-row">
                      <span class="part-number">{{ part.item_number }}</span>
                      <span class="part-name">{{ part.name }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <div class="slideout-footer">
        <div class="footer-info">
          <template v-if="kits.length > 0">
            <span class="total-label">Total Kit Cost:</span>
            <span class="total-value">
              {{ formatCurrency(kits.filter(k => k.use_kit).reduce((sum, k) => sum + k.price, 0)) }}
            </span>
          </template>
        </div>
        <button class="secondary-btn" @click="emit('close')">Close</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.slideout-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  justify-content: flex-end;
  z-index: 1000;
}

.kit-slideout {
  background: #0f172a;
  width: 100%;
  max-width: 480px;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.3);
}

.slideout-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 24px;
  border-bottom: 1px solid #1e293b;
}

.slideout-header h2 {
  margin: 0;
  font-size: 16px;
  color: #e5e7eb;
}

.project-code {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #64748b;
}

.close-btn {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #e5e7eb;
}

.slideout-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.loading-state {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #9ca3af;
  font-size: 13px;
  padding: 32px 0;
  justify-content: center;
}

/* Section Header */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #1e293b;
  border: 1px solid #334155;
  color: #e5e7eb;
  padding: 6px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.add-btn:hover {
  background: #334155;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 32px 16px;
  color: #64748b;
}

.empty-state i {
  font-size: 32px;
  margin-bottom: 12px;
}

.empty-state p {
  margin: 4px 0;
}

.empty-state .hint {
  font-size: 12px;
  color: #475569;
}

/* Kit Cards */
.kit-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kit-card {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 12px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.kit-card:hover {
  border-color: #334155;
}

.kit-card.selected {
  border-color: #2563eb;
}

.kit-card.disabled {
  opacity: 0.7;
}

.kit-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.kit-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.kit-number {
  font-size: 11px;
  color: #64748b;
  font-family: monospace;
}

.kit-name {
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
}

.kit-actions {
  display: flex;
  gap: 4px;
}

.icon-btn {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.icon-btn:hover {
  color: #e5e7eb;
  background: #1e293b;
}

.icon-btn.danger:hover {
  color: #ef4444;
}

.toggle-btn {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  font-size: 16px;
}

.toggle-btn.active {
  color: #22c55e;
}

.toggle-btn:hover {
  background: #1e293b;
}

.kit-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 10px;
}

.vendor {
  color: #94a3b8;
}

.part-count {
  color: #38bdf8;
}

/* Kit Pricing */
.kit-pricing {
  background: #0f172a;
  border-radius: 6px;
  padding: 8px 10px;
}

.price-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  padding: 2px 0;
}

.price-row .label {
  color: #9ca3af;
}

.price-row .value {
  font-weight: 600;
  color: #e5e7eb;
}

.price-row .value.kit-price {
  color: #22c55e;
}

.price-row .value.inhouse {
  color: #94a3b8;
}

.price-row.savings .value.positive {
  color: #22c55e;
}

.price-row.savings .value.negative {
  color: #ef4444;
}

.percent {
  font-weight: 400;
  font-size: 11px;
  color: #64748b;
  margin-left: 4px;
}

.disabled-warning {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 8px;
  background: #422006;
  border-radius: 4px;
  font-size: 11px;
  color: #fbbf24;
}

/* Parts Section */
.parts-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #1e293b;
}

.parts-header {
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.loading-parts {
  font-size: 12px;
  color: #64748b;
  padding: 8px 0;
}

.no-parts {
  font-size: 12px;
  color: #64748b;
  padding: 8px 0;
  text-align: center;
}

.no-parts .hint {
  font-size: 11px;
  color: #475569;
}

.parts-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.part-row {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 8px;
  font-size: 12px;
  padding: 4px 6px;
  background: #0f172a;
  border-radius: 4px;
}

.part-number {
  color: #38bdf8;
  font-family: monospace;
  font-weight: 500;
}

.part-name {
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Form */
.kit-form {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 16px;
}

.kit-form h3 {
  margin: 0 0 16px 0;
  font-size: 14px;
  color: #e5e7eb;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-field.full-width {
  grid-column: 1 / -1;
}

.form-field label {
  font-size: 11px;
  color: #9ca3af;
}

.form-field input,
.form-field textarea {
  width: 100%;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #1e293b;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 13px;
  box-sizing: border-box;
}

.form-field input:focus,
.form-field textarea:focus {
  outline: none;
  border-color: #38bdf8;
}

.form-field textarea {
  resize: vertical;
  font-family: inherit;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

/* Footer */
.slideout-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 24px;
  border-top: 1px solid #1e293b;
  background: #020617;
}

.footer-info {
  display: flex;
  gap: 8px;
  align-items: center;
}

.total-label {
  font-size: 12px;
  color: #9ca3af;
}

.total-value {
  font-size: 14px;
  font-weight: 600;
  color: #22c55e;
}

/* Buttons */
.primary-btn {
  background: #2563eb;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.primary-btn:hover {
  background: #1d4ed8;
}

.primary-btn:disabled {
  background: #374151;
  color: #6b7280;
  cursor: not-allowed;
}

.secondary-btn {
  background: #374151;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.secondary-btn:hover {
  background: #4b5563;
}
</style>
