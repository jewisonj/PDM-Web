<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { DxfViewer } from 'dxf-viewer'
import { Color, Scene, OrthographicCamera, Vector3 } from 'three'
import { getSignedUrlFromPath } from '../services/storage'

interface FileInfo {
  id: string
  file_name: string
  file_path?: string
  file_type: string
}

interface MeasurePoint {
  // World coordinates (before rotation compensation, for screen projection)
  worldX: number
  worldY: number
  // DXF coordinates (after rotation compensation, for distance calculation)
  dxfX: number
  dxfY: number
  snapped: boolean
}

interface DxfViewerInstance {
  Load: (options: { url: string }) => Promise<void>
  Destroy: () => void
  FitView: (minX: number, maxX: number, minY: number, maxY: number, padding: number) => void
  Render: () => void
  GetScene: () => Scene
  GetCamera: () => OrthographicCamera
  GetCanvas: () => HTMLCanvasElement
  GetOrigin: () => { x: number; y: number }
  bounds?: { minX: number; maxX: number; minY: number; maxY: number }
  origin?: { x: number; y: number }
}

const props = defineProps<{
  file: FileInfo
}>()

const emit = defineEmits<{
  close: []
}>()

const viewerContainer = ref<HTMLDivElement | null>(null)
const loading = ref(true)
const error = ref('')
const signedUrl = ref('')

// Rotation state
const rotation = ref(0)

// Measurement state
const measureMode = ref(false)
const measurePoint1 = ref<MeasurePoint | null>(null)
const measurePoint2 = ref<MeasurePoint | null>(null)
const measuredDistance = ref<number | null>(null)

// Live cursor state (for snap preview)
const cursorPos = ref<{ x: number; y: number; snapped: boolean } | null>(null)

let viewer: DxfViewerInstance | null = null

// Snap threshold in pixels
const SNAP_THRESHOLD = 15

// Cache of geometry vertices for snapping (world coordinates)
let cachedVertices: Vector3[] = []

// Extract all vertices from scene geometry
function extractVertices(): Vector3[] {
  if (!viewer) return []

  const vertices: Vector3[] = []
  const scene = viewer.GetScene()

  scene.traverse((obj) => {
    // Skip non-mesh objects
    if (!('geometry' in obj)) return

    const geometry = (obj as any).geometry
    if (!geometry || !geometry.attributes) return

    const positionAttr = geometry.attributes.position
    if (!positionAttr) return

    // Get world matrix for this object
    const worldMatrix = obj.matrixWorld

    // Extract vertices
    for (let i = 0; i < positionAttr.count; i++) {
      const vertex = new Vector3(
        positionAttr.getX(i),
        positionAttr.getY(i),
        positionAttr.getZ(i)
      )
      // Transform to world coordinates
      vertex.applyMatrix4(worldMatrix)
      vertices.push(vertex)
    }
  })

  return vertices
}

// Convert world position to screen pixels
function worldToScreen(worldPos: Vector3): { x: number; y: number } | null {
  if (!viewer) return null

  const camera = viewer.GetCamera()
  const canvas = viewer.GetCanvas()

  // Clone and project
  const projected = worldPos.clone().project(camera)

  // Convert from NDC to screen pixels
  const x = (projected.x + 1) / 2 * canvas.clientWidth
  const y = (1 - projected.y) / 2 * canvas.clientHeight

  return { x, y }
}

async function initViewer() {
  if (!viewerContainer.value || !props.file.file_path) return

  loading.value = true
  error.value = ''
  resetMeasurement()
  rotation.value = 0

  try {
    const url = await getSignedUrlFromPath(props.file.file_path)
    if (!url) {
      throw new Error('Failed to get file URL')
    }
    signedUrl.value = url

    viewer = new DxfViewer(viewerContainer.value, {
      clearColor: new Color('#1e293b'),
      autoResize: true,
      colorCorrection: true,
      blackWhiteInversion: true,
      antialias: true
    }) as unknown as DxfViewerInstance

    await viewer.Load({ url })

    // Cache vertices for snapping
    cachedVertices = extractVertices()
    console.log(`Cached ${cachedVertices.length} vertices for snapping`)

    // Add event handlers for measurement (passive to not interfere with zoom/pan)
    const canvas = viewer.GetCanvas()
    canvas.addEventListener('click', handleCanvasClick)
    canvas.addEventListener('mousemove', handleCanvasMouseMove, { passive: true })

    loading.value = false
  } catch (e: unknown) {
    console.error('DXF viewer error:', e)
    error.value = e instanceof Error ? e.message : 'Failed to load DXF file'
    loading.value = false
  }
}

function fitView() {
  if (viewer && viewer.bounds) {
    viewer.FitView(
      viewer.bounds.minX - (viewer.origin?.x || 0),
      viewer.bounds.maxX - (viewer.origin?.x || 0),
      viewer.bounds.minY - (viewer.origin?.y || 0),
      viewer.bounds.maxY - (viewer.origin?.y || 0),
      0.1
    )
  }
}

function rotateScene(degrees: number) {
  if (!viewer) return
  rotation.value = (rotation.value + degrees) % 360
  if (rotation.value < 0) rotation.value += 360
  const scene = viewer.GetScene()
  scene.rotation.z = (rotation.value * Math.PI) / 180
  viewer.Render()
}

function resetRotation() {
  if (!viewer) return
  rotation.value = 0
  const scene = viewer.GetScene()
  scene.rotation.z = 0
  viewer.Render()
}

// Get screen pixel position from client coordinates
function getScreenPosition(clientX: number, clientY: number): { x: number; y: number } {
  if (!viewer) return { x: 0, y: 0 }
  const canvas = viewer.GetCanvas()
  const rect = canvas.getBoundingClientRect()
  return {
    x: clientX - rect.left,
    y: clientY - rect.top
  }
}

// Convert screen coordinates to DXF world coordinates
function screenToWorld(clientX: number, clientY: number): { x: number; y: number } {
  if (!viewer) return { x: 0, y: 0 }

  const canvas = viewer.GetCanvas()
  const camera = viewer.GetCamera()
  const rect = canvas.getBoundingClientRect()

  const ndcX = ((clientX - rect.left) / rect.width) * 2 - 1
  const ndcY = -((clientY - rect.top) / rect.height) * 2 + 1

  const worldPos = new Vector3(ndcX, ndcY, 0).unproject(camera)
  const origin = viewer.GetOrigin()

  // Account for scene rotation
  const angle = rotation.value * Math.PI / 180
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  const rotatedX = worldPos.x * cos + worldPos.y * sin
  const rotatedY = -worldPos.x * sin + worldPos.y * cos

  return {
    x: rotatedX + origin.x,
    y: rotatedY + origin.y
  }
}

interface SnapResult {
  // World coordinates (for screen projection - these move with zoom/pan)
  worldX: number
  worldY: number
  // DXF coordinates (for distance calculation - rotation compensated)
  dxfX: number
  dxfY: number
  snapped: boolean
  snapScreenPos?: { x: number; y: number }
}

// Try to snap to nearby geometry vertex
function trySnap(clientX: number, clientY: number): SnapResult {
  if (!viewer) return { worldX: 0, worldY: 0, dxfX: 0, dxfY: 0, snapped: false }

  const screenPos = getScreenPosition(clientX, clientY)
  const origin = viewer.GetOrigin()
  const angle = rotation.value * Math.PI / 180
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)

  // Find nearest vertex within snap threshold
  let nearestDist = Infinity
  let nearestVertex: Vector3 | null = null
  let nearestScreenPos: { x: number; y: number } | null = null

  for (const vertex of cachedVertices) {
    const vertexScreen = worldToScreen(vertex)
    if (!vertexScreen) continue

    const dx = vertexScreen.x - screenPos.x
    const dy = vertexScreen.y - screenPos.y
    const dist = Math.sqrt(dx * dx + dy * dy)

    if (dist < nearestDist && dist < SNAP_THRESHOLD) {
      nearestDist = dist
      nearestVertex = vertex
      nearestScreenPos = vertexScreen
    }
  }

  if (nearestVertex && nearestScreenPos) {
    // DXF coordinates (rotation compensated)
    const rotatedX = nearestVertex.x * cos + nearestVertex.y * sin
    const rotatedY = -nearestVertex.x * sin + nearestVertex.y * cos

    return {
      worldX: nearestVertex.x,
      worldY: nearestVertex.y,
      dxfX: rotatedX + origin.x,
      dxfY: rotatedY + origin.y,
      snapped: true,
      snapScreenPos: nearestScreenPos
    }
  }

  // No snap - use cursor position
  const camera = viewer.GetCamera()
  const canvas = viewer.GetCanvas()
  const rect = canvas.getBoundingClientRect()

  const ndcX = ((clientX - rect.left) / rect.width) * 2 - 1
  const ndcY = -((clientY - rect.top) / rect.height) * 2 + 1
  const worldPos = new Vector3(ndcX, ndcY, 0).unproject(camera)

  const rotatedX = worldPos.x * cos + worldPos.y * sin
  const rotatedY = -worldPos.x * sin + worldPos.y * cos

  return {
    worldX: worldPos.x,
    worldY: worldPos.y,
    dxfX: rotatedX + origin.x,
    dxfY: rotatedY + origin.y,
    snapped: false
  }
}

function handleCanvasMouseMove(event: MouseEvent) {
  if (!measureMode.value || !viewer) {
    cursorPos.value = null
    return
  }

  const screenPos = getScreenPosition(event.clientX, event.clientY)
  const snapResult = trySnap(event.clientX, event.clientY)

  // If snapped, show cursor at snap point; otherwise at mouse position
  cursorPos.value = {
    x: snapResult.snapScreenPos?.x ?? screenPos.x,
    y: snapResult.snapScreenPos?.y ?? screenPos.y,
    snapped: snapResult.snapped
  }
}

function handleCanvasClick(event: MouseEvent) {
  if (!measureMode.value || !viewer) return

  const snapResult = trySnap(event.clientX, event.clientY)

  const point: MeasurePoint = {
    worldX: snapResult.worldX,
    worldY: snapResult.worldY,
    dxfX: snapResult.dxfX,
    dxfY: snapResult.dxfY,
    snapped: snapResult.snapped
  }

  if (!measurePoint1.value) {
    measurePoint1.value = point
    measuredDistance.value = null
  } else if (!measurePoint2.value) {
    measurePoint2.value = point
    // Calculate distance using DXF coordinates
    const dx = measurePoint2.value.dxfX - measurePoint1.value.dxfX
    const dy = measurePoint2.value.dxfY - measurePoint1.value.dxfY
    measuredDistance.value = Math.sqrt(dx * dx + dy * dy)
  } else {
    // Start new measurement
    measurePoint1.value = point
    measurePoint2.value = null
    measuredDistance.value = null
  }
}

function toggleMeasureMode() {
  measureMode.value = !measureMode.value
  if (!measureMode.value) {
    resetMeasurement()
  }
}

function resetMeasurement() {
  measurePoint1.value = null
  measurePoint2.value = null
  measuredDistance.value = null
  cursorPos.value = null
}

// Convert a measure point's world coordinates to current screen position
function getPointScreenPos(point: MeasurePoint | null): { x: number; y: number } | null {
  if (!point || !viewer) return null
  const worldVec = new Vector3(point.worldX, point.worldY, 0)
  return worldToScreen(worldVec)
}

// Reactive screen positions that update with cursorPos (which updates on mousemove)
const point1ScreenPos = computed(() => {
  // Depend on cursorPos to trigger recalculation on mouse move
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  cursorPos.value
  return getPointScreenPos(measurePoint1.value)
})

const point2ScreenPos = computed(() => {
  // Depend on cursorPos to trigger recalculation on mouse move
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  cursorPos.value
  return getPointScreenPos(measurePoint2.value)
})

// Computed SVG line for measurement visualization
const measureLine = computed(() => {
  if (!point1ScreenPos.value || !point2ScreenPos.value) return null
  return {
    x1: point1ScreenPos.value.x,
    y1: point1ScreenPos.value.y,
    x2: point2ScreenPos.value.x,
    y2: point2ScreenPos.value.y
  }
})

// Computed position for distance label (midpoint of line)
const distanceLabelPos = computed(() => {
  if (!measureLine.value) return null
  return {
    x: (measureLine.value.x1 + measureLine.value.x2) / 2,
    y: (measureLine.value.y1 + measureLine.value.y2) / 2 - 20
  }
})

async function downloadFile() {
  if (!props.file.file_path) return
  if (!signedUrl.value) {
    const url = await getSignedUrlFromPath(props.file.file_path)
    if (url) window.open(url, '_blank')
  } else {
    window.open(signedUrl.value, '_blank')
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (measureMode.value) {
      measureMode.value = false
      resetMeasurement()
    } else {
      emit('close')
    }
  }
}

function cleanup() {
  if (viewer) {
    const canvas = viewer.GetCanvas()
    canvas.removeEventListener('click', handleCanvasClick)
    canvas.removeEventListener('mousemove', handleCanvasMouseMove)
    viewer.Destroy()
    viewer = null
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  initViewer()
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  cleanup()
})

watch(() => props.file.id, () => {
  cleanup()
  initViewer()
})
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="dxf-modal">
      <div class="modal-header">
        <h2>
          <i class="pi pi-file"></i>
          {{ file.file_name }}
        </h2>
        <button class="close-btn" @click="emit('close')" title="Close (Esc)">&times;</button>
      </div>

      <div class="modal-body">
        <!-- Loading State -->
        <div v-if="loading" class="loading-state">
          <i class="pi pi-spin pi-spinner"></i>
          Loading DXF file...
        </div>

        <!-- Error State -->
        <div v-else-if="error" class="error-state">
          <i class="pi pi-exclamation-triangle"></i>
          {{ error }}
        </div>

        <!-- Viewer Container -->
        <div ref="viewerContainer" class="viewer-container" :class="{ hidden: loading || error, 'measure-mode': measureMode }"></div>

        <!-- Measurement Overlay (HTML/CSS based) -->
        <div v-if="measureMode && !loading && !error" class="measure-overlay">
          <!-- SVG for line drawing -->
          <svg class="measure-svg">
            <!-- Measurement line -->
            <line
              v-if="measureLine"
              :x1="measureLine.x1"
              :y1="measureLine.y1"
              :x2="measureLine.x2"
              :y2="measureLine.y2"
              class="measure-line"
            />
            <!-- Point 1 marker -->
            <circle
              v-if="point1ScreenPos"
              :cx="point1ScreenPos.x"
              :cy="point1ScreenPos.y"
              r="5"
              class="measure-point"
            />
            <!-- Point 2 marker -->
            <circle
              v-if="point2ScreenPos"
              :cx="point2ScreenPos.x"
              :cy="point2ScreenPos.y"
              r="5"
              class="measure-point"
            />
          </svg>

          <!-- Cursor snap indicator -->
          <div
            v-if="cursorPos"
            class="cursor-indicator"
            :class="{ snapped: cursorPos.snapped }"
            :style="{ left: cursorPos.x + 'px', top: cursorPos.y + 'px' }"
          >
            <div class="cursor-dot"></div>
            <div v-if="cursorPos.snapped" class="snap-ring"></div>
          </div>

          <!-- Distance label near the line -->
          <div
            v-if="distanceLabelPos && measuredDistance !== null"
            class="distance-label"
            :style="{ left: distanceLabelPos.x + 'px', top: distanceLabelPos.y + 'px' }"
          >
            <span class="dist-tag">Dist</span>
            <span class="dist-value">{{ measuredDistance.toFixed(2) }}in</span>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <div class="toolbar">
          <button class="tool-btn" @click="fitView" title="Fit to View">
            <i class="pi pi-arrows-alt"></i>
            Fit
          </button>

          <div class="toolbar-divider"></div>

          <button class="tool-btn" @click="rotateScene(-90)" title="Rotate 90° CCW">
            <i class="pi pi-replay"></i>
          </button>
          <button class="tool-btn" @click="rotateScene(90)" title="Rotate 90° CW">
            <i class="pi pi-refresh"></i>
          </button>
          <button v-if="rotation !== 0" class="tool-btn" @click="resetRotation" title="Reset Rotation">
            {{ rotation }}°
          </button>

          <div class="toolbar-divider"></div>

          <button
            class="tool-btn"
            :class="{ active: measureMode }"
            @click="toggleMeasureMode"
            title="Measure Distance"
          >
            <i class="pi pi-arrows-h"></i>
            Measure
          </button>
          <button v-if="measureMode" class="tool-btn" @click="resetMeasurement" title="Clear">
            <i class="pi pi-times"></i>
          </button>
        </div>

        <div class="actions">
          <button class="download-btn" @click="downloadFile">
            <i class="pi pi-download"></i>
            Download DXF
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dxf-modal {
  background: #0f172a;
  border-radius: 8px;
  width: 90vw;
  height: 85vh;
  max-width: 1400px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-bottom: 1px solid #1e293b;
  flex-shrink: 0;
}

.modal-header h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: #e5e7eb;
  display: flex;
  align-items: center;
  gap: 8px;
}

.modal-header h2 i {
  color: #a1a1aa;
}

.close-btn {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  line-height: 1;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}

.close-btn:hover {
  color: #e5e7eb;
  background: #1e293b;
}

.modal-body {
  flex: 1;
  position: relative;
  overflow: hidden;
  min-height: 0;
}

.viewer-container {
  width: 100%;
  height: 100%;
  background: #1e293b;
}

.viewer-container.hidden {
  visibility: hidden;
}

.viewer-container.measure-mode {
  cursor: crosshair;
}

.loading-state,
.error-state {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #9ca3af;
  font-size: 14px;
}

.loading-state i {
  font-size: 24px;
  color: #60a5fa;
}

.error-state {
  color: #f87171;
}

.error-state i {
  font-size: 24px;
}

/* Measurement overlay */
.measure-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.measure-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.measure-line {
  stroke: #ef4444;
  stroke-width: 2;
  stroke-linecap: round;
}

.measure-point {
  fill: #ef4444;
  stroke: white;
  stroke-width: 1.5;
}

/* Cursor indicator */
.cursor-indicator {
  position: absolute;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.cursor-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #9ca3af;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

.cursor-indicator.snapped .cursor-dot {
  background: #fbbf24;
}

.snap-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid #fbbf24;
  background: rgba(251, 191, 36, 0.2);
  animation: pulse 0.8s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
  50% { transform: translate(-50%, -50%) scale(1.2); opacity: 0.7; }
}

/* Distance label */
.distance-label {
  position: absolute;
  transform: translate(-50%, -100%);
  background: #dc2626;
  border-radius: 4px;
  padding: 4px 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
  white-space: nowrap;
}

.dist-tag {
  font-size: 10px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.8);
  text-transform: uppercase;
}

.dist-value {
  font-size: 13px;
  font-weight: 700;
  font-family: monospace;
  color: white;
}

.modal-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-top: 1px solid #1e293b;
  flex-shrink: 0;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background: #334155;
  margin: 0 4px;
}

.tool-btn {
  background: #1e293b;
  border: 1px solid #334155;
  color: #e5e7eb;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 32px;
  justify-content: center;
}

.tool-btn:hover {
  background: #334155;
}

.tool-btn.active {
  background: #2563eb;
  border-color: #3b82f6;
}

.tool-btn i {
  font-size: 12px;
}

.tool-btn .pi-replay {
  transform: scaleX(-1);
}

.actions {
  display: flex;
  gap: 8px;
}

.download-btn {
  background: #2563eb;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 4px;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

.download-btn:hover {
  background: #1d4ed8;
}

.download-btn i {
  font-size: 14px;
}
</style>
