import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Supplier, SupplierItemView, SupplierComment } from '../types/supplier'

const STORAGE_KEY = 'pdm-web-supplier-auth'
const API_BASE = '/api/supplier'

export const useSupplierAuthStore = defineStore('supplierAuth', () => {
  const supplier = ref<Supplier | null>(null)
  const token = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const initialized = ref(false)

  const isAuthenticated = computed(() => !!supplier.value && !!token.value)

  /**
   * Initialize from localStorage on app load
   */
  function initialize() {
    if (initialized.value) return

    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      try {
        const data = JSON.parse(stored)
        supplier.value = data.supplier
        token.value = data.token
      } catch {
        localStorage.removeItem(STORAGE_KEY)
      }
    }
    initialized.value = true
  }

  /**
   * Login with email and password
   */
  async function login(email: string, password: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const response = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Login failed' }))
        throw new Error(err.detail || 'Login failed')
      }

      const data = await response.json()
      supplier.value = data.supplier
      token.value = data.access_token

      // Persist to localStorage
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        supplier: data.supplier,
        token: data.access_token,
      }))

      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Login failed'
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * Logout and clear session
   */
  function logout() {
    supplier.value = null
    token.value = null
    localStorage.removeItem(STORAGE_KEY)
  }

  /**
   * Make authenticated API calls to supplier endpoints
   */
  async function apiCall<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    if (!token.value) {
      throw new Error('Not authenticated')
    }

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token.value}`,
      ...options.headers,
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    })

    if (response.status === 401) {
      // Session expired
      logout()
      throw new Error('Session expired. Please login again.')
    }

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Request failed' }))
      throw new Error(err.detail || `Request failed: ${response.status}`)
    }

    return response.json()
  }

  /**
   * Get all items the supplier has access to
   */
  async function getItems(): Promise<SupplierItemView[]> {
    return apiCall<SupplierItemView[]>('/items')
  }

  /**
   * Get a specific item
   */
  async function getItem(itemNumber: string): Promise<SupplierItemView> {
    return apiCall<SupplierItemView>(`/items/${itemNumber}`)
  }

  /**
   * Get download URL for a file
   */
  async function getDownloadUrl(itemNumber: string, fileId: string): Promise<{ url: string; filename: string }> {
    return apiCall(`/items/${itemNumber}/files/${fileId}/download`)
  }

  /**
   * Get comments for an item
   */
  async function getComments(itemNumber: string): Promise<SupplierComment[]> {
    return apiCall<SupplierComment[]>(`/items/${itemNumber}/comments`)
  }

  /**
   * Post a new comment on an item
   */
  async function postComment(itemNumber: string, content: string): Promise<SupplierComment> {
    return apiCall<SupplierComment>(`/items/${itemNumber}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    })
  }

  return {
    // State
    supplier,
    token,
    loading,
    error,
    initialized,

    // Computed
    isAuthenticated,

    // Actions
    initialize,
    login,
    logout,
    apiCall,

    // API helpers
    getItems,
    getItem,
    getDownloadUrl,
    getComments,
    postComment,
  }
})
