<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { supabase, API_BASE_URL } from '../services/supabase'

const router = useRouter()

interface ProjectPart {
  id: string
  item_id: string
  item_number: string
  name: string
  quantity: number
  is_assembly: boolean
  has_routing: boolean
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
  top_assembly_number?: string
  created_at: string
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
const explodingBom = ref(false)
const generatingPacket = ref(false)
const packetSuccess = ref('')
const packetUrl = ref<string | null>(null)

const newProject = ref({
  project_code: '',
  description: '',
  customer: '',
  due_date: '',
  start_date: ''
})

const statusOptions = ['Setup', 'Released', 'On Hold', 'Complete']

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
  // TODO: Calculate from routing data
  return 0
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

    // Get part counts for each project
    const projectsWithCounts = await Promise.all((data || []).map(async (project) => {
      const { count } = await supabase
        .from('mrp_project_parts')
        .select('*', { count: 'exact', head: true })
        .eq('project_id', project.id)

      // Get top assembly item number if set
      let top_assembly_number = null
      if (project.top_assembly_id) {
        const { data: item } = await supabase
          .from('items')
          .select('item_number')
          .eq('id', project.top_assembly_id)
          .single()
        top_assembly_number = item?.item_number
      }

      return {
        ...project,
        part_count: count || 0,
        top_assembly_number
      }
    }))

    projects.value = projectsWithCounts
  } catch (e: any) {
    error.value = e.message || 'Failed to load projects'
  } finally {
    loading.value = false
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
        items(item_number, name, is_supplier_part)
      `)
      .eq('project_id', projectId)
      .order('created_at', { ascending: true })

    if (queryError) throw queryError

    // Get routing info for each part
    const partsWithRouting = await Promise.all((data || []).map(async (pp: any) => {
      // Check if this item has routing
      const { count } = await supabase
        .from('routing')
        .select('*', { count: 'exact', head: true })
        .eq('item_id', pp.item_id)

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
        has_routing: (count || 0) > 0
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

  // Load parts and check for existing print packet in parallel
  await Promise.all([
    loadProjectParts(project.id),
    loadExistingPacket(project.id)
  ])
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

async function explodeBom() {
  if (!selectedProject.value || !addAssemblyInput.value.trim()) return

  explodingBom.value = true
  error.value = ''

  try {
    const itemNumber = addAssemblyInput.value.trim().toLowerCase()

    // Find the item
    const { data: item, error: itemError } = await supabase
      .from('items')
      .select('id, item_number')
      .eq('item_number', itemNumber)
      .single()

    if (itemError || !item) {
      throw new Error(`Item ${itemNumber} not found`)
    }

    // Update top assembly if not set
    if (!selectedProject.value.top_assembly_id) {
      await supabase
        .from('mrp_projects')
        .update({ top_assembly_id: item.id })
        .eq('id', selectedProject.value.id)

      selectedProject.value.top_assembly_id = item.id
      selectedProject.value.top_assembly_number = item.item_number
    }

    // Recursively get all BOM items
    const allParts = new Map<string, { item_id: string, quantity: number }>()
    await explodeBomRecursive(item.id, 1, allParts)

    // Add the top assembly itself
    allParts.set(item.id, { item_id: item.id, quantity: 1 })

    // Insert all parts that aren't already in the project
    const existingParts = new Set(projectParts.value.map(p => p.item_id))
    const newParts = Array.from(allParts.entries())
      .filter(([itemId]) => !existingParts.has(itemId))
      .map(([_, part]) => ({
        project_id: selectedProject.value!.id,
        item_id: part.item_id,
        quantity: part.quantity
      }))

    if (newParts.length > 0) {
      const { error: insertError } = await supabase
        .from('mrp_project_parts')
        .insert(newParts)

      if (insertError) throw insertError
    }

    addAssemblyInput.value = ''
    await loadProjectParts(selectedProject.value.id)
    await loadProjects() // Refresh counts
  } catch (e: any) {
    error.value = e.message || 'Failed to explode BOM'
  } finally {
    explodingBom.value = false
  }
}

async function explodeBomRecursive(
  parentId: string,
  parentQty: number,
  parts: Map<string, { item_id: string, quantity: number }>
) {
  const { data: bomEntries } = await supabase
    .from('bom')
    .select('child_item_id, quantity')
    .eq('parent_item_id', parentId)

  if (!bomEntries || bomEntries.length === 0) return

  for (const entry of bomEntries) {
    const totalQty = entry.quantity * parentQty
    const existing = parts.get(entry.child_item_id)

    if (existing) {
      existing.quantity += totalQty
    } else {
      parts.set(entry.child_item_id, { item_id: entry.child_item_id, quantity: totalQty })
    }

    // Recurse into children
    await explodeBomRecursive(entry.child_item_id, totalQty, parts)
  }
}

async function deleteProject() {
  if (!selectedProject.value) return
  if (!confirm(`Delete project ${selectedProject.value.project_code}? This will also delete all associated parts.`)) return

  try {
    // Delete project parts first
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

onMounted(() => {
  loadProjects()
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
        <button class="nav-btn tracking" @click="goToProjectTracking">
          <span class="nav-dot tracking"></span>
          Project Tracking
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
                <span class="label">Top Assembly</span>
                <span class="value">{{ selectedProject.top_assembly_number || '-' }}</span>
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

            <!-- Add Assembly -->
            <div class="add-assembly-section">
              <div class="section-label">Add Top Assembly</div>
              <div class="add-assembly-row">
                <input
                  v-model="addAssemblyInput"
                  placeholder="e.g., csa00010"
                  @keyup.enter="explodeBom"
                />
                <button
                  class="primary-btn"
                  @click="explodeBom"
                  :disabled="explodingBom || !addAssemblyInput.trim()"
                >
                  <i v-if="explodingBom" class="pi pi-spin pi-spinner"></i>
                  <span v-else>Add & Explode BOM</span>
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
                  @click="goToRouting(part.item_number)"
                >
                  <span class="part-number">{{ part.item_number }} <i class="pi pi-arrow-right"></i></span>
                  <span class="part-qty">Qty: {{ part.quantity }}</span>
                </div>
              </div>
            </div>

            <!-- Assemblies -->
            <div v-if="assemblies.length > 0" class="section">
              <div class="section-header">Assemblies ({{ assemblies.length }})</div>
              <div class="parts-list">
                <div v-for="asm in assemblies" :key="asm.id" class="part-item">
                  <span class="part-number">{{ asm.item_number }}</span>
                  <span class="part-qty">Qty: {{ asm.quantity }}</span>
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
                  </span>
                  <span class="part-qty">Qty: {{ part.quantity }}</span>
                </div>
              </div>
            </div>

            <!-- Loading Parts -->
            <div v-if="loadingParts" class="loading-parts">
              <i class="pi pi-spin pi-spinner"></i>
              Loading parts...
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

/* Add Assembly Section */
.add-assembly-section {
  margin-bottom: 16px;
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
</style>
