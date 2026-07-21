<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

interface PrefixData {
  prefix: string
  available: string[]
  highest_existing: number
  total_existing: number
  total_used: number
}

const prefixData = ref<Map<string, PrefixData>>(new Map())
const loading = ref(true)
const error = ref('')
const copiedNumber = ref('')
const selectedPrefix = ref<string | null>(null)

// Standard prefixes in our system
const STANDARD_PREFIXES = ['CSA', 'CSP', 'HBL', 'STA', 'STP', 'XXA', 'XXP', 'WMA', 'WMP']

// Filtered prefixes based on selection
const filteredPrefixes = computed(() => {
  const allPrefixes = Array.from(prefixData.value.values())
  if (!selectedPrefix.value) return allPrefixes
  return allPrefixes.filter(p => p.prefix.toUpperCase() === selectedPrefix.value)
})

async function loadPrefixes() {
  loading.value = true
  error.value = ''

  try {
    // Fetch available numbers for all prefixes in parallel
    const promises = STANDARD_PREFIXES.map(async (prefix) => {
      const response = await fetch(`/api/items/available-numbers/${prefix.toLowerCase()}?count=50`)
      if (!response.ok) {
        throw new Error(`Failed to load ${prefix}: ${response.statusText}`)
      }
      return response.json()
    })

    const results = await Promise.all(promises)

    // Build the prefix data map
    const newData = new Map<string, PrefixData>()
    for (const result of results) {
      newData.set(result.prefix.toUpperCase(), result)
    }
    prefixData.value = newData

  } catch (e: any) {
    error.value = e.message || 'Failed to load part numbers'
  } finally {
    loading.value = false
  }
}

async function copyAndMarkUsed(partNumber: string, prefixKey: string) {
  try {
    // Copy to clipboard
    await navigator.clipboard.writeText(partNumber)
    copiedNumber.value = partNumber

    // Mark as used on the server
    const response = await fetch('/api/items/mark-number-used', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item_number: partNumber })
    })

    if (response.ok) {
      // Remove from local list (optimistic update)
      const data = prefixData.value.get(prefixKey)
      if (data) {
        data.available = data.available.filter(n => n !== partNumber)
        data.total_used++
      }
    }

    // Clear copied indicator after delay
    setTimeout(() => {
      copiedNumber.value = ''
    }, 2000)

  } catch (e) {
    console.error('Failed to copy/mark:', e)
  }
}

function selectPrefix(prefix: string | null) {
  selectedPrefix.value = prefix
}

function goHome() {
  router.push('/')
}

onMounted(() => {
  loadPrefixes()
})
</script>

<template>
  <div class="part-numbers-container">
    <header class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="goHome">
          <i class="pi pi-arrow-left"></i>
          Home
        </button>
        <div>
          <h1>Part Number Generator</h1>
          <p class="subtitle">Click any part number to copy and reserve it</p>
        </div>
      </div>
      <button class="refresh-btn" @click="loadPrefixes" :disabled="loading">
        <i class="pi pi-refresh" :class="{ 'pi-spin': loading }"></i>
        Refresh
      </button>
    </header>

    <!-- Prefix Filter Bar -->
    <div class="prefix-filter-bar">
      <button
        class="prefix-filter-btn"
        :class="{ active: selectedPrefix === null }"
        @click="selectPrefix(null)"
      >
        All
      </button>
      <button
        v-for="prefix in STANDARD_PREFIXES"
        :key="prefix"
        class="prefix-filter-btn"
        :class="{ active: selectedPrefix === prefix }"
        @click="selectPrefix(prefix)"
      >
        {{ prefix }}
      </button>
    </div>

    <div class="instructions-card">
      <h3><i class="pi pi-info-circle"></i> How to Use</h3>
      <p>
        These are the next 50 available part numbers for each prefix, filling gaps first.
        Click any number to <strong>copy it to clipboard and reserve it</strong>.
        Reserved numbers won't appear again until you actually create the item in PDM.
      </p>
    </div>

    <div v-if="error" class="error-message">
      <i class="pi pi-exclamation-triangle"></i>
      {{ error }}
    </div>

    <div v-if="loading" class="loading">
      <i class="pi pi-spin pi-spinner"></i>
      Loading part numbers...
    </div>

    <div v-else class="prefixes-grid">
      <div v-for="data in filteredPrefixes" :key="data.prefix" class="prefix-card">
        <div class="prefix-header">
          <div class="prefix-name">{{ data.prefix.toUpperCase() }}#####</div>
          <div class="prefix-info">
            Highest in use: <strong>{{ data.prefix.toLowerCase() }}{{ String(data.highest_existing).padStart(5, '0') }}</strong>
            | {{ data.total_existing }} in PDM | {{ data.total_used }} reserved
          </div>
        </div>
        <div class="numbers-grid">
          <div
            v-for="num in data.available"
            :key="num"
            class="number-chip"
            :class="{ copied: copiedNumber === num }"
            @click="copyAndMarkUsed(num, data.prefix.toUpperCase())"
          >
            {{ num.toUpperCase() }}
            <span v-if="copiedNumber === num" class="copied-badge">Copied!</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="copiedNumber" class="toast">
      <i class="pi pi-check-circle"></i>
      Copied {{ copiedNumber.toUpperCase() }} to clipboard (reserved)
    </div>
  </div>
</template>

<style scoped>
.part-numbers-container {
  min-height: 100vh;
  background: #f5f5f5;
  color: #333;
  padding: 1.5rem;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  padding: 1rem 1.5rem;
  background: #fff;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #2563eb;
  border: none;
  color: #fff;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.85rem;
}

.back-btn:hover {
  background: #1d4ed8;
}

.page-header h1 {
  font-size: 1.5rem;
  margin: 0;
  color: #333;
}

.subtitle {
  margin: 0.25rem 0 0 0;
  color: #666;
  font-size: 0.85rem;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #2563eb;
  border: none;
  color: #fff;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.85rem;
}

.refresh-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.prefix-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
  padding: 1rem;
  background: #fff;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  align-items: center;
}

.prefix-filter-btn {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #475569;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  font-family: monospace;
  transition: all 0.15s;
}

.prefix-filter-btn:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.prefix-filter-btn.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

.instructions-card {
  background: #e0f2fe;
  border: 1px solid #7dd3fc;
  border-radius: 0.5rem;
  padding: 1rem 1.5rem;
  margin-bottom: 1.5rem;
}

.instructions-card h3 {
  margin: 0 0 0.5rem 0;
  color: #0369a1;
  font-size: 0.95rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.instructions-card p {
  margin: 0;
  color: #0c4a6e;
  font-size: 0.85rem;
  line-height: 1.5;
}

.error-message {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  border-radius: 0.5rem;
  padding: 1rem;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #dc2626;
}

.loading {
  text-align: center;
  padding: 3rem;
  color: #666;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  font-size: 1rem;
}

.prefixes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 1.25rem;
}

.prefix-card {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 0.5rem;
  overflow: hidden;
}

.prefix-header {
  background: #f8fafc;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #e0e0e0;
}

.prefix-name {
  font-size: 1rem;
  font-weight: 600;
  color: #333;
  font-family: monospace;
  margin-bottom: 0.25rem;
}

.prefix-info {
  font-size: 0.75rem;
  color: #666;
}

.prefix-info strong {
  color: #2563eb;
  font-family: monospace;
}

.numbers-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  padding: 0.75rem;
  max-height: 280px;
  overflow-y: auto;
}

.number-chip {
  background: #f0f7ff;
  border: 1px solid #bfdbfe;
  color: #1e40af;
  padding: 0.3rem 0.6rem;
  border-radius: 0.25rem;
  font-family: monospace;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}

.number-chip:hover {
  background: #dbeafe;
  border-color: #2563eb;
  transform: scale(1.02);
}

.number-chip.copied {
  background: #dcfce7;
  border-color: #22c55e;
  color: #166534;
}

.copied-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  background: #22c55e;
  color: #fff;
  font-size: 0.6rem;
  padding: 0.1rem 0.3rem;
  border-radius: 0.2rem;
}

.toast {
  position: fixed;
  bottom: 2rem;
  left: 50%;
  transform: translateX(-50%);
  background: #22c55e;
  color: #fff;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}

/* Scrollbar styling */
.numbers-grid::-webkit-scrollbar {
  width: 6px;
}

.numbers-grid::-webkit-scrollbar-track {
  background: #f1f5f9;
  border-radius: 3px;
}

.numbers-grid::-webkit-scrollbar-thumb {
  background: #94a3b8;
  border-radius: 3px;
}

.numbers-grid::-webkit-scrollbar-thumb:hover {
  background: #64748b;
}
</style>
