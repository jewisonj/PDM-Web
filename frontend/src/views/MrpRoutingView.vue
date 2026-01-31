<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { supabase } from '../services/supabase'
import { getSignedUrlFromPath } from '../services/storage'

interface FileInfo {
  id: string
  item_id: string
  file_type: string
  file_name: string
  file_path?: string
  created_at: string
}

const router = useRouter()
const route = useRoute()

interface Item {
  id: string
  item_number: string
  name: string
  description: string
  lifecycle_state: string
  material?: string
  thickness?: number
  cut_length?: number
  cut_time?: number
  mass?: number
  has_routing?: boolean
  routing_count?: number
  has_pdf?: boolean
  has_material?: boolean
  part_type?: string
  project_id?: string
  project_name?: string
  mrp_project_codes?: string[]
  is_supplier_part?: boolean
  unit_price?: number | null
  supplier_name?: string | null
  supplier_pn?: string | null
}

interface Workstation {
  id: string
  station_code: string
  station_name: string
  sort_order: number
  hourly_rate: number | null
  is_outsourced: boolean
  outsourced_cost_default: number | null
}

interface RoutingStep {
  id?: string
  item_id: string
  station_id: string
  station_code?: string
  station_name?: string
  sequence: number
  est_time_min: number
  notes: string
  cost_override: number | null
}

interface RawMaterial {
  id: string
  material_type: string
  material_code: string
  part_number: string
  description: string
  profile?: string
  dim1_in?: number
  dim2_in?: number
  wall_or_thk_in?: number
  stock_length_ft?: number
  weight_lb_per_ft?: number
  density_lb_per_cuin?: number
  price_per_unit: number | null
}

interface CostSetting {
  setting_key: string
  setting_value: number
}

interface RoutingMaterial {
  id?: string
  item_id: string
  material_id: string
  qty_required: number
  blank_width_in?: number
  blank_height_in?: number
  material?: RawMaterial
}

const items = ref<Item[]>([])
const workstations = ref<Workstation[]>([])
const selectedItem = ref<Item | null>(null)
const routing = ref<RoutingStep[]>([])
const searchQuery = ref('')
const loading = ref(true)
const savingRouting = ref(false)
const error = ref('')
const successMessage = ref('')

// PDF Preview state
const pdfUrl = ref<string | null>(null)
const showPdfPreview = ref(false)
const pdfPreviewWidth = ref(700)
const loadingPdf = ref(false)

// Files state
const itemFiles = ref<FileInfo[]>([])

// Raw materials state
const rawMaterials = ref<RawMaterial[]>([])
const itemMaterials = ref<RoutingMaterial[]>([])
const selectedMaterialType = ref<string>('all')
const selectedMaterialSize = ref<string>('all')
const selectedMaterial = ref<string>('')
const materialQty = ref<number>(1)
const calculatedLength = ref<number | null>(null)
const blankWidth = ref<number | null>(null)
const blankHeight = ref<number | null>(null)

// Cost state
const costSettings = ref<CostSetting[]>([])
const editingCostIndex = ref<number | null>(null)
const editingCostValue = ref<string>('')

// Purchased part state
const purchasePrice = ref<number | null>(null)
const purchaseSupplier = ref<string>('')
const purchasePn = ref<string>('')
const savingPurchase = ref(false)

// Detect if selected material is sheet metal
const selectedMaterialIsSM = computed(() => {
  if (!selectedMaterial.value) return false
  const mat = rawMaterials.value.find(m => m.id === selectedMaterial.value)
  return mat?.material_type === 'SM'
})

// Create new station
const newStationCode = ref('')
const newStationName = ref('')
const creatingStation = ref(false)

// Add station to routing
const addStationId = ref('')
const addStationTime = ref<number>(0)

// Custom template save
const customTemplateName = ref('')

// Filters
const partTypeFilter = ref<string>('all')
const routingStatusFilter = ref<string>('all')
const projectFilter = ref<string>('all')

// Part type options based on item number prefixes
const partTypeOptions = [
  { value: 'all', label: 'All Types' },
  { value: 'formed_sm', label: 'Formed SM' },
  { value: 'flat_sm', label: 'Flat SM' },
  { value: 'tube', label: 'Tube' },
  { value: 'weldment', label: 'Weldment' },
  { value: 'mech_asm', label: 'Mech Asm' },
  { value: 'machined', label: 'Machined' },
  { value: 'purchased', label: 'Purchased' }
]

const routingStatusOptions = [
  { value: 'all', label: 'All' },
  { value: 'has_routing', label: 'Routed' },
  { value: 'no_routing', label: 'Unrouted' }
]

// Legacy templates using numeric station codes
const routingTemplates = [
  { key: 'FORMED_SM', label: 'Formed SM', stations: ['012', '013', '011', '050'] },
  { key: 'FLAT_SM', label: 'Flat SM', stations: ['012', '011', '050'] },
  { key: 'TUBE', label: 'Tube', stations: ['010', '011', '018', '050'] },
  { key: 'WELD_ASM', label: 'Weld Asm', stations: ['014', '015', '017', '050'] },
  { key: 'MECH_ASM', label: 'Mech Asm', stations: ['025', '050'] }
]

// Determine part type from item characteristics
function getPartType(item: Item): string {
  const pn = item.item_number.toLowerCase()
  const desc = (item.description || '').toLowerCase()
  const name = (item.name || '').toLowerCase()

  if (pn.startsWith('mmc') || pn.startsWith('spn') || pn.startsWith('zzz')) {
    return 'purchased'
  }

  if (desc.includes('weld') || name.includes('weld') || desc.includes('wmt')) {
    return 'weldment'
  }
  if (desc.includes('assembly') || desc.includes('asm') || name.includes('asm')) {
    return 'mech_asm'
  }
  if (desc.includes('tube') || name.includes('tube') || desc.includes('extr')) {
    return 'tube'
  }
  if (desc.includes('machined') || desc.includes('mach')) {
    return 'machined'
  }

  if (item.thickness && item.thickness > 0) {
    if (desc.includes('flat') || desc.includes('blank') || desc.includes('plate')) {
      return 'flat_sm'
    }
    return 'formed_sm'
  }

  if (pn.startsWith('cs') || pn.startsWith('wm')) {
    return 'formed_sm'
  }

  return 'formed_sm'
}

// Get unique projects for filter dropdown (merged PDM + MRP names)
const projectOptions = computed(() => {
  const projects = new Set<string>()
  items.value.forEach(item => {
    if (item.project_name) projects.add(item.project_name)
    if (item.mrp_project_codes) {
      item.mrp_project_codes.forEach(code => projects.add(code))
    }
  })
  return Array.from(projects).sort()
})

// Filter items based on search and filters
const filteredItems = computed(() => {
  let result = items.value

  if (projectFilter.value !== 'all') {
    const pf = projectFilter.value
    result = result.filter(item =>
      item.project_name === pf || item.mrp_project_codes?.includes(pf)
    )
  }

  if (partTypeFilter.value !== 'all') {
    result = result.filter(item => item.part_type === partTypeFilter.value)
  }

  if (routingStatusFilter.value === 'has_routing') {
    result = result.filter(item => item.has_routing)
  } else if (routingStatusFilter.value === 'no_routing') {
    result = result.filter(item => !item.has_routing)
  }

  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    result = result.filter(item =>
      item.item_number.toLowerCase().includes(q) ||
      (item.name && item.name.toLowerCase().includes(q)) ||
      (item.description && item.description.toLowerCase().includes(q))
    )
  }

  return result.slice(0, 100)
})

// Total estimated time
const totalEstTime = computed(() => {
  return routing.value.reduce((sum, r) => sum + (r.est_time_min || 0), 0)
})

// Cost helper: get a cost setting value by key
function getCostSetting(key: string): number {
  const s = costSettings.value.find(c => c.setting_key === key)
  return s ? Number(s.setting_value) : 0
}

// Cost helper: get the workstation for a routing step
function getStepWorkstation(step: RoutingStep): Workstation | undefined {
  return workstations.value.find(w => w.id === step.station_id)
}

// Cost helper: calculate cost for a single routing step
function getStepCost(step: RoutingStep): number {
  const ws = getStepWorkstation(step)
  if (!ws) return 0

  if (ws.is_outsourced) {
    return step.cost_override ?? ws.outsourced_cost_default ?? 0
  }

  if (step.cost_override != null) return step.cost_override

  const rate = ws.hourly_rate ?? getCostSetting('default_labor_rate')
  return ((step.est_time_min || 0) / 60) * rate
}

// Cost helper: is this step outsourced?
function isStepOutsourced(step: RoutingStep): boolean {
  const ws = getStepWorkstation(step)
  return ws?.is_outsourced ?? false
}

// Total labor cost (non-outsourced steps)
const totalLaborCost = computed(() => {
  return routing.value
    .filter(r => !isStepOutsourced(r))
    .reduce((sum, r) => sum + getStepCost(r), 0)
})

// Total outsourced cost
const totalOutsourcedCost = computed(() => {
  return routing.value
    .filter(r => isStepOutsourced(r))
    .reduce((sum, r) => sum + getStepCost(r), 0)
})

// Cost helper: get default $/lb for a material code (CS, AL, SS)
function getDefaultPricePerLb(materialCode: string): number {
  const keyMap: Record<string, string> = { CS: 'default_cs_price_per_lb', AL: 'default_al_price_per_lb', SS: 'default_ss_price_per_lb' }
  return getCostSetting(keyMap[materialCode] || '')
}

// Material cost for a single routing material
function getMaterialCost(rm: RoutingMaterial): number {
  const mat = rm.material
  if (!mat) return 0

  if (mat.material_type === 'SM') {
    // Sheet metal: price_per_unit is $/lb, fallback to per-material default $/lb
    const pricePerLb = mat.price_per_unit ?? getDefaultPricePerLb(mat.material_code)
    return (rm.qty_required || 0) * pricePerLb
  } else {
    // Tubing: if price_per_unit is set, it's a direct $/ft override
    // Otherwise, derive $/ft from default $/lb * weight_lb_per_ft
    let pricePerFt: number
    if (mat.price_per_unit != null) {
      pricePerFt = mat.price_per_unit
    } else {
      const pricePerLb = getDefaultPricePerLb(mat.material_code)
      pricePerFt = pricePerLb * (mat.weight_lb_per_ft || 0)
    }
    if (selectedItem.value?.mass && mat.weight_lb_per_ft) {
      const lengthFt = (selectedItem.value.mass / mat.weight_lb_per_ft) + (2 / 12)
      return lengthFt * pricePerFt
    }
    // Fallback: use qty_required as inches
    return ((rm.qty_required || 0) / 12) * pricePerFt
  }
}

// Total material cost
const totalMaterialCost = computed(() => {
  return itemMaterials.value.reduce((sum, rm) => sum + getMaterialCost(rm), 0)
})

// Total estimated cost
const totalEstCost = computed(() => {
  return totalLaborCost.value + totalOutsourcedCost.value + totalMaterialCost.value
})

// Format dollar amount
function formatCost(val: number): string {
  return '$' + val.toFixed(2)
}

// Click-to-edit cost override handlers
function startEditCost(index: number) {
  const step = routing.value[index]
  editingCostIndex.value = index
  editingCostValue.value = (step.cost_override ?? getStepCost(step)).toFixed(2)
}

function commitEditCost(index: number) {
  const step = routing.value[index]
  const val = parseFloat(editingCostValue.value)
  if (!isNaN(val) && val >= 0) {
    step.cost_override = val
  }
  editingCostIndex.value = null
}

function cancelEditCost() {
  editingCostIndex.value = null
}

function clearCostOverride(index: number) {
  routing.value[index].cost_override = null
}

// Available stations not yet in routing
const availableStations = computed(() => {
  const usedIds = new Set(routing.value.map(r => r.station_id))
  return workstations.value.filter(w => !usedIds.has(w.id))
})

// Material type options
const materialTypeOptions = computed(() => {
  const types = new Set(rawMaterials.value.map(m => m.material_type))
  return Array.from(types).sort()
})

// Material size options based on selected type
const materialSizeOptions = computed(() => {
  if (selectedMaterialType.value === 'all') return []

  const filtered = rawMaterials.value.filter(m => m.material_type === selectedMaterialType.value)
  const sizes = new Map<string, string>()

  filtered.forEach(m => {
    let sizeLabel = ''
    if (m.material_type === 'SQ') {
      sizeLabel = `${m.dim1_in}x${m.dim2_in}x${m.wall_or_thk_in}`
    } else if (m.material_type === 'OT') {
      sizeLabel = `${m.dim1_in} OD x ${m.wall_or_thk_in}`
    } else if (m.material_type === 'SM') {
      sizeLabel = `${m.wall_or_thk_in}" thick`
    }
    if (sizeLabel && !sizes.has(sizeLabel)) {
      sizes.set(sizeLabel, sizeLabel)
    }
  })

  return Array.from(sizes.keys()).sort()
})

// Materials matching current filters
const filteredMaterials = computed(() => {
  let result = rawMaterials.value

  if (selectedMaterialType.value !== 'all') {
    result = result.filter(m => m.material_type === selectedMaterialType.value)
  }

  if (selectedMaterialSize.value !== 'all') {
    result = result.filter(m => {
      let sizeLabel = ''
      if (m.material_type === 'SQ') {
        sizeLabel = `${m.dim1_in}x${m.dim2_in}x${m.wall_or_thk_in}`
      } else if (m.material_type === 'OT') {
        sizeLabel = `${m.dim1_in} OD x ${m.wall_or_thk_in}`
      } else if (m.material_type === 'SM') {
        sizeLabel = `${m.wall_or_thk_in}" thick`
      }
      return sizeLabel === selectedMaterialSize.value
    })
  }

  return result
})

// Filter persistence via localStorage
const FILTER_KEY = 'mrp-routing-filters'

function restoreFilters() {
  const saved = localStorage.getItem(FILTER_KEY)
  if (saved) {
    try {
      const f = JSON.parse(saved)
      if (f.project) projectFilter.value = f.project
      if (f.type) partTypeFilter.value = f.type
      if (f.status) routingStatusFilter.value = f.status
      if (f.search) searchQuery.value = f.search
    } catch { /* ignore corrupt data */ }
  }
}

watch([projectFilter, partTypeFilter, routingStatusFilter, searchQuery], () => {
  localStorage.setItem(FILTER_KEY, JSON.stringify({
    project: projectFilter.value,
    type: partTypeFilter.value,
    status: routingStatusFilter.value,
    search: searchQuery.value,
  }))
})

// Reset blank dimension fields when material type changes
watch(selectedMaterialType, () => {
  blankWidth.value = null
  blankHeight.value = null
  calculatedLength.value = null
})

// Auto-calculate when both blank dimensions are filled in
watch([blankWidth, blankHeight], () => {
  if (blankWidth.value && blankHeight.value && selectedMaterial.value) {
    calculateMaterial()
  }
})

// Map item.material string to raw_materials material_code (CS/AL/SS)
function mapMaterialCode(itemMaterial: string | undefined): string | null {
  if (!itemMaterial) return null
  const m = itemMaterial.toUpperCase()
  if (m.includes('SS') || m.includes('STAINLESS')) return 'SS'
  if (m.includes('AL') || m.includes('ALUMINUM') || m.includes('ALUMINIUM')) return 'AL'
  if (m.includes('STEEL') || m === 'CS' || m === 'CRS' || m === 'HRS' || m === 'HSLA') return 'CS'
  return null
}

// Find closest matching wall_or_thk_in from available SM raw materials
function findClosestThickness(targetThk: number, materialCode: string): RawMaterial | null {
  const candidates = rawMaterials.value.filter(
    m => m.material_type === 'SM' && m.material_code === materialCode
  )
  if (candidates.length === 0) return null

  let best = candidates[0]
  let bestDiff = Math.abs((best.wall_or_thk_in || 0) - targetThk)
  for (const c of candidates) {
    const diff = Math.abs((c.wall_or_thk_in || 0) - targetThk)
    if (diff < bestDiff) {
      best = c
      bestDiff = diff
    }
  }
  // Only match if within 15% tolerance
  if (bestDiff > targetThk * 0.15 && bestDiff > 0.005) return null
  return best
}

// Auto-prefill material filters from item properties
function prefillMaterialFromItem(item: Item) {
  const code = mapMaterialCode(item.material)
  if (!code || !item.thickness || item.thickness <= 0) return

  const match = findClosestThickness(item.thickness, code)
  if (!match) return

  // Set filters to narrow to this exact material
  selectedMaterialType.value = 'SM'
  // Build the size label the same way materialSizeOptions does
  selectedMaterialSize.value = `${match.wall_or_thk_in}" thick`
  // Wait one tick for filteredMaterials to update, then select the specific material
  setTimeout(() => {
    const found = filteredMaterials.value.find(m => m.id === match.id)
    if (found) {
      selectedMaterial.value = found.id
    }
  }, 0)
}

async function refreshData() {
  const previousItemNumber = selectedItem.value?.item_number
  await loadData()
  if (previousItemNumber) {
    const target = items.value.find(i => i.item_number === previousItemNumber)
    if (target) await selectItem(target)
  }
}

async function loadData() {
  loading.value = true
  error.value = ''

  try {
    // Load items with project info
    const { data: itemsData, error: itemsError } = await supabase
      .from('items')
      .select('id, item_number, name, description, lifecycle_state, material, thickness, cut_length, cut_time, mass, project_id, is_supplier_part, unit_price, supplier_name, supplier_pn, projects(name, status)')
      .order('item_number')

    if (itemsError) throw itemsError

    // Get routing counts per item
    const { data: routingData, error: routingError } = await supabase
      .from('routing')
      .select('item_id')

    if (routingError) throw routingError

    const routingCounts = new Map<string, number>()
    ;(routingData || []).forEach(r => {
      routingCounts.set(r.item_id, (routingCounts.get(r.item_id) || 0) + 1)
    })

    // Get items with PDFs
    const { data: pdfData, error: pdfError } = await supabase
      .from('files')
      .select('item_id')
      .eq('file_type', 'PDF')
      .not('file_path', 'is', null)

    if (pdfError) throw pdfError

    const itemsWithPdf = new Set((pdfData || []).map(f => f.item_id))

    // Get items with materials assigned
    const { data: matData, error: matError } = await supabase
      .from('routing_materials')
      .select('item_id')

    if (matError) throw matError

    const itemsWithMaterial = new Set((matData || []).map(m => m.item_id))

    // Load MRP project memberships (item_id -> project codes)
    const { data: mrpData } = await supabase
      .from('mrp_project_parts')
      .select('item_id, mrp_projects(project_code)')

    const mrpItemMap = new Map<string, string[]>()
    ;(mrpData || []).forEach((mp: any) => {
      const code = mp.mrp_projects?.project_code
      if (code) {
        const existing = mrpItemMap.get(mp.item_id) || []
        if (!existing.includes(code)) existing.push(code)
        mrpItemMap.set(mp.item_id, existing)
      }
    })

    // Enrich items
    items.value = (itemsData || []).map(item => ({
      ...item,
      has_routing: routingCounts.has(item.id),
      routing_count: routingCounts.get(item.id) || 0,
      has_pdf: itemsWithPdf.has(item.id),
      has_material: itemsWithMaterial.has(item.id),
      part_type: getPartType(item),
      project_name: (item as any).projects?.status !== 'archived' ? (item as any).projects?.name || null : null,
      mrp_project_codes: mrpItemMap.get(item.id) || []
    }))

    // Load workstations
    const { data: stationsData, error: stationsError } = await supabase
      .from('workstations')
      .select('*')
      .order('sort_order')

    if (stationsError) throw stationsError
    workstations.value = stationsData || []

    // Load cost settings
    const { data: costData, error: costError } = await supabase
      .from('cost_settings')
      .select('setting_key, setting_value')

    if (costError) throw costError
    costSettings.value = costData || []

    // Load raw materials
    const { data: materialsData, error: materialsError } = await supabase
      .from('raw_materials')
      .select('*')
      .order('material_type, part_number')

    if (materialsError) throw materialsError
    rawMaterials.value = materialsData || []

    // Check for item parameter from URL
    const itemParam = route.query.item as string
    if (itemParam) {
      const targetItem = items.value.find(i => i.item_number === itemParam)
      if (targetItem) {
        searchQuery.value = itemParam
        await selectItem(targetItem)
      }
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load data'
  } finally {
    loading.value = false
  }
}

async function selectItem(item: Item) {
  selectedItem.value = item
  routing.value = []
  itemFiles.value = []
  itemMaterials.value = []
  pdfUrl.value = null

  // Populate purchased part fields
  purchasePrice.value = item.unit_price ?? null
  purchaseSupplier.value = item.supplier_name ?? ''
  purchasePn.value = item.supplier_pn ?? ''

  try {
    // Load routing with station info
    const { data, error: routingError } = await supabase
      .from('routing')
      .select(`
        *,
        workstations(station_code, station_name)
      `)
      .eq('item_id', item.id)
      .order('sequence')

    if (routingError) throw routingError

    routing.value = (data || []).map(r => ({
      ...r,
      station_code: r.workstations?.station_code,
      station_name: r.workstations?.station_name
    }))

    // Load files
    const { data: filesData, error: filesError } = await supabase
      .from('files')
      .select('*')
      .eq('item_id', item.id)
      .order('file_type')

    if (filesError) throw filesError
    itemFiles.value = filesData || []

    // Load item materials
    const { data: itemMatsData, error: itemMatsError } = await supabase
      .from('routing_materials')
      .select(`
        *,
        raw_materials(*)
      `)
      .eq('item_id', item.id)

    if (itemMatsError) throw itemMatsError
    itemMaterials.value = (itemMatsData || []).map(m => ({
      ...m,
      material: m.raw_materials
    }))

    // Auto-load PDF if available
    const pdfFile = itemFiles.value.find(f => f.file_type === 'PDF' && f.file_path)
    if (pdfFile) {
      await loadPdfPreview(pdfFile)
    } else {
      showPdfPreview.value = false
    }

    // Auto-prefill material filters if no materials assigned yet
    if (itemMaterials.value.length === 0) {
      prefillMaterialFromItem(item)
    } else {
      // Reset filters when item already has materials
      selectedMaterialType.value = 'all'
      selectedMaterialSize.value = 'all'
      selectedMaterial.value = ''
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to load item data'
  }
}

async function loadPdfPreview(file: FileInfo) {
  if (!file.file_path) return

  loadingPdf.value = true
  try {
    const url = await getSignedUrlFromPath(file.file_path)
    if (url) {
      pdfUrl.value = url
      showPdfPreview.value = true
    }
  } catch (e) {
    console.error('Failed to load PDF:', e)
  } finally {
    loadingPdf.value = false
  }
}

function closePdfPreview() {
  showPdfPreview.value = false
}

function setPdfSize(size: 'S' | 'M' | 'L') {
  const sizes = { S: 500, M: 700, L: 900 }
  pdfPreviewWidth.value = sizes[size]
}

function addRoutingStep() {
  if (!selectedItem.value || !addStationId.value) return

  const station = workstations.value.find(w => w.id === addStationId.value)
  if (!station) return

  const lastSequence = routing.value.length > 0
    ? Math.max(...routing.value.map(r => r.sequence))
    : 0

  // Auto-fill cut_time for Waterjet (012) if user left time empty
  let estTime = addStationTime.value || 0
  if (station.station_code === '012' && selectedItem.value.cut_time && estTime === 0) {
    estTime = Math.round(selectedItem.value.cut_time * 10) / 10
  }

  routing.value.push({
    item_id: selectedItem.value.id,
    station_id: station.id,
    station_code: station.station_code,
    station_name: station.station_name,
    sequence: lastSequence + 10,
    est_time_min: estTime,
    notes: '',
    cost_override: null
  })

  addStationId.value = ''
  addStationTime.value = 0
}

function removeRoutingStep(index: number) {
  routing.value.splice(index, 1)
}

function moveStepUp(index: number) {
  if (index === 0) return
  const temp = routing.value[index].sequence
  routing.value[index].sequence = routing.value[index - 1].sequence
  routing.value[index - 1].sequence = temp
  routing.value.sort((a, b) => a.sequence - b.sequence)
}

function moveStepDown(index: number) {
  if (index === routing.value.length - 1) return
  const temp = routing.value[index].sequence
  routing.value[index].sequence = routing.value[index + 1].sequence
  routing.value[index + 1].sequence = temp
  routing.value.sort((a, b) => a.sequence - b.sequence)
}

function applyTemplate(templateKey: string) {
  if (!selectedItem.value) return

  const template = routingTemplates.find(t => t.key === templateKey)
  if (!template) return

  routing.value = template.stations.map((stationCode, i) => {
    const station = workstations.value.find(w => w.station_code === stationCode)

    // Auto-fill cut_time for Waterjet (012)
    let estTime = 0
    if (stationCode === '012' && selectedItem.value!.cut_time) {
      estTime = Math.round(selectedItem.value!.cut_time * 10) / 10
    }

    return {
      item_id: selectedItem.value!.id,
      station_id: station?.id || '',
      station_code: station?.station_code,
      station_name: station?.station_name,
      sequence: (i + 1) * 10,
      est_time_min: estTime,
      notes: '',
      cost_override: null
    }
  })
}

function clearRouting() {
  routing.value = []
}

async function saveRouting() {
  if (!selectedItem.value) return

  savingRouting.value = true
  error.value = ''
  successMessage.value = ''

  try {
    // Delete existing routing
    await supabase
      .from('routing')
      .delete()
      .eq('item_id', selectedItem.value.id)

    // Insert new routing
    if (routing.value.length > 0) {
      const { error: insertError } = await supabase
        .from('routing')
        .insert(routing.value.map(r => ({
          item_id: r.item_id,
          station_id: r.station_id,
          sequence: r.sequence,
          est_time_min: r.est_time_min || 0,
          notes: r.notes || null,
          cost_override: r.cost_override ?? null
        })))

      if (insertError) throw insertError
    }

    // Update item's has_routing status in local state
    const item = items.value.find(i => i.id === selectedItem.value!.id)
    if (item) {
      item.has_routing = routing.value.length > 0
      item.routing_count = routing.value.length
    }

    successMessage.value = 'Routing saved'
    setTimeout(() => { successMessage.value = '' }, 3000)
  } catch (e: any) {
    error.value = e.message || 'Failed to save routing'
  } finally {
    savingRouting.value = false
  }
}

async function createStation() {
  if (!newStationCode.value || !newStationName.value) {
    error.value = 'Station code and name are required'
    return
  }

  creatingStation.value = true
  error.value = ''

  try {
    const maxOrder = workstations.value.length > 0
      ? Math.max(...workstations.value.map(w => w.sort_order))
      : 0

    const { data, error: insertError } = await supabase
      .from('workstations')
      .insert({
        station_code: newStationCode.value,
        station_name: newStationName.value,
        sort_order: maxOrder + 1
      })
      .select()

    if (insertError) throw insertError
    if (!data || data.length === 0) throw new Error('Insert returned no data — check RLS policies')

    workstations.value.push(data[0])
    workstations.value.sort((a, b) => a.sort_order - b.sort_order)

    newStationCode.value = ''
    newStationName.value = ''
    successMessage.value = 'Station created'
    setTimeout(() => { successMessage.value = '' }, 3000)
  } catch (e: any) {
    console.error('createStation error:', e)
    error.value = e.message || 'Failed to create station'
  } finally {
    creatingStation.value = false
  }
}

function calculateMaterial() {
  if (!selectedMaterial.value) {
    calculatedLength.value = null
    return
  }

  const material = rawMaterials.value.find(m => m.id === selectedMaterial.value)
  if (!material) {
    calculatedLength.value = null
    return
  }

  if (material.material_type === 'SM') {
    // Sheet metal: blank mass = width * height * thickness * density
    if (!blankWidth.value || !blankHeight.value || !material.wall_or_thk_in || !material.density_lb_per_cuin) {
      calculatedLength.value = null
      return
    }
    const blankMass = blankWidth.value * blankHeight.value * material.wall_or_thk_in * material.density_lb_per_cuin
    calculatedLength.value = Math.round(blankMass * 100) / 100
    materialQty.value = calculatedLength.value
  } else {
    // Tubing: length = (part_mass / weight_per_ft * 12) + 2"
    if (!selectedItem.value?.mass || !material.weight_lb_per_ft) {
      calculatedLength.value = null
      return
    }
    const mass = selectedItem.value.mass
    const lengthInches = (mass / material.weight_lb_per_ft * 12) + 2
    calculatedLength.value = Math.round(lengthInches * 10) / 10
  }
}

async function updatePurchaseInfo() {
  if (!selectedItem.value) return
  savingPurchase.value = true
  try {
    const { error: updateError } = await supabase
      .from('items')
      .update({
        unit_price: purchasePrice.value,
        supplier_name: purchaseSupplier.value || null,
        supplier_pn: purchasePn.value || null,
        is_supplier_part: true
      })
      .eq('id', selectedItem.value.id)

    if (updateError) throw updateError

    // Update local item data
    selectedItem.value.unit_price = purchasePrice.value
    selectedItem.value.supplier_name = purchaseSupplier.value || null
    selectedItem.value.supplier_pn = purchasePn.value || null
    selectedItem.value.is_supplier_part = true

    // Update in items list too
    const idx = items.value.findIndex(i => i.id === selectedItem.value!.id)
    if (idx !== -1) {
      items.value[idx] = { ...items.value[idx], ...selectedItem.value }
    }
  } catch (e: any) {
    error.value = e.message || 'Failed to update purchase info'
  } finally {
    savingPurchase.value = false
  }
}

async function assignMaterial() {
  if (!selectedItem.value || !selectedMaterial.value || materialQty.value <= 0) {
    error.value = 'Select a material and enter quantity'
    return
  }

  try {
    const insertData: Record<string, any> = {
      item_id: selectedItem.value.id,
      material_id: selectedMaterial.value,
      qty_required: materialQty.value
    }

    // Include blank dimensions for sheet metal
    const material = rawMaterials.value.find(m => m.id === selectedMaterial.value)
    if (material?.material_type === 'SM' && blankWidth.value && blankHeight.value) {
      insertData.blank_width_in = blankWidth.value
      insertData.blank_height_in = blankHeight.value
    }

    const { data, error: insertError } = await supabase
      .from('routing_materials')
      .insert(insertData)
      .select(`
        *,
        raw_materials(*)
      `)

    if (insertError) throw insertError
    if (!data || data.length === 0) throw new Error('Insert returned no data — check RLS policies')

    const row = data[0]
    itemMaterials.value.push({
      ...row,
      material: row.raw_materials
    })

    selectedMaterial.value = ''
    materialQty.value = 1
    calculatedLength.value = null
    blankWidth.value = null
    blankHeight.value = null
    successMessage.value = 'Material assigned'
    setTimeout(() => { successMessage.value = '' }, 3000)
  } catch (e: any) {
    error.value = e.message || 'Failed to assign material'
  }
}

async function removeMaterial(materialId: string) {
  try {
    await supabase
      .from('routing_materials')
      .delete()
      .eq('id', materialId)

    itemMaterials.value = itemMaterials.value.filter(m => m.id !== materialId)
  } catch (e: any) {
    error.value = e.message || 'Failed to remove material'
  }
}

async function openFile(file: FileInfo) {
  if (!file.file_path) {
    error.value = 'File not available in storage'
    return
  }

  const url = await getSignedUrlFromPath(file.file_path)
  if (url) {
    window.open(url, '_blank')
  } else {
    error.value = 'Failed to generate file URL'
  }
}

function goHome() {
  router.push('/')
}

function goToDashboard() {
  router.push('/mrp/dashboard')
}

onMounted(() => {
  restoreFilters()
  loadData()
})
</script>

<template>
  <div class="routing-editor">
    <header class="page-header">
      <div class="header-left">
        <button class="back-btn" @click="goToDashboard">
          <i class="pi pi-arrow-left"></i>
          Dashboard
        </button>
        <div>
          <h1>Routing Editor</h1>
        </div>
      </div>
      <div class="header-actions">
        <button class="refresh-btn" @click="refreshData" :disabled="loading">
          <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i>
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
        <button class="nav-btn" @click="goHome">
          <i class="pi pi-home"></i>
          Home
        </button>
      </div>
    </header>

    <div v-if="error" class="error-message">
      <i class="pi pi-exclamation-triangle"></i>
      {{ error }}
      <button class="close-msg" @click="error = ''">&times;</button>
    </div>

    <div v-if="successMessage" class="success-message">
      <i class="pi pi-check-circle"></i>
      {{ successMessage }}
    </div>

    <div class="editor-layout" :class="{ 'with-preview': showPdfPreview }">
      <!-- Left Sidebar - Item List -->
      <div class="sidebar">
        <div class="sidebar-header">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search parts..."
            class="search-input"
          />
          <div class="filter-row">
            <select v-model="projectFilter" class="filter-select">
              <option value="all">All Projects</option>
              <option v-for="proj in projectOptions" :key="proj" :value="proj">
                {{ proj }}
              </option>
            </select>
          </div>
          <div class="filter-row">
            <select v-model="partTypeFilter" class="filter-select">
              <option v-for="opt in partTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <select v-model="routingStatusFilter" class="filter-select">
              <option v-for="opt in routingStatusOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div class="filter-stats">
            {{ filteredItems.length }} items
          </div>
        </div>

        <div v-if="loading" class="loading-small">Loading...</div>
        <div v-else class="items-list">
          <div
            v-for="item in filteredItems"
            :key="item.id"
            class="item-row"
            :class="{ selected: selectedItem?.id === item.id }"
            @click="selectItem(item)"
          >
            <div class="item-row-main">
              <span v-if="item.has_pdf" class="pdf-icon" title="Has PDF">
                <i class="pi pi-file-pdf"></i>
              </span>
              <span class="item-number">{{ item.item_number }}</span>
              <span v-if="item.has_material" class="mat-badge" title="Material assigned">Mat</span>
              <span v-if="item.has_routing" class="ops-badge" :title="`${item.routing_count} operations`">
                {{ item.routing_count }} ops
              </span>
              <span v-else class="no-routing-badge">No routing</span>
            </div>
            <span class="item-name">{{ item.name || item.description || '-' }}</span>
          </div>
        </div>
      </div>

      <!-- Middle Panel - Routing Editor -->
      <div class="main-panel">
        <div v-if="!selectedItem" class="no-selection">
          <i class="pi pi-arrow-left"></i>
          <p>Select an item to edit routing</p>
        </div>

        <template v-else>
          <!-- Item Header -->
          <div class="item-header">
            <div class="item-info">
              <span class="item-number-large">{{ selectedItem.item_number }}</span>
              <span class="item-desc">{{ selectedItem.description || selectedItem.name }}</span>
            </div>
            <div class="file-tiles">
              <button
                v-for="file in itemFiles.filter(f => f.file_path)"
                :key="file.id"
                class="file-tile"
                :class="file.file_type.toLowerCase()"
                @click="openFile(file)"
                :title="`Open ${file.file_name}`"
              >
                {{ file.file_type }}
              </button>
            </div>
          </div>

          <!-- Part Info -->
          <div v-if="selectedItem.material || selectedItem.mass" class="part-info-bar">
            <span v-if="selectedItem.material" class="info-chip">{{ selectedItem.material }}</span>
            <span v-if="selectedItem.thickness" class="info-chip">{{ selectedItem.thickness }}"</span>
            <span v-if="selectedItem.mass" class="info-chip">{{ Number(selectedItem.mass).toFixed(1) }} lb</span>
            <span v-if="selectedItem.cut_length" class="info-chip">{{ Number(selectedItem.cut_length).toFixed(1) }}" cut</span>
            <span v-if="selectedItem.cut_time" class="info-chip cut-time-chip">{{ Number(selectedItem.cut_time).toFixed(1) }} min cut time</span>
          </div>

          <!-- Routing Operations Table -->
          <div class="section-title">Routing Operations</div>
          <div class="routing-table">
            <div class="table-header">
              <span class="col-order">Order</span>
              <span class="col-seq">Seq</span>
              <span class="col-station">Station</span>
              <span class="col-name">Name</span>
              <span class="col-time">Est. Time</span>
              <span class="col-cost">Est. Cost</span>
              <span class="col-actions"></span>
            </div>

            <div v-if="routing.length === 0" class="no-steps">
              No routing steps. Apply a template or add stations below.
            </div>

            <div v-for="(step, index) in routing" :key="index" class="table-row">
              <span class="col-order">
                <button class="order-btn" @click="moveStepUp(index)" :disabled="index === 0" title="Move Up">
                  <i class="pi pi-chevron-up"></i>
                </button>
                <button class="order-btn" @click="moveStepDown(index)" :disabled="index === routing.length - 1" title="Move Down">
                  <i class="pi pi-chevron-down"></i>
                </button>
              </span>
              <span class="col-seq">{{ step.sequence }}</span>
              <span class="col-station">{{ step.station_code }}</span>
              <span class="col-name">
                {{ step.station_name }}
                <span v-if="isStepOutsourced(step)" class="outsourced-tag">outsourced</span>
              </span>
              <span class="col-time">
                <input v-model.number="step.est_time_min" type="number" min="0" step="0.1" class="time-input" :class="{ 'input-dimmed': isStepOutsourced(step) }" /> min
                <span v-if="step.station_code === '012' && selectedItem?.cut_time" class="cut-time-hint">(from cut_time)</span>
              </span>
              <span class="col-cost">
                <!-- Outsourced: always editable flat cost -->
                <template v-if="isStepOutsourced(step)">
                  <span class="cost-dollar">$</span>
                  <input
                    type="number"
                    :value="step.cost_override ?? getStepWorkstation(step)?.outsourced_cost_default ?? ''"
                    min="0"
                    step="0.5"
                    placeholder="flat $"
                    class="cost-input outsourced-input"
                    @change="step.cost_override = parseFloat(($event.target as HTMLInputElement).value) || null"
                  />
                </template>
                <!-- In-house: click-to-edit calculated value -->
                <template v-else>
                  <template v-if="editingCostIndex === index">
                    <span class="cost-dollar">$</span>
                    <input
                      v-model="editingCostValue"
                      type="number"
                      min="0"
                      step="0.01"
                      class="cost-input cost-editing"
                      @blur="commitEditCost(index)"
                      @keyup.enter="commitEditCost(index)"
                      @keyup.escape="cancelEditCost()"
                      ref="costEditInput"
                    />
                  </template>
                  <template v-else>
                    <span
                      class="cost-display"
                      :class="{ 'cost-overridden': step.cost_override != null }"
                      @click="startEditCost(index)"
                      :title="step.cost_override != null ? 'Overridden (click to edit, x to reset)' : 'Click to override'"
                    >
                      {{ formatCost(getStepCost(step)) }}
                    </span>
                    <button
                      v-if="step.cost_override != null"
                      class="cost-reset-btn"
                      @click.stop="clearCostOverride(index)"
                      title="Reset to calculated"
                    >&times;</button>
                  </template>
                </template>
              </span>
              <span class="col-actions">
                <button class="remove-btn" @click="removeRoutingStep(index)" title="Remove">
                  <i class="pi pi-times"></i>
                </button>
              </span>
            </div>

            <div class="table-footer">
              <span class="footer-time"><strong>Total: {{ totalEstTime }} min</strong></span>
              <span class="footer-costs">
                <span v-if="totalLaborCost > 0">Labor: {{ formatCost(totalLaborCost) }}</span>
                <span v-if="totalOutsourcedCost > 0">Outsourced: {{ formatCost(totalOutsourcedCost) }}</span>
                <span v-if="totalMaterialCost > 0">Material: {{ formatCost(totalMaterialCost) }}</span>
                <span class="footer-total">Est. Cost: <strong>{{ formatCost(totalEstCost) }}</strong></span>
              </span>
            </div>
          </div>

          <!-- Add Station -->
          <div class="add-station-row">
            <select v-model="addStationId" class="station-select">
              <option value="">-- Select Station --</option>
              <option v-for="station in availableStations" :key="station.id" :value="station.id">
                {{ station.station_code }} - {{ station.station_name }}
              </option>
            </select>
            <input v-model.number="addStationTime" type="number" min="0" step="0.1" placeholder="Est. min" class="time-input-sm" />
            <button class="add-btn" @click="addRoutingStep" :disabled="!addStationId">
              <i class="pi pi-plus"></i> Add Station
            </button>
          </div>

          <!-- Templates -->
          <div class="section-title">Apply Routing Template</div>
          <div class="templates-section">
            <button
              v-for="tmpl in routingTemplates"
              :key="tmpl.key"
              class="template-btn"
              @click="applyTemplate(tmpl.key)"
            >
              {{ tmpl.label }}
            </button>
          </div>

          <!-- Create New Station -->
          <div class="section-title">Create New Station</div>
          <div class="create-station-row">
            <input v-model="newStationCode" type="text" placeholder="Code (e.g. 055)" class="station-code-input" />
            <input v-model="newStationName" type="text" placeholder="Name" class="station-name-input" />
            <button class="create-btn" @click="createStation" :disabled="creatingStation || !newStationCode || !newStationName">
              {{ creatingStation ? 'Creating...' : 'Create' }}
            </button>
          </div>

          <!-- Raw Material Requirements -->
          <div class="section-title">Raw Material Requirements</div>
          <div class="material-section">
            <div v-if="selectedItem.mass" class="part-mass">
              Part mass: <strong>{{ selectedItem.mass?.toFixed(1) }} lb</strong>
            </div>
            <div class="material-filters">
              <select v-model="selectedMaterialType" class="mat-select">
                <option value="all">Type</option>
                <option v-for="type in materialTypeOptions" :key="type" :value="type">
                  {{ type === 'SQ' ? 'Square/Rect Tube' : type === 'OT' ? 'Round Tube' : 'Sheet Metal' }}
                </option>
              </select>
              <select v-model="selectedMaterialSize" class="mat-select" :disabled="selectedMaterialType === 'all'">
                <option value="all">Size</option>
                <option v-for="size in materialSizeOptions" :key="size" :value="size">
                  {{ size }}
                </option>
              </select>
              <select v-model="selectedMaterial" class="mat-select">
                <option value="">Material</option>
                <option v-for="mat in filteredMaterials" :key="mat.id" :value="mat.id">
                  {{ mat.part_number }} ({{ mat.material_code }})
                </option>
              </select>
            </div>
            <!-- Blank dimensions (SM only) -->
            <div v-if="selectedMaterialIsSM" class="blank-dims">
              <label>Blank W:</label>
              <input v-model.number="blankWidth" type="number" min="0.1" step="0.1" placeholder="W (in)" class="dim-input" />
              <label>x H:</label>
              <input v-model.number="blankHeight" type="number" min="0.1" step="0.1" placeholder="H (in)" class="dim-input" />
            </div>
            <div class="material-actions">
              <button class="calc-btn" @click="calculateMaterial" :disabled="!selectedMaterial">
                Calc
              </button>
              <span v-if="calculatedLength !== null" class="calc-result">
                {{ calculatedLength }}{{ selectedMaterialIsSM ? ' lb' : '" needed' }}
              </span>
              <input v-model.number="materialQty" type="number" min="0.01" step="0.01" placeholder="Qty" class="qty-input" />
              <button class="assign-btn" @click="assignMaterial" :disabled="!selectedMaterial">
                Assign
              </button>
            </div>

            <!-- Assigned Materials -->
            <div v-if="itemMaterials.length > 0" class="assigned-materials">
              <div v-for="mat in itemMaterials" :key="mat.id" class="assigned-item">
                <span class="mat-pn">{{ mat.material?.part_number }}</span>
                <span class="mat-qty">
                  {{ mat.qty_required }}{{ mat.material?.material_type === 'SM' ? ' lb' : '"' }}
                  <span v-if="mat.blank_width_in && mat.blank_height_in" class="blank-info">
                    ({{ mat.blank_width_in }}" x {{ mat.blank_height_in }}")
                  </span>
                </span>
                <span class="mat-cost">{{ formatCost(getMaterialCost(mat)) }}</span>
                <button class="remove-mat-btn" @click="removeMaterial(mat.id!)">&times;</button>
              </div>
            </div>
          </div>

          <!-- Purchased Part Info -->
          <div v-if="selectedItem?.is_supplier_part || selectedItem?.item_number?.startsWith('mmc') || selectedItem?.item_number?.startsWith('spn')" class="section-title">Purchased Part Info</div>
          <div v-if="selectedItem?.is_supplier_part || selectedItem?.item_number?.startsWith('mmc') || selectedItem?.item_number?.startsWith('spn')" class="purchase-section">
            <div class="purchase-fields">
              <div class="purchase-field">
                <label>Supplier</label>
                <input v-model="purchaseSupplier" type="text" placeholder="e.g. McMaster-Carr" class="purchase-input" />
              </div>
              <div class="purchase-field">
                <label>Supplier P/N</label>
                <input v-model="purchasePn" type="text" placeholder="e.g. 93337A110" class="purchase-input" />
              </div>
              <div class="purchase-field price-field">
                <label>Unit Price</label>
                <div class="price-input-wrap">
                  <span class="dollar-sign">$</span>
                  <input v-model.number="purchasePrice" type="number" min="0" step="0.01" placeholder="0.00" class="purchase-input price-input" />
                </div>
              </div>
              <button class="update-purchase-btn" @click="updatePurchaseInfo" :disabled="savingPurchase">
                {{ savingPurchase ? 'Saving...' : 'Update' }}
              </button>
            </div>
          </div>

          <!-- Save / Clear Buttons -->
          <div class="action-buttons">
            <button class="clear-btn" @click="clearRouting">
              <i class="pi pi-trash"></i> Clear All
            </button>
            <button class="save-btn" @click="saveRouting" :disabled="savingRouting">
              <i class="pi pi-save"></i>
              {{ savingRouting ? 'Saving...' : 'Save Routing' }}
            </button>
          </div>
        </template>
      </div>

      <!-- Right Panel - PDF Preview -->
      <div v-if="showPdfPreview" class="pdf-panel" :style="{ width: pdfPreviewWidth + 'px' }">
        <div class="pdf-header">
          <span class="pdf-title">{{ selectedItem?.item_number }} - PDF</span>
          <div class="pdf-controls">
            <button class="size-btn" @click="setPdfSize('S')">S</button>
            <button class="size-btn" @click="setPdfSize('M')">M</button>
            <button class="size-btn" @click="setPdfSize('L')">L</button>
            <button class="close-btn" @click="closePdfPreview">&times;</button>
          </div>
        </div>
        <div class="pdf-content">
          <div v-if="loadingPdf" class="pdf-loading">Loading PDF...</div>
          <iframe v-else-if="pdfUrl" :src="pdfUrl" class="pdf-iframe"></iframe>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
* {
  box-sizing: border-box;
}

.routing-editor {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  font-family: system-ui, -apple-system, sans-serif;
}

/* Header */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: #0f172a;
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
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid #334155;
  background: #1e293b;
  color: #9ca3af;
  cursor: pointer;
  font-size: 12px;
}

.back-btn:hover {
  background: #334155;
  color: #e5e7eb;
}

.page-header h1 {
  font-size: 16px;
  margin: 0;
  color: #e5e7eb;
}

.nav-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #374151;
  border: none;
  color: white;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}

.nav-btn:hover {
  background: #4b5563;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #059669;
  border: none;
  color: white;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.15s;
}

.refresh-btn:hover:not(:disabled) {
  background: #047857;
}

.refresh-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* Messages */
.error-message, .success-message {
  margin: 8px 16px 0;
  padding: 8px 12px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.error-message {
  background: #7f1d1d;
  color: #fca5a5;
}

.success-message {
  background: #065f46;
  color: #6ee7b7;
}

.close-msg {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 16px;
}

/* Layout */
.editor-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  height: calc(100vh - 50px);
  overflow: hidden;
}

.editor-layout.with-preview {
  grid-template-columns: 280px 1fr auto;
}

/* Sidebar */
.sidebar {
  background: #0f172a;
  border-right: 1px solid #1e293b;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 12px;
  border-bottom: 1px solid #1e293b;
}

.search-input {
  width: 100%;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #334155;
  background: #020617;
  color: #e5e7eb;
  font-size: 13px;
}

.search-input:focus {
  outline: none;
  border-color: #38bdf8;
}

.filter-row {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.filter-select {
  flex: 1;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid #334155;
  background: #020617;
  color: #e5e7eb;
  font-size: 11px;
}

.filter-stats {
  margin-top: 8px;
  font-size: 11px;
  color: #6b7280;
}

.loading-small {
  padding: 20px;
  text-align: center;
  color: #6b7280;
}

/* Items List */
.items-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.items-list::-webkit-scrollbar {
  width: 6px;
}

.items-list::-webkit-scrollbar-track {
  background: #0f172a;
}

.items-list::-webkit-scrollbar-thumb {
  background: #374151;
  border-radius: 3px;
}

.item-row {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 2px;
}

.item-row:hover {
  background: #1e293b;
}

.item-row.selected {
  background: #1d4ed8;
}

.item-row-main {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pdf-icon {
  color: #f87171;
  font-size: 12px;
}

.item-number {
  font-size: 13px;
  font-weight: 600;
  color: #e5e7eb;
}

.mat-badge {
  padding: 1px 5px;
  border-radius: 3px;
  border: 1px solid #b8860b;
  color: #fbbf24;
  font-size: 9px;
  font-weight: 600;
}

.ops-badge {
  margin-left: auto;
  padding: 2px 6px;
  border-radius: 4px;
  background: #065f46;
  color: #6ee7b7;
  font-size: 10px;
  font-weight: 600;
}

.no-routing-badge {
  margin-left: auto;
  padding: 2px 6px;
  border-radius: 4px;
  background: #7f1d1d;
  color: #fca5a5;
  font-size: 10px;
}

.item-name {
  display: block;
  font-size: 11px;
  color: #9ca3af;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Main Panel */
.main-panel {
  padding: 16px;
  overflow-y: auto;
  background: #020617;
}

.no-selection {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6b7280;
}

.no-selection i {
  font-size: 32px;
  margin-bottom: 12px;
}

/* Item Header */
.item-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #1e293b;
}

.item-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-number-large {
  font-size: 20px;
  font-weight: 700;
  color: #e5e7eb;
}

.item-desc {
  font-size: 13px;
  color: #9ca3af;
}

.file-tiles {
  display: flex;
  gap: 6px;
}

.file-tile {
  padding: 4px 10px;
  border: none;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  text-transform: uppercase;
}

.file-tile.pdf {
  background: #7f1d1d;
  color: #fca5a5;
}

.file-tile.pdf:hover { background: #991b1b; }

.file-tile.svg {
  background: #365314;
  color: #bef264;
}

.file-tile.svg:hover { background: #3f6212; }

.file-tile.dxf {
  background: #3f3f46;
  color: #a1a1aa;
}

.file-tile.dxf:hover { background: #52525b; }

.file-tile.step, .file-tile.cad {
  background: #1e3a5f;
  color: #93c5fd;
}

.file-tile.step:hover, .file-tile.cad:hover { background: #1e40af; }

/* Part Info */
.part-info-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.info-chip {
  padding: 4px 10px;
  background: #1e293b;
  border-radius: 4px;
  font-size: 12px;
  color: #9ca3af;
}

/* Section Titles */
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #9ca3af;
  margin: 16px 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Routing Table */
.routing-table {
  background: #0f172a;
  border-radius: 8px;
  border: 1px solid #1e293b;
  overflow: hidden;
}

.table-header {
  display: grid;
  grid-template-columns: 70px 50px 70px 1fr 100px 110px 36px;
  gap: 8px;
  padding: 10px 12px;
  background: #1e293b;
  font-size: 11px;
  font-weight: 600;
  color: #9ca3af;
  text-transform: uppercase;
}

.table-row {
  display: grid;
  grid-template-columns: 70px 50px 70px 1fr 100px 110px 36px;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #1e293b;
  align-items: center;
  font-size: 13px;
}

.table-row:hover {
  background: #1e293b;
}

.col-order {
  display: flex;
  gap: 2px;
}

.order-btn {
  padding: 4px 6px;
  background: #374151;
  border: none;
  border-radius: 3px;
  color: #9ca3af;
  cursor: pointer;
  font-size: 10px;
}

.order-btn:hover:not(:disabled) {
  background: #4b5563;
  color: #e5e7eb;
}

.order-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.col-seq {
  font-family: monospace;
  color: #6b7280;
}

.col-station {
  font-weight: 600;
  color: #38bdf8;
}

.col-name {
  color: #e5e7eb;
}

.col-time {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #9ca3af;
}

.time-input {
  width: 60px;
  padding: 4px 6px;
  border: 1px solid #334155;
  border-radius: 4px;
  background: #020617;
  color: #e5e7eb;
  font-size: 12px;
  text-align: right;
}

.time-input:focus {
  outline: none;
  border-color: #38bdf8;
}

.cut-time-hint {
  position: absolute;
  right: 100%;
  margin-right: 6px;
  font-size: 10px;
  color: #6ee7b7;
  white-space: nowrap;
}

.cut-time-chip {
  background: #065f46;
  color: #6ee7b7;
}

.remove-btn {
  padding: 4px 8px;
  background: transparent;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
}

.remove-btn:hover {
  color: #f87171;
}

.no-steps {
  padding: 24px;
  text-align: center;
  color: #6b7280;
  font-size: 13px;
}

.table-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: #1e293b;
  font-size: 13px;
  color: #e5e7eb;
  flex-wrap: wrap;
  gap: 8px;
}

.footer-costs {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #9ca3af;
}

.footer-total {
  color: #10b981;
}

/* Cost column */
.col-cost {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
}

.cost-dollar {
  color: #6b7280;
  font-size: 11px;
}

.cost-input {
  width: 72px;
  padding: 4px 6px;
  border: 1px solid #334155;
  border-radius: 4px;
  background: #020617;
  color: #e5e7eb;
  font-size: 12px;
  text-align: right;
}

.cost-input:focus {
  border-color: #3b82f6;
  outline: none;
}

.outsourced-input {
  border-color: #92400e;
}

.outsourced-input:focus {
  border-color: #f59e0b;
}

.cost-editing {
  border-color: #f59e0b;
  background: #1c1917;
}

.cost-display {
  cursor: pointer;
  padding: 3px 6px;
  border-radius: 3px;
  color: #9ca3af;
  font-size: 12px;
  transition: background 0.15s;
}

.cost-display:hover {
  background: #374151;
  color: #e5e7eb;
}

.cost-overridden {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
  font-weight: 500;
}

.cost-reset-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  padding: 0 2px;
  line-height: 1;
}

.cost-reset-btn:hover {
  color: #f87171;
}

.outsourced-tag {
  font-size: 10px;
  background: #92400e;
  color: #fde68a;
  padding: 1px 5px;
  border-radius: 3px;
  margin-left: 4px;
}

.input-dimmed {
  opacity: 0.4;
}

.mat-cost {
  color: #10b981;
  font-size: 12px;
  font-weight: 500;
  margin-left: 8px;
}

/* Add Station */
.add-station-row {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.station-select {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 13px;
}

.time-input-sm {
  width: 80px;
  padding: 8px 10px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 13px;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #374151;
  border: none;
  border-radius: 6px;
  color: #e5e7eb;
  cursor: pointer;
  font-size: 13px;
}

.add-btn:hover:not(:disabled) {
  background: #4b5563;
}

.add-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Templates */
.templates-section {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.template-btn {
  padding: 8px 16px;
  background: #374151;
  border: none;
  border-radius: 6px;
  color: #e5e7eb;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.template-btn:hover {
  background: #4b5563;
}

/* Create Station */
.create-station-row {
  display: flex;
  gap: 8px;
}

.station-code-input {
  width: 100px;
  padding: 8px 10px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 13px;
}

.station-name-input {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid #334155;
  border-radius: 6px;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 13px;
}

.create-btn {
  padding: 8px 16px;
  background: #065f46;
  border: none;
  border-radius: 6px;
  color: #6ee7b7;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}

.create-btn:hover:not(:disabled) {
  background: #047857;
}

.create-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Material Section */
.material-section {
  background: #0f172a;
  border-radius: 8px;
  padding: 12px;
  border: 1px solid #1e293b;
}

.part-mass {
  margin-bottom: 12px;
  font-size: 13px;
  color: #9ca3af;
}

.part-mass strong {
  color: #38bdf8;
}

.material-filters {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.mat-select {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid #334155;
  border-radius: 4px;
  background: #020617;
  color: #e5e7eb;
  font-size: 12px;
}

.blank-dims {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 12px;
  color: #94a3b8;
}

.blank-dims label {
  white-space: nowrap;
}

.dim-input {
  width: 80px;
  padding: 6px 8px;
  border: 1px solid #334155;
  border-radius: 4px;
  background: #020617;
  color: #e5e7eb;
  font-size: 12px;
}

.blank-info {
  color: #94a3b8;
  font-size: 11px;
}

.material-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.calc-btn {
  padding: 6px 12px;
  background: #374151;
  border: none;
  border-radius: 4px;
  color: #e5e7eb;
  cursor: pointer;
  font-size: 12px;
}

.calc-btn:hover:not(:disabled) {
  background: #4b5563;
}

.calc-result {
  font-size: 12px;
  color: #6ee7b7;
  font-weight: 500;
}

.qty-input {
  width: 60px;
  padding: 6px 8px;
  border: 1px solid #334155;
  border-radius: 4px;
  background: #020617;
  color: #e5e7eb;
  font-size: 12px;
}

.assign-btn {
  padding: 6px 12px;
  background: #065f46;
  border: none;
  border-radius: 4px;
  color: #6ee7b7;
  cursor: pointer;
  font-size: 12px;
}

.assign-btn:hover:not(:disabled) {
  background: #047857;
}

.assigned-materials {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #1e293b;
}

.assigned-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #1e293b;
  border: 1px solid #b8860b;
  border-radius: 4px;
  margin-bottom: 4px;
  font-size: 12px;
}

.mat-pn {
  flex: 1;
  color: #e5e7eb;
}

.mat-qty {
  color: #6ee7b7;
  font-weight: 600;
}

.remove-mat-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  padding: 0 4px;
}

.remove-mat-btn:hover {
  color: #f87171;
}

/* Purchased Part Section */
.purchase-section {
  background: #0f172a;
  border-radius: 8px;
  padding: 12px;
  border: 1px solid #1e293b;
}

.purchase-fields {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.purchase-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 140px;
}

.purchase-field label {
  font-size: 11px;
  color: #9ca3af;
  text-transform: uppercase;
  font-weight: 600;
}

.purchase-input {
  padding: 6px 8px;
  border: 1px solid #334155;
  border-radius: 4px;
  background: #020617;
  color: #e5e7eb;
  font-size: 12px;
}

.purchase-input:focus {
  outline: none;
  border-color: #38bdf8;
}

.price-field {
  flex: 0 0 120px;
  min-width: 120px;
}

.price-input-wrap {
  display: flex;
  align-items: center;
  gap: 0;
}

.dollar-sign {
  padding: 6px 0 6px 8px;
  background: #020617;
  border: 1px solid #334155;
  border-right: none;
  border-radius: 4px 0 0 4px;
  color: #6ee7b7;
  font-size: 12px;
  font-weight: 600;
}

.price-input {
  border-radius: 0 4px 4px 0 !important;
  flex: 1;
}

.update-purchase-btn {
  padding: 6px 16px;
  background: #059669;
  border: none;
  border-radius: 4px;
  color: white;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  align-self: flex-end;
}

.update-purchase-btn:hover:not(:disabled) {
  background: #047857;
}

.update-purchase-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Action Buttons */
.action-buttons {
  display: flex;
  gap: 12px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #1e293b;
}

.clear-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  background: #374151;
  border: none;
  border-radius: 6px;
  color: #e5e7eb;
  cursor: pointer;
  font-size: 14px;
}

.clear-btn:hover {
  background: #4b5563;
}

.save-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 24px;
  background: #2563eb;
  border: none;
  border-radius: 6px;
  color: white;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  margin-left: auto;
}

.save-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.save-btn:disabled {
  background: #374151;
  color: #6b7280;
  cursor: not-allowed;
}

/* PDF Panel */
.pdf-panel {
  background: #0f172a;
  border-left: 1px solid #1e293b;
  display: flex;
  flex-direction: column;
  min-width: 400px;
  max-width: 1000px;
}

.pdf-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: #1e293b;
  border-bottom: 1px solid #334155;
}

.pdf-title {
  font-size: 13px;
  font-weight: 600;
  color: #e5e7eb;
}

.pdf-controls {
  display: flex;
  gap: 4px;
}

.size-btn {
  padding: 4px 10px;
  background: #374151;
  border: none;
  border-radius: 4px;
  color: #9ca3af;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
}

.size-btn:hover {
  background: #4b5563;
  color: #e5e7eb;
}

.close-btn {
  padding: 4px 10px;
  background: #374151;
  border: none;
  border-radius: 4px;
  color: #9ca3af;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}

.close-btn:hover {
  background: #dc2626;
  color: white;
}

.pdf-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.pdf-loading {
  padding: 40px;
  text-align: center;
  color: #6b7280;
}

.pdf-iframe {
  flex: 1;
  width: 100%;
  border: none;
  background: white;
}
</style>
