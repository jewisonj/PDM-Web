<script setup lang="ts">
/**
 * Shop Companion - /shop
 *
 * One-screen, phone-first note form for shop-floor workers:
 *   PIN once -> name once -> project -> (assembly) -> (part) -> note -> photos -> Send.
 * Everything optional except a note or a photo. Project + name are remembered on the phone.
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  pinLogin,
  listShopProjects,
  getProjectItems,
  createShopNote,
  shopDevice,
  ShopApiError,
  type ShopProject,
  type ShopItem,
  type ShopAssembly,
} from '../services/shopNotesApi'
import { partsForAssembly, defaultAssemblyForPart, resizeImage } from '../utils/shopNotes'
import ShopItemPicker from '../components/ShopItemPicker.vue'

type Screen = 'pin' | 'name' | 'form' | 'sent'

const screen = ref<Screen>('pin')

// --- PIN ---
const pin = ref('')
const pinError = ref('')
const pinBusy = ref(false)
const pinInput = ref<HTMLInputElement | null>(null)

// --- Name ---
const name = ref(shopDevice.getName())
const nameDraft = ref(shopDevice.getName())
const nameInput = ref<HTMLInputElement | null>(null)

// --- Form ---
const projects = ref<ShopProject[]>([])
const projectId = ref<string>(shopDevice.getProjectId() || '')
const loadingProjects = ref(false)
const loadingItems = ref(false)
const assemblies = ref<ShopAssembly[]>([])
const parts = ref<ShopItem[]>([])

const assembly = ref<ShopAssembly | null>(null)
const assemblyText = ref('')
const part = ref<ShopItem | null>(null)
const partText = ref('')
const note = ref('')
const noteEl = ref<HTMLTextAreaElement | null>(null)

interface PendingPhoto { id: number; blob: Blob; url: string; name: string }
const photos = ref<PendingPhoto[]>([])
const cameraInput = ref<HTMLInputElement | null>(null)
const galleryInput = ref<HTMLInputElement | null>(null)
const processingPhotos = ref(0)
let photoSeq = 0

const sending = ref(false)
const sendError = ref('')
const lastSent = ref<{ project: string; part: string; assembly: string; photos: number } | null>(null)

const selectedProject = computed(() => projects.value.find(p => p.id === projectId.value) || null)
const partChoices = computed(() => partsForAssembly(parts.value, assembly.value?.id || null))
const canSend = computed(() => !sending.value && processingPhotos.value === 0 && (note.value.trim().length > 0 || photos.value.length > 0))

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

onMounted(async () => {
  installPwaMeta()
  if (!shopDevice.getToken()) {
    screen.value = 'pin'
    requestAnimationFrame(() => pinInput.value?.focus())
    return
  }
  await enterApp()
})

async function enterApp() {
  if (!name.value) {
    screen.value = 'name'
    requestAnimationFrame(() => nameInput.value?.focus())
    return
  }
  screen.value = 'form'
  await loadProjects()
}

// ---------------------------------------------------------------------------
// PIN + name
// ---------------------------------------------------------------------------

async function submitPin() {
  if (pinBusy.value || pin.value.length < 4) return
  pinBusy.value = true
  pinError.value = ''
  try {
    await pinLogin(pin.value)
    pin.value = ''
    await enterApp()
  } catch (e) {
    pinError.value = e instanceof ShopApiError && e.status === 401 ? 'Wrong PIN, try again' : 'Could not reach the server'
    pin.value = ''
    requestAnimationFrame(() => pinInput.value?.focus())
  } finally {
    pinBusy.value = false
  }
}

function onPinInput() {
  pin.value = pin.value.replace(/\D/g, '').slice(0, 6)
  if (pin.value.length === 4) submitPin()
}

async function saveName() {
  const n = nameDraft.value.trim()
  if (!n) return
  name.value = n
  shopDevice.setName(n)
  screen.value = 'form'
  if (!projects.value.length) await loadProjects()
}

function changeName() {
  nameDraft.value = name.value
  screen.value = 'name'
  requestAnimationFrame(() => nameInput.value?.select())
}

function handleAuthError(e: unknown): boolean {
  if (e instanceof ShopApiError && e.status === 401) {
    shopDevice.setToken(null)
    screen.value = 'pin'
    pinError.value = 'Please enter the PIN again'
    requestAnimationFrame(() => pinInput.value?.focus())
    return true
  }
  return false
}

// ---------------------------------------------------------------------------
// Projects + items
// ---------------------------------------------------------------------------

async function loadProjects() {
  loadingProjects.value = true
  sendError.value = ''
  try {
    projects.value = await listShopProjects()
    if (projectId.value && !projects.value.some(p => p.id === projectId.value)) projectId.value = ''
    if (projectId.value) await loadItems()
  } catch (e) {
    if (!handleAuthError(e)) sendError.value = 'Could not load projects. Check your connection.'
  } finally {
    loadingProjects.value = false
  }
}

async function loadItems() {
  assemblies.value = []
  parts.value = []
  if (!projectId.value) return
  loadingItems.value = true
  try {
    const data = await getProjectItems(projectId.value)
    assemblies.value = data.assemblies
    parts.value = data.parts
  } catch (e) {
    if (!handleAuthError(e)) sendError.value = 'Could not load the project BOM.'
  } finally {
    loadingItems.value = false
  }
}

watch(projectId, async (id, prev) => {
  shopDevice.setProjectId(id || null)
  if (id !== prev) {
    assembly.value = null
    assemblyText.value = ''
    part.value = null
    partText.value = ''
    await loadItems()
  }
})

// When a part is picked and no assembly chosen yet, fill in its parent weldment/assembly.
watch(part, p => {
  if (p && !assembly.value) {
    const asm = defaultAssemblyForPart(p, assemblies.value)
    if (asm) {
      assembly.value = asm
      assemblyText.value = asm.item_number
    }
  }
})

// ---------------------------------------------------------------------------
// Photos
// ---------------------------------------------------------------------------

async function addFiles(list: FileList | null) {
  if (!list || !list.length) return
  const files = Array.from(list)
  for (const f of files) {
    if (photos.value.length >= 10) break
    processingPhotos.value++
    try {
      const blob = await resizeImage(f, 1600, 0.82)
      photos.value.push({ id: ++photoSeq, blob, url: URL.createObjectURL(blob), name: f.name })
    } catch {
      photos.value.push({ id: ++photoSeq, blob: f, url: URL.createObjectURL(f), name: f.name })
    } finally {
      processingPhotos.value--
    }
  }
}

function onCamera(ev: Event) {
  const input = ev.target as HTMLInputElement
  addFiles(input.files)
  input.value = ''
}

function onGallery(ev: Event) {
  const input = ev.target as HTMLInputElement
  addFiles(input.files)
  input.value = ''
}

function removePhoto(id: number) {
  const idx = photos.value.findIndex(p => p.id === id)
  if (idx >= 0) {
    URL.revokeObjectURL(photos.value[idx]!.url)
    photos.value.splice(idx, 1)
  }
}

onBeforeUnmount(() => photos.value.forEach(p => URL.revokeObjectURL(p.url)))

// ---------------------------------------------------------------------------
// Send
// ---------------------------------------------------------------------------

function autoGrow() {
  const el = noteEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 320) + 'px'
}

async function send() {
  if (!canSend.value) return
  sending.value = true
  sendError.value = ''
  try {
    const result = await createShopNote({
      note: note.value.trim(),
      author_name: name.value,
      project_id: projectId.value || null,
      assembly_item_id: assembly.value?.id || null,
      part_item_id: part.value?.id || null,
      assembly_text: assembly.value ? null : assemblyText.value.trim() || null,
      part_text: part.value ? null : partText.value.trim() || null,
      photos: photos.value.map(p => p.blob),
    })
    lastSent.value = {
      project: selectedProject.value?.project_code || '',
      part: part.value?.item_number || partText.value || '',
      assembly: assembly.value?.item_number || assemblyText.value || '',
      photos: result.photos.length,
    }
    resetForm()
    screen.value = 'sent'
    window.scrollTo(0, 0)
  } catch (e) {
    if (!handleAuthError(e)) {
      sendError.value = e instanceof Error ? e.message : 'Send failed'
    }
  } finally {
    sending.value = false
  }
}

function resetForm() {
  note.value = ''
  part.value = null
  partText.value = ''
  assembly.value = null
  assemblyText.value = ''
  photos.value.forEach(p => URL.revokeObjectURL(p.url))
  photos.value = []
  requestAnimationFrame(autoGrow)
}

function newNote() {
  screen.value = 'form'
  sendError.value = ''
}

// ---------------------------------------------------------------------------
// PWA: link the shop manifest only on this page so "Add to Home Screen" opens /shop
// ---------------------------------------------------------------------------

function installPwaMeta() {
  const head = document.head
  if (!head.querySelector('link[rel="manifest"][data-shop]')) {
    const link = document.createElement('link')
    link.rel = 'manifest'
    link.href = '/shop.webmanifest'
    link.setAttribute('data-shop', '1')
    head.appendChild(link)
  }
  const metas: [string, string][] = [
    ['apple-mobile-web-app-capable', 'yes'],
    ['mobile-web-app-capable', 'yes'],
    ['apple-mobile-web-app-status-bar-style', 'black-translucent'],
    ['apple-mobile-web-app-title', 'Shop Notes'],
    ['theme-color', '#020617'],
  ]
  for (const [n, c] of metas) {
    if (!head.querySelector(`meta[name="${n}"][data-shop]`)) {
      const m = document.createElement('meta')
      m.name = n
      m.content = c
      m.setAttribute('data-shop', '1')
      head.appendChild(m)
    }
  }
  if (!head.querySelector('link[rel="apple-touch-icon"][data-shop]')) {
    const icon = document.createElement('link')
    icon.rel = 'apple-touch-icon'
    icon.href = '/shop-icon-192.png'
    icon.setAttribute('data-shop', '1')
    head.appendChild(icon)
  }
  const vp = head.querySelector('meta[name="viewport"]')
  if (vp) vp.setAttribute('content', 'width=device-width, initial-scale=1, viewport-fit=cover, maximum-scale=1')
}
</script>

<template>
  <div class="shop">
    <!-- PIN -->
    <section v-if="screen === 'pin'" class="screen center">
      <div class="brand">
        <div class="brand-mark">✎</div>
        <h1>Shop Notes</h1>
        <p>Enter the shop PIN once. This phone stays signed in.</p>
      </div>
      <form class="pin-form" @submit.prevent="submitPin">
        <input
          ref="pinInput"
          v-model="pin"
          class="pin-input"
          :class="{ shake: pinError }"
          type="password"
          inputmode="numeric"
          pattern="[0-9]*"
          autocomplete="one-time-code"
          placeholder="••••"
          maxlength="6"
          :disabled="pinBusy"
          @input="onPinInput"
        />
        <p v-if="pinError" class="error-text">{{ pinError }}</p>
        <button class="btn-primary" type="submit" :disabled="pinBusy || pin.length < 4">
          {{ pinBusy ? 'Checking…' : 'Continue' }}
        </button>
      </form>
    </section>

    <!-- NAME -->
    <section v-else-if="screen === 'name'" class="screen center">
      <div class="brand">
        <h1>Who are you?</h1>
        <p>So engineering knows who to ask. Saved on this phone.</p>
      </div>
      <form class="pin-form" @submit.prevent="saveName">
        <input
          ref="nameInput"
          v-model="nameDraft"
          class="name-input"
          type="text"
          autocomplete="given-name"
          autocapitalize="words"
          enterkeyhint="done"
          placeholder="Your name"
        />
        <button class="btn-primary" type="submit" :disabled="!nameDraft.trim()">Continue</button>
      </form>
    </section>

    <!-- SENT -->
    <section v-else-if="screen === 'sent'" class="screen center">
      <div class="sent-mark">✓</div>
      <h1>Sent</h1>
      <p class="sent-detail" v-if="lastSent">
        <span v-if="lastSent.project">{{ lastSent.project }}</span>
        <span v-if="lastSent.assembly"> · {{ lastSent.assembly }}</span>
        <span v-if="lastSent.part"> · {{ lastSent.part }}</span>
        <span v-if="lastSent.photos"> · {{ lastSent.photos }} photo{{ lastSent.photos === 1 ? '' : 's' }}</span>
      </p>
      <p class="muted">Engineering will see it on the Shop Notes page.</p>
      <button class="btn-primary" type="button" @click="newNote">New note</button>
    </section>

    <!-- FORM -->
    <section v-else class="screen form">
      <header class="topbar">
        <div class="topbar-title">
          <span class="brand-mark small">✎</span>
          <span>Shop Note</span>
        </div>
        <button type="button" class="name-chip" @click="changeName">{{ name }}</button>
      </header>

      <div class="field">
        <label class="field-label" for="project">Project</label>
        <div class="select-wrap">
          <select id="project" v-model="projectId" class="select" :disabled="loadingProjects">
            <option value="">{{ loadingProjects ? 'Loading…' : 'Pick a project (optional)' }}</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">
              {{ p.project_code }}{{ p.description ? ' — ' + p.description : '' }}{{ p.status === 'Complete' ? ' (complete)' : '' }}
            </option>
          </select>
        </div>
      </div>

      <div class="field">
        <ShopItemPicker
          v-model="assembly"
          v-model:text="assemblyText"
          :items="assemblies"
          label="Assembly / weldment"
          :hint="loadingItems ? 'loading…' : (projectId ? '' : 'pick a project to get suggestions')"
          placeholder="e.g. wma20120"
        />
      </div>

      <div class="field">
        <ShopItemPicker
          v-model="part"
          v-model:text="partText"
          :items="partChoices"
          label="Part"
          :hint="assembly ? 'parts in this assembly first' : ''"
          placeholder="e.g. csp0030"
        />
      </div>

      <div class="field">
        <label class="field-label" for="note">What's up?</label>
        <textarea
          id="note"
          ref="noteEl"
          v-model="note"
          class="note"
          rows="4"
          placeholder="Describe the issue. Tip: tap the mic on your keyboard to dictate."
          enterkeyhint="enter"
          @input="autoGrow"
        ></textarea>
      </div>

      <div class="field">
        <label class="field-label">Photos</label>
        <div class="photo-buttons">
          <button type="button" class="btn-photo" @click="cameraInput?.click()">
            <span class="ico">📷</span> Take photo
          </button>
          <button type="button" class="btn-photo" @click="galleryInput?.click()">
            <span class="ico">🖼️</span> Gallery
          </button>
          <input ref="cameraInput" type="file" accept="image/*" capture="environment" hidden @change="onCamera" />
          <input ref="galleryInput" type="file" accept="image/*" multiple hidden @change="onGallery" />
        </div>
        <div v-if="photos.length || processingPhotos" class="thumbs">
          <div v-for="p in photos" :key="p.id" class="thumb">
            <img :src="p.url" :alt="p.name" />
            <button type="button" class="thumb-x" aria-label="Remove photo" @click="removePhoto(p.id)">✕</button>
          </div>
          <div v-for="n in processingPhotos" :key="'p' + n" class="thumb thumb-loading">…</div>
        </div>
      </div>

      <p v-if="sendError" class="error-bar">{{ sendError }}</p>

      <div class="send-bar">
        <button type="button" class="btn-send" :disabled="!canSend" @click="send">
          <span v-if="sending">Sending{{ photos.length ? ' ' + photos.length + ' photo' + (photos.length === 1 ? '' : 's') : '' }}…</span>
          <span v-else>Send to engineering</span>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.shop {
  min-height: 100vh;
  min-height: 100dvh;
  background: #020617;
  color: #f1f5f9;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  -webkit-tap-highlight-color: transparent;
}

.screen {
  max-width: 560px;
  margin: 0 auto;
  padding: calc(16px + env(safe-area-inset-top)) 16px calc(16px + env(safe-area-inset-bottom));
}
.screen.center {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 18px;
}
.screen.form { padding-bottom: 120px; }

h1 { font-size: 1.6rem; margin: 0; }
p { margin: 0; }
.muted { color: #94a3b8; }

.brand { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.brand p { color: #94a3b8; max-width: 320px; }
.brand-mark {
  width: 64px; height: 64px;
  border-radius: 18px;
  background: #0ea5e9;
  color: #020617;
  font-size: 2rem;
  display: flex; align-items: center; justify-content: center;
}
.brand-mark.small { width: 28px; height: 28px; border-radius: 8px; font-size: 1rem; }

.pin-form { display: flex; flex-direction: column; gap: 12px; width: 100%; max-width: 320px; }
.pin-input, .name-input {
  width: 100%;
  text-align: center;
  font-size: 2rem;
  letter-spacing: 0.5em;
  padding: 14px;
  border-radius: 14px;
  border: 1.5px solid #334155;
  background: #0f172a;
  color: #f1f5f9;
  outline: none;
}
.name-input { letter-spacing: normal; font-size: 1.4rem; }
.pin-input:focus, .name-input:focus { border-color: #38bdf8; }
.pin-input.shake { animation: shake 0.3s; border-color: #ef4444; }
@keyframes shake { 0%,100%{transform:translateX(0)} 25%{transform:translateX(-6px)} 75%{transform:translateX(6px)} }

.error-text { color: #f87171; font-size: 0.95rem; }
.error-bar {
  background: #450a0a;
  border: 1px solid #ef4444;
  color: #fecaca;
  padding: 12px 14px;
  border-radius: 12px;
  margin-bottom: 12px;
}

.btn-primary, .btn-send {
  width: 100%;
  font-size: 1.15rem;
  font-weight: 600;
  padding: 16px;
  border-radius: 14px;
  border: none;
  background: #0ea5e9;
  color: #020617;
}
.btn-primary:disabled, .btn-send:disabled { opacity: 0.4; }
.btn-primary:active, .btn-send:active { background: #0284c7; }

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.topbar-title { display: flex; align-items: center; gap: 10px; font-size: 1.25rem; font-weight: 700; }
.name-chip {
  border: 1px solid #334155;
  background: #0f172a;
  color: #cbd5e1;
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 0.95rem;
}

.field { margin-bottom: 18px; }
.field-label {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #94a3b8;
  margin-bottom: 6px;
}

.select-wrap { position: relative; }
.select-wrap::after {
  content: '▾';
  position: absolute; right: 14px; top: 50%; transform: translateY(-50%);
  color: #94a3b8; pointer-events: none;
}
.select {
  width: 100%;
  font-size: 1.15rem;
  padding: 14px 40px 14px 14px;
  border-radius: 12px;
  border: 1.5px solid #334155;
  background: #0f172a;
  color: #f1f5f9;
  -webkit-appearance: none;
  appearance: none;
}
.select:focus { outline: none; border-color: #38bdf8; }

.note {
  width: 100%;
  font-size: 1.15rem;
  line-height: 1.4;
  padding: 14px;
  border-radius: 12px;
  border: 1.5px solid #334155;
  background: #0f172a;
  color: #f1f5f9;
  resize: none;
  font-family: inherit;
}
.note:focus { outline: none; border-color: #38bdf8; }
.note::placeholder { color: #475569; }

.photo-buttons { display: flex; gap: 10px; }
.btn-photo {
  flex: 1;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  font-size: 1.05rem;
  font-weight: 600;
  padding: 16px 10px;
  border-radius: 12px;
  border: 1.5px dashed #475569;
  background: #0f172a;
  color: #e2e8f0;
}
.btn-photo:active { background: #1e293b; }
.ico { font-size: 1.3rem; }

.thumbs { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 10px; margin-top: 12px; }
.thumb { position: relative; aspect-ratio: 1; border-radius: 10px; overflow: hidden; background: #0f172a; border: 1px solid #1e293b; }
.thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.thumb-loading { display: flex; align-items: center; justify-content: center; color: #64748b; font-size: 1.5rem; }
.thumb-x {
  position: absolute; top: 4px; right: 4px;
  width: 30px; height: 30px; border-radius: 50%;
  border: none; background: rgba(2,6,23,0.8); color: #f8fafc; font-size: 0.9rem;
}

.send-bar {
  position: fixed;
  left: 0; right: 0; bottom: 0;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  background: linear-gradient(to top, #020617 70%, rgba(2,6,23,0));
}
.send-bar .btn-send { max-width: 560px; margin: 0 auto; display: block; }

.sent-mark {
  width: 96px; height: 96px; border-radius: 50%;
  background: #059669; color: #ecfdf5;
  font-size: 3rem; display: flex; align-items: center; justify-content: center;
}
.sent-detail { color: #cbd5e1; font-size: 1.05rem; }
</style>
