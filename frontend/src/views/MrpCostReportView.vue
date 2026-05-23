<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { supabase, API_BASE_URL } from '../services/supabase'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer])

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
  station_group: string
  is_outsourced: boolean
  total_time_min: number
  total_cost: number
  item_count: number
  items: string[]
}

interface GroupStation {
  station_code: string
  station_name: string
  is_outsourced: boolean
  total_time_min: number
  total_cost: number
}

interface OperationSummaryGrouped {
  group_name: string
  total_time_min: number
  total_cost: number
  station_count: number
  stations: GroupStation[]
}

interface ChartSlice {
  label: string
  value: number
  category: string
  station_group?: string
}

interface ChartSliceGrouped {
  label: string
  value: number
  category: string
  stations?: GroupStation[]
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
  operations_summary_grouped: OperationSummaryGrouped[]
  cost_breakdown_chart: ChartSlice[]
  cost_breakdown_chart_grouped: ChartSliceGrouped[]
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

// Grouping state for table view
const groupByStation = ref(true) // true = grouped view, false = individual stations

// Legend toggle state
const showDetailedLegend = ref(false) // false = groups, true = individual stations

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
      selectedProjectId.value = projects.value[0]!.id
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

const sortedOperationsGrouped = computed(() => {
  if (!report.value?.operations_summary_grouped) return []
  return [...report.value.operations_summary_grouped].sort(
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

// --- Chart (ECharts Nested Pie) ---

// Group-level colors
const groupColors: Record<string, string> = {
  'Weld': '#ef4444',        // Red
  'Assembly': '#8b5cf6',    // Purple
  'Fabrication': '#3b82f6', // Blue
  'QC': '#10b981',          // Green
  'Outsourced': '#f97316',  // Orange
  'Other': '#6b7280',       // Gray
  'Raw Material': '#f59e0b', // Amber
  'Purchased Parts': '#a855f7', // Purple
}

// Lighter versions for stations (inner ring)
const stationColors: Record<string, string[]> = {
  'Weld': ['#fecaca', '#fca5a5', '#f87171', '#ef4444'],
  'Assembly': ['#ddd6fe', '#c4b5fd', '#a78bfa', '#8b5cf6'],
  'Fabrication': ['#bfdbfe', '#93c5fd', '#60a5fa', '#3b82f6'],
  'QC': ['#a7f3d0', '#6ee7b7', '#34d399', '#10b981'],
  'Outsourced': ['#fed7aa', '#fdba74', '#fb923c', '#f97316'],
  'Other': ['#e5e7eb', '#d1d5db', '#9ca3af', '#6b7280'],
}

function getStationColor(groupName: string, index: number): string {
  const colors = stationColors[groupName] ?? stationColors['Other'] ?? ['#6b7280']
  return colors[index % colors.length] ?? '#6b7280'
}

// Inner ring data (individual stations)
const innerRingData = computed(() => {
  if (!report.value) return []

  const data: any[] = []
  const grouped = report.value.cost_breakdown_chart_grouped || []

  // Add individual stations from each group
  grouped.forEach(grp => {
    if (grp.category === 'labor_group' && grp.stations) {
      grp.stations.forEach((st, idx) => {
        if (st.total_cost > 0) {
          data.push({
            name: st.station_name,
            value: st.total_cost,
            groupName: grp.label,
            itemStyle: { color: getStationColor(grp.label, idx) },
          })
        }
      })
    }
  })

  // Add material, purchased, outsourced as single items
  if (report.value.material_cost > 0) {
    data.push({
      name: 'Raw Material',
      value: report.value.material_cost,
      groupName: 'Raw Material',
      itemStyle: { color: '#fcd34d' }, // Lighter amber
    })
  }
  if (report.value.purchased_cost > 0) {
    data.push({
      name: 'Purchased Parts',
      value: report.value.purchased_cost,
      groupName: 'Purchased Parts',
      itemStyle: { color: '#c4b5fd' }, // Lighter purple
    })
  }
  if (report.value.outsourced_cost > 0) {
    data.push({
      name: 'Outsourced Ops',
      value: report.value.outsourced_cost,
      groupName: 'Outsourced',
      itemStyle: { color: '#fdba74' }, // Lighter orange
    })
  }

  return data
})

// Outer ring data (groups)
const outerRingData = computed(() => {
  if (!report.value) return []

  const data: any[] = []
  const grouped = report.value.cost_breakdown_chart_grouped || []

  // Add labor groups
  grouped.forEach(grp => {
    if (grp.category === 'labor_group' && grp.value > 0) {
      data.push({
        name: grp.label,
        value: grp.value,
        itemStyle: { color: groupColors[grp.label] || groupColors['Other'] },
      })
    }
  })

  // Add non-labor categories
  if (report.value.material_cost > 0) {
    data.push({
      name: 'Raw Material',
      value: report.value.material_cost,
      itemStyle: { color: '#f59e0b' },
    })
  }
  if (report.value.purchased_cost > 0) {
    data.push({
      name: 'Purchased Parts',
      value: report.value.purchased_cost,
      itemStyle: { color: '#a855f7' },
    })
  }
  if (report.value.outsourced_cost > 0) {
    data.push({
      name: 'Outsourced',
      value: report.value.outsourced_cost,
      itemStyle: { color: '#f97316' },
    })
  }

  return data
})

// Legend data for right side - switches based on toggle
const legendData = computed(() => {
  if (showDetailedLegend.value) {
    return innerRingData.value.map(d => d.name)
  }
  return outerRingData.value.map(d => d.name)
})

const chartOptions = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'item',
    formatter: (params: any) => {
      const value = params.value
      const total = report.value?.subtotal || 1
      const pct = ((value / total) * 100).toFixed(1)
      const groupInfo = params.data.groupName ? `<br/><span style="color:#9ca3af">${params.data.groupName}</span>` : ''
      return `<strong>${params.name}</strong>${groupInfo}<br/>$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${pct}%)`
    },
    backgroundColor: '#1e293b',
    borderColor: '#334155',
    textStyle: { color: '#e5e7eb' },
  },
  legend: {
    orient: 'vertical',
    right: 10,
    top: 'center',
    textStyle: { color: '#e5e7eb', fontSize: 11 },
    itemWidth: 12,
    itemHeight: 12,
    itemGap: 6,
    data: legendData.value,
    formatter: (name: string) => {
      const dataSource = showDetailedLegend.value ? innerRingData.value : outerRingData.value
      const item = dataSource.find(d => d.name === name)
      if (!item) return name
      const total = report.value?.subtotal || 1
      const pct = ((item.value / total) * 100).toFixed(1)
      return `${name}: $${item.value.toLocaleString(undefined, { maximumFractionDigits: 0 })} (${pct}%)`
    },
  },
  series: [
    // Inner ring - individual stations
    {
      type: 'pie',
      radius: ['20%', '50%'],
      center: ['35%', '50%'],
      label: { show: false },
      labelLine: { show: false },
      itemStyle: {
        borderColor: '#020617',
        borderWidth: 1,
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)',
        },
      },
      data: innerRingData.value,
    },
    // Outer ring - groups
    {
      type: 'pie',
      radius: ['55%', '75%'],
      center: ['35%', '50%'],
      label: { show: false },
      labelLine: { show: false },
      itemStyle: {
        borderColor: '#020617',
        borderWidth: 2,
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)',
        },
      },
      data: outerRingData.value,
    },
  ],
}))

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
          <div class="chart-header">
            <span class="chart-title">Cost Breakdown</span>
            <div class="chart-controls">
              <button class="legend-toggle" @click="showDetailedLegend = !showDetailedLegend">
                {{ showDetailedLegend ? 'Show Groups' : 'Show Stations' }}
              </button>
              <span class="chart-hint">Inner: Stations | Outer: Groups</span>
            </div>
          </div>
          <v-chart
            v-if="innerRingData.length > 0"
            class="nested-pie-chart"
            :option="chartOptions"
            autoresize
          />
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
        <div class="section-header">
          <h2>
            Operations Summary
            <span class="count-badge">{{ groupByStation ? sortedOperationsGrouped.length + ' groups' : sortedOperations.length }}</span>
          </h2>
          <button class="view-toggle" @click="groupByStation = !groupByStation">
            {{ groupByStation ? 'Show All Stations' : 'Show Groups' }}
          </button>
        </div>

        <!-- Grouped View -->
        <table v-if="groupByStation" class="report-table">
          <thead>
            <tr>
              <th>Group</th>
              <th class="num">Stations</th>
              <th class="num">Total Time</th>
              <th class="num">Total Cost</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="grp in sortedOperationsGrouped" :key="grp.group_name">
              <tr class="group-row" :style="{ borderLeft: `4px solid ${groupColors[grp.group_name] || '#6b7280'}` }">
                <td class="group-name">
                  <span class="group-color" :style="{ background: groupColors[grp.group_name] || '#6b7280' }"></span>
                  {{ grp.group_name }}
                </td>
                <td class="num">{{ grp.station_count }}</td>
                <td class="num">{{ fmtTime(grp.total_time_min) }}</td>
                <td class="num extended">{{ fmt(grp.total_cost) }}</td>
              </tr>
              <tr v-for="st in grp.stations" :key="st.station_code" class="station-subrow">
                <td class="station-indent">
                  <span class="station-code">{{ st.station_code }}</span>
                  {{ st.station_name }}
                </td>
                <td class="num">-</td>
                <td class="num">{{ st.is_outsourced ? '-' : fmtTime(st.total_time_min) }}</td>
                <td class="num">{{ fmt(st.total_cost) }}</td>
              </tr>
            </template>
          </tbody>
        </table>

        <!-- Individual View -->
        <table v-else class="report-table">
          <thead>
            <tr>
              <th>Station</th>
              <th>Group</th>
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
                <span class="group-badge" :style="{ background: groupColors[op.station_group] || '#6b7280' }">
                  {{ op.station_group }}
                </span>
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
  height: 540px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
}

.chart-container > canvas,
.chart-container > div:not(.chart-header):not(.no-chart) {
  flex: 1;
  min-height: 0;
}

.no-chart {
  color: #9ca3af;
  font-size: 14px;
}

/* Chart header */
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  width: 100%;
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: #e5e7eb;
}

.chart-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.legend-toggle {
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid #1e293b;
  background: #020617;
  color: #9ca3af;
  font-size: 11px;
  cursor: pointer;
}

.legend-toggle:hover {
  background: #1e293b;
  color: #e5e7eb;
}

.chart-hint {
  font-size: 11px;
  color: #6b7280;
}

/* Nested pie chart */
.nested-pie-chart {
  flex: 1;
  min-height: 460px;
  width: 100%;
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

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

h2 {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.view-toggle {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #1e293b;
  background: #020617;
  color: #9ca3af;
  font-size: 12px;
  cursor: pointer;
}

.view-toggle:hover {
  background: #1e293b;
  color: #e5e7eb;
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

/* Group table styles */
.group-row {
  background: #0c1222;
}

.group-row:hover {
  background: #0f172a;
}

.group-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
}

.group-color {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.station-subrow {
  background: #020617;
}

.station-subrow td {
  font-size: 12px;
  color: #9ca3af;
}

.station-indent {
  padding-left: 32px !important;
}

.group-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
  color: white;
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
