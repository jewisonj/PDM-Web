<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiCall } from '../services/supabase'
import type { Task } from '../types'

const tasks = ref<Task[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  await loadTasks()
})

async function loadTasks() {
  loading.value = true
  try {
    tasks.value = await apiCall<Task[]>('/tasks?limit=50')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load tasks'
  } finally {
    loading.value = false
  }
}

function getStatusClass(status: string) {
  return {
    'status-pending': status === 'pending',
    'status-processing': status === 'processing',
    'status-completed': status === 'completed',
    'status-failed': status === 'failed',
  }
}

function formatDate(date: string) {
  return new Date(date).toLocaleString()
}
</script>

<template>
  <div class="tasks-view">
    <header class="page-header">
      <h1>Work Queue</h1>
      <button @click="loadTasks" class="btn-secondary">Refresh</button>
    </header>

    <div v-if="loading" class="loading">Loading tasks...</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <table v-else class="tasks-table">
      <thead>
        <tr>
          <th>Type</th>
          <th>Status</th>
          <th>Created</th>
          <th>Started</th>
          <th>Completed</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="task in tasks" :key="task.id">
          <td>{{ task.task_type }}</td>
          <td>
            <span class="status-badge" :class="getStatusClass(task.status)">
              {{ task.status }}
            </span>
          </td>
          <td>{{ formatDate(task.created_at) }}</td>
          <td>{{ task.started_at ? formatDate(task.started_at) : '-' }}</td>
          <td>{{ task.completed_at ? formatDate(task.completed_at) : '-' }}</td>
          <td class="error-cell">{{ task.error_message || '-' }}</td>
        </tr>
        <tr v-if="!tasks.length">
          <td colspan="6" class="empty">No tasks in queue</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.tasks-view {
  padding: 1rem;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.page-header h1 {
  color: #fff;
  margin: 0;
}

.btn-secondary {
  padding: 0.5rem 1rem;
  background: transparent;
  color: #888;
  border: 1px solid #444;
  border-radius: 4px;
  cursor: pointer;
}

.loading, .error, .empty {
  padding: 2rem;
  text-align: center;
  color: #888;
}

.error {
  color: #ff6b6b;
}

.tasks-table {
  width: 100%;
  border-collapse: collapse;
  background: #16213e;
  border-radius: 8px;
  overflow: hidden;
}

.tasks-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  background: #0f0f1a;
  color: #888;
  font-weight: 500;
  font-size: 0.85rem;
}

.tasks-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #1a1a2e;
  color: #e0e0e0;
}

.status-badge {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
}

.status-pending {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
}

.status-processing {
  background: rgba(100, 181, 246, 0.2);
  color: #64b5f6;
}

.status-completed {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.status-failed {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

.error-cell {
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #f44336;
}

.empty {
  text-align: center;
  color: #666;
}
</style>
