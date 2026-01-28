<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')

async function handleLogin() {
  const success = await authStore.login(email.value, password.value)

  if (success) {
    const redirect = route.query.redirect as string || '/'
    router.push(redirect)
  }
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <h1>PDM-Web</h1>
      <p class="subtitle">Product Data Management</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="field">
          <label for="email">Email</label>
          <input
            id="email"
            v-model="email"
            type="email"
            placeholder="Enter your email"
            required
            autocomplete="username"
            :disabled="authStore.loading"
          />
        </div>

        <div class="field">
          <label for="password">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            placeholder="Enter your password"
            required
            autocomplete="current-password"
            :disabled="authStore.loading"
          />
        </div>

        <div v-if="authStore.error" class="error">
          {{ authStore.error }}
        </div>

        <button type="submit" :disabled="authStore.loading" class="login-btn">
          {{ authStore.loading ? 'Signing in...' : 'Sign In' }}
        </button>
      </form>

      <div class="help-text">
        <p>Users: jack@pdm.local, dan@pdm.local, shop@pdm.local</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #e5e5e5;
}

.login-card {
  background: #fff;
  padding: 2.5rem;
  border-radius: 8px;
  width: 100%;
  max-width: 380px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

h1 {
  margin: 0;
  color: #333;
  font-size: 1.75rem;
  text-align: center;
  font-weight: 600;
}

.subtitle {
  color: #888;
  text-align: center;
  margin: 0.5rem 0 2rem;
  font-size: 14px;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

label {
  color: #555;
  font-size: 13px;
  font-weight: 500;
}

input {
  padding: 10px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #fff;
  color: #333;
  font-size: 14px;
}

input:focus {
  outline: none;
  border-color: #666;
}

input:disabled {
  opacity: 0.7;
  background: #f5f5f5;
}

input::placeholder {
  color: #aaa;
}

.error {
  color: #c0392b;
  font-size: 13px;
  padding: 10px;
  background: #fdf2f2;
  border: 1px solid #f5c6cb;
  border-radius: 4px;
}

.login-btn {
  padding: 12px;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
  margin-top: 0.5rem;
}

.login-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.login-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.help-text {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #e0e0e0;
  text-align: center;
}

.help-text p {
  color: #999;
  font-size: 12px;
  margin: 0;
}
</style>
