<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useSupplierAuthStore } from '../../stores/supplierAuth'

const router = useRouter()
const route = useRoute()
const supplierAuth = useSupplierAuthStore()

const email = ref('')
const password = ref('')

async function handleLogin() {
  const success = await supplierAuth.login(email.value, password.value)
  if (success) {
    const redirect = route.query.redirect as string
    router.push(redirect || '/supplier/portal')
  }
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <h1>Supplier Portal</h1>
      <p class="subtitle">Access your assigned drawings and documents</p>

      <form @submit.prevent="handleLogin" class="login-form">
        <div class="field">
          <label for="email">Email</label>
          <input
            id="email"
            v-model="email"
            type="email"
            placeholder="Enter your email"
            required
            :disabled="supplierAuth.loading"
            autocomplete="email"
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
            :disabled="supplierAuth.loading"
            autocomplete="current-password"
          />
        </div>

        <div v-if="supplierAuth.error" class="error">
          {{ supplierAuth.error }}
        </div>

        <button type="submit" :disabled="supplierAuth.loading" class="login-btn">
          {{ supplierAuth.loading ? 'Signing in...' : 'Sign In' }}
        </button>
      </form>

      <div class="help-text">
        <p>Contact your account manager for access credentials</p>
        <router-link to="/login" class="internal-link">
          Internal Employee Login
        </router-link>
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
  background: linear-gradient(135deg, #f0f4f8 0%, #e2e8f0 100%);
}

.login-card {
  background: #fff;
  padding: 2.5rem;
  border-radius: 12px;
  width: 100%;
  max-width: 400px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);
}

h1 {
  margin: 0;
  color: #1e40af;
  font-size: 1.75rem;
  text-align: center;
}

.subtitle {
  color: #64748b;
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
  color: #475569;
  font-size: 13px;
  font-weight: 500;
}

input {
  padding: 12px 14px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

input:focus {
  outline: none;
  border-color: #1e40af;
  box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1);
}

input:disabled {
  background: #f1f5f9;
}

.error {
  color: #dc2626;
  background: #fef2f2;
  border: 1px solid #fecaca;
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
}

.login-btn {
  padding: 12px;
  background: #1e40af;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 0.5rem;
  transition: background 0.2s;
}

.login-btn:hover:not(:disabled) {
  background: #1e3a8a;
}

.login-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.help-text {
  margin-top: 2rem;
  text-align: center;
  padding-top: 1.5rem;
  border-top: 1px solid #e2e8f0;
}

.help-text p {
  color: #94a3b8;
  font-size: 12px;
  margin: 0 0 0.75rem;
}

.internal-link {
  color: #1e40af;
  font-size: 13px;
  text-decoration: none;
}

.internal-link:hover {
  text-decoration: underline;
}
</style>
