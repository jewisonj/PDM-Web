<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js'

interface Annotation {
  id: string
  position_x: number
  position_y: number
  position_z: number
  normal_x?: number
  normal_y?: number
  normal_z?: number
  content: string
  author_type: string
  author_id: string
  author_name: string
  created_at: string
}

interface AuthorInfo {
  type: 'user' | 'supplier'
  id: string
  name: string
}

const props = defineProps<{
  stlUrl: string
  fileId: string
  itemId: string
  itemNumber: string
  authorInfo: AuthorInfo
  apiBase?: string  // '/api' for users, '/api/supplier' for suppliers
}>()

const emit = defineEmits<{
  close: []
}>()

// Refs
const containerRef = ref<HTMLDivElement | null>(null)
const loading = ref(true)
const error = ref('')
const annotationMode = ref(false)
const showAnnotations = ref(true)
const annotations = ref<Annotation[]>([])
const selectedAnnotation = ref<Annotation | null>(null)
const newAnnotationText = ref('')
const pendingAnnotation = ref<{ position: THREE.Vector3; normal: THREE.Vector3 } | null>(null)

// Three.js objects
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let renderer: THREE.WebGLRenderer
let labelRenderer: CSS2DRenderer
let controls: OrbitControls
let model: THREE.Mesh | null = null
let raycaster: THREE.Raycaster
let mouse: THREE.Vector2
let annotationMarkers: Map<string, THREE.Mesh> = new Map()
let annotationLabels: Map<string, CSS2DObject> = new Map()
let animationId: number

// Initialize Three.js scene
function initScene() {
  if (!containerRef.value) return

  const container = containerRef.value
  const width = container.clientWidth
  const height = container.clientHeight

  // Scene
  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x1a1a2e)

  // Camera
  camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000)
  camera.position.set(100, 100, 100)

  // Renderer
  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setSize(width, height)
  renderer.setPixelRatio(window.devicePixelRatio)
  container.appendChild(renderer.domElement)

  // CSS2D Renderer for labels
  labelRenderer = new CSS2DRenderer()
  labelRenderer.setSize(width, height)
  labelRenderer.domElement.style.position = 'absolute'
  labelRenderer.domElement.style.top = '0'
  labelRenderer.domElement.style.pointerEvents = 'none'
  container.appendChild(labelRenderer.domElement)

  // Controls
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05

  // Lights
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
  scene.add(ambientLight)

  const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8)
  directionalLight.position.set(100, 100, 50)
  scene.add(directionalLight)

  const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4)
  directionalLight2.position.set(-100, -100, -50)
  scene.add(directionalLight2)

  // Grid
  const gridHelper = new THREE.GridHelper(200, 20, 0x444444, 0x333333)
  scene.add(gridHelper)

  // Raycaster for click detection
  raycaster = new THREE.Raycaster()
  mouse = new THREE.Vector2()

  // Event listeners
  renderer.domElement.addEventListener('click', onModelClick)
  window.addEventListener('resize', onWindowResize)

  // Animation loop
  animate()
}

function animate() {
  animationId = requestAnimationFrame(animate)
  controls.update()
  renderer.render(scene, camera)
  labelRenderer.render(scene, camera)
}

function onWindowResize() {
  if (!containerRef.value) return
  const width = containerRef.value.clientWidth
  const height = containerRef.value.clientHeight
  camera.aspect = width / height
  camera.updateProjectionMatrix()
  renderer.setSize(width, height)
  labelRenderer.setSize(width, height)
}

// Load STL model
async function loadModel() {
  loading.value = true
  error.value = ''

  try {
    const loader = new STLLoader()
    const geometry = await loader.loadAsync(props.stlUrl)

    // Center geometry
    geometry.computeBoundingBox()
    const center = new THREE.Vector3()
    geometry.boundingBox!.getCenter(center)
    geometry.translate(-center.x, -center.y, -center.z)

    // Material
    const material = new THREE.MeshPhongMaterial({
      color: 0x4a90d9,
      specular: 0x111111,
      shininess: 50,
      flatShading: false,
    })

    // Create mesh
    model = new THREE.Mesh(geometry, material)
    scene.add(model)

    // Fit camera to model
    const box = new THREE.Box3().setFromObject(model)
    const size = box.getSize(new THREE.Vector3())
    const maxDim = Math.max(size.x, size.y, size.z)
    camera.position.set(maxDim * 1.5, maxDim * 1.5, maxDim * 1.5)
    controls.target.set(0, 0, 0)
    controls.update()

    loading.value = false
  } catch (e) {
    console.error('Failed to load STL:', e)
    error.value = 'Failed to load 3D model'
    loading.value = false
  }
}

// Load annotations from API
async function loadAnnotations() {
  try {
    const base = props.apiBase || '/api'
    let url: string

    if (props.authorInfo.type === 'supplier') {
      url = `${base}/items/${props.itemNumber}/files/${props.fileId}/annotations`
    } else {
      url = `${base}/files/${props.fileId}/annotations`
    }

    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem(props.authorInfo.type === 'supplier' ? 'supplier_token' : 'access_token')}`,
      },
    })

    if (response.ok) {
      annotations.value = await response.json()
      renderAnnotationMarkers()
    }
  } catch (e) {
    console.warn('Failed to load annotations:', e)
  }
}

// Render annotation markers in 3D
function renderAnnotationMarkers() {
  // Clear existing markers
  annotationMarkers.forEach(marker => scene.remove(marker))
  annotationLabels.forEach(label => scene.remove(label))
  annotationMarkers.clear()
  annotationLabels.clear()

  if (!showAnnotations.value) return

  annotations.value.forEach(ann => {
    // Create marker sphere
    const geometry = new THREE.SphereGeometry(2, 16, 16)
    const material = new THREE.MeshBasicMaterial({
      color: ann.author_type === 'supplier' ? 0x22c55e : 0x3b82f6,
    })
    const marker = new THREE.Mesh(geometry, material)
    marker.position.set(ann.position_x, ann.position_y, ann.position_z)
    marker.userData.annotationId = ann.id
    scene.add(marker)
    annotationMarkers.set(ann.id, marker)

    // Create label
    const labelDiv = document.createElement('div')
    labelDiv.className = 'annotation-label'
    labelDiv.innerHTML = `
      <div class="annotation-author">${ann.author_name}</div>
      <div class="annotation-content">${ann.content}</div>
    `
    labelDiv.style.cssText = `
      background: ${ann.author_type === 'supplier' ? '#166534' : '#1e40af'};
      color: white;
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 12px;
      max-width: 200px;
      pointer-events: auto;
      cursor: pointer;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    `
    labelDiv.addEventListener('click', () => selectAnnotation(ann))

    const label = new CSS2DObject(labelDiv)
    label.position.set(ann.position_x, ann.position_y + 5, ann.position_z)
    scene.add(label)
    annotationLabels.set(ann.id, label)
  })
}

function selectAnnotation(ann: Annotation) {
  selectedAnnotation.value = ann
  // Move camera to focus on annotation
  const pos = new THREE.Vector3(ann.position_x, ann.position_y, ann.position_z)
  controls.target.copy(pos)
  camera.position.set(pos.x + 50, pos.y + 50, pos.z + 50)
  controls.update()
}

// Handle click on model for annotation
function onModelClick(event: MouseEvent) {
  if (!annotationMode.value || !model) return

  const rect = renderer.domElement.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

  raycaster.setFromCamera(mouse, camera)
  const intersects = raycaster.intersectObject(model)

  if (intersects.length > 0) {
    const point = intersects[0].point
    const normal = intersects[0].face?.normal || new THREE.Vector3(0, 1, 0)

    pendingAnnotation.value = { position: point.clone(), normal: normal.clone() }
    newAnnotationText.value = ''
  }
}

// Save new annotation
async function saveAnnotation() {
  if (!pendingAnnotation.value || !newAnnotationText.value.trim()) return

  try {
    const base = props.apiBase || '/api'
    let url: string

    if (props.authorInfo.type === 'supplier') {
      url = `${base}/items/${props.itemNumber}/files/${props.fileId}/annotations`
    } else {
      url = `${base}/files/${props.fileId}/annotations`
    }

    const body = {
      position_x: pendingAnnotation.value.position.x,
      position_y: pendingAnnotation.value.position.y,
      position_z: pendingAnnotation.value.position.z,
      normal_x: pendingAnnotation.value.normal.x,
      normal_y: pendingAnnotation.value.normal.y,
      normal_z: pendingAnnotation.value.normal.z,
      content: newAnnotationText.value.trim(),
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem(props.authorInfo.type === 'supplier' ? 'supplier_token' : 'access_token')}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })

    if (response.ok) {
      const newAnn = await response.json()
      annotations.value.push(newAnn)
      renderAnnotationMarkers()
      pendingAnnotation.value = null
      annotationMode.value = false
    } else {
      alert('Failed to save annotation')
    }
  } catch (e) {
    console.error('Failed to save annotation:', e)
    alert('Failed to save annotation')
  }
}

function cancelAnnotation() {
  pendingAnnotation.value = null
  newAnnotationText.value = ''
}

function toggleAnnotations() {
  showAnnotations.value = !showAnnotations.value
  renderAnnotationMarkers()
}

function resetView() {
  if (!model) return
  const box = new THREE.Box3().setFromObject(model)
  const size = box.getSize(new THREE.Vector3())
  const maxDim = Math.max(size.x, size.y, size.z)
  camera.position.set(maxDim * 1.5, maxDim * 1.5, maxDim * 1.5)
  controls.target.set(0, 0, 0)
  controls.update()
  selectedAnnotation.value = null
}

function closeViewer() {
  emit('close')
}

// Lifecycle
onMounted(async () => {
  initScene()
  await loadModel()
  await loadAnnotations()
})

onUnmounted(() => {
  cancelAnimationFrame(animationId)
  window.removeEventListener('resize', onWindowResize)
  renderer?.dispose()
  controls?.dispose()
})

watch(() => props.stlUrl, async () => {
  if (model) {
    scene.remove(model)
    model = null
  }
  await loadModel()
  await loadAnnotations()
})
</script>

<template>
  <div class="stl-viewer-overlay">
    <div class="stl-viewer-container">
      <!-- Header -->
      <header class="viewer-header">
        <div class="header-left">
          <h2>3D Model Viewer</h2>
          <span class="item-number">{{ itemNumber }}</span>
        </div>
        <div class="header-controls">
          <button
            :class="['control-btn', { active: annotationMode }]"
            @click="annotationMode = !annotationMode"
            title="Add Annotation"
          >
            <i class="pi pi-plus-circle"></i>
            Add Note
          </button>
          <button
            :class="['control-btn', { active: showAnnotations }]"
            @click="toggleAnnotations"
            title="Toggle Annotations"
          >
            <i class="pi pi-comments"></i>
            {{ annotations.length }}
          </button>
          <button class="control-btn" @click="resetView" title="Reset View">
            <i class="pi pi-refresh"></i>
          </button>
          <button class="close-btn" @click="closeViewer">
            <i class="pi pi-times"></i>
          </button>
        </div>
      </header>

      <!-- 3D Viewport -->
      <div ref="containerRef" class="viewport">
        <div v-if="loading" class="loading-overlay">
          <div class="spinner"></div>
          <span>Loading 3D Model...</span>
        </div>
        <div v-if="error" class="error-overlay">
          <i class="pi pi-exclamation-triangle"></i>
          <span>{{ error }}</span>
        </div>

        <!-- Annotation Mode Indicator -->
        <div v-if="annotationMode" class="mode-indicator">
          Click on the model to add an annotation
        </div>
      </div>

      <!-- New Annotation Form -->
      <div v-if="pendingAnnotation" class="annotation-form">
        <h4>Add Annotation</h4>
        <textarea
          v-model="newAnnotationText"
          placeholder="Enter your note or question..."
          rows="3"
        ></textarea>
        <div class="form-actions">
          <button class="cancel-btn" @click="cancelAnnotation">Cancel</button>
          <button class="save-btn" @click="saveAnnotation" :disabled="!newAnnotationText.trim()">
            Save Annotation
          </button>
        </div>
      </div>

      <!-- Selected Annotation Detail -->
      <div v-if="selectedAnnotation && !pendingAnnotation" class="annotation-detail">
        <div class="detail-header">
          <span :class="['author-badge', selectedAnnotation.author_type]">
            {{ selectedAnnotation.author_name }}
          </span>
          <span class="detail-date">
            {{ new Date(selectedAnnotation.created_at).toLocaleDateString() }}
          </span>
          <button class="close-detail" @click="selectedAnnotation = null">
            <i class="pi pi-times"></i>
          </button>
        </div>
        <p class="detail-content">{{ selectedAnnotation.content }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stl-viewer-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.9);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stl-viewer-container {
  width: 95vw;
  height: 95vh;
  background: #0f0f1a;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.viewer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #1a1a2e;
  border-bottom: 1px solid #2a2a4a;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-left h2 {
  margin: 0;
  font-size: 16px;
  color: #fff;
}

.item-number {
  font-family: 'JetBrains Mono', monospace;
  color: #64b5f6;
  font-size: 14px;
}

.header-controls {
  display: flex;
  gap: 8px;
}

.control-btn {
  background: #2a2a4a;
  border: 1px solid #3a3a5a;
  color: #ccc;
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  transition: all 0.2s;
}

.control-btn:hover {
  background: #3a3a5a;
  color: #fff;
}

.control-btn.active {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #fff;
}

.close-btn {
  background: transparent;
  border: none;
  color: #888;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 18px;
}

.close-btn:hover {
  color: #fff;
}

.viewport {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.loading-overlay,
.error-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #888;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #2a2a4a;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-overlay {
  color: #ef4444;
}

.error-overlay i {
  font-size: 32px;
}

.mode-indicator {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #3b82f6;
  color: white;
  padding: 10px 20px;
  border-radius: 20px;
  font-size: 14px;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.annotation-form {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background: #1a1a2e;
  border: 1px solid #3a3a5a;
  border-radius: 10px;
  padding: 16px;
  width: 400px;
  max-width: 90%;
}

.annotation-form h4 {
  margin: 0 0 12px;
  color: #fff;
  font-size: 14px;
}

.annotation-form textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #3a3a5a;
  border-radius: 6px;
  background: #0f0f1a;
  color: #fff;
  font-size: 14px;
  resize: vertical;
  font-family: inherit;
}

.annotation-form textarea:focus {
  outline: none;
  border-color: #3b82f6;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
}

.cancel-btn {
  background: transparent;
  border: 1px solid #3a3a5a;
  color: #888;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
}

.cancel-btn:hover {
  color: #fff;
  border-color: #888;
}

.save-btn {
  background: #3b82f6;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-weight: 500;
}

.save-btn:hover:not(:disabled) {
  background: #2563eb;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.annotation-detail {
  position: absolute;
  bottom: 20px;
  right: 20px;
  background: #1a1a2e;
  border: 1px solid #3a3a5a;
  border-radius: 10px;
  padding: 14px;
  width: 300px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.author-badge {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.author-badge.user {
  background: #1e40af;
  color: white;
}

.author-badge.supplier {
  background: #166534;
  color: white;
}

.detail-date {
  color: #666;
  font-size: 12px;
  flex: 1;
}

.close-detail {
  background: transparent;
  border: none;
  color: #666;
  cursor: pointer;
  padding: 4px;
}

.close-detail:hover {
  color: #fff;
}

.detail-content {
  margin: 0;
  color: #ccc;
  font-size: 14px;
  line-height: 1.5;
}
</style>
