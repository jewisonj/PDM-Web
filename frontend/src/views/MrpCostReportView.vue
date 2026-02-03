<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { supabase, API_BASE_URL } from '../services/supabase'
import { Pie } from 'vue-chartjs'
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(ArcElement, Tooltip, Legend)

// --- Interfaces ---

interface ItemOperation {
  station_code: string
  station_name: string
  is_outsourced: boolean
  est_time_min: number
  cost: number
}

interface ManufacturedItem {
  item_id: string
  item_number: string
  name: string
  quantity: number
  material_cost: number
  labor_cost: number
  outsourced_cost: number
  unit_cost: number
  extended_cost: number
  operations: ItemOperation[]
}

interface PurchasedItem {
  item_id: string
  item_number: string
  name: string
  quantity: number
  unit_price: number
  extended_cost: number
  supplier_name: string
  supplier_pn: string
}

interface OperationSummary {
  station_code: string
  station_name: string
  is_outsourced: boolean
  total_time_min: number
  total_cost: number
  item_count: number
  items: string[]
}

interface ChartSlice {
  label: string
  value: number
  category: string
}

interface CostReportData {
  project_id: string
  project_code: string
  customer: string
  description: string
  labor_cost: number
  material_cost: number
  outsourced_cost: number
  purchased_cost: number
  overhead_multiplier: number
  subtotal: number
  total: number
  manufactured_items: ManufacturedItem[]
  purchased_items: PurchasedItem[]
  operations_summary: OperationSummary[]
  cost_breakdown_chart: ChartSlice[]
}

interface ProjectOption {
  id: string
  project_code: string
  description: string
  status: string
}

// --- State ---

const router = useRouter()
const route = useRoute()
const projects = ref<ProjectOption[]>([])
const selectedProjectId = ref('')
const report = ref<CostReportData | null>(null)
const loading = ref(false)
const loadingProjects = ref(true)
const error = ref('')

// --- Data Loading ---

async function loadProjects() {
  loadingProjects.value = true
  try {
    const { data, error: queryError } = await supabase
      .from('mrp_projects')
      .select('id, project_code, description, status')
      .order('due_date', { ascending: true })

    if (queryError) throw queryError
    projects.value = data || []

    // Auto-select from query param or first project
    const queryProject = route.query.project as string
    if (queryProject && projects.value.find(p => p.id === queryProject)) {
      selectedProjectId.value = queryProject
    } else if (projects.value.length > 0 && !selectedProjectId.value) {
      selectedProjectId.value = projects.value[0].id
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load projects'
  } finally {
    loadingProjects.value = false
  }
}

async function loadReport(projectId: string) {
  if (!projectId) return
  loading.value = true
  error.value = ''
  report.value = null

  try {
    const response = await fetch(`${API_BASE_URL}/mrp/projects/${projectId}/cost-report`)
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Failed to load report' }))
      throw new Error(err.detail || `Error ${response.status}`)
    }
    report.value = await response.json()
  } catch (e: any) {
    error.value = e.message || 'Failed to load cost report'
  } finally {
    loading.value = false
  }
}

watch(selectedProjectId, (id) => {
  if (id) loadReport(id)
})

onMounted(() => {
  loadProjects()
})

// --- Computed ---

const sortedManufacturedItems = computed(() => {
  if (!report.value) return []
  return [...report.value.manufactured_items].sort(
    (a, b) => b.extended_cost - a.extended_cost
  )
})

const sortedOperations = computed(() => {
  if (!report.value) return []
  return [...report.value.operations_summary].sort(
    (a, b) => b.total_cost - a.total_cost
  )
})

const sortedPurchasedItems = computed(() => {
  if (!report.value) return []
  return [...report.value.purchased_items].sort(
    (a, b) => b.extended_cost - a.extended_cost
  )
})

const manufacturedTotal = computed(() => {
  if (!report.value) return 0
  return report.value.manufactured_items.reduce((s, i) => s + i.extended_cost, 0)
})

const purchasedTotal = computed(() => {
  if (!report.value) return 0
  return report.value.purchased_items.reduce((s, i) => s + i.extended_cost, 0)
})

// --- Chart ---

const laborColors = ['#3b82f6', '#06b6d4', '#10b981', '#0ea5e9', '#14b8a6', '#22d3ee', '#2dd4bf', '#38bdf8', '#34d399', '#67e8f9']

function getSliceColor(slice: ChartSlice, laborIndex: number): string {
  if (slice.category === 'material') return '#f59e0b'
  if (slice.category === 'purchased') return '#8b5cf6'
  if (slice.category === 'outsourced') return '#f97316'
  return laborColors[laborIndex % laborColors.length]
}

const chartData = computed(() => {
  if (!report.value) return null
  const slices = report.value.cost_breakdown_chart.filter(s => s.value > 0)
  if (slices.length === 0) return null

  let laborIdx = 0
  const colors = slices.map(s => {
    const color = getSliceColor(s, laborIdx)
    if (s.category === 'labor') laborIdx++
    return color
  })

  return {
    labels: slices.map(s => s.label),
    datasets: [{
      data: slices.map(s => s.value),
      backgroundColor: colors,
      borderColor: '#020617',
      borderWidth: 2,
    }]
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'right' as const,
      labels: {
        color: '#e5e7eb',
        font: { size: 12 },
        padding: 12,
        generateLabels: (chart: any) => {
          const data = chart.data
          if (!data.labels || !data.datasets.length) return []
          const dataset = data.datasets[0]
          const total = dataset.data.reduce((a: number, b: number) => a + b, 0)
          return data.labels.map((label: string, i: number) => {
            const value = dataset.data[i]
            const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0'
            return {
              text: `${label}: $${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })} (${pct}%)`,
              fillStyle: dataset.backgroundColor[i],
              fontColor: '#e5e7eb',
              strokeStyle: dataset.borderColor,
              lineWidth: dataset.borderWidth,
              index: i,
            }
          })
        }
      }
    },
    tooltip: {
      callbacks: {
        label: (context: any) => {
          const value = context.raw as number
          const total = context.dataset.data.reduce((a: number, b: number) => a + b, 0)
          const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0'
          return ` $${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${pct}%)`
        }
      }
    }
  }
}

// --- Helpers ---

function fmt(val: number): string {
  return '$' + val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtTime(minutes: number): string {
  const hrs = minutes / 60
  return hrs.toFixed(1) + ' hrs'
}

function goBack() {
  router.push('/mrp/dashboard')
}

function printReport() {
  window.print()
}

function navigateToItem(itemNumber: string) {
  router.push(`/items?q=${itemNumber}`)
}
</script>

<template>
  <div class="report-page">
    <!-- Header -->
    <div class="header no-print">
      <h1>Cost Report</h1>
      <div class="header-actions">
        <select v-model="selectedProjectId" class="project-select">
          <option value="" disabled>Select Project...</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">
            {{ p.project_code }} - {{ p.description || 'Untitled' }}
          </option>
        </select>
        <button class="btn btn-print" @click="printReport" :disabled="!report">
          <span>&#x1F5B6;</span> Print
        </button>
        <button class="btn btn-back" @click="goBack">
          <span class="back-arrow">&larr;</span> Back to MRP
        </button>
      </div>
    </div>

    <!-- Print-only header -->
    <div class="print-header print-only">
      <h1 v-if="report">Cost Report: {{ report.project_code }}</h1>
      <p v-if="report">{{ report.description }} {{ report.customer ? '| Customer: ' + report.customer : '' }}</p>
    </div>

    <!-- Loading / Error -->
    <div v-if="loadingProjects || loading" class="loading-state">Loading...</div>
    <div v-else-if="error" class="error-state">{{ error }}</div>
    <div v-else-if="!report" class="loading-state">Select a project to view cost report</div>

    <!-- Report Content -->
    <template v-else>
      <!-- Project Info Bar -->
      <div class="project-info">
        <div class="project-title">
          <span class="project-code">{{ report.project_code }}</span>
          <span class="project-desc">{{ report.description }}</span>
          <span v-if="report.customer" class="project-customer">Customer: {{ report.customer }}</span>
        </div>
        <div class="project-total">
          <span class="total-label">Project Total</span>
          <span class="total-value">{{ fmt(report.total) }}</span>
          <span v-if="report.overhead_multiplier !== 1" class="overhead-note">
            (includes {{ ((report.overhead_multiplier - 1) * 100).toFixed(0) }}% overhead)
          </span>
        </div>
      </div>

      <!-- Chart + Summary Row -->
      <div class="chart-summary-row">
        <div class="chart-container">
          <Pie v-if="chartData" :data="chartData" :options="chartOptions" />
          <div v-else class="no-chart">No cost data to chart</div>
        </div>
        <div class="summary-cards">
          <div class="summary-card">
            <span class="card-label">Labor</span>
            <span class="card-value labor">{{ fmt(report.labor_cost) }}</span>
          </div>
          <div class="summary-card">
            <span class="card-label">Raw Material</span>
            <span class="card-value material">{{ fmt(report.material_cost) }}</span>
          </div>
          <div class="summary-card">
            <span class="card-label">Outsourced</span>
            <span class="card-value outsourced">{{ fmt(report.outsourced_cost) }}</span>
          </div>
          <div class="summary-card">
            <span class="card-label">Purchased Parts</span>
            <span class="card-value purchased">{{ fmt(report.purchased_cost) }}</span>
          </div>
          <div class="summary-card summary-subtotal">
            <span class="card-label">Subtotal</span>
            <span class="card-value">{{ fmt(report.subtotal) }}</span>
          </div>
          <div v-if="report.overhead_multiplier !== 1" class="summary-card">
            <span class="card-label">Overhead ({{ report.overhead_multiplier }}x)</span>
            <span class="card-value">{{ fmt(report.total - report.subtotal) }}</span>
          </div>
          <div class="summary-card summary-total">
            <span class="card-label">Total</span>
            <span class="card-value total">{{ fmt(report.total) }}</span>
          </div>
        </div>
      </div>

      <!-- Manufactured Items Table -->
      <div v-if="sortedManufacturedItems.length > 0" class="section">
        <h2>Manufactured Items <span class="count-badge">{{ sortedManufacturedItems.length }}</span></h2>
        <table class="report-table">
          <thead>
            <tr>
              <th>Item #</th>
              <th>Name</th>
              <th class="num">Qty</th>
              <th class="num">Material</th>
              <th class="num">Labor</th>
              <th class="num">Outsource</th>
              <th class="num">Unit Cost</th>
              <th class="num">Extended</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sortedManufacturedItems" :key="item.item_id">
              <td class="item-number" @click="navigateToItem(item.item_number)">{{ item.item_number }}</td>
              <td class="item-name">{{ item.name }}</td>
              <td class="num">{{ item.quantity }}</td>
              <td class="num">{{ item.material_cost > 0 ? fmt(item.material_cost) : '-' }}</td>
              <td class="num">{{ item.labor_cost > 0 ? fmt(item.labor_cost) : '-' }}</td>
              <td class="num">{{ item.outsourced_cost > 0 ? fmt(item.outsourced_cost) : '-' }}</td>
              <td class="num">{{ fmt(item.unit_cost) }}</td>
              <td class="num extended">{{ fmt(item.extended_cost) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="7" class="footer-label">Manufactured Total</td>
              <td class="num extended">{{ fmt(manufacturedTotal) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <!-- Operations Summary Table -->
      <div v-if="sortedOperations.length > 0" class="section">
        <h2>Operations Summary <span class="count-badge">{{ sortedOperations.length }}</span></h2>
        <table class="report-table">
          <thead>
            <tr>
              <th>Station</th>
              <th>Type</th>
              <th class="num">Parts</th>
              <th class="num">Total Time</th>
              <th class="num">Total Cost</th>
              <th>Items</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="op in sortedOperations" :key="op.station_code">
              <td class="station-name">
                <span class="station-code">{{ op.station_code }}</span>
                {{ op.station_name }}
              </td>
              <td>
                <span :class="['type-badge', op.is_outsourced ? 'outsourced' : 'in-house']">
                  {{ op.is_outsourced ? 'Outsourced' : 'In-House' }}
                </span>
              </td>
              <td class="num">{{ op.item_count }}</td>
              <td class="num">{{ op.is_outsourced ? '-' : fmtTime(op.total_time_min) }}</td>
              <td class="num extended">{{ fmt(op.total_cost) }}</td>
              <td class="items-cell">
                <span v-for="(item, idx) in op.items.slice(0, 8)" :key="item" class="item-tag" @click="navigateToItem(item)">
                  {{ item }}<span v-if="idx < Math.min(op.items.length, 8) - 1">, </span>
                </span>
                <span v-if="op.items.length > 8" class="more-items">+{{ op.items.length - 8 }} more</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Purchased Parts Table -->
      <div v-if="sortedPurchasedItems.length > 0" class="section">
        <h2>Purchased Parts <span class="count-badge">{{ sortedPurchasedItems.length }}</span></h2>
        <table class="report-table">
          <thead>
            <tr>
              <th>Item #</th>
              <th>Name</th>
              <th>Supplier</th>
              <th>Supplier PN</th>
              <th class="num">Qty</th>
              <th class="num">Unit Price</th>
              <th class="num">Extended</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in sortedPurchasedItems" :key="item.item_id">
              <td class="item-number" @click="navigateToItem(item.item_number)">{{ item.item_number }}</td>
              <td class="item-name">{{ item.name }}</td>
              <td>{{ item.supplier_name || '-' }}</td>
              <td class="supplier-pn">{{ item.supplier_pn || '-' }}</td>
              <td class="num">{{ item.quantity }}</td>
              <td class="num">{{ fmt(item.unit_price) }}</td>
              <td class="num extended">{{ fmt(item.extended_cost) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="6" class="footer-label">Purchased Total</td>
              <td class="num extended">{{ fmt(purchasedTotal) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* Page */
.report-page {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  padding: 20px;
}

/* Header */
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.project-select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #1e293b;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 14px;
  min-width: 300px;
  cursor: pointer;
}

.project-select:focus {
  outline: none;
  border-color: #38bdf8;
}

/* Buttons */
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

.btn-print {
  background: #1e293b;
  color: #e5e7eb;
}

.btn-print:hover:not(:disabled) {
  background: #334155;
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

/* Loading / Error */
.loading-state {
  text-align: center;
  padding: 40px;
  color: #9ca3af;
  font-size: 14px;
}

.error-state {
  text-align: center;
  padding: 40px;
  color: #fca5a5;
  font-size: 14px;
}

/* Project Info Bar */
.project-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #0f172a;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 20px;
}

.project-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.project-code {
  font-family: monospace;
  font-size: 18px;
  font-weight: 700;
  color: #38bdf8;
}

.project-desc {
  font-size: 15px;
  color: #e5e7eb;
}

.project-customer {
  font-size: 13px;
  color: #9ca3af;
}

.project-total {
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.total-label {
  font-size: 11px;
  color: #9ca3af;
  text-transform: uppercase;
}

.total-value {
  font-size: 28px;
  font-weight: 700;
  color: #10b981;
  font-family: monospace;
}

.overhead-note {
  font-size: 11px;
  color: #9ca3af;
}

/* Chart + Summary Row */
.chart-summary-row {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 20px;
  margin-bottom: 24px;
}

.chart-container {
  background: #0f172a;
  border-radius: 8px;
  padding: 20px;
  height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.no-chart {
  color: #9ca3af;
  font-size: 14px;
}

.summary-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-card {
  background: #0f172a;
  border-radius: 6px;
  padding: 10px 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-label {
  font-size: 13px;
  color: #9ca3af;
}

.card-value {
  font-family: monospace;
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
}

.card-value.labor { color: #3b82f6; }
.card-value.material { color: #f59e0b; }
.card-value.outsourced { color: #f97316; }
.card-value.purchased { color: #8b5cf6; }
.card-value.total { color: #10b981; }

.summary-subtotal {
  border-top: 1px solid #1e293b;
  padding-top: 12px;
  margin-top: 4px;
}

.summary-total {
  background: #020617;
  border: 1px solid #1e293b;
}

/* Sections */
.section {
  margin-bottom: 28px;
}

h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 12px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-badge {
  background: #1e293b;
  color: #9ca3af;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 10px;
}

/* Tables */
.report-table {
  width: 100%;
  border-collapse: collapse;
  background: #0f172a;
  border-radius: 8px;
  overflow: hidden;
}

.report-table th {
  background: #1e293b;
  padding: 10px 12px;
  text-align: left;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: #9ca3af;
}

.report-table th.num {
  text-align: right;
}

.report-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #1e293b;
  font-size: 13px;
}

.report-table td.num {
  text-align: right;
  font-family: monospace;
}

.report-table tr:hover {
  background: #020617;
}

.report-table tfoot td {
  border-top: 2px solid #1e293b;
  font-weight: 600;
  padding: 10px 12px;
}

.footer-label {
  text-align: right;
  font-size: 13px;
  color: #9ca3af;
}

.item-number {
  font-family: monospace;
  font-weight: 600;
  color: #38bdf8;
  cursor: pointer;
}

.item-number:hover {
  text-decoration: underline;
}

.item-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.extended {
  font-weight: 600;
  color: #e5e7eb;
}

/* Operations table */
.station-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.station-code {
  font-family: monospace;
  font-weight: 600;
  color: #38bdf8;
  font-size: 12px;
}

.type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.type-badge.in-house {
  background: #064e3b;
  color: #6ee7b7;
}

.type-badge.outsourced {
  background: #7c2d12;
  color: #fed7aa;
}

.items-cell {
  max-width: 300px;
  font-size: 12px;
  color: #9ca3af;
}

.item-tag {
  cursor: pointer;
  font-family: monospace;
}

.item-tag:hover {
  color: #38bdf8;
}

.more-items {
  color: #6b7280;
  font-style: italic;
}

/* Purchased table */
.supplier-pn {
  font-family: monospace;
  font-size: 12px;
}

/* Print-only / No-print */
.print-only {
  display: none;
}

.print-header h1 {
  font-size: 20px;
}

.print-header p {
  font-size: 14px;
  color: #666;
  margin: 4px 0 0 0;
}

/* Print styles */
@media print {
  .no-print {
    display: none !important;
  }

  .print-only {
    display: block !important;
  }

  .report-page {
    background: white;
    color: #1a1a1a;
    padding: 0;
    min-height: auto;
  }

  .project-info {
    background: #f5f5f5;
    border: 1px solid #ddd;
  }

  .project-code { color: #1a1a1a; }
  .project-desc { color: #333; }
  .project-customer { color: #666; }
  .total-value { color: #1a1a1a; }
  .total-label, .overhead-note { color: #666; }

  .chart-summary-row {
    grid-template-columns: 1fr 280px;
  }

  .chart-container {
    background: white;
    border: 1px solid #ddd;
    height: 280px;
  }

  .summary-cards {
    gap: 4px;
  }

  .summary-card {
    background: #f5f5f5;
    border: 1px solid #eee;
    padding: 6px 10px;
  }

  .card-label { color: #666; }
  .card-value { color: #1a1a1a; }
  .card-value.labor { color: #1d4ed8; }
  .card-value.material { color: #b45309; }
  .card-value.outsourced { color: #c2410c; }
  .card-value.purchased { color: #6d28d9; }
  .card-value.total { color: #059669; }

  .report-table {
    background: white;
    border: 1px solid #ddd;
  }

  .report-table th {
    background: #f0f0f0;
    color: #333;
    border-bottom: 2px solid #ccc;
  }

  .report-table td {
    border-bottom: 1px solid #eee;
    color: #1a1a1a;
  }

  .report-table tr:hover {
    background: transparent;
  }

  .item-number { color: #1a1a1a; }
  .station-code { color: #333; }
  .count-badge { background: #eee; color: #666; }
  .type-badge.in-house { background: #dcfce7; color: #166534; }
  .type-badge.outsourced { background: #ffedd5; color: #9a3412; }
  .items-cell { color: #666; }
  .footer-label { color: #666; }

  h2 { color: #1a1a1a; }

  .section {
    page-break-inside: avoid;
  }
}
</style>
