<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiCall } from '../services/supabase'
import type { Project } from '../types'

const projects = ref<Project[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  loading.value = true
  try {
    projects.value = await apiCall<Project[]>('/projects')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load projects'
  } finally {
    loading.value = false
  }
})

function getStatusClass(status: string) {
  return {
    'status-active': status === 'active',
    'status-completed': status === 'completed',
    'status-archived': status === 'archived',
  }
}
</script>

<template>
  <div class="projects-view">
    <header class="page-header">
      <h1>Projects</h1>
    </header>

    <div v-if="loading" class="loading">Loading projects...</div>
    <div v-else-if="error" class="error">{{ error }}</div>

    <div v-else class="projects-grid">
      <div v-for="project in projects" :key="project.id" class="project-card">
        <div class="project-header">
          <h2>{{ project.name }}</h2>
          <span class="status-badge" :class="getStatusClass(project.status)">
            {{ project.status }}
          </span>
        </div>
        <p class="project-desc">{{ project.description || 'No description' }}</p>
        <div class="project-meta">
          Created {{ new Date(project.created_at).toLocaleDateString() }}
        </div>
      </div>

      <div v-if="!projects.length" class="empty">No projects found</div>
    </div>
  </div>
</template>

<style scoped>
.projects-view {
  padding: 1rem;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 1.5rem;
}

.page-header h1 {
  color: #fff;
  margin: 0;
}

.loading, .error, .empty {
  padding: 2rem;
  text-align: center;
  color: #888;
}

.error {
  color: #ff6b6b;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1rem;
}

.project-card {
  background: #16213e;
  border-radius: 8px;
  padding: 1.5rem;
}

.project-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 0.75rem;
}

.project-header h2 {
  margin: 0;
  color: #fff;
  font-size: 1.25rem;
}

.status-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
}

.status-active {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.status-completed {
  background: rgba(100, 181, 246, 0.2);
  color: #64b5f6;
}

.status-archived {
  background: rgba(158, 158, 158, 0.2);
  color: #9e9e9e;
}

.project-desc {
  color: #888;
  margin: 0 0 1rem;
}

.project-meta {
  color: #666;
  font-size: 0.85rem;
}
</style>
