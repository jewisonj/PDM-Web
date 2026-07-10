<script setup lang="ts">
/**
 * Design Book update preview — the confirmation step.
 *
 * Shows the dry-run diff (/check) before anything is rendered or uploaded.
 * Missing prints must each be explicitly acknowledged before Commit enables
 * (Documentation/36 decision 3: warn + per-hole acknowledgment, no placeholders).
 */
import { ref, computed } from 'vue'
import type { CheckResult, CheckWarning } from '../services/designBook'

const props = defineProps<{
  diff: CheckResult
  committing: boolean
  firstGen: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'commit'): void
}>()

const missingPrints = computed<CheckWarning[]>(() =>
  props.diff.warnings.filter(w => w.type === 'missing_print')
)
const acked = ref<Set<string>>(new Set())

function ackKey(w: CheckWarning): string {
  return `${w.section_code}|${w.item_number}`
}
function toggleAck(w: CheckWarning) {
  const key = ackKey(w)
  const next = new Set(acked.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  acked.value = next
}

const totalChanges = computed(
  () => props.diff.added.length + props.diff.changed.length + props.diff.retired.length
)
const hasChanges = computed(() => totalChanges.value > 0)
const allAcked = computed(() => missingPrints.value.every(w => acked.value.has(ackKey(w))))
const canCommit = computed(() => hasChanges.value && allAcked.value && !props.committing)

function reasonText(reasons: string[]): string {
  return (reasons || []).join('; ')
}
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <h2>{{ firstGen ? 'Generate Master Design Book' : 'Update Book — pending changes' }}</h2>
        <button class="close-btn" @click="emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <div v-if="!hasChanges" class="no-changes">
          <i class="pi pi-check-circle"></i>
          No changes — the book matches the current template data and prints.
        </div>

        <template v-else>
          <div class="rev-line">
            Book rev <span class="mono">{{ diff.book_rev }}</span>
            <i class="pi pi-arrow-right"></i>
            <span class="mono strong">{{ diff.next_book_rev }}</span>
            <span v-if="firstGen" class="muted">— first generation, all sections issue at rev A</span>
            <span v-else-if="diff.would_issue_notice" class="muted">
              — change notice CHANGE-NOTICE-rev{{ String(diff.next_book_rev).padStart(3, '0') }} will be issued
            </span>
          </div>

          <table class="diff-table">
            <thead>
              <tr>
                <th>Action</th>
                <th>Section</th>
                <th>Title</th>
                <th>Rev</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="e in diff.changed" :key="'c' + e.section_code">
                <td><span class="chip chip-changed">REPLACE</span></td>
                <td class="mono">{{ e.section_code }}</td>
                <td class="title-cell">{{ e.title }}</td>
                <td class="mono">{{ e.old_rev }} <i class="pi pi-arrow-right tiny"></i> {{ e.new_rev }}</td>
                <td class="reason">{{ reasonText(e.reasons) }}</td>
              </tr>
              <tr v-for="e in diff.added" :key="'a' + e.section_code">
                <td><span class="chip chip-new">INSERT</span></td>
                <td class="mono">{{ e.section_code }}</td>
                <td class="title-cell">{{ e.title }}</td>
                <td class="mono">{{ e.new_rev }}</td>
                <td class="reason">{{ reasonText(e.reasons) }}</td>
              </tr>
              <tr v-for="e in diff.retired" :key="'r' + e.section_code">
                <td><span class="chip chip-retired">REMOVE</span></td>
                <td class="mono">{{ e.section_code }}</td>
                <td class="title-cell">{{ e.title }}</td>
                <td class="mono">{{ e.last_rev }}</td>
                <td class="reason">{{ reasonText(e.reasons) }}</td>
              </tr>
            </tbody>
          </table>

          <div v-if="diff.unchanged.length" class="unchanged-line">
            {{ diff.unchanged.length }} section{{ diff.unchanged.length === 1 ? '' : 's' }} unchanged
          </div>

          <div v-if="missingPrints.length" class="ack-block">
            <div class="ack-title">
              <i class="pi pi-exclamation-triangle"></i>
              {{ missingPrints.length }} missing print{{ missingPrints.length === 1 ? '' : 's' }} —
              acknowledge each to publish with a MISSING flag on the booklet cover
            </div>
            <label v-for="w in missingPrints" :key="ackKey(w)" class="ack-row">
              <input
                type="checkbox"
                :checked="acked.has(ackKey(w))"
                @change="toggleAck(w)"
              />
              <span class="mono">{{ w.item_number }}</span>
              <span class="muted">in {{ w.section_code }} — no PDF on file</span>
            </label>
          </div>
        </template>
      </div>

      <div class="modal-actions">
        <button class="secondary-btn" :disabled="committing" @click="emit('close')">Cancel</button>
        <button v-if="hasChanges" class="primary-btn" :disabled="!canCommit" @click="emit('commit')">
          <i :class="committing ? 'pi pi-spin pi-spinner' : 'pi pi-sync'"></i>
          {{
            committing
              ? 'Publishing…'
              : firstGen
                ? `Generate Book (${totalChanges} sections)`
                : `Commit Update (${totalChanges} section${totalChanges === 1 ? '' : 's'})`
          }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  width: 760px;
  max-width: 94vw;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  color: #e5e7eb;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #1e293b;
}

.modal-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 22px;
  cursor: pointer;
  line-height: 1;
}
.close-btn:hover { color: #e5e7eb; }

.modal-body {
  padding: 16px 20px;
  overflow-y: auto;
}

.no-changes {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #6ee7b7;
  font-size: 14px;
  padding: 12px 0;
}

.rev-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 12px;
}
.rev-line .strong { font-weight: 700; }

.mono { font-family: 'Consolas', 'Monaco', monospace; }
.muted { color: #9ca3af; font-size: 12px; }
.tiny { font-size: 10px; }

.diff-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.diff-table th {
  text-align: left;
  padding: 8px;
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  background: #020617;
  border-bottom: 1px solid #1e293b;
}
.diff-table td {
  padding: 8px;
  border-bottom: 1px solid #1e293b;
  vertical-align: top;
}
.title-cell { max-width: 190px; }
.reason { color: #9ca3af; font-size: 11px; }

.chip {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  color: white;
}
.chip-changed { background: #d97706; }
.chip-new { background: #7c3aed; }
.chip-retired { background: #374151; color: #9ca3af; }

.unchanged-line {
  margin-top: 10px;
  color: #6b7280;
  font-size: 12px;
}

.ack-block {
  margin-top: 16px;
  background: #1c1206;
  border: 1px solid #92400e;
  border-radius: 6px;
  padding: 12px;
}
.ack-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #fbbf24;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 10px;
}
.ack-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  cursor: pointer;
}
.ack-row input { accent-color: #d97706; }

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid #1e293b;
}

.primary-btn,
.secondary-btn {
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
.primary-btn:disabled,
.secondary-btn:disabled {
  background: #374151;
  color: #6b7280;
  cursor: not-allowed;
}
</style>
