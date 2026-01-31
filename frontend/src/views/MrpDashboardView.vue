<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { supabase, API_BASE_URL } from '../services/supabase'
import NestConfigModal from '../components/NestConfigModal.vue'
import type { NestGroup, NestJob, NestSheet } from '../types'

const router = useRouter()

interface ProjectPart {
  id: string
  item_id: string
  item_number: string
  name: string
  quantity: number
  is_assembly: boolean
  has_routing: boolean
  is_manual: boolean
  est_time_min: number
}

interface ProjectAssembly {
  id: string
  item_id: string
  item_number: string
  name: string
  quantity: number
}

interface MrpProject {
  id: string
  project_code: string
  description: string
  customer: string
  due_date: string
  start_date: string
  status: string
  top_assembly_id: string
  created_at: string
  assemblies?: ProjectAssembly[]
  parts?: ProjectPart[]
  print_packet_path?: string
  print_packet_generated_at?: string
}

const projects = ref<MrpProject[]>([])
const selectedProject = ref<MrpProject | null>(null)
const loading = ref(true)
const loadingParts = ref(false)
const error = ref('')
const showNewProjectModal = ref(false)
const showDetailPanel = ref(false)
const addAssemblyInput = ref('')
const addingAssembly = ref(false)
const updatingBom = ref(false)
const addPartInput = ref('')
const addingPart = ref(false)
const generatingPacket = ref(false)
const packetSuccess = ref('')
const packetUrl = ref<string | null>(null)

// Nesting state
const showNestModal = ref(false)
const nestGroups = ref<NestGroup[]>([])
const loadingNestGroups = ref(false)
const nestJobs = ref<NestJob[]>([])
const nestResults = ref<Map<string, NestSheet[]>>(new Map())
const nestPollingInterval = ref<ReturnType<typeof setInterval> | null>(null)

const newProject = ref({
  project_code: '',
  description: '',
  customer: '',
  due_date: '',
  start_date: ''
})

const statusOptions = ['Setup', 'Released', 'On Hold', 'Complete']

// Cost estimate state
interface CostEstimate {
  labor_cost: number
  material_cost: number
  outsourced_cost: number
  purchased_cost: number
  overhead_multiplier: number
  subtotal: number
  total: number
}
const projectCost = ref<CostEstimate | null>(null)
const loadingCost = ref(false)

// Computed properties for selected project
const projectParts = computed(() => selectedProject.value?.parts || [])

const assemblies = computed(() =>
  projectParts.value.filter(p => p.is_assembly)
)

const parts = computed(() =>
  projectParts.value.filter(p => !p.is_assembly)
)

const unroutedParts = computed(() =>
  projectParts.value.filter(p => !p.has_routing && !p.is_assembly)
)

const totalParts = computed(() => projectParts.value.length)

const totalHours = computed(() => {
  const totalMinutes = projectParts.value.reduce((sum, p) => sum + (p.quantity * p.est_time_min), 0)
  return Math.round(totalMinutes / 60 * 10) / 10
})

async function loadProjects() {
  loading.value = true
  error.value = ''

  try {
    const { data, error: queryError } = await supabase
      .from('mrp_projects')
      .select('*')
      .order('due_date', { ascending: true })

    if (queryError) throw queryError

    // Single query for all part counts (avoids N+1 hang risk)
    const { data: countData, error: countError } = await supabase
      .from('mrp_project_parts')
      .select('project_id')

    if (countError) throw countError

    const counts = new Map<string, number>()
    ;(countData || []).forEach((row: any) => {
      counts.set(row.project_id, (counts.get(row.project_id) || 0) + 1)
    })

    projects.value = (data || []).map(p => ({
      ...p,
      part_count: counts.get(p.id) || 0
    }))
  } catch (e: any) {
    error.value = e.message || 'Failed to load projects'
  } finally {
    loading.value = false
  }
}

async function refreshDashboard() {
  const previousProjectId = selectedProject.value?.id
  await loadProjects()
  if (previousProjectId) {
    const target = projects.value.find(p => p.id === previousProjectId)
    if (target) {
      selectedProject.value = target
      showDetailPanel.value = true
      await loadProjectParts(target.id)
    }
  }
}

async function loadProjectParts(projectId: string) {
  loadingParts.value = true

  try {
    const { data, error: queryError } = await supabase
      .from('mrp_project_parts')
      .select(`
        id,
        item_id,
        quantity,
        is_manual,
        items(item_number, name, is_supplier_part)
      `)
      .eq('project_id', projectId)
      .order('created_at', { ascending: true })

    if (queryError) throw queryError

    // Get routing info for each part
    const partsWithRouting = await Promise.all((data || []).map(async (pp: any) => {
      // Fetch routing steps for this item (to check existence + sum est_time_min)
      const { data: routingData } = await supabase
        .from('routing')
        .select('est_time_min')
        .eq('item_id', pp.item_id)

      const routingSteps = routingData || []
      const estTimeMin = routingSteps.reduce((sum: number, r: any) => sum + (r.est_time_min || 0), 0)

      // Check if it's an assembly (has children in BOM)
      const { count: bomCount } = await supabase
        .from('bom')
        .select('*', { count: 'exact', head: true })
        .eq('parent_item_id', pp.item_id)

      return {
        id: pp.id,
        item_id: pp.item_id,
        item_number: pp.items?.item_number || '',
        name: pp.items?.name || '',
        quantity: pp.quantity,
        is_assembly: (bomCount || 0) > 0,
        has_routing: routingSteps.length > 0,
        is_manual: pp.is_manual || false,
        est_time_min: estTimeMin
      }
    }))

    if (selectedProject.value) {
      selectedProject.value.parts = partsWithRouting
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load project parts'
  } finally {
    loadingParts.value = false
  }
}

async function selectProject(project: MrpProject) {
  selectedProject.value = { ...project, parts: [] }
  showDetailPanel.value = true
  packetUrl.value = null  // Clear packet URL when switching projects
  packetSuccess.value = ''
  projectCost.value = null

  // Load parts, assemblies, cost estimate, and check for existing print packet in parallel
  await Promise.all([
    loadProjectParts(project.id),
    loadProjectAssemblies(project.id),
    loadExistingPacket(project.id),
    loadCostEstimate(project.id)
  ])
}

async function loadCostEstimate(projectId: string) {
  loadingCost.value = true
  try {
    const response = await fetch(`${API_BASE_URL}/mrp/projects/${projectId}/cost-estimate`)
    if (response.ok) {
      projectCost.value = await response.json()
    }
  } catch (e) {
    console.debug('Failed to load cost estimate:', e)
  } finally {
    loadingCost.value = false
  }
}

async function loadExistingPacket(projectId: string) {
  try {
    const response = await fetch(`${API_BASE_URL}/mrp/projects/${projectId}/print-packet`)

    if (response.ok) {
      const data = await response.json()
      if (data.url) {
        packetUrl.value = data.url
      }
    }
    // 404 means no packet exists - that's fine, just don't set URL
  } catch (e) {
    // Ignore errors - packet just won't be available
    console.debug('No existing print packet:', e)
  }
}

function closeDetailPanel() {
  showDetailPanel.value = false
  selectedProject.value = null
}

async function createProject() {
  try {
    const { data, error: insertError } = await supabase
      .from('mrp_projects')
      .insert({
        project_code: newProject.value.project_code,
        description: newProject.value.description,
        customer: newProject.value.customer,
        due_date: newProject.value.due_date || null,
        start_date: newProject.value.start_date || null
      })
      .select()
      .single()

    if (insertError) throw insertError

    showNewProjectModal.value = false
    newProject.value = { project_code: '', description: '', customer: '', due_date: '', start_date: '' }
    await loadProjects()

    // Auto-select the new project
    if (data) {
      selectProject(data)
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to create project'
  }
}

async function updateProjectStatus(status: string) {
  if (!selectedProject.value) return

  try {
    const { error: updateError } = await supabase
      .from('mrp_projects')
      .update({ status })
      .eq('id', selectedProject.value.id)

    if (updateError) throw updateError
    selectedProject.value.status = status

    // Update in list
    const idx = projects.value.findIndex(p => p.id === selectedProject.value?.id)
    if (idx !== -1) {
      projects.value[idx].status = status
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to update status'
  }
}

async function loadProjectAssemblies(projectId: string) {
  const { data, error: queryError } = await supabase
    .from('mrp_project_assemblies')
    .select(`
      id,
      item_id,
      quantity,
      items(item_number, name)
    `)
    .eq('project_id', projectId)
    .order('created_at', { ascending: true })

  if (queryError) throw queryError

  const assemblies: ProjectAssembly[] = (data || []).map((a: any) => ({
    id: a.id,
    item_id: a.item_id,
    item_number: a.items?.item_number || '',
    name: a.items?.name || '',
    quantity: a.quantity
  }))

  if (selectedProject.value) {
    selectedProject.value.assemblies = assemblies
  }
}

async function addAssembly() {
  if (!selectedProject.value || !addAssemblyInput.value.trim()) return

  addingAssembly.value = true
  error.value = ''

  try {
    const itemNumber = addAssemblyInput.value.trim().toLowerCase()

    const { data: item, error: itemError } = await supabase
      .from('items')
      .select('id, item_number, name')
      .eq('item_number', itemNumber)
      .single()

    if (itemError || !item) {
      throw new Error(`Item "${itemNumber}" not found`)
    }

    const { error: insertError } = await supabase
      .from('mrp_project_assemblies')
      .insert({
        project_id: selectedProject.value.id,
        item_id: item.id,
        quantity: 1
      })

    if (insertError) {
      if (insertError.code === '23505') {
        throw new Error(`Assembly "${itemNumber}" is already in this project`)
      }
      throw insertError
    }

    addAssemblyInput.value = ''
    await loadProjectAssemblies(selectedProject.value.id)
  } catch (e: any) {
    error.value = e.message || 'Failed to add assembly'
  } finally {
    addingAssembly.value = false
  }
}

async function removeAssembly(assemblyId: string) {
  if (!selectedProject.value) return

  try {
    const { error: deleteError } = await supabase
      .from('mrp_project_assemblies')
      .delete()
      .eq('id', assemblyId)

    if (deleteError) throw deleteError

    await loadProjectAssemblies(selectedProject.value.id)
  } catch (e: any) {
    error.value = e.message || 'Failed to remove assembly'
  }
}

async function updateAssemblyQty(assemblyId: string, newQty: number) {
  if (!selectedProject.value || newQty < 1) return

  try {
    const { error: updateError } = await supabase
      .from('mrp_project_assemblies')
      .update({ quantity: newQty })
      .eq('id', assemblyId)

    if (updateError) throw updateError

    const asm = selectedProject.value.assemblies?.find(a => a.id === assemblyId)
    if (asm) asm.quantity = newQty
  } catch (e: any) {
    error.value = e.message || 'Failed to update assembly quantity'
  }
}

async function updateBom() {
  if (!selectedProject.value) return

  const assemblies = selectedProject.value.assemblies || []
  if (assemblies.length === 0) {
    error.value = 'Add at least one assembly before updating BOM'
    return
  }

  updatingBom.value = true
  error.value = ''

  try {
    const projectId = selectedProject.value.id

    // 1. Delete all BOM-derived parts
    const { error: deleteError } = await supabase
      .from('mrp_project_parts')
      .delete()
      .eq('project_id', projectId)
      .eq('is_manual', false)

    if (deleteError) throw deleteError

    // 2. Add top-level assemblies as parts (they are produced items too)
    const allParts = new Map<string, { item_id: string, quantity: number }>()

    for (const asm of assemblies) {
      allParts.set(asm.item_id, { item_id: asm.item_id, quantity: asm.quantity })
    }

    // 3. Recursively explode all assemblies (skip top assemblies in BOM children to avoid double-counting)
    const topAssemblyIds = new Set(assemblies.map(a => a.item_id))

    for (const asm of assemblies) {
      await explodeBomRecursive(asm.item_id, asm.quantity, allParts, topAssemblyIds)
    }

    // 4. Get manual parts to avoid conflicts
    const { data: manualParts } = await supabase
      .from('mrp_project_parts')
      .select('item_id')
      .eq('project_id', projectId)
      .eq('is_manual', true)

    const manualItemIds = new Set((manualParts || []).map(p => p.item_id))

    // 5. Insert BOM-derived parts (skip items that exist as manual)
    const newParts = Array.from(allParts.entries())
      .filter(([itemId]) => !manualItemIds.has(itemId))
      .map(([_, part]) => ({
        project_id: projectId,
        item_id: part.item_id,
        quantity: part.quantity,
        is_manual: false
      }))

    if (newParts.length > 0) {
      const { error: insertError } = await supabase
        .from('mrp_project_parts')
        .insert(newParts)

      if (insertError) throw insertError
    }

    // 6. Update top_assembly_id for backward compat
    await supabase
      .from('mrp_projects')
      .update({ top_assembly_id: assemblies[0].item_id })
      .eq('id', projectId)

    await loadProjectParts(projectId)
    await loadProjects()
  } catch (e: any) {
    error.value = e.message || 'Failed to update BOM'
  } finally {
    updatingBom.value = false
  }
}

async function addManualPart() {
  if (!selectedProject.value || !addPartInput.value.trim()) return

  addingPart.value = true
  error.value = ''

  try {
    const itemNumber = addPartInput.value.trim().toLowerCase()

    const { data: item, error: itemError } = await supabase
      .from('items')
      .select('id, item_number')
      .eq('item_number', itemNumber)
      .single()

    if (itemError || !item) {
      throw new Error(`Item "${itemNumber}" not found`)
    }

    const existing = projectParts.value.find(p => p.item_id === item.id)
    if (existing) {
      throw new Error(`"${itemNumber}" is already in this project`)
    }

    const { error: insertError } = await supabase
      .from('mrp_project_parts')
      .insert({
        project_id: selectedProject.value.id,
        item_id: item.id,
        quantity: 1,
        is_manual: true
      })

    if (insertError) throw insertError

    addPartInput.value = ''
    await loadProjectParts(selectedProject.value.id)
    await loadProjects()
  } catch (e: any) {
    error.value = e.message || 'Failed to add part'
  } finally {
    addingPart.value = false
  }
}

async function removeProjectPart(partId: string) {
  if (!selectedProject.value) return

  try {
    const { error: deleteError } = await supabase
      .from('mrp_project_parts')
      .delete()
      .eq('id', partId)

    if (deleteError) throw deleteError

    await loadProjectParts(selectedProject.value.id)
    await loadProjects()
  } catch (e: any) {
    error.value = e.message || 'Failed to remove part'
  }
}

async function updatePartQty(partId: string, newQty: number) {
  if (!selectedProject.value || newQty < 1) return

  try {
    const { error: updateError } = await supabase
      .from('mrp_project_parts')
      .update({ quantity: newQty })
      .eq('id', partId)

    if (updateError) throw updateError

    const part = projectParts.value.find(p => p.id === partId)
    if (part) part.quantity = newQty
  } catch (e: any) {
    error.value = e.message || 'Failed to update quantity'
  }
}

async function explodeBomRecursive(
  parentId: string,
  parentQty: number,
  parts: Map<string, { item_id: string, quantity: number }>,
  excludeIds?: Set<string>
) {
  const { data: bomEntries } = await supabase
    .from('bom')
    .select('child_item_id, quantity')
    .eq('parent_item_id', parentId)

  if (!bomEntries || bomEntries.length === 0) return

  for (const entry of bomEntries) {
    const totalQty = entry.quantity * parentQty

    // Skip top-level assemblies (they're tracked separately)
    if (excludeIds && excludeIds.has(entry.child_item_id)) continue

    const existing = parts.get(entry.child_item_id)

    if (existing) {
      existing.quantity += totalQty
    } else {
      parts.set(entry.child_item_id, { item_id: entry.child_item_id, quantity: totalQty })
    }

    // Recurse into children
    await explodeBomRecursive(entry.child_item_id, totalQty, parts, excludeIds)
  }
}

async function deleteProject() {
  if (!selectedProject.value) return
  if (!confirm(`Delete project ${selectedProject.value.project_code}? This will also delete all associated parts.`)) return

  try {
    // Delete project assemblies first
    await supabase
      .from('mrp_project_assemblies')
      .delete()
      .eq('project_id', selectedProject.value.id)

    // Delete project parts
    await supabase
      .from('mrp_project_parts')
      .delete()
      .eq('project_id', selectedProject.value.id)

    // Delete project
    const { error: deleteError } = await supabase
      .from('mrp_projects')
      .delete()
      .eq('id', selectedProject.value.id)

    if (deleteError) throw deleteError

    closeDetailPanel()
    await loadProjects()
  } catch (e: any) {
    error.value = e.message || 'Failed to delete project'
  }
}

async function generatePrintPacket() {
  if (!selectedProject.value) return

  generatingPacket.value = true
  error.value = ''
  packetSuccess.value = ''
  packetUrl.value = null

  try {
    const response = await fetch(`${API_BASE_URL}/mrp/projects/${selectedProject.value.id}/print-packet`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      const data = await response.json()
      throw new Error(data.detail || 'Failed to generate print packet')
    }

    const data = await response.json()

    if (data.url) {
      packetUrl.value = data.url
      packetSuccess.value = 'Print packet generated!'
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to generate print packet'
  } finally {
    generatingPacket.value = false
  }
}

function downloadPacket() {
  if (packetUrl.value) {
    window.open(packetUrl.value, '_blank')
  }
}

function goToRouting(itemNumber?: string) {
  if (itemNumber) {
    router.push({ path: '/mrp/routing', query: { item: itemNumber } })
  } else {
    router.push('/mrp/routing')
  }
}

function getStatusClass(status: string) {
  const classes: Record<string, string> = {
    'Setup': 'status-setup',
    'Released': 'status-released',
    'On Hold': 'status-hold',
    'Complete': 'status-complete'
  }
  return classes[status] || ''
}

function formatDate(date: string) {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

function goHome() {
  router.push('/')
}

function goToShop() {
  router.push('/mrp/shop')
}

function goToRawMaterials() {
  router.push('/mrp/materials')
}

function goToPartLookup() {
  router.push('/mrp/parts')
}

function goToProjectTracking() {
  router.push('/mrp/tracking')
}

function goToCostSettings() {
  router.push('/mrp/settings')
}

// === Nesting Functions ===

async function openNestModal() {
  if (!selectedProject.value) return
  showNestModal.value = true
  loadingNestGroups.value = true
  nestGroups.value = []

  try {
    const response = await fetch(`${API_BASE_URL}/nesting/projects/${selectedProject.value.id}/groups`)
    if (!response.ok) throw new Error('Failed to load nest groups')
    const data = await response.json()
    nestGroups.value = data.groups
  } catch (e: any) {
    error.value = e.message || 'Failed to load nest groups'
  } finally {
    loadingNestGroups.value = false
  }
}

async function submitNestJob(config: {
  material: string
  thickness: number
  sheetWidth: number
  sheetHeight: number
  sheetLabel: string
  spacing: number
  margin: number
  rotationStep: number
}) {
  if (!selectedProject.value) return
  showNestModal.value = false

  try {
    const response = await fetch(`${API_BASE_URL}/nesting/projects/${selectedProject.value.id}/nest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        material: config.material,
        thickness: config.thickness,
        sheet_width_in: config.sheetWidth,
        sheet_height_in: config.sheetHeight,
        sheet_label: config.sheetLabel,
        spacing_in: config.spacing,
        margin_in: config.margin,
        rotation_step_deg: config.rotationStep,
      }),
    })

    if (!response.ok) {
      const data = await response.json()
      throw new Error(data.detail || 'Failed to create nest job')
    }

    // Refresh nest jobs list and start polling
    await loadNestJobs()
    startNestPolling()
  } catch (e: any) {
    error.value = e.message || 'Failed to start nesting'
  }
}

async function loadNestJobs() {
  if (!selectedProject.value) return

  try {
    const response = await fetch(`${API_BASE_URL}/nesting/projects/${selectedProject.value.id}/jobs`)
    if (!response.ok) return
    const data = await response.json()
    nestJobs.value = data.jobs || []

    // Load results for completed jobs
    for (const job of nestJobs.value) {
      if (job.status === 'completed' && !nestResults.value.has(job.id)) {
        await loadNestJobResults(job.id)
      }
    }
  } catch (e) {
    console.debug('Failed to load nest jobs:', e)
  }
}

async function loadNestJobResults(jobId: string) {
  try {
    const response = await fetch(`${API_BASE_URL}/nesting/jobs/${jobId}`)
    if (!response.ok) return
    const data = await response.json()
    if (data.results && data.results.length > 0) {
      nestResults.value.set(jobId, data.results)
    }
  } catch (e) {
    console.debug('Failed to load nest results:', e)
  }
}

function startNestPolling() {
  stopNestPolling()
  nestPollingInterval.value = setInterval(async () => {
    const hasActive = nestJobs.value.some(j => j.status === 'pending' || j.status === 'processing')
    if (!hasActive) {
      stopNestPolling()
      return
    }
    await loadNestJobs()
  }, 3000)
}

function stopNestPolling() {
  if (nestPollingInterval.value) {
    clearInterval(nestPollingInterval.value)
    nestPollingInterval.value = null
  }
}

async function downloadNestSheet(jobId: string, sheetIndex: number) {
  try {
    const response = await fetch(`${API_BASE_URL}/nesting/jobs/${jobId}/sheets/${sheetIndex}/download`)
    if (!response.ok) throw new Error('Failed to get download URL')
    const data = await response.json()
    if (data.url) {
      window.open(data.url, '_blank')
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to download sheet'
  }
}

async function previewNestSheet(jobId: string, sheetIndex: number) {
  try {
    const response = await fetch(`${API_BASE_URL}/nesting/jobs/${jobId}/sheets/${sheetIndex}/svg`)
    if (!response.ok) throw new Error('SVG preview not available')
    const data = await response.json()
    if (data.url) {
      window.open(data.url, '_blank')
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load SVG preview'
  }
}

async function deleteNestJob(jobId: string) {
  if (!confirm('Delete this nest job and its output files?')) return
  try {
    const response = await fetch(`${API_BASE_URL}/nesting/jobs/${jobId}`, { method: 'DELETE' })
    if (!response.ok) throw new Error('Failed to delete nest job')
    // Remove from local state
    nestJobs.value = nestJobs.value.filter(j => j.id !== jobId)
    nestResults.value.delete(jobId)
  } catch (e: any) {
    error.value = e.message || 'Failed to delete nest job'
  }
}

function formatUtilization(util: number | null | undefined): string {
  if (util == null) return '-'
  return `${(util * 100).toFixed(1)}%`
}

// Load nest jobs when project is selected
watch(selectedProject, async (newVal) => {
  nestJobs.value = []
  nestResults.value = new Map()
  stopNestPolling()
  if (newVal) {
    await loadNestJobs()
    const hasActive = nestJobs.value.some(j => j.status === 'pending' || j.status === 'processing')
    if (hasActive) startNestPolling()
  }
})

onMounted(() => {
  loadProjects()
})

onUnmounted(() => {
  stopNestPolling()
})
</script>

<template>
  <div class="mrp-dashboard">
    <header class="page-header">
      <div class="header-left">
        <h1>MRP Dashboard</h1>
      </div>
      <div class="header-actions">
        <button class="nav-btn routing" @click="goToRouting()">
          <span class="nav-dot routing"></span>
          Routing Editor
        </button>
        <button class="nav-btn materials" @click="goToRawMaterials">
          <span class="nav-dot materials"></span>
          Raw Materials
        </button>
        <button class="nav-btn shop" @click="goToShop">
          <span class="nav-dot shop"></span>
          Shop Terminal
        </button>
        <button class="nav-btn lookup" @click="goToPartLookup">
          <span class="nav-dot lookup"></span>
          Part Lookup
        </button>
        <button class="nav-btn settings" @click="goToCostSettings">
          <span class="nav-dot settings"></span>
          Cost Settings
        </button>
        <button class="nav-btn tracking" @click="goToProjectTracking">
          <span class="nav-dot tracking"></span>
          Project Tracking
        </button>
        <button class="refresh-btn" @click="refreshDashboard" :disabled="loading">
          <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i>
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
        <button class="primary-btn" @click="showNewProjectModal = true">
          <i class="pi pi-plus"></i>
          New Project
        </button>
      </div>
    </header>

    <div v-if="error" class="error-message">
      <i class="pi pi-exclamation-triangle"></i>
      {{ error }}
      <button class="dismiss-btn" @click="error = ''">&times;</button>
    </div>

    <div v-if="packetSuccess" class="success-message">
      <i class="pi pi-check-circle"></i>
      {{ packetSuccess }}
      <button class="dismiss-btn" @click="packetSuccess = ''">&times;</button>
    </div>

    <div class="main-content">
      <!-- Projects Table -->
      <div class="projects-table-container" :class="{ 'panel-open': showDetailPanel }">
        <div v-if="loading" class="loading">
          <i class="pi pi-spin pi-spinner"></i>
          Loading projects...
        </div>

        <table v-else-if="projects.length > 0" class="projects-table">
          <thead>
            <tr>
              <th>Project Code</th>
              <th>Description</th>
              <th>Customer</th>
              <th>Due Date</th>
              <th>Status</th>
              <th>Parts</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="project in projects"
              :key="project.id"
              :class="{ selected: selectedProject?.id === project.id }"
              @click="selectProject(project)"
            >
              <td class="project-code">{{ project.project_code }}</td>
              <td>{{ project.description || '-' }}</td>
              <td>{{ project.customer || '-' }}</td>
              <td>{{ formatDate(project.due_date) }}</td>
              <td>
                <span :class="['status-badge', getStatusClass(project.status)]">
                  {{ project.status }}
                </span>
              </td>
              <td>{{ project.part_count || 0 }}</td>
            </tr>
          </tbody>
        </table>

        <div v-else class="empty-state">
          <i class="pi pi-inbox"></i>
          <p>No MRP projects yet</p>
          <button class="primary-btn" @click="showNewProjectModal = true">
            Create First Project
          </button>
        </div>
      </div>

      <!-- Project Detail Panel -->
      <div class="detail-panel" :class="{ open: showDetailPanel }">
        <template v-if="selectedProject">
          <div class="panel-header">
            <h2>{{ selectedProject.project_code }}</h2>
            <button class="close-btn" @click="closeDetailPanel">&times;</button>
          </div>

          <div class="panel-content">
            <!-- Project Info -->
            <div class="info-section">
              <div class="info-row">
                <span class="label">Description</span>
                <span class="value">{{ selectedProject.description || '-' }}</span>
              </div>
              <div class="info-row">
                <span class="label">Customer</span>
                <span class="value">{{ selectedProject.customer || '-' }}</span>
              </div>
              <div class="info-row">
                <span class="label">Assemblies</span>
                <span class="value">{{ (selectedProject.assemblies?.length || 0) }} top-level</span>
              </div>
            </div>

            <!-- Stats Row -->
            <div class="stats-row">
              <div class="stat-box">
                <div class="stat-value">{{ formatDate(selectedProject.due_date) }}</div>
                <div class="stat-label">Due Date</div>
              </div>
              <div class="stat-box">
                <div class="stat-value">{{ formatDate(selectedProject.start_date) }}</div>
                <div class="stat-label">Start Date</div>
              </div>
              <div class="stat-box">
                <div class="stat-value">{{ totalParts }}</div>
                <div class="stat-label">Total Parts</div>
              </div>
              <div class="stat-box">
                <div class="stat-value">{{ totalHours }}h</div>
                <div class="stat-label">Est. Hours</div>
              </div>
              <div class="stat-box cost-stat" v-if="projectCost">
                <div class="stat-value">${{ Math.round(projectCost.total).toLocaleString() }}</div>
                <div class="stat-label">Est. Cost</div>
              </div>
              <div class="stat-box cost-stat" v-else-if="loadingCost">
                <div class="stat-value">...</div>
                <div class="stat-label">Est. Cost</div>
              </div>
            </div>

            <!-- Cost Breakdown -->
            <div v-if="projectCost && projectCost.total > 0" class="cost-breakdown">
              <div class="section-label">Cost Breakdown</div>
              <div class="cost-rows">
                <div v-if="projectCost.labor_cost > 0" class="cost-row">
                  <span class="cost-label">Labor</span>
                  <span class="cost-value">${{ projectCost.labor_cost.toFixed(2) }}</span>
                </div>
                <div v-if="projectCost.material_cost > 0" class="cost-row">
                  <span class="cost-label">Material</span>
                  <span class="cost-value">${{ projectCost.material_cost.toFixed(2) }}</span>
                </div>
                <div v-if="projectCost.outsourced_cost > 0" class="cost-row">
                  <span class="cost-label">Outsourced</span>
                  <span class="cost-value">${{ projectCost.outsourced_cost.toFixed(2) }}</span>
                </div>
                <div v-if="projectCost.purchased_cost > 0" class="cost-row">
                  <span class="cost-label">Purchased</span>
                  <span class="cost-value">${{ projectCost.purchased_cost.toFixed(2) }}</span>
                </div>
                <div class="cost-row cost-total">
                  <span class="cost-label">Total</span>
                  <span class="cost-value">${{ projectCost.total.toFixed(2) }}</span>
                </div>
              </div>
            </div>

            <!-- Status -->
            <div class="status-section">
              <span class="label">Status</span>
              <select
                :value="selectedProject.status"
                @change="updateProjectStatus(($event.target as HTMLSelectElement).value)"
                :class="['status-select', getStatusClass(selectedProject.status)]"
              >
                <option v-for="status in statusOptions" :key="status" :value="status">
                  {{ status }}
                </option>
              </select>
            </div>

            <!-- Assembly List -->
            <div class="assembly-section">
              <div class="section-label">Top Assemblies</div>

              <div v-if="selectedProject.assemblies && selectedProject.assemblies.length > 0" class="assembly-list">
                <div v-for="asm in selectedProject.assemblies" :key="asm.id" class="assembly-item">
                  <span class="assembly-number">{{ asm.item_number }}</span>
                  <span class="assembly-name">{{ asm.name }}</span>
                  <button class="icon-btn danger" @click="removeAssembly(asm.id)" title="Remove assembly">
                    <i class="pi pi-times"></i>
                  </button>
                  <span class="assembly-qty-label">Qty:</span>
                  <input
                    type="number"
                    :value="asm.quantity"
                    min="1"
                    class="qty-input"
                    @change="updateAssemblyQty(asm.id, parseInt(($event.target as HTMLInputElement).value) || 1)"
                  />
                </div>
              </div>

              <div v-else class="empty-assembly-hint">
                No assemblies added yet
              </div>

              <div class="add-assembly-row">
                <input
                  v-model="addAssemblyInput"
                  placeholder="e.g., csa00010"
                  @keyup.enter="addAssembly"
                />
                <button
                  class="secondary-btn"
                  @click="addAssembly"
                  :disabled="addingAssembly || !addAssemblyInput.trim()"
                >
                  <i v-if="addingAssembly" class="pi pi-spin pi-spinner"></i>
                  <span v-else>+ Add</span>
                </button>
                <button
                  class="update-bom-btn"
                  @click="updateBom"
                  :disabled="updatingBom || !selectedProject.assemblies?.length"
                >
                  <i v-if="updatingBom" class="pi pi-spin pi-spinner"></i>
                  <span v-else>Update</span>
                </button>
              </div>
            </div>

            <!-- Unrouted Parts Warning -->
            <div v-if="unroutedParts.length > 0" class="section warning-section">
              <div class="section-header warning">
                <i class="pi pi-exclamation-triangle"></i>
                Unrouted Parts ({{ unroutedParts.length }})
              </div>
              <div class="parts-list">
                <div
                  v-for="part in unroutedParts"
                  :key="part.id"
                  class="part-item clickable"
                >
                  <span class="part-number" @click="goToRouting(part.item_number)">
                    {{ part.item_number }} <i class="pi pi-arrow-right"></i>
                    <span v-if="part.is_manual" class="manual-badge" title="Manually added">M</span>
                  </span>
                  <div class="part-actions">
                    <span class="part-qty-label">Qty:</span>
                    <input
                      type="number"
                      :value="part.quantity"
                      min="1"
                      class="qty-input"
                      @change="updatePartQty(part.id, parseInt(($event.target as HTMLInputElement).value) || 1)"
                      @click.stop
                    />
                    <button class="icon-btn danger" @click.stop="removeProjectPart(part.id)" title="Remove part">
                      <i class="pi pi-times"></i>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Assemblies -->
            <div v-if="assemblies.length > 0" class="section">
              <div class="section-header">Assemblies ({{ assemblies.length }})</div>
              <div class="parts-list">
                <div v-for="asm in assemblies" :key="asm.id" class="part-item">
                  <span class="part-number">{{ asm.item_number }}</span>
                  <div class="part-actions">
                    <span class="part-qty-label">Qty:</span>
                    <input
                      type="number"
                      :value="asm.quantity"
                      min="1"
                      class="qty-input"
                      @change="updatePartQty(asm.id, parseInt(($event.target as HTMLInputElement).value) || 1)"
                    />
                    <button class="icon-btn danger" @click="removeProjectPart(asm.id)" title="Remove">
                      <i class="pi pi-times"></i>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Parts -->
            <div v-if="parts.length > 0" class="section">
              <div class="section-header">Parts ({{ parts.length }})</div>
              <div class="parts-list">
                <div
                  v-for="part in parts"
                  :key="part.id"
                  class="part-item"
                  :class="{ 'has-warning': !part.has_routing }"
                >
                  <span class="part-number">
                    {{ part.item_number }}
                    <i v-if="!part.has_routing" class="pi pi-exclamation-triangle warning-icon"></i>
                    <span v-if="part.is_manual" class="manual-badge" title="Manually added">M</span>
                  </span>
                  <div class="part-actions">
                    <span class="part-qty-label">Qty:</span>
                    <input
                      type="number"
                      :value="part.quantity"
                      min="1"
                      class="qty-input"
                      @change="updatePartQty(part.id, parseInt(($event.target as HTMLInputElement).value) || 1)"
                    />
                    <button class="icon-btn danger" @click="removeProjectPart(part.id)" title="Remove part">
                      <i class="pi pi-times"></i>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Add Manual Part -->
            <div class="add-part-section">
              <div class="add-assembly-row">
                <input
                  v-model="addPartInput"
                  placeholder="Add part by item number..."
                  @keyup.enter="addManualPart"
                />
                <button
                  class="secondary-btn"
                  @click="addManualPart"
                  :disabled="addingPart || !addPartInput.trim()"
                >
                  <i v-if="addingPart" class="pi pi-spin pi-spinner"></i>
                  <span v-else>+ Add Part</span>
                </button>
              </div>
            </div>

            <!-- Loading Parts -->
            <div v-if="loadingParts" class="loading-parts">
              <i class="pi pi-spin pi-spinner"></i>
              Loading parts...
            </div>

            <!-- Nesting Results -->
            <div v-if="nestJobs.length > 0" class="panel-section">
              <div class="section-header">
                <h3>Nesting Jobs</h3>
              </div>
              <div class="nest-jobs-list">
                <div
                  v-for="job in nestJobs"
                  :key="job.id"
                  class="nest-job-card"
                  :class="'nest-status-' + job.status"
                >
                  <div class="nest-job-header">
                    <span class="nest-job-label">
                      {{ job.material }} {{ job.thickness }}" - {{ job.sheet_label || `${job.sheet_width_in}x${job.sheet_height_in}` }}
                    </span>
                    <span class="nest-job-status" :class="'status-' + job.status">
                      <i v-if="job.status === 'pending' || job.status === 'processing'" class="pi pi-spin pi-spinner"></i>
                      {{ job.status }}
                    </span>
                  </div>
                  <div v-if="job.status === 'completed'" class="nest-job-results">
                    <span class="nest-stat">{{ job.sheets_used }} sheet{{ job.sheets_used !== 1 ? 's' : '' }}</span>
                    <span class="nest-stat">{{ job.total_parts_placed }} parts placed</span>
                    <span class="nest-stat">{{ formatUtilization(job.avg_utilization) }} avg utilization</span>
                  </div>
                  <div v-if="job.status === 'failed'" class="nest-job-error">
                    {{ job.error_message || 'Nesting failed' }}
                  </div>
                  <!-- Skipped parts warning -->
                  <div v-if="job.skipped_parts && job.skipped_parts.length > 0" class="nest-skipped-warning">
                    <i class="pi pi-exclamation-triangle"></i>
                    {{ job.skipped_parts.length }} part{{ job.skipped_parts.length !== 1 ? 's' : '' }} could not be nested:
                    <ul class="skipped-parts-list">
                      <li v-for="(sp, idx) in job.skipped_parts" :key="idx">
                        {{ sp.part_id }}<span v-if="sp.instance > 1"> #{{ sp.instance }}</span> &mdash; {{ sp.reason }}
                      </li>
                    </ul>
                  </div>
                  <!-- Sheet results -->
                  <div v-if="job.status === 'completed' && nestResults.has(job.id)" class="nest-sheets">
                    <div
                      v-for="sheet in nestResults.get(job.id)"
                      :key="sheet.sheet_index"
                      class="nest-sheet-group"
                    >
                      <span class="nest-sheet-label">
                        Sheet {{ sheet.sheet_index }}
                        <span v-if="sheet.utilization" class="sheet-util">({{ formatUtilization(sheet.utilization) }})</span>
                      </span>
                      <button
                        v-if="sheet.svg_path"
                        class="nest-sheet-btn preview-btn"
                        @click="previewNestSheet(job.id, sheet.sheet_index)"
                      >
                        <i class="pi pi-eye"></i>
                        Preview
                      </button>
                      <button
                        class="nest-sheet-btn"
                        @click="downloadNestSheet(job.id, sheet.sheet_index)"
                      >
                        <i class="pi pi-download"></i>
                        DXF
                      </button>
                    </div>
                  </div>
                  <button class="delete-nest-btn" @click="deleteNestJob(job.id)">
                    <i class="pi pi-trash"></i>
                    Delete Nest
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Panel Footer Actions -->
          <div class="panel-footer">
            <div class="footer-left">
              <button
                class="primary-btn"
                @click="generatePrintPacket"
                :disabled="generatingPacket"
              >
                <i :class="generatingPacket ? 'pi pi-spin pi-spinner' : 'pi pi-print'"></i>
                {{ generatingPacket ? 'Generating...' : 'Generate Print Packet' }}
              </button>
              <button
                v-if="packetUrl"
                class="success-btn"
                @click="downloadPacket"
              >
                <i class="pi pi-download"></i>
                Download PDF
              </button>
              <button
                class="primary-btn nest-btn"
                @click="openNestModal"
                :disabled="loadingParts"
              >
                <i class="pi pi-th-large"></i>
                Nest DXF
              </button>
            </div>
            <button class="danger-btn" @click="deleteProject">
              <i class="pi pi-trash"></i>
              Delete
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- New Project Modal -->
    <div v-if="showNewProjectModal" class="modal-overlay" @click.self="showNewProjectModal = false">
      <div class="modal">
        <div class="modal-header">
          <h2>New MRP Project</h2>
          <button class="close-btn" @click="showNewProjectModal = false">&times;</button>
        </div>
        <form @submit.prevent="createProject" class="modal-body">
          <div class="form-field">
            <label>Project Code *</label>
            <input v-model="newProject.project_code" required placeholder="e.g., PRJ-2024-001" />
          </div>
          <div class="form-field">
            <label>Description</label>
            <input v-model="newProject.description" placeholder="Project description" />
          </div>
          <div class="form-field">
            <label>Customer</label>
            <input v-model="newProject.customer" placeholder="Customer name" />
          </div>
          <div class="form-row">
            <div class="form-field">
              <label>Start Date</label>
              <input v-model="newProject.start_date" type="date" />
            </div>
            <div class="form-field">
              <label>Due Date</label>
              <input v-model="newProject.due_date" type="date" />
            </div>
          </div>
          <div class="modal-actions">
            <button type="button" class="secondary-btn" @click="showNewProjectModal = false">
              Cancel
            </button>
            <button type="submit" class="primary-btn">
              Create Project
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Nest Config Modal -->
    <NestConfigModal
      v-if="showNestModal"
      :groups="nestGroups"
      :loading="loadingNestGroups"
      @close="showNestModal = false"
      @submit="submitNestJob"
    />
  </div>
</template>

<style scoped>
/* ============================================
   MRP DASHBOARD - DARK THEME (matches old system)
   ============================================ */

* {
  box-sizing: border-box;
}

.mrp-dashboard {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  display: flex;
  flex-direction: column;
}

/* Header */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background: #020617;
  border-bottom: 1px solid #1e293b;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #374151;
  border: none;
  color: #e5e7eb;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.back-btn:hover {
  background: #4b5563;
}

.page-header h1 {
  font-size: 24px;
  margin: 0;
  color: #e5e7eb;
}

.subtitle {
  margin: 4px 0 0 0;
  color: #9ca3af;
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 12px;
}

/* Buttons */
.nav-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #374151;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.nav-btn:hover {
  background: #4b5563;
}

.nav-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.nav-dot.routing { background: #3b82f6; }
.nav-dot.materials { background: #f97316; }
.nav-dot.shop { background: #eab308; }
.nav-dot.lookup { background: #22d3ee; }
.nav-dot.tracking { background: #a855f7; }
.nav-dot.settings { background: #10b981; }

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #059669;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
}

.refresh-btn:hover:not(:disabled) {
  background: #047857;
}

.refresh-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
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

.danger-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #dc2626;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.danger-btn:hover {
  background: #b91c1c;
}

.success-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #059669;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.success-btn:hover {
  background: #047857;
}

/* Error/Status Messages */
.error-message {
  background: #7f1d1d;
  border-radius: 6px;
  padding: 8px 12px;
  margin: 12px 20px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #fca5a5;
  font-size: 12px;
}

.success-message {
  background: #065f46;
  border-radius: 6px;
  padding: 8px 12px;
  margin: 12px 20px 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #6ee7b7;
  font-size: 12px;
}

.dismiss-btn {
  margin-left: auto;
  background: none;
  border: none;
  color: #fca5a5;
  font-size: 18px;
  cursor: pointer;
}

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}

/* Projects Table Container */
.projects-table-container {
  flex: 1;
  padding: 20px;
  overflow: auto;
  transition: margin-right 0.3s ease;
}

.projects-table-container.panel-open {
  margin-right: 0;
}

.loading {
  text-align: center;
  padding: 48px;
  color: #9ca3af;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

/* Projects Table */
.projects-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.projects-table th {
  text-align: left;
  padding: 12px;
  background: #0f172a;
  font-size: 12px;
  font-weight: 600;
  color: #9ca3af;
  border-bottom: 1px solid #1e293b;
}

.projects-table td {
  padding: 12px;
  border-bottom: 1px solid #1e293b;
  color: #e5e7eb;
}

.projects-table tbody tr {
  cursor: pointer;
  transition: background 0.1s;
}

.projects-table tbody tr:hover {
  background: #0f172a;
}

.projects-table tbody tr.selected {
  background: #1e3a5f;
}

.project-code {
  font-weight: 600;
  color: #e5e7eb;
}

/* Status Badges */
.status-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

.status-setup { background: #7c3aed; color: white; }
.status-released { background: #059669; color: white; }
.status-hold { background: #d97706; color: white; }
.status-complete { background: #374151; color: #9ca3af; }

.unrouted-badge {
  background: #dc2626;
  color: white;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  margin-left: 4px;
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: 48px 24px;
  color: #6b7280;
  font-size: 13px;
}

.empty-state i {
  font-size: 48px;
  color: #374151;
  margin-bottom: 16px;
  display: block;
}

.empty-state p {
  color: #6b7280;
  margin-bottom: 20px;
}

/* Detail Panel */
.detail-panel {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 450px;
  background: #0f172a;
  border-left: 1px solid #1e293b;
  transform: translateX(100%);
  transition: transform 0.3s ease;
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.detail-panel.open {
  transform: translateX(0);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #1e293b;
}

.panel-header h2 {
  margin: 0;
  font-size: 18px;
  color: #e5e7eb;
}

.close-btn {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 24px;
  cursor: pointer;
  line-height: 1;
}

.close-btn:hover {
  color: #e5e7eb;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.panel-content::-webkit-scrollbar {
  width: 8px;
}

.panel-content::-webkit-scrollbar-track {
  background: #0f172a;
  border-radius: 4px;
}

.panel-content::-webkit-scrollbar-thumb {
  background: #374151;
  border-radius: 4px;
}

.panel-content::-webkit-scrollbar-thumb:hover {
  background: #4b5563;
}

/* Info Section */
.info-section {
  margin-bottom: 12px;
}

.info-row {
  margin-bottom: 12px;
}

.info-row .label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 2px;
}

.info-row .value {
  font-size: 14px;
  color: #e5e7eb;
}

/* Stats Grid */
.stats-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.stat-box {
  background: #020617;
  border-radius: 6px;
  padding: 12px;
  text-align: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #e5e7eb;
}

.stat-label {
  font-size: 11px;
  color: #9ca3af;
}

.cost-stat .stat-value {
  color: #10b981;
}

/* Cost Breakdown */
.cost-breakdown {
  margin-bottom: 16px;
  background: #020617;
  border-radius: 6px;
  padding: 12px;
}

.cost-rows {
  margin-top: 6px;
}

.cost-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
  font-size: 13px;
}

.cost-label {
  color: #9ca3af;
}

.cost-value {
  color: #e5e7eb;
  font-family: monospace;
}

.cost-total {
  border-top: 1px solid #1e293b;
  margin-top: 4px;
  padding-top: 6px;
  font-weight: 600;
}

.cost-total .cost-value {
  color: #10b981;
}

/* Status Section */
.status-section {
  margin-bottom: 12px;
}

.status-section .label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 4px;
  display: block;
}

.status-select {
  width: 100%;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #1f2937;
  background: #020617;
  color: #e5e7eb;
  font-size: 13px;
  cursor: pointer;
}

.status-select:focus {
  outline: none;
  border-color: #38bdf8;
}

/* Assembly Section */
.assembly-section {
  margin-bottom: 16px;
}

.assembly-list {
  background: #020617;
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
  max-height: 160px;
  overflow-y: auto;
  font-size: 12px;
}

.assembly-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid #1e293b;
}

.assembly-item:last-child {
  border-bottom: none;
}

.assembly-number {
  font-family: monospace;
  color: #e5e7eb;
  min-width: 80px;
}

.assembly-name {
  flex: 1;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assembly-qty-label {
  color: #6b7280;
  font-size: 11px;
}

.empty-assembly-hint {
  color: #6b7280;
  font-size: 12px;
  padding: 8px;
  text-align: center;
  background: #020617;
  border-radius: 6px;
  margin-bottom: 8px;
}

.section-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #1e293b;
  color: #e5e7eb;
}

.add-assembly-row {
  display: flex;
  gap: 8px;
}

.add-assembly-row input {
  flex: 1;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid #1f2937;
  background: #020617;
  color: #e5e7eb;
  font-size: 13px;
}

.add-assembly-row input:focus {
  outline: none;
  border-color: #38bdf8;
}

/* Sections */
.section {
  margin-bottom: 16px;
}

.section-header {
  font-size: 13px;
  font-weight: 600;
  margin: 20px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #1e293b;
  color: #e5e7eb;
}

.section-header.warning {
  color: #fca5a5;
  display: flex;
  align-items: center;
  gap: 6px;
}

.warning-section .section-header {
  margin-top: 0;
}

/* Parts List */
.parts-list {
  font-size: 12px;
  max-height: 200px;
  overflow-y: auto;
  background: #020617;
  border-radius: 6px;
  padding: 8px;
}

.parts-list::-webkit-scrollbar {
  width: 6px;
}

.parts-list::-webkit-scrollbar-track {
  background: #0f172a;
}

.parts-list::-webkit-scrollbar-thumb {
  background: #374151;
  border-radius: 3px;
}

.part-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid #1e293b;
}

.part-item:last-child {
  border-bottom: none;
}

.part-item.clickable {
  cursor: pointer;
}

.part-item.clickable:hover {
  color: #38bdf8;
}

.part-item.has-warning .part-number,
.part-item.no-routing {
  color: #fca5a5;
}

.part-number {
  font-family: monospace;
  color: #e5e7eb;
}

.warning-icon {
  color: #fca5a5;
  font-size: 10px;
  margin-left: 4px;
}

.part-qty {
  color: #9ca3af;
}

.part-qty-label {
  color: #6b7280;
  font-size: 11px;
  white-space: nowrap;
}

.part-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.qty-input {
  width: 50px;
  padding: 3px 6px;
  border-radius: 4px;
  border: 1px solid #1f2937;
  background: #020617;
  color: #e5e7eb;
  font-size: 12px;
  text-align: center;
}

.qty-input:focus {
  outline: none;
  border-color: #38bdf8;
}

.qty-input::-webkit-inner-spin-button,
.qty-input::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.icon-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 11px;
}

.icon-btn:hover {
  background: #1e293b;
}

.icon-btn.danger:hover {
  color: #f87171;
  background: #7f1d1d33;
}

.update-bom-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: #059669;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}

.update-bom-btn:hover:not(:disabled) {
  background: #047857;
}

.update-bom-btn:disabled {
  background: #374151;
  color: #6b7280;
  cursor: not-allowed;
}

.secondary-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #1d4ed8;
  border: none;
  color: white;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}

.secondary-btn:hover:not(:disabled) {
  background: #2563eb;
}

.secondary-btn:disabled {
  background: #374151;
  color: #6b7280;
  cursor: not-allowed;
}

.manual-badge {
  display: inline-block;
  background: #7c3aed;
  color: white;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 600;
  margin-left: 4px;
  vertical-align: middle;
}

.add-part-section {
  margin-top: 12px;
  margin-bottom: 16px;
  padding-top: 8px;
  border-top: 1px solid #1e293b;
}

.loading-parts {
  text-align: center;
  padding: 16px;
  color: #9ca3af;
  font-size: 12px;
}

/* Panel Footer */
.panel-footer {
  padding: 16px;
  border-top: 1px solid #1e293b;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.footer-left {
  display: flex;
  gap: 8px;
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #0f172a;
  border-radius: 8px;
  width: 100%;
  max-width: 400px;
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

.modal-body {
  padding: 24px;
}

.form-field {
  margin-bottom: 12px;
}

.form-field label {
  display: block;
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 4px;
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

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}

/* === Nesting Styles === */

.nest-btn {
  background: #7c3aed;
}

.nest-btn:hover {
  background: #6d28d9;
}

.nest-jobs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nest-job-card {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 10px 12px;
}

.nest-job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.nest-job-label {
  font-size: 13px;
  font-weight: 500;
  color: #e5e7eb;
}

.nest-job-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
}

.nest-job-status.status-pending {
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.1);
}

.nest-job-status.status-processing {
  color: #38bdf8;
  background: rgba(56, 189, 248, 0.1);
}

.nest-job-status.status-completed {
  color: #6ee7b7;
  background: rgba(110, 231, 183, 0.1);
}

.nest-job-status.status-failed {
  color: #fca5a5;
  background: rgba(252, 165, 165, 0.1);
}

.nest-job-results {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.nest-stat {
  display: flex;
  align-items: center;
  gap: 4px;
}

.nest-job-error {
  font-size: 12px;
  color: #fca5a5;
  margin-top: 4px;
}

.nest-skipped-warning {
  font-size: 12px;
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.2);
  border-radius: 4px;
  padding: 6px 8px;
  margin-top: 6px;
}

.nest-skipped-warning i {
  margin-right: 4px;
}

.skipped-parts-list {
  margin: 4px 0 0 18px;
  padding: 0;
  list-style: disc;
}

.skipped-parts-list li {
  margin: 2px 0;
  color: #d4d4d8;
}

.nest-sheets {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}

.nest-sheet-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nest-sheet-label {
  color: #e5e7eb;
  font-size: 12px;
  min-width: 120px;
}

.nest-sheet-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #1e293b;
  border: 1px solid #334155;
  color: #e5e7eb;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.nest-sheet-btn:hover {
  background: #334155;
  border-color: #475569;
}

.nest-sheet-btn.preview-btn {
  border-color: #0e7490;
  color: #22d3ee;
}

.nest-sheet-btn.preview-btn:hover {
  background: #164e63;
  border-color: #22d3ee;
}

.sheet-util {
  color: #9ca3af;
  font-size: 11px;
}

.delete-nest-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: 1px solid #7f1d1d;
  color: #f87171;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  margin-top: 6px;
  align-self: flex-start;
}

.delete-nest-btn:hover {
  background: #7f1d1d;
  color: #fecaca;
}
</style>
