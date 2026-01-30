<script setup lang="ts">
import { ref, computed } from 'vue'
import type { NestGroup } from '../types'

const props = defineProps<{
  groups: NestGroup[]
  loading: boolean
}>()

const emit = defineEmits<{
  close: []
  submit: [config: {
    material: string
    thickness: number
    sheetWidth: number
    sheetHeight: number
    sheetLabel: string
    spacing: number
    margin: number
    rotationStep: number
  }]
}>()

const selectedGroupKey = ref<string | null>(null)
const selectedSheetPreset = ref<string | null>(null)
const customWidth = ref<number | null>(null)
const customHeight = ref<number | null>(null)
const showAdvanced = ref(false)
const spacing = ref(0.125)
const margin = ref(0.5)
const rotationStep = ref(5)

const sheetPresets = [
  { label: '48 x 96 in (4x8 ft)', width: 48, height: 96 },
  { label: '60 x 120 in (5x10 ft)', width: 60, height: 120 },
]

const selectedGroup = computed(() =>
  props.groups.find(g => g.group_key === selectedGroupKey.value) || null
)

const sheetWidth = computed(() => {
  if (selectedSheetPreset.value === 'custom') return customWidth.value
  const preset = sheetPresets.find(p => p.label === selectedSheetPreset.value)
  return preset?.width || null
})

const sheetHeight = computed(() => {
  if (selectedSheetPreset.value === 'custom') return customHeight.value
  const preset = sheetPresets.find(p => p.label === selectedSheetPreset.value)
  return preset?.height || null
})

const sheetLabel = computed(() => {
  if (selectedSheetPreset.value === 'custom') {
    return `${customWidth.value} x ${customHeight.value} in (Custom)`
  }
  return selectedSheetPreset.value || ''
})

const canSubmit = computed(() => {
  if (!selectedGroup.value) return false
  if (selectedGroup.value.parts_with_dxf === 0) return false
  if (!sheetWidth.value || !sheetHeight.value) return false
  if (sheetWidth.value <= 0 || sheetHeight.value <= 0) return false
  return true
})

function handleSubmit() {
  if (!canSubmit.value || !selectedGroup.value) return
  emit('submit', {
    material: selectedGroup.value.material,
    thickness: selectedGroup.value.thickness,
    sheetWidth: sheetWidth.value!,
    sheetHeight: sheetHeight.value!,
    sheetLabel: sheetLabel.value,
    spacing: spacing.value,
    margin: margin.value,
    rotationStep: rotationStep.value,
  })
}
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="nest-modal">
      <div class="modal-header">
        <h2>Nest DXF Parts</h2>
        <button class="close-btn" @click="emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <!-- Loading State -->
        <div v-if="loading" class="loading-state">
          <i class="pi pi-spin pi-spinner"></i>
          Loading part groups...
        </div>

        <!-- No Groups -->
        <div v-else-if="groups.length === 0" class="empty-state">
          <i class="pi pi-info-circle"></i>
          No nestable parts found. Parts need material, thickness, and a DXF file.
        </div>

        <template v-else>
          <!-- Section 1: Material/Thickness Groups -->
          <div class="section">
            <label class="section-label">Select Material Group</label>
            <div class="group-cards">
              <div
                v-for="group in groups"
                :key="group.group_key"
                class="group-card"
                :class="{
                  selected: selectedGroupKey === group.group_key,
                  disabled: group.parts_with_dxf === 0
                }"
                @click="group.parts_with_dxf > 0 && (selectedGroupKey = group.group_key)"
              >
                <div class="group-header">
                  <span class="group-material">{{ group.material }}</span>
                  <span class="group-thickness">{{ group.thickness }}" thk</span>
                </div>
                <div class="group-stats">
                  <span>{{ group.parts_with_dxf }} / {{ group.part_count }} parts with DXF</span>
                  <span class="group-pieces">{{ group.total_pieces }} total pcs</span>
                </div>
                <div v-if="group.parts_with_dxf < group.part_count" class="group-warning">
                  <i class="pi pi-exclamation-triangle"></i>
                  {{ group.part_count - group.parts_with_dxf }} parts missing DXF
                </div>
              </div>
            </div>
          </div>

          <!-- Section 2: Sheet Size -->
          <div class="section">
            <label class="section-label">Sheet Size</label>
            <div class="sheet-options">
              <button
                v-for="preset in sheetPresets"
                :key="preset.label"
                class="sheet-btn"
                :class="{ selected: selectedSheetPreset === preset.label }"
                @click="selectedSheetPreset = preset.label"
              >
                {{ preset.label }}
              </button>
              <button
                class="sheet-btn"
                :class="{ selected: selectedSheetPreset === 'custom' }"
                @click="selectedSheetPreset = 'custom'"
              >
                Custom...
              </button>
            </div>
            <div v-if="selectedSheetPreset === 'custom'" class="custom-sheet">
              <div class="form-field">
                <label>Width (in)</label>
                <input v-model.number="customWidth" type="number" min="1" step="0.5" placeholder="Width" />
              </div>
              <div class="form-field">
                <label>Height (in)</label>
                <input v-model.number="customHeight" type="number" min="1" step="0.5" placeholder="Height" />
              </div>
            </div>
          </div>

          <!-- Section 3: Advanced Parameters -->
          <div class="section">
            <button class="advanced-toggle" @click="showAdvanced = !showAdvanced">
              <i :class="showAdvanced ? 'pi pi-chevron-down' : 'pi pi-chevron-right'"></i>
              Advanced Parameters
            </button>
            <div v-if="showAdvanced" class="advanced-params">
              <div class="param-row">
                <div class="form-field">
                  <label>Part Spacing (in)</label>
                  <input v-model.number="spacing" type="number" min="0" step="0.0625" />
                </div>
                <div class="form-field">
                  <label>Sheet Margin (in)</label>
                  <input v-model.number="margin" type="number" min="0" step="0.25" />
                </div>
                <div class="form-field">
                  <label>Rotation Step (deg)</label>
                  <input v-model.number="rotationStep" type="number" min="1" max="90" step="1" />
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <button class="secondary-btn" @click="emit('close')">Cancel</button>
        <button
          class="primary-btn"
          :disabled="!canSubmit"
          @click="handleSubmit"
        >
          <i class="pi pi-cog"></i>
          Start Nesting
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.nest-modal {
  background: #0f172a;
  border-radius: 8px;
  width: 100%;
  max-width: 520px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid #1e293b;
}

.modal-header h2 {
  margin: 0;
  font-size: 16px;
  color: #e5e7eb;
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

.modal-body {
  padding: 24px;
  overflow-y: auto;
  flex: 1;
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #9ca3af;
  font-size: 13px;
  padding: 16px 0;
}

.section {
  margin-bottom: 20px;
}

.section-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

/* Group Cards */
.group-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.group-card {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 12px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.group-card:hover:not(.disabled) {
  border-color: #334155;
  background: #0f172a;
}

.group-card.selected {
  border-color: #2563eb;
  background: #0f172a;
}

.group-card.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.group-material {
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
}

.group-thickness {
  font-size: 13px;
  color: #38bdf8;
  font-weight: 500;
}

.group-stats {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #9ca3af;
}

.group-pieces {
  color: #6ee7b7;
  font-weight: 500;
}

.group-warning {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #fbbf24;
  margin-top: 6px;
}

/* Sheet Size Options */
.sheet-options {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.sheet-btn {
  background: #020617;
  border: 1px solid #1e293b;
  color: #e5e7eb;
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: border-color 0.15s;
}

.sheet-btn:hover {
  border-color: #334155;
}

.sheet-btn.selected {
  border-color: #2563eb;
  background: #0f172a;
}

.custom-sheet {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

/* Form Fields */
.form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-field label {
  font-size: 11px;
  color: #9ca3af;
}

.form-field input {
  width: 100%;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #1f2937;
  background: #020617;
  color: #e5e7eb;
  font-size: 13px;
  box-sizing: border-box;
}

.form-field input:focus {
  outline: none;
  border-color: #38bdf8;
}

/* Advanced Toggle */
.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}

.advanced-toggle:hover {
  color: #e5e7eb;
}

.advanced-params {
  margin-top: 12px;
}

.param-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}

/* Footer */
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid #1e293b;
}

.primary-btn {
  display: flex;
  align-items: center;
  gap: 6px;
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
