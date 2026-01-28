import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://lnytnxmmemdzwqburtgf.supabase.co'
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || ''

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
    flowType: 'implicit',
    storageKey: 'pdm-web-auth'
  }
})

// API base URL for FastAPI backend
// Dynamically determine based on current host
function getApiBaseUrl(): string {
  // Allow explicit override via env var
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL
  }

  // Production: API is served from same origin (single container deployment)
  if (import.meta.env.PROD) {
    return `${window.location.origin}/api`
  }

  // Development: use current hostname with separate backend port
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  const backendPort = 8001

  return `${protocol}//${hostname}:${backendPort}/api`
}

export const API_BASE_URL = getApiBaseUrl()

// Helper for API calls with auth
export async function apiCall<T>(
  endpoint: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  // Get fresh session - Supabase auto-refreshes if token is expired
  const { data: { session }, error: sessionError } = await supabase.auth.getSession()

  if (sessionError) {
    console.error('Session error:', sessionError)
  }

  const token = session?.access_token

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (token) {
    ;(headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  })

  // On 401, try to refresh session and retry once
  if (response.status === 401 && retry) {
    console.log('Got 401, attempting session refresh...')
    const { data: { session: newSession } } = await supabase.auth.refreshSession()

    if (newSession) {
      // Retry with new token
      return apiCall<T>(endpoint, options, false)
    }
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(error.detail || `API error: ${response.status}`)
  }

  return response.json()
}
