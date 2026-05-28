<script setup lang="ts">
import { ref, shallowRef, onMounted, watch, computed } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// Set worker path for PDF.js - use bundled worker via Vite
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker

const props = defineProps<{
  pdfUrl: string
  partNumber?: string
}>()

const emit = defineEmits<{
  close: []
}>()

// Canvas refs
const containerRef = ref<HTMLDivElement | null>(null)
const pdfCanvasRef = ref<HTMLCanvasElement | null>(null)
const overlayCanvasRef = ref<HTMLCanvasElement | null>(null)

// PDF state - use shallowRef to avoid Vue proxy breaking PDF.js private fields
const pdfDoc = shallowRef<pdfjsLib.PDFDocumentProxy | null>(null)
const currentPage = ref(1)
const totalPages = ref(0)
const scale = ref(1.5)
const loading = ref(true)
const error = ref('')

// Measurement state
type MeasureMode = 'none' | 'calibrate' | 'measure'
const measureMode = ref<MeasureMode>('none')
const calibrationScale = ref(1) // pixels per inch (or mm)
const calibrationUnit = ref<'in' | 'mm'>('in')

// Points for current measurement
interface Point { x: number; y: number }
const startPoint = ref<Point | null>(null)
const endPoint = ref<Point | null>(null)
const mousePos = ref<Point | null>(null)

// Stored measurements
interface Measurement {
  start: Point
  end: Point
  distance: number
  unit: string
}
const measurements = ref<Measurement[]>([])

// Calibration dialog
const showCalibrationDialog = ref(false)
const calibrationInput = ref('')

// Magnifier
const showMagnifier = ref(true)
const magnifierSize = 120
const magnifierZoom = 3

// Load PDF
async function loadPdf() {
  if (!props.pdfUrl) return

  loading.value = true
  error.value = ''

  try {
    const loadingTask = pdfjsLib.getDocument(props.pdfUrl)
    pdfDoc.value = await loadingTask.promise
    totalPages.value = pdfDoc.value.numPages

    // Set loading false to mount canvases, then render
    loading.value = false
    await new Promise(resolve => setTimeout(resolve, 50))
    await renderPage()
  } catch (e: any) {
    error.value = e.message || 'Failed to load PDF'
    loading.value = false
  }
}

// Render current page
async function renderPage() {
  if (!pdfDoc.value || !pdfCanvasRef.value) return

  try {
    const page = await pdfDoc.value.getPage(currentPage.value)
    const viewport = page.getViewport({ scale: scale.value })

    const canvas = pdfCanvasRef.value
    const context = canvas.getContext('2d')
    if (!context) return

    // Set canvas dimensions
    canvas.width = viewport.width
    canvas.height = viewport.height
    canvas.style.width = viewport.width + 'px'
    canvas.style.height = viewport.height + 'px'

    // Also resize overlay canvas
    if (overlayCanvasRef.value) {
      overlayCanvasRef.value.width = viewport.width
      overlayCanvasRef.value.height = viewport.height
      overlayCanvasRef.value.style.width = viewport.width + 'px'
      overlayCanvasRef.value.style.height = viewport.height + 'px'
    }

    // Render PDF page
    const renderContext = {
      canvasContext: context,
      viewport: viewport
    }

    await page.render(renderContext).promise
    console.log('PDF page rendered successfully')

    // Redraw measurements
    drawMeasurements()
  } catch (e) {
    console.error('Error rendering PDF page:', e)
  }
}

// Draw all measurements on overlay
function drawMeasurements() {
  const canvas = overlayCanvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  ctx.clearRect(0, 0, canvas.width, canvas.height)

  // Draw stored measurements
  measurements.value.forEach((m, i) => {
    drawLine(ctx, m.start, m.end, '#22c55e', `${m.distance.toFixed(3)} ${m.unit}`)
  })

  // Draw current measurement in progress
  if (startPoint.value) {
    const end = endPoint.value || mousePos.value
    if (end) {
      const color = measureMode.value === 'calibrate' ? '#f59e0b' : '#3b82f6'
      const pixelDist = Math.sqrt(
        Math.pow(end.x - startPoint.value.x, 2) +
        Math.pow(end.y - startPoint.value.y, 2)
      )

      let label = ''
      if (measureMode.value === 'calibrate') {
        label = `${pixelDist.toFixed(0)} px`
      } else if (calibrationScale.value > 0) {
        const realDist = pixelDist / calibrationScale.value
        label = `${realDist.toFixed(3)} ${calibrationUnit.value}`
      } else {
        label = `${pixelDist.toFixed(0)} px`
      }

      drawLine(ctx, startPoint.value, end, color, label)
    }
  }
}

function drawLine(ctx: CanvasRenderingContext2D, start: Point, end: Point, color: string, label: string) {
  // Line
  ctx.beginPath()
  ctx.moveTo(start.x, start.y)
  ctx.lineTo(end.x, end.y)
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.stroke()

  // End points
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(start.x, start.y, 5, 0, Math.PI * 2)
  ctx.fill()
  ctx.beginPath()
  ctx.arc(end.x, end.y, 5, 0, Math.PI * 2)
  ctx.fill()

  // Label background
  const midX = (start.x + end.x) / 2
  const midY = (start.y + end.y) / 2
  ctx.font = 'bold 14px system-ui'
  const textWidth = ctx.measureText(label).width

  ctx.fillStyle = 'rgba(0, 0, 0, 0.8)'
  ctx.fillRect(midX - textWidth/2 - 6, midY - 10, textWidth + 12, 22)

  // Label text
  ctx.fillStyle = '#fff'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, midX, midY + 1)
}

// Draw magnifier
function drawMagnifier() {
  if (!showMagnifier.value || !mousePos.value || !pdfCanvasRef.value || !overlayCanvasRef.value) return

  const pdfCtx = pdfCanvasRef.value.getContext('2d')
  const overlayCtx = overlayCanvasRef.value.getContext('2d')
  if (!pdfCtx || !overlayCtx) return

  const { x, y } = mousePos.value
  const size = magnifierSize
  const zoom = magnifierZoom
  const sourceSize = size / zoom

  // Position magnifier (offset from cursor)
  const magX = Math.min(x + 20, overlayCanvasRef.value.width - size - 10)
  const magY = Math.max(y - size - 20, 10)

  // Draw magnifier border
  overlayCtx.save()
  overlayCtx.beginPath()
  overlayCtx.arc(magX + size/2, magY + size/2, size/2, 0, Math.PI * 2)
  overlayCtx.strokeStyle = '#38bdf8'
  overlayCtx.lineWidth = 3
  overlayCtx.stroke()
  overlayCtx.clip()

  // Draw magnified PDF content
  overlayCtx.drawImage(
    pdfCanvasRef.value,
    x - sourceSize/2, y - sourceSize/2, sourceSize, sourceSize,
    magX, magY, size, size
  )

  // Draw crosshair in center
  overlayCtx.strokeStyle = '#ef4444'
  overlayCtx.lineWidth = 1
  overlayCtx.beginPath()
  overlayCtx.moveTo(magX + size/2 - 10, magY + size/2)
  overlayCtx.lineTo(magX + size/2 + 10, magY + size/2)
  overlayCtx.moveTo(magX + size/2, magY + size/2 - 10)
  overlayCtx.lineTo(magX + size/2, magY + size/2 + 10)
  overlayCtx.stroke()

  overlayCtx.restore()
}

// Mouse handlers
function getCanvasCoords(e: MouseEvent): Point | null {
  const canvas = overlayCanvasRef.value
  if (!canvas) return null

  const rect = canvas.getBoundingClientRect()
  return {
    x: (e.clientX - rect.left) * (canvas.width / rect.width),
    y: (e.clientY - rect.top) * (canvas.height / rect.height)
  }
}

function handleMouseMove(e: MouseEvent) {
  mousePos.value = getCanvasCoords(e)
  drawMeasurements()
  drawMagnifier()
}

function handleMouseLeave() {
  mousePos.value = null
  drawMeasurements()
}

function handleClick(e: MouseEvent) {
  if (measureMode.value === 'none') return

  const point = getCanvasCoords(e)
  if (!point) return

  if (!startPoint.value) {
    // First click - set start point
    startPoint.value = point
  } else {
    // Second click - complete measurement
    endPoint.value = point

    if (measureMode.value === 'calibrate') {
      // Show calibration dialog
      showCalibrationDialog.value = true
    } else {
      // Add measurement to list
      const pixelDist = Math.sqrt(
        Math.pow(endPoint.value.x - startPoint.value.x, 2) +
        Math.pow(endPoint.value.y - startPoint.value.y, 2)
      )
      const realDist = calibrationScale.value > 0 ? pixelDist / calibrationScale.value : pixelDist

      measurements.value.push({
        start: { ...startPoint.value },
        end: { ...endPoint.value },
        distance: realDist,
        unit: calibrationScale.value > 0 ? calibrationUnit.value : 'px'
      })

      // Reset for next measurement
      startPoint.value = null
      endPoint.value = null
    }

    drawMeasurements()
  }
}

function confirmCalibration() {
  const value = parseFloat(calibrationInput.value)
  if (isNaN(value) || value <= 0 || !startPoint.value || !endPoint.value) {
    return
  }

  const pixelDist = Math.sqrt(
    Math.pow(endPoint.value.x - startPoint.value.x, 2) +
    Math.pow(endPoint.value.y - startPoint.value.y, 2)
  )

  calibrationScale.value = pixelDist / value

  // Reset
  showCalibrationDialog.value = false
  calibrationInput.value = ''
  startPoint.value = null
  endPoint.value = null
  measureMode.value = 'measure' // Auto-switch to measure mode

  drawMeasurements()
}

function cancelCalibration() {
  showCalibrationDialog.value = false
  calibrationInput.value = ''
  startPoint.value = null
  endPoint.value = null
}

function clearMeasurements() {
  measurements.value = []
  startPoint.value = null
  endPoint.value = null
  drawMeasurements()
}

function resetCalibration() {
  calibrationScale.value = 0
  measurements.value = []
  startPoint.value = null
  endPoint.value = null
  measureMode.value = 'none'
  drawMeasurements()
}

// Zoom controls
function zoomIn() {
  scale.value = Math.min(scale.value + 0.25, 4)
  renderPage()
}

function zoomOut() {
  scale.value = Math.max(scale.value - 0.25, 0.5)
  renderPage()
}

// Page navigation
function prevPage() {
  if (currentPage.value > 1) {
    currentPage.value--
    measurements.value = []
    startPoint.value = null
    endPoint.value = null
    renderPage()
  }
}

function nextPage() {
  if (currentPage.value < totalPages.value) {
    currentPage.value++
    measurements.value = []
    startPoint.value = null
    endPoint.value = null
    renderPage()
  }
}

// Computed
const isCalibrated = computed(() => calibrationScale.value > 0)
const currentModeLabel = computed(() => {
  if (measureMode.value === 'calibrate') return 'Click two points on a known dimension'
  if (measureMode.value === 'measure') return 'Click two points to measure'
  return 'Select a mode to begin'
})

// Lifecycle
onMounted(() => {
  loadPdf()
})

watch(() => props.pdfUrl, () => {
  loadPdf()
})
</script>

<template>
  <div class="pdf-measure">
    <!-- Header -->
    <div class="measure-header">
      <div class="header-left">
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back
        </button>
        <h2>{{ partNumber || 'PDF Measure' }}</h2>
      </div>

      <div class="header-center">
        <span class="mode-label">{{ currentModeLabel }}</span>
      </div>

      <div class="header-right">
        <label class="magnifier-toggle">
          <input type="checkbox" v-model="showMagnifier" />
          Magnifier
        </label>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="measure-toolbar">
      <div class="tool-group">
        <span class="group-label">Mode:</span>
        <button
          :class="['tool-btn', { active: measureMode === 'calibrate' }]"
          @click="measureMode = 'calibrate'"
          title="Calibrate: Click two points on a known dimension"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 6H3M21 12H3M21 18H3M6 6v12M18 6v12"/>
          </svg>
          Calibrate
        </button>
        <button
          :class="['tool-btn', { active: measureMode === 'measure', disabled: !isCalibrated }]"
          @click="isCalibrated && (measureMode = 'measure')"
          :disabled="!isCalibrated"
          :title="isCalibrated ? 'Measure distance' : 'Calibrate first'"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 20L20 4M4 20l3-1M4 20l1-3M20 4l-3 1M20 4l-1 3"/>
          </svg>
          Measure
        </button>
      </div>

      <div class="tool-group" v-if="measureMode === 'calibrate' || !isCalibrated">
        <span class="group-label">Unit:</span>
        <select v-model="calibrationUnit" class="unit-select">
          <option value="in">Inches</option>
          <option value="mm">Millimeters</option>
        </select>
      </div>

      <div class="tool-group" v-if="isCalibrated">
        <span class="calibration-info">
          Scale: {{ (1 / calibrationScale).toFixed(4) }} {{ calibrationUnit }}/px
        </span>
      </div>

      <div class="tool-group">
        <button class="tool-btn" @click="clearMeasurements" title="Clear all measurements">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M8 6V4h8v2M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6"/>
          </svg>
          Clear
        </button>
        <button class="tool-btn" @click="resetCalibration" title="Reset calibration">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M1 4v6h6M23 20v-6h-6M20.5 9A9 9 0 005.6 5.6L1 10m22 4l-4.6 4.4A9 9 0 013.5 15"/>
          </svg>
          Reset
        </button>
      </div>

      <div class="spacer"></div>

      <div class="tool-group">
        <button class="tool-btn" @click="zoomOut" title="Zoom out">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35M8 11h6"/>
          </svg>
        </button>
        <span class="zoom-level">{{ Math.round(scale * 100) }}%</span>
        <button class="tool-btn" @click="zoomIn" title="Zoom in">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35M11 8v6M8 11h6"/>
          </svg>
        </button>
      </div>

      <div class="tool-group" v-if="totalPages > 1">
        <button class="tool-btn" @click="prevPage" :disabled="currentPage <= 1">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M15 18l-6-6 6-6"/>
          </svg>
        </button>
        <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
        <button class="tool-btn" @click="nextPage" :disabled="currentPage >= totalPages">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 18l6-6-6-6"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Canvas area -->
    <div class="canvas-container" ref="containerRef">
      <div v-if="loading" class="loading-overlay">
        <div class="spinner"></div>
        <span>Loading PDF...</span>
      </div>

      <div v-else-if="error" class="error-overlay">
        <span>{{ error }}</span>
      </div>

      <div v-else class="canvas-wrapper">
        <canvas ref="pdfCanvasRef" class="pdf-canvas"></canvas>
        <canvas
          ref="overlayCanvasRef"
          class="overlay-canvas"
          :class="{ 'cursor-crosshair': measureMode !== 'none' }"
          @mousemove="handleMouseMove"
          @mouseleave="handleMouseLeave"
          @click="handleClick"
        ></canvas>
      </div>
    </div>

    <!-- Measurements list -->
    <div class="measurements-panel" v-if="measurements.length > 0">
      <h3>Measurements</h3>
      <ul>
        <li v-for="(m, i) in measurements" :key="i">
          {{ i + 1 }}. <strong>{{ m.distance.toFixed(3) }} {{ m.unit }}</strong>
        </li>
      </ul>
    </div>

    <!-- Calibration dialog -->
    <div v-if="showCalibrationDialog" class="dialog-overlay" @click.self="cancelCalibration">
      <div class="dialog">
        <h3>Enter Known Distance</h3>
        <p>What is the actual length of the line you drew?</p>
        <div class="dialog-input">
          <input
            type="number"
            v-model="calibrationInput"
            step="0.001"
            min="0"
            placeholder="e.g., 1.000"
            autofocus
            @keyup.enter="confirmCalibration"
          />
          <span class="unit">{{ calibrationUnit }}</span>
        </div>
        <div class="dialog-actions">
          <button class="btn-cancel" @click="cancelCalibration">Cancel</button>
          <button class="btn-confirm" @click="confirmCalibration">Calibrate</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-measure {
  position: fixed;
  inset: 0;
  background: #0f172a;
  display: flex;
  flex-direction: column;
  z-index: 1000;
}

/* Header */
.measure-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: #1e293b;
  border-bottom: 1px solid #334155;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.header-left h2 {
  margin: 0;
  font-size: 1.125rem;
  color: #fff;
}

.close-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #374151;
  border: none;
  color: #e5e7eb;
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.875rem;
}

.close-btn:hover {
  background: #4b5563;
}

.close-btn svg {
  width: 18px;
  height: 18px;
}

.header-center {
  flex: 1;
  text-align: center;
}

.mode-label {
  color: #94a3b8;
  font-size: 0.875rem;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.magnifier-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #94a3b8;
  font-size: 0.875rem;
  cursor: pointer;
}

.magnifier-toggle input {
  accent-color: #38bdf8;
}

/* Toolbar */
.measure-toolbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  flex-wrap: wrap;
}

.tool-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.group-label {
  font-size: 0.75rem;
  color: #64748b;
  text-transform: uppercase;
}

.tool-btn {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: #374151;
  border: 1px solid #4b5563;
  color: #e5e7eb;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  cursor: pointer;
  font-size: 0.8rem;
  transition: all 0.15s;
}

.tool-btn svg {
  width: 16px;
  height: 16px;
}

.tool-btn:hover:not(:disabled) {
  background: #4b5563;
}

.tool-btn.active {
  background: #2563eb;
  border-color: #3b82f6;
}

.tool-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.unit-select {
  background: #374151;
  border: 1px solid #4b5563;
  color: #e5e7eb;
  padding: 0.5rem;
  border-radius: 0.375rem;
  font-size: 0.8rem;
}

.calibration-info {
  font-size: 0.8rem;
  color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
  padding: 0.35rem 0.75rem;
  border-radius: 0.375rem;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.zoom-level, .page-info {
  font-size: 0.8rem;
  color: #94a3b8;
  min-width: 50px;
  text-align: center;
}

.spacer {
  flex: 1;
}

/* Canvas */
.canvas-container {
  flex: 1;
  overflow: auto;
  background: #1e293b;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 1rem;
}

.canvas-wrapper {
  position: relative;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
}

.pdf-canvas {
  display: block;
  background: #fff;
}

.overlay-canvas {
  position: absolute;
  top: 0;
  left: 0;
  cursor: default;
}

.overlay-canvas.cursor-crosshair {
  cursor: crosshair;
}

.loading-overlay, .error-overlay {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 4rem;
  color: #94a3b8;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #334155;
  border-top-color: #38bdf8;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Measurements panel */
.measurements-panel {
  position: absolute;
  bottom: 1rem;
  right: 1rem;
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid #334155;
  border-radius: 0.5rem;
  padding: 1rem;
  min-width: 200px;
  max-height: 200px;
  overflow-y: auto;
}

.measurements-panel h3 {
  margin: 0 0 0.5rem 0;
  font-size: 0.875rem;
  color: #94a3b8;
}

.measurements-panel ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.measurements-panel li {
  padding: 0.25rem 0;
  font-size: 0.875rem;
  color: #e5e7eb;
  border-bottom: 1px solid #1e293b;
}

.measurements-panel li:last-child {
  border-bottom: none;
}

.measurements-panel strong {
  color: #22c55e;
}

/* Dialog */
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100;
}

.dialog {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 0.75rem;
  padding: 1.5rem;
  min-width: 320px;
}

.dialog h3 {
  margin: 0 0 0.5rem 0;
  color: #fff;
}

.dialog p {
  margin: 0 0 1rem 0;
  color: #94a3b8;
  font-size: 0.875rem;
}

.dialog-input {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
}

.dialog-input input {
  flex: 1;
  padding: 0.75rem;
  background: #0f172a;
  border: 1px solid #334155;
  border-radius: 0.375rem;
  color: #fff;
  font-size: 1.25rem;
  text-align: center;
}

.dialog-input input:focus {
  outline: none;
  border-color: #38bdf8;
}

.dialog-input .unit {
  font-size: 1rem;
  color: #94a3b8;
}

.dialog-actions {
  display: flex;
  gap: 0.75rem;
  justify-content: flex-end;
}

.btn-cancel, .btn-confirm {
  padding: 0.75rem 1.5rem;
  border-radius: 0.375rem;
  border: none;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
}

.btn-cancel {
  background: #374151;
  color: #e5e7eb;
}

.btn-cancel:hover {
  background: #4b5563;
}

.btn-confirm {
  background: #2563eb;
  color: #fff;
}

.btn-confirm:hover {
  background: #1d4ed8;
}
</style>
