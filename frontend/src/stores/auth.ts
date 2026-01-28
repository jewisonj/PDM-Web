import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { supabase, apiCall } from '../services/supabase'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const initialized = ref(false)

  const isAuthenticated = computed(() => !!user.value)
  const isEngineer = computed(() => user.value?.role === 'engineer' || user.value?.role === 'admin')
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function initialize() {
    // Prevent multiple initializations
    if (initialized.value) {
      return
    }
    initialized.value = true

    loading.value = true
    error.value = null

    try {
      const { data: { session } } = await supabase.auth.getSession()

      if (session) {
        await fetchUser()
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to initialize auth'
      console.error('Auth initialization error:', e)
    } finally {
      loading.value = false
    }

    // Listen for auth changes (only once)
    supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session) {
        await fetchUser()
      } else if (event === 'SIGNED_OUT') {
        user.value = null
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
