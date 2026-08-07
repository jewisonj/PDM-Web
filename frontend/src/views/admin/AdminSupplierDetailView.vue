<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { apiCall } from '../../services/supabase'
import { supabase } from '../../services/supabase'
import type { Supplier, SupplierUpdate, ItemAccess, SupplierComment } from '../../types/supplier'

const router = useRouter()
const route = useRoute()

const supplierId = computed(() => route.params.id as string)
const supplier = ref<Supplier | null>(null)
const itemAccess = ref<ItemAccess[]>([])
const comments = ref<SupplierComment[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const saving = ref(false)
const activeTab = ref<'details' | 'items' | 'comments'>('details')

// Edit form
const editForm = ref<SupplierUpdate>({})

// Add item access
const showAddItem = ref(false)
const itemSearchQuery = ref('')
const itemSearchResults = ref<Array<{ id: string; item_number: string; name: string }>>([])
const selectedFileTypes = ref<string[]>(['PDF', 'STEP'])
const addingItem = ref(false)

// Password reset
const showResetPassword = ref(false)
const newPassword = ref('')
const resettingPassword = ref(false)

// Reply
const replyToItemId = ref<string | null>(null)
const replyContent = ref('')
const postingReply = ref(false)

onMounted(async () => {
  await loadData()
})

async function loadData() {
  loading.value = true
  error.value = null
  try {
    const [supplierData, accessData, commentsData] = await Promise.all([
      apiCall<Supplier>(`/admin/suppliers/${supplierId.value}`),
      apiCall<ItemAccess[]>(`/admin/suppliers/${supplierId.value}/items`),
      apiCall<SupplierComment[]>(`/admin/suppliers/${supplierId.value}/comments`),
    ])
    supplier.value = supplierData
    itemAccess.value = accessData
    comments.value = commentsData

    // Initialize edit form
    editForm.value = {
      company_name: supplierData.company_name,
      contact_name: supplierData.contact_name,
      contact_email: supplierData.contact_email,
      phone: supplierData.phone,
      login_email: supplierData.login_email,
      is_active: supplierData.is_active,
      notes: supplierData.notes,
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load supplier'
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/admin/suppliers')
}

async function saveChanges() {
  saving.value = true
  try {
    await apiCall(`/admin/suppliers/${supplierId.value}`, {
      method: 'PATCH',
      body: JSON.stringify(editForm.value),
    })
    await loadData()
    alert('Supplier updated successfully')
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to update supplier')
  } finally {
    saving.value = false
  }
}

async function deactivateSupplier() {
  if (!confirm('Are you sure you want to deactivate this supplier? They will no longer be able to log in.')) {
    return
  }

  try {
    await apiCall(`/admin/suppliers/${supplierId.value}`, {
      method: 'DELETE',
    })
    router.push('/admin/suppliers')
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to deactivate supplier')
  }
}

async function resetPassword() {
  if (newPassword.value.length < 8) {
    alert('Password must be at least 8 characters')
    return
  }

  resettingPassword.value = true
  try {
    await apiCall(`/admin/suppliers/${supplierId.value}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ new_password: newPassword.value }),
    })
    showResetPassword.value = false
    newPassword.value = ''
    alert('Password reset successfully')
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to reset password')
  } finally {
    resettingPassword.value = false
  }
}

// Item search
async function searchItems() {
  if (itemSearchQuery.value.length < 2) {
    itemSearchResults.value = []
    return
  }

  const { data } = await supabase
    .from('items')
    .select('id, item_number, name')
    .or(`item_number.ilike.%${itemSearchQuery.value}%,name.ilike.%${itemSearchQuery.value}%`)
    .limit(10)

  // Filter out already-added items
  const existingIds = new Set(itemAccess.value.map(a => a.item_id))
  itemSearchResults.value = (data || []).filter(item => !existingIds.has(item.id))
}

async function addItemAccess(item: { id: string; item_number: string; name: string }) {
  addingItem.value = true
  try {
    await apiCall(`/admin/suppliers/${supplierId.value}/items`, {
      method: 'POST',
      body: JSON.stringify({
        item_id: item.id,
        file_types: selectedFileTypes.value,
      }),
    })
    showAddItem.value = false
    itemSearchQuery.value = ''
    itemSearchResults.value = []
    selectedFileTypes.value = ['PDF', 'STEP']
    await loadData()
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to add item access')
  } finally {
    addingItem.value = false
  }
}

async function removeItemAccess(itemId: string) {
  if (!confirm('Remove access to this item?')) return

  try {
    await apiCall(`/admin/suppliers/${supplierId.value}/items/${itemId}`, {
      method: 'DELETE',
    })
    await loadData()
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to remove access')
  }
}

async function postReply() {
  if (!replyContent.value.trim() || !replyToItemId.value) return

  postingReply.value = true
  try {
    await apiCall(`/admin/suppliers/${supplierId.value}/items/${replyToItemId.value}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content: replyContent.value.trim() }),
    })
    replyContent.value = ''
    replyToItemId.value = null
    await loadData()
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Failed to post reply')
  } finally {
    postingReply.value = false
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// Group comments by item
const commentsByItem = computed(() => {
  const grouped: Record<string, SupplierComment[]> = {}
  for (const comment of comments.value) {
    ;(grouped[comment.item_id] ??= []).push(comment)
  }
  return grouped
})

// Get item number for an item_id
function getItemNumber(itemId: string): string {
  const access = itemAccess.value.find(a => a.item_id === itemId)
  return access?.item_number || itemId
}
</script>

<template>
  <div class="supplier-detail-view">
    <header class="view-header">
      <div class="header-left">
        <button class="back-btn" @click="goBack">&larr; Suppliers</button>
        <h1 v-if="supplier">{{ supplier.company_name }}</h1>
      </div>
      <div class="header-right" v-if="supplier">
        <span :class="['status-badge', supplier.is_active ? 'active' : 'inactive']">
          {{ supplier.is_active ? 'Active' : 'Inactive' }}
        </span>
      </div>
    </header>

    <main class="view-main">
      <div v-if="loading" class="loading-state">Loading supplier details...</div>
      <div v-else-if="error" class="error-state">{{ error }}</div>

      <template v-else-if="supplier">
        <!-- Tabs -->
        <div class="tabs">
          <button
            :class="['tab', { active: activeTab === 'details' }]"
            @click="activeTab = 'details'"
          >
            Details
          </button>
          <button
            :class="['tab', { active: activeTab === 'items' }]"
            @click="activeTab = 'items'"
          >
            Item Access ({{ itemAccess.length }})
          </button>
          <button
            :class="['tab', { active: activeTab === 'comments' }]"
            @click="activeTab = 'comments'"
          >
            Comments ({{ comments.length }})
          </button>
        </div>

        <!-- Details Tab -->
        <div v-if="activeTab === 'details'" class="tab-content">
          <form @submit.prevent="saveChanges" class="details-form">
            <div class="form-section">
              <h3>Company Information</h3>
              <div class="form-row">
                <div class="form-field">
                  <label>Company Name</label>
                  <input v-model="editForm.company_name" type="text" required />
                </div>
              </div>
              <div class="form-row">
                <div class="form-field">
                  <label>Contact Name</label>
                  <input v-model="editForm.contact_name" type="text" />
                </div>
                <div class="form-field">
                  <label>Contact Email</label>
                  <input v-model="editForm.contact_email" type="email" />
                </div>
              </div>
              <div class="form-row">
                <div class="form-field">
                  <label>Phone</label>
                  <input v-model="editForm.phone" type="text" />
                </div>
              </div>
            </div>

            <div class="form-section">
              <h3>Account Settings</h3>
              <div class="form-row">
                <div class="form-field">
                  <label>Login Email</label>
                  <input v-model="editForm.login_email" type="email" required />
                </div>
                <div class="form-field">
                  <label>Password</label>
                  <button type="button" class="reset-pwd-btn" @click="showResetPassword = true">
                    Reset Password
                  </button>
                </div>
              </div>
              <div class="form-row">
                <label class="checkbox-label">
                  <input type="checkbox" v-model="editForm.is_active" />
                  Active (can log in)
                </label>
              </div>
            </div>

            <div class="form-section">
              <h3>Notes</h3>
              <div class="form-row">
                <div class="form-field full-width">
                  <textarea v-model="editForm.notes" rows="3"></textarea>
                </div>
              </div>
            </div>

            <div class="form-actions">
              <button type="button" class="danger-btn" @click="deactivateSupplier">
                Deactivate Supplier
              </button>
              <button type="submit" class="save-btn" :disabled="saving">
                {{ saving ? 'Saving...' : 'Save Changes' }}
              </button>
            </div>
          </form>
        </div>

        <!-- Items Tab -->
        <div v-if="activeTab === 'items'" class="tab-content">
          <div class="items-header">
            <h3>Assigned Items</h3>
            <button class="add-item-btn" @click="showAddItem = true">
              + Add Item
            </button>
          </div>

          <div v-if="itemAccess.length === 0" class="empty-items">
            No items assigned yet. Click "Add Item" to grant access.
          </div>

          <div v-else class="items-list">
            <div v-for="access in itemAccess" :key="access.id" class="item-row">
              <div class="item-info">
                <span class="item-number">{{ access.item_number }}</span>
                <span class="item-name">{{ access.item_name || '-' }}</span>
              </div>
              <div class="file-types">
                <span v-for="ft in access.file_types" :key="ft" class="file-type-tag">
                  {{ ft }}
                </span>
              </div>
              <button class="remove-btn" @click="removeItemAccess(access.item_id)">
                Remove
              </button>
            </div>
          </div>
        </div>

        <!-- Comments Tab -->
        <div v-if="activeTab === 'comments'" class="tab-content">
          <h3>Supplier Comments & Questions</h3>

          <div v-if="comments.length === 0" class="empty-comments">
            No comments from this supplier yet.
          </div>

          <div v-else class="comments-by-item">
            <div
              v-for="(itemComments, itemId) in commentsByItem"
              :key="itemId"
              class="item-comments-group"
            >
              <div class="item-comments-header">
                <span class="item-number">{{ getItemNumber(itemId) }}</span>
                <button
                  class="reply-btn"
                  @click="replyToItemId = replyToItemId === itemId ? null : itemId"
                >
                  {{ replyToItemId === itemId ? 'Cancel' : 'Reply' }}
                </button>
              </div>

              <div class="comments-thread">
                <div
                  v-for="comment in itemComments"
                  :key="comment.id"
                  :class="['comment', comment.author_type, { unread: !comment.is_read && comment.author_type === 'supplier' }]"
                >
                  <div class="comment-header">
                    <span class="comment-author">{{ comment.author_name }}</span>
                    <span class="comment-date">{{ formatDate(comment.created_at) }}</span>
                  </div>
                  <div class="comment-content">{{ comment.content }}</div>
                </div>
              </div>

              <form
                v-if="replyToItemId === itemId"
                @submit.prevent="postReply"
                class="reply-form"
              >
                <textarea
                  v-model="replyContent"
                  placeholder="Type your reply..."
                  rows="2"
                ></textarea>
                <button type="submit" :disabled="!replyContent.trim() || postingReply">
                  {{ postingReply ? 'Posting...' : 'Post Reply' }}
                </button>
              </form>
            </div>
          </div>
        </div>
      </template>
    </main>

    <!-- Add Item Modal -->
    <div v-if="showAddItem" class="modal-overlay" @click.self="showAddItem = false">
      <div class="modal-content">
        <div class="modal-header">
          <h2>Add Item Access</h2>
          <button class="close-btn" @click="showAddItem = false">&times;</button>
        </div>

        <div class="modal-body">
          <div class="form-field">
            <label>Search Items</label>
            <input
              v-model="itemSearchQuery"
              @input="searchItems"
              type="text"
              placeholder="Type item number or name..."
            />
          </div>

          <div v-if="itemSearchResults.length > 0" class="search-results">
            <div
              v-for="item in itemSearchResults"
              :key="item.id"
              class="search-result"
              @click="addItemAccess(item)"
            >
              <span class="result-number">{{ item.item_number }}</span>
              <span class="result-name">{{ item.name || '-' }}</span>
            </div>
          </div>

          <div class="form-field" style="margin-top: 1rem;">
            <label>Allowed File Types</label>
            <div class="file-type-checkboxes">
              <label>
                <input type="checkbox" value="PDF" v-model="selectedFileTypes" /> PDF
              </label>
              <label>
                <input type="checkbox" value="STEP" v-model="selectedFileTypes" /> STEP
              </label>
              <label>
                <input type="checkbox" value="DXF" v-model="selectedFileTypes" /> DXF
              </label>
              <label>
                <input type="checkbox" value="SVG" v-model="selectedFileTypes" /> SVG
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Reset Password Modal -->
    <div v-if="showResetPassword" class="modal-overlay" @click.self="showResetPassword = false">
      <div class="modal-content modal-small">
        <div class="modal-header">
          <h2>Reset Password</h2>
          <button class="close-btn" @click="showResetPassword = false">&times;</button>
        </div>

        <form @submit.prevent="resetPassword" class="modal-body">
          <div class="form-field">
            <label>New Password (min 8 chars)</label>
            <input v-model="newPassword" type="password" minlength="8" required />
          </div>

          <div class="form-actions">
            <button type="button" class="cancel-btn" @click="showResetPassword = false">
              Cancel
            </button>
            <button type="submit" class="submit-btn" :disabled="resettingPassword">
              {{ resettingPassword ? 'Resetting...' : 'Reset Password' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.supplier-detail-view {
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

h1 {
  margin: 0;
  font-size: 1.5rem;
  color: #1e293b;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
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

.view-main {
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem;
}

.loading-state,
.error-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #64748b;
}

.error-state {
  color: #dc2626;
}

/* Tabs */
.tabs {
  display: flex;
  gap: 0;
  background: white;
  border-radius: 8px 8px 0 0;
  border: 1px solid #e2e8f0;
  border-bottom: none;
  overflow: hidden;
}

.tab {
  flex: 1;
  padding: 1rem;
  background: #f8fafc;
  border: none;
  border-right: 1px solid #e2e8f0;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #64748b;
}

.tab:last-child {
  border-right: none;
}

.tab.active {
  background: white;
  color: #1e40af;
  border-bottom: 2px solid #1e40af;
}

.tab-content {
  background: white;
  border: 1px solid #e2e8f0;
  border-top: none;
  border-radius: 0 0 8px 8px;
  padding: 1.5rem;
}

/* Forms */
.form-section {
  margin-bottom: 2rem;
}

.form-section h3 {
  margin: 0 0 1rem;
  font-size: 14px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
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

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 14px;
  color: #475569;
  cursor: pointer;
}

.reset-pwd-btn {
  padding: 10px 16px;
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #475569;
}

.reset-pwd-btn:hover {
  background: #e2e8f0;
}

.form-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.danger-btn {
  background: white;
  border: 1px solid #fca5a5;
  color: #dc2626;
  padding: 0.6rem 1.25rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}

.danger-btn:hover {
  background: #fef2f2;
}

.save-btn {
  background: #1e40af;
  color: white;
  border: none;
  padding: 0.6rem 1.5rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
}

.save-btn:hover:not(:disabled) {
  background: #1e3a8a;
}

.save-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

/* Items Tab */
.items-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.items-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #1e293b;
}

.add-item-btn {
  background: #1e40af;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.empty-items,
.empty-comments {
  color: #94a3b8;
  text-align: center;
  padding: 2rem;
}

.items-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.item-row {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.item-info {
  flex: 1;
  display: flex;
  gap: 1rem;
}

.item-number {
  font-family: monospace;
  font-weight: 600;
  color: #1e40af;
}

.item-name {
  color: #64748b;
}

.file-types {
  display: flex;
  gap: 0.5rem;
  margin-right: 1rem;
}

.file-type-tag {
  background: #e0e7ff;
  color: #3730a3;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.remove-btn {
  background: white;
  border: 1px solid #fca5a5;
  color: #dc2626;
  padding: 0.4rem 0.75rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.remove-btn:hover {
  background: #fef2f2;
}

/* Comments Tab */
.item-comments-group {
  margin-bottom: 1.5rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.item-comments-group:last-child {
  border-bottom: none;
}

.item-comments-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
}

.item-comments-header .item-number {
  font-family: monospace;
  font-weight: 600;
  color: #1e40af;
}

.reply-btn {
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  color: #475569;
  padding: 0.4rem 0.75rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.comments-thread {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.comment {
  padding: 0.75rem 1rem;
  border-radius: 8px;
}

.comment.supplier {
  background: #eff6ff;
  margin-right: 3rem;
}

.comment.admin {
  background: #f0fdf4;
  margin-left: 3rem;
}

.comment.unread {
  border-left: 3px solid #dc2626;
}

.comment-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.25rem;
  font-size: 12px;
}

.comment-author {
  font-weight: 600;
  color: #334155;
}

.comment-date {
  color: #94a3b8;
}

.comment-content {
  color: #475569;
  font-size: 14px;
  white-space: pre-wrap;
}

.reply-form {
  margin-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.reply-form textarea {
  padding: 0.75rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
  resize: vertical;
}

.reply-form button {
  align-self: flex-end;
  background: #1e40af;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.reply-form button:disabled {
  opacity: 0.5;
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
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-small {
  max-width: 400px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-header h2 {
  margin: 0;
  font-size: 1.1rem;
  color: #1e293b;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: #94a3b8;
  cursor: pointer;
}

.modal-body {
  padding: 1.5rem;
}

.search-results {
  margin-top: 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
}

.search-result {
  display: flex;
  gap: 1rem;
  padding: 0.75rem 1rem;
  cursor: pointer;
  border-bottom: 1px solid #f1f5f9;
}

.search-result:hover {
  background: #f8fafc;
}

.search-result:last-child {
  border-bottom: none;
}

.result-number {
  font-family: monospace;
  font-weight: 600;
  color: #1e40af;
}

.result-name {
  color: #64748b;
}

.file-type-checkboxes {
  display: flex;
  gap: 1.5rem;
}

.file-type-checkboxes label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 14px;
  cursor: pointer;
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

.submit-btn:disabled {
  opacity: 0.7;
}
</style>
