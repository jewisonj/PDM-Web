<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { apiCall } from '../../services/supabase'
import type { SupplierWithUnread, SupplierCreate } from '../../types/supplier'

const router = useRouter()

const suppliers = ref<SupplierWithUnread[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const showCreateForm = ref(false)
const searchQuery = ref('')
const saving = ref(false)

// Create form
const form = ref<SupplierCreate>({
  company_name: '',
  contact_name: '',
  contact_email: '',
  phone: '',
  login_email: '',
  password: '',
  is_active: true,
  notes: '',
})

const filteredSuppliers = computed(() => {
  if (!searchQuery.value) return suppliers.value
  const q = searchQuery.value.toLowerCase()
  return suppliers.value.filter(s =>
    s.company_name.toLowerCase().includes(q) ||
    s.login_email.toLowerCase().includes(q) ||
    (s.contact_name && s.contact_name.toLowerCase().includes(q))
  )
})

const totalUnread = computed(() => {
  return suppliers.value.reduce((sum, s) => sum + s.unread_count, 0)
})

onMounted(async () => {
  await loadSuppliers()
})

async function loadSuppliers() {
  loading.value = true
  error.value = null
  try {
    suppliers.value = await apiCall<SupplierWithUnread[]>('/admin/suppliers')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load suppliers'
  } finally {
    loading.value = false
  }
}

function viewSupplier(id: string) {
  router.push(`/admin/suppliers/${id}`)
}

function resetForm() {
  form.value = {
    company_name: '',
    contact_name: '',
    contact_email: '',
    phone: '',
    login_email: '',
    password: '',
    is_active: true,
    notes: '',
  }
}

async function createSupplier() {
  if (!form.value.company_name || !form.value.login_email || !form.value.password) {
    alert('Company name, login email, and password are required')
    return
  }

  saving.value = true
  try {
    await apiCall('/admin/suppliers', {
      method: 'POST',
      body: JSON.stringify(form.value),
    })
    showCreateForm.value = false
    resetForm()
    await loadSuppliers()
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to create supplier')
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push('/')
}
</script>

<template>
  <div class="admin-suppliers-view">
    <header class="view-header">
      <div class="header-left">
        <button class="back-btn" @click="goBack">&larr; Home</button>
        <h1>Supplier Management</h1>
        <span v-if="totalUnread > 0" class="total-unread">
          {{ totalUnread }} unread
        </span>
      </div>
      <button class="create-btn" @click="showCreateForm = true">
        + New Supplier
      </button>
    </header>

    <main class="view-main">
      <div class="controls-bar">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search suppliers..."
          class="search-input"
        />
        <span class="supplier-count">{{ filteredSuppliers.length }} suppliers</span>
      </div>

      <div v-if="loading" class="loading-state">Loading suppliers...</div>
      <div v-else-if="error" class="error-state">{{ error }}</div>

      <div v-else-if="suppliers.length === 0" class="empty-state">
        <h3>No Suppliers Yet</h3>
        <p>Create your first supplier account to get started.</p>
      </div>

      <div v-else class="suppliers-table">
        <div class="table-header">
          <div class="col-company">Company</div>
          <div class="col-contact">Contact</div>
          <div class="col-email">Login Email</div>
          <div class="col-status">Status</div>
          <div class="col-unread">Unread</div>
        </div>

        <div
          v-for="supplier in filteredSuppliers"
          :key="supplier.id"
          class="table-row"
          @click="viewSupplier(supplier.id)"
        >
          <div class="col-company">
            <strong>{{ supplier.company_name }}</strong>
          </div>
          <div class="col-contact">
            {{ supplier.contact_name || '-' }}
          </div>
          <div class="col-email">
            {{ supplier.login_email }}
          </div>
          <div class="col-status">
            <span :class="['status-badge', supplier.is_active ? 'active' : 'inactive']">
              {{ supplier.is_active ? 'Active' : 'Inactive' }}
            </span>
          </div>
          <div class="col-unread">
            <span v-if="supplier.unread_count > 0" class="unread-badge">
              {{ supplier.unread_count }}
            </span>
            <span v-else class="no-unread">-</span>
          </div>
        </div>
      </div>
    </main>

    <!-- Create Supplier Modal -->
    <div v-if="showCreateForm" class="modal-overlay" @click.self="showCreateForm = false">
      <div class="modal-content">
        <div class="modal-header">
          <h2>Create New Supplier</h2>
          <button class="close-btn" @click="showCreateForm = false">&times;</button>
        </div>

        <form @submit.prevent="createSupplier" class="supplier-form">
          <div class="form-row">
            <div class="form-field">
              <label>Company Name *</label>
              <input v-model="form.company_name" type="text" required />
            </div>
          </div>

          <div class="form-row">
            <div class="form-field">
              <label>Contact Name</label>
              <input v-model="form.contact_name" type="text" />
            </div>
            <div class="form-field">
              <label>Contact Email</label>
              <input v-model="form.contact_email" type="email" />
            </div>
          </div>

          <div class="form-row">
            <div class="form-field">
              <label>Phone</label>
              <input v-model="form.phone" type="text" />
            </div>
          </div>

          <hr />

          <div class="form-row">
            <div class="form-field">
              <label>Login Email *</label>
              <input v-model="form.login_email" type="email" required />
            </div>
            <div class="form-field">
              <label>Password * (min 8 chars)</label>
              <input v-model="form.password" type="password" minlength="8" required />
            </div>
          </div>

          <div class="form-row">
            <div class="form-field full-width">
              <label>Notes</label>
              <textarea v-model="form.notes" rows="2"></textarea>
            </div>
          </div>

          <div class="form-row">
            <label class="checkbox-label">
              <input type="checkbox" v-model="form.is_active" />
              Active (can log in)
            </label>
          </div>

          <div class="form-actions">
            <button type="button" class="cancel-btn" @click="showCreateForm = false">
              Cancel
            </button>
            <button type="submit" class="submit-btn" :disabled="saving">
              {{ saving ? 'Creating...' : 'Create Supplier' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-suppliers-view {
  min-height: 100vh;
  background: #f1f5f9;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: white;
  border-bottom: 1px solid #e2e8f0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.back-btn {
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  color: #475569;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.back-btn:hover {
  background: #e2e8f0;
}

h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #1e293b;
}

.total-unread {
  background: #dc2626;
  color: white;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.create-btn {
  background: #1e40af;
  color: white;
  border: none;
  padding: 0.6rem 1.25rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.create-btn:hover {
  background: #1e3a8a;
}

.view-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
}

.controls-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.search-input {
  padding: 10px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
  width: 300px;
}

.search-input:focus {
  outline: none;
  border-color: #1e40af;
}

.supplier-count {
  color: #64748b;
  font-size: 14px;
}

.loading-state,
.error-state,
.empty-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #64748b;
}

.error-state {
  color: #dc2626;
}

.empty-state h3 {
  margin: 0 0 0.5rem;
  color: #334155;
}

/* Table */
.suppliers-table {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.table-header {
  display: grid;
  grid-template-columns: 1fr 150px 200px 100px 80px;
  gap: 1rem;
  padding: 0.75rem 1rem;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
}

.table-row {
  display: grid;
  grid-template-columns: 1fr 150px 200px 100px 80px;
  gap: 1rem;
  padding: 1rem;
  border-bottom: 1px solid #f1f5f9;
  cursor: pointer;
  align-items: center;
}

.table-row:hover {
  background: #f8fafc;
}

.table-row:last-child {
  border-bottom: none;
}

.col-company strong {
  color: #1e293b;
}

.col-contact,
.col-email {
  color: #64748b;
  font-size: 14px;
}

.status-badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.status-badge.active {
  background: #d1fae5;
  color: #065f46;
}

.status-badge.inactive {
  background: #f3f4f6;
  color: #6b7280;
}

.unread-badge {
  display: inline-block;
  background: #dc2626;
  color: white;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
}

.no-unread {
  color: #cbd5e1;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-content {
  background: white;
  border-radius: 12px;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-header h2 {
  margin: 0;
  font-size: 1.25rem;
  color: #1e293b;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: #94a3b8;
  cursor: pointer;
}

.close-btn:hover {
  color: #64748b;
}

.supplier-form {
  padding: 1.5rem;
}

.form-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

.form-field {
  flex: 1;
}

.form-field.full-width {
  flex: 1;
}

.form-field label {
  display: block;
  margin-bottom: 0.4rem;
  font-size: 13px;
  font-weight: 500;
  color: #475569;
}

.form-field input,
.form-field textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
}

.form-field input:focus,
.form-field textarea:focus {
  outline: none;
  border-color: #1e40af;
}

hr {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 1.5rem 0;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 14px;
  color: #475569;
  cursor: pointer;
}

.checkbox-label input {
  width: 16px;
  height: 16px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.cancel-btn {
  background: white;
  border: 1px solid #cbd5e1;
  color: #64748b;
  padding: 0.6rem 1.25rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.cancel-btn:hover {
  background: #f8fafc;
}

.submit-btn {
  background: #1e40af;
  color: white;
  border: none;
  padding: 0.6rem 1.25rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.submit-btn:hover:not(:disabled) {
  background: #1e3a8a;
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
</style>
