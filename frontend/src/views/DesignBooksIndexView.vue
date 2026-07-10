<script setup lang="ts">
/**
 * Design Books index — list every master design book and start a new one.
 *
 * Books are product-level (one per product line): spa-standard is the first,
 * more can be added as other products get a controlled build document. A book
 * isn't persisted until its first publish, so "New Design Book" just collects a
 * code + title + template and lands on the per-book view in first-gen state.
 */
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  listDesignBooks,
  slugifyBookCode,
  isValidBookCode,
  type BookListItem,
} from '../services/designBook'

const router = useRouter()

const loading = ref(true)
const error = ref('')
const books = ref<BookListItem[]>([])

const showNew = ref(false)
const newCode = ref('')
const newTitle = ref('')
const newTemplate = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    books.value = await listDesignBooks()
  } catch (e: any) {
    error.value = e?.message || 'Failed to load design books'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const existingCodes = computed(() => new Set(books.value.map(b => b.book_code)))
const codeError = computed(() => {
  const code = newCode.value.trim()
  if (!code) return ''
  if (!isValidBookCode(code)) return 'Lowercase letters, numbers and single hyphens only'
  if (existingCodes.value.has(code)) return 'A book with this code already exists'
  return ''
})
const canCreate = computed(
  () => !!newCode.value.trim() && !codeError.value && !!newTemplate.value.trim()
)

function onCodeInput(e: Event) {
  newCode.value = slugifyBookCode((e.target as HTMLInputElement).value)
}

function openBook(code: string) {
  router.push(`/mrp/design-book/${code}`)
}

function createBook() {
  if (!canCreate.value) return
  const code = newCode.value.trim()
  router.push({
    path: `/mrp/design-book/${code}`,
    query: { title: newTitle.value.trim() || undefined, template: newTemplate.value.trim() },
  })
}

function fmtDate(iso: string | null): string {
  return iso ? iso.slice(0, 10) : '—'
}
</script>

<template>
  <div class="design-books">
    <header class="page-header">
      <div class="header-left">
        <button class="secondary-btn" @click="router.push('/mrp')">
          <i class="pi pi-arrow-left"></i> Dashboard
        </button>
        <h1>Design Books</h1>
        <span class="muted">product-level master build documents</span>
      </div>
      <div class="header-actions">
        <button class="secondary-btn" :disabled="loading" @click="load">
          <i :class="loading ? 'pi pi-spin pi-spinner' : 'pi pi-refresh'"></i> Refresh
        </button>
        <button class="primary-btn" @click="showNew = !showNew">
          <i class="pi pi-plus"></i> New Design Book
        </button>
      </div>
    </header>

    <div v-if="error" class="error-message">
      <i class="pi pi-exclamation-triangle"></i>
      <span>{{ error }}</span>
      <button class="dismiss" @click="error = ''">&times;</button>
    </div>

    <!-- new book form -->
    <div v-if="showNew" class="new-panel">
      <h2>New Design Book</h2>
      <p class="muted">
        The template project's model, routing and prints become the book. Product number is
        derived from the template's top assembly. Nothing is published until you Generate on the
        next screen.
      </p>
      <div class="new-form">
        <label>
          <span>Book code</span>
          <input
            :value="newCode"
            type="text"
            class="mono"
            placeholder="e.g. spa-standard"
            @input="onCodeInput"
          />
          <small v-if="codeError" class="field-error">{{ codeError }}</small>
          <small v-else class="muted">bucket folder + URL — permanent</small>
        </label>
        <label>
          <span>Title</span>
          <input v-model="newTitle" type="text" placeholder="Standard Spa Master Design Book" />
        </label>
        <label>
          <span>Template project</span>
          <input v-model="newTemplate" type="text" class="mono" placeholder="e.g. SPA0030" />
        </label>
      </div>
      <div class="new-actions">
        <button class="secondary-btn" @click="showNew = false">Cancel</button>
        <button class="primary-btn" :disabled="!canCreate" @click="createBook">
          <i class="pi pi-arrow-right"></i> Continue to Generate
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading-msg">Loading design books…</div>

    <div v-else-if="!books.length && !showNew" class="empty-state">
      <i class="pi pi-book"></i>
      <p>No design books yet.</p>
      <button class="primary-btn" @click="showNew = true">
        <i class="pi pi-plus"></i> Create the first one
      </button>
    </div>

    <div v-else-if="books.length" class="book-grid">
      <button v-for="b in books" :key="b.book_code" class="book-card" @click="openBook(b.book_code)">
        <div class="card-top">
          <span class="mono book-code">{{ b.book_code }}</span>
          <span class="rev-badge">REV {{ b.book_rev }}</span>
        </div>
        <div class="card-title">{{ b.title }}</div>
        <div class="card-meta">
          <span class="mono">{{ b.product_item_number }}</span>
          <span>·</span>
          <span>{{ b.section_count }} sections</span>
        </div>
        <div class="card-footer">
          <span class="muted">Published {{ fmtDate(b.generated_at) }}</span>
          <span v-if="b.stale_print_count > 0" class="stale-badge">
            {{ b.stale_print_count }} stale
          </span>
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.design-books {
  min-height: 100vh;
  background: #020617;
  color: #e5e7eb;
  padding-bottom: 40px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  background: #020617;
  border-bottom: 1px solid #1e293b;
  flex-wrap: wrap;
  gap: 12px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-left h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.header-actions {
  display: flex;
  gap: 12px;
}

.mono { font-family: 'Consolas', 'Monaco', monospace; }
.muted { color: #9ca3af; font-size: 12px; }

.primary-btn,
.secondary-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  border: none;
  color: white;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
}
.primary-btn { background: #2563eb; }
.primary-btn:hover:not(:disabled) { background: #1d4ed8; }
.secondary-btn { background: #374151; }
.secondary-btn:hover:not(:disabled) { background: #4b5563; }
.primary-btn:disabled,
.secondary-btn:disabled {
  background: #374151;
  color: #6b7280;
  cursor: not-allowed;
}

.error-message {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 20px 0;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  background: #7f1d1d;
  color: #fca5a5;
}
.dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  font-size: 18px;
  cursor: pointer;
  line-height: 1;
}

.new-panel {
  margin: 20px;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 20px;
  max-width: 900px;
}
.new-panel h2 {
  margin: 0 0 6px;
  font-size: 16px;
}
.new-panel p {
  margin: 0 0 14px;
  line-height: 1.5;
}
.new-form {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.new-form label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.new-form input {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 6px;
  color: #e5e7eb;
  padding: 8px 10px;
  font-size: 13px;
  min-width: 240px;
}
.new-form input:focus {
  outline: none;
  border-color: #38bdf8;
}
.new-form small {
  text-transform: none;
  letter-spacing: 0;
}
.field-error { color: #fca5a5; font-size: 11px; }
.new-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 16px;
}

.loading-msg {
  padding: 40px 20px;
  color: #9ca3af;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 60px 20px;
  color: #9ca3af;
}
.empty-state i {
  font-size: 40px;
  color: #374151;
}
.empty-state p {
  margin: 0;
  font-size: 14px;
}

.book-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  padding: 20px;
}
.book-card {
  text-align: left;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  color: #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.book-card:hover {
  border-color: #38bdf8;
  background: #14203a;
}
.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.book-code { color: #9ca3af; font-size: 13px; }
.rev-badge {
  background: #059669;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.card-title {
  font-size: 15px;
  font-weight: 600;
}
.card-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  color: #9ca3af;
  font-size: 12px;
}
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}
.stale-badge {
  background: #d97706;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}
</style>
