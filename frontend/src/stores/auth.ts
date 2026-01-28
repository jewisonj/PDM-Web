import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { supabase, apiCall } from '../services/supabase'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const initialized = ref(false)
  const initPromise = ref<Promise<void> | null>(null)

  const isAuthenticated = computed(() => !!user.value)
  const isEngineer = computed(() => user.value?.role === 'engineer' || user.value?.role === 'admin')
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function initialize() {
    // If already initialized, return immediately
    if (initialized.value) {
      return
    }

    // If initialization is in progress, wait for it
    if (initPromise.value) {
      return initPromise.value
    }

    // Start initialization
    initPromise.value = doInitialize()
    return initPromise.value
  }

  async function doInitialize() {
    loading.value = true
    error.value = null

    try {
      // Get current session - Supabase will auto-refresh if needed
      const { data: { session }, error: sessionError } = await supabase.auth.getSession()

      if (sessionError) {
        console.error('Session error:', sessionError)
      }

      if (session) {
        await fetchUser()
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to initialize auth'
      console.error('Auth initialization error:', e)
    } finally {
      loading.value = false
      initialized.value = true
    }

    // Listen for auth changes (only once)
    supabase.auth.onAuthStateChange(async (event, session) => {
      console.log('Auth state change:', event)

      if (event === 'SIGNED_IN' && session) {
        await fetchUser()
      } else if (event === 'SIGNED_OUT') {
        user.value = null
      } else if (event === 'TOKEN_REFRESHED' && session) {
        // Token was refreshed, re-fetch user to ensure we have valid data
        await fetchUser()
      }
    })
  }

  async function fetchUser() {
    try {
      user.value = await apiCall<User>('/auth/me')
    } catch (e) {
      console.error('Failed to fetch user:', e)
      user.value = null
    }
  }

  async function login(email: string, password: string) {
    loading.value = true
    error.value = null

    try {
      const { error: authError } = await supabase.auth.signInWithPassword({
        email,
        password,
      })

      if (authError) throw authError

      await fetchUser()
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Login failed'
      return false
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    loading.value = true

    try {
      await supabase.auth.signOut()
      user.value = null
    } catch (e) {
      console.error('Logout error:', e)
    } finally {
      loading.value = false
    }
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    isEngineer,
    isAdmin,
    initialize,
    login,
    logout,
  }
})
