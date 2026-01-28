<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { supabase } from '../services/supabase'

const router = useRouter()

interface PrefixData {
  prefix: string
  highest: string
  highestNum: number
  count: number
}

const prefixes = ref<PrefixData[]>([])
const loading = ref(true)
const error = ref('')
const copiedNumber = ref('')

// Standard prefixes in our system
const STANDARD_PREFIXES = ['CSA', 'CSP', 'HBL', 'STA', 'STP', 'XXA', 'XXP', 'WMA', 'WMP']

async function loadPrefixes() {
  loading.value = true
  error.value = ''

  try {
    const { data, error: queryError } = await supabase
      .from('items')
      .select('item_number')

    if (queryError) throw queryError

    // Process items to find highest for each prefix
    const prefixMap = new Map<string, { highest: string, highestNum: number, count: number }>()

    // Initialize standard prefixes
    STANDARD_PREFIXES.forEach(p => {
      prefixMap.set(p, { highest: '', highestNum: 0, count: 0 })
    })

    data?.forEach(item => {
      const itemNum = item.item_number?.toLowerCase() || ''
      const match = itemNum.match(/^([a-z]{3})(\d+)$/)
      if (match) {
        const prefix = match[1].toUpperCase()
        const num = parseInt(match[2], 10)

        const existing = prefixMap.get(prefix) || { highest: '', highestNum: 0, count: 0 }
        existing.count++
        if (num > existing.highestNum) {
          existing.highestNum = num
          existing.highest = itemNum
        }
        prefixMap.set(prefix, existing)
      }
    })

    // Convert to array and sort
    prefixes.value = Array.from(prefixMap.entries())
      .map(([prefix, data]) => ({
        prefix,
        highest: data.highest || `${prefix.toLowerCase()}00000`,
        highestNum: data.highestNum,
        count: data.count
      }))
      .sort((a, b) => a.prefix.localeCompare(b.prefix))

  } catch (e: any) {
    error.value = e.message || 'Failed to load part numbers'
  } finally {
    loading.value = false
  }
}

function generateNextNumbers(prefixData: PrefixData, count: number = 50): string[] {
  const numbers: string[] = []
  const prefix = prefixData.prefix.toLowerCase()

  // Start from next 10-increment after highest
  let nextNum = Math.ceil((prefixData.highestNum + 1) / 10) * 10
  if (nextNum <= prefixData.highestNum) nextNum += 10

  for (let i = 0; i < count; i++) {
    const numStr = String(nextNum).padStart(5, '0')
    numbers.push(`${prefix}${numStr}`)
    nextNum += 10
  }

  return numbers
}

async function copyToClipboard(partNumber: string) {
  try {
    await navigator.clipboard.writeText(partNumber)
    copiedNumber.value = partNumber
    setTimeout(() => {
      copiedNumber.value = ''
    }, 2000)
  } catch (e) {
    console.error('Failed to copy:', e)
  }
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
          <p class="subtitle">Click any part number to copy it to clipboard</p>
        </div>
      </div>
      <button class="refresh-btn" @click="loadPrefixes" :disabled="loading">
        <i class="pi pi-refresh" :class="{ 'pi-spin': loading }"></i>
        Refresh
      </button>
    </header>

    <div class="instructions-card">
      <h3><i class="pi pi-info-circle"></i> How to Use</h3>
      <p>
        These are the next 50 available part numbers for each prefix.
        Numbers increment by 10 from the highest existing number.
        Click any number to copy it to your clipboard for use in CAD.
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
      <div v-for="prefixData in prefixes" :key="prefixData.prefix" class="prefix-card">
        <div class="prefix-header">
          <div class="prefix-name">{{ prefixData.prefix }}#####</div>
          <div class="prefix-info">
            Highest in use: <strong>{{ prefixData.highest.toUpperCase() || 'None' }}</strong>
            | Next available: <strong>{{ generateNextNumbers(prefixData)[0]?.toUpperCase() }}</strong>
          </div>
        </div>
        <div class="numbers-grid">
          <div
            v-for="num in generateNextNumbers(prefixData)"
            :key="num"
            class="number-chip"
            :class="{ copied: copiedNumber === num }"
            @click="copyToClipboard(num)"
          >
            {{ num.toUpperCase() }}
            <span v-if="copiedNumber === num" class="copied-badge">Copied!</span>
          </div>
        </div>
      </div>
    </div>

    <div v-if="copiedNumber" class="toast">
      <i class="pi pi-check-circle"></i>
      Copied {{ copiedNumber.toUpperCase() }} to clipboard
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
