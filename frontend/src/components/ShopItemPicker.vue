<script setup lang="ts">
/**
 * Phone-friendly autocomplete for picking a BOM item (assembly or part).
 * - Type to filter by item number or name; tap a row to select.
 * - Selected item shows as a chip with a clear button.
 * - Free text that never matched is kept (emitted via `text`) so the reviewer can fix it later.
 */
import { ref, computed, watch } from 'vue'
import { filterItems, type Suggestable } from '../utils/shopNotes'

const props = defineProps<{
  modelValue: Suggestable | null
  text: string
  items: Suggestable[]
  label: string
  placeholder?: string
  disabled?: boolean
  hint?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: Suggestable | null): void
  (e: 'update:text', v: string): void
}>()

const open = ref(false)
const inputEl = ref<HTMLInputElement | null>(null)

const suggestions = computed(() => filterItems(props.items, props.text, 14))

function onInput(ev: Event) {
  const v = (ev.target as HTMLInputElement).value
  emit('update:text', v)
  if (props.modelValue) emit('update:modelValue', null)
  open.value = true
}

function pick(it: Suggestable) {
  emit('update:modelValue', it)
  emit('update:text', it.item_number)
  open.value = false
  inputEl.value?.blur()
}

function clear() {
  emit('update:modelValue', null)
  emit('update:text', '')
  open.value = false
  requestAnimationFrame(() => inputEl.value?.focus())
}

function onFocus() {
  open.value = true
}

function onBlur() {
  // Let a suggestion tap land before closing
  setTimeout(() => (open.value = false), 120)
}

watch(() => props.disabled, d => { if (d) open.value = false })
</script>

<template>
  <div class="picker" :class="{ disabled }">
    <label class="picker-label">{{ label }}<span v-if="hint" class="picker-hint"> · {{ hint }}</span></label>

    <div v-if="modelValue" class="chip">
      <div class="chip-text">
        <strong>{{ modelValue.item_number }}</strong>
        <span v-if="modelValue.name" class="chip-name">{{ modelValue.name }}</span>
      </div>
      <button type="button" class="chip-clear" aria-label="Clear" @click="clear">✕</button>
    </div>

    <div v-else class="input-wrap">
      <input
        ref="inputEl"
        class="picker-input"
        type="text"
        :value="text"
        :placeholder="placeholder || 'Type a number or name'"
        :disabled="disabled"
        autocomplete="off"
        autocapitalize="off"
        autocorrect="off"
        spellcheck="false"
        enterkeyhint="done"
        @input="onInput"
        @focus="onFocus"
        @blur="onBlur"
      />
      <button v-if="text" type="button" class="input-clear" aria-label="Clear" @mousedown.prevent @click="clear">✕</button>

      <ul v-if="open && suggestions.length" class="menu">
        <li v-for="it in suggestions" :key="it.id" @mousedown.prevent="pick(it)" @touchend.prevent="pick(it)">
          <strong>{{ it.item_number }}</strong>
          <span class="menu-name">{{ it.name }}</span>
        </li>
      </ul>
      <div v-else-if="open && text && items.length" class="menu menu-empty">
        No match — “{{ text }}” will be saved as typed
      </div>
    </div>
  </div>
</template>

<style scoped>
.picker { position: relative; }
.picker.disabled { opacity: 0.5; }

.picker-label {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #94a3b8;
  margin-bottom: 6px;
}
.picker-hint { font-weight: 400; text-transform: none; letter-spacing: 0; color: #64748b; }

.input-wrap { position: relative; }

.picker-input {
  width: 100%;
  font-size: 1.15rem;
  padding: 14px 44px 14px 14px;
  border-radius: 12px;
  border: 1.5px solid #334155;
  background: #0f172a;
  color: #f1f5f9;
  outline: none;
  -webkit-appearance: none;
}
.picker-input:focus { border-color: #38bdf8; }
.picker-input::placeholder { color: #475569; }

.input-clear, .chip-clear {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: #1e293b;
  color: #cbd5e1;
  font-size: 1rem;
}

.chip {
  position: relative;
  display: flex;
  align-items: center;
  min-height: 54px;
  padding: 10px 48px 10px 14px;
  border-radius: 12px;
  border: 1.5px solid #0ea5e9;
  background: #082f49;
  color: #f1f5f9;
}
.chip-text { display: flex; flex-direction: column; line-height: 1.2; min-width: 0; }
.chip-text strong { font-size: 1.15rem; letter-spacing: 0.02em; }
.chip-name { font-size: 0.85rem; color: #bae6fd; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.menu {
  position: absolute;
  z-index: 30;
  left: 0; right: 0;
  top: calc(100% + 4px);
  max-height: 46vh;
  overflow-y: auto;
  margin: 0;
  padding: 4px 0;
  list-style: none;
  background: #0f172a;
  border: 1.5px solid #334155;
  border-radius: 12px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5);
}
.menu li {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 14px;
  border-bottom: 1px solid #1e293b;
  line-height: 1.2;
  cursor: pointer;
}
.menu li:last-child { border-bottom: none; }
.menu li:active { background: #1e293b; }
.menu li strong { font-size: 1.05rem; color: #f1f5f9; }
.menu-name { font-size: 0.85rem; color: #94a3b8; }
.menu-empty { padding: 12px 14px; font-size: 0.9rem; color: #94a3b8; }
</style>
