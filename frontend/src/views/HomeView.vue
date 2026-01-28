<script setup lang="ts">
import { useAuthStore } from '../stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const pdmTools = [
  {
    title: 'PDM Browser',
    icon: 'pi pi-folder-open',
    description: 'Browse and search all items in your PDM system with detailed views of files, BOMs, and lifecycle history.',
    route: '/pdm-browser',
    features: [
      'Search & filter items',
      'View files, BOMs, where-used',
      'Navigate assembly structures',
      'Lifecycle history tracking'
    ]
  },
  {
    title: 'Part Number Generator',
    icon: 'pi pi-hashtag',
    description: 'Generate new available part numbers for each prefix. Click to copy for use in CAD.',
    route: '/part-numbers',
    features: [
      'Shows next available numbers',
      'All prefixes (CS, XX, WM, etc.)',
      'Click to copy to clipboard',
      'Real-time database sync'
    ]
  },
  {
    title: 'Projects',
    icon: 'pi pi-briefcase',
    description: 'View and manage projects and their associated items.',
    route: '/projects',
    features: [
      'Project overview',
      'Item grouping',
      'Status tracking'
    ]
  },
  {
    title: 'Work Queue',
    icon: 'pi pi-list-check',
    description: 'Monitor background tasks like DXF generation and file syncing.',
    route: '/tasks',
    features: [
      'Task status monitoring',
      'Error tracking',
      'Processing history'
    ]
  }
]

const mrpTools = [
  {
    title: 'MRP Dashboard',
    icon: 'pi pi-chart-bar',
    description: 'Overview of production orders, work packets, and shop floor status.',
    route: '/mrp/dashboard',
    features: [
      'Production order tracking',
      'Work packet status',
      'Shop floor overview',
      'Real-time updates'
    ]
  },
  {
    title: 'Routing Editor',
    icon: 'pi pi-sitemap',
    description: 'Define and manage production routings for parts and assemblies.',
    route: '/mrp/routing',
    features: [
      'Create/edit routings',
      'Workstation assignment',
      'Operation sequencing'
    ]
  },
  {
    title: 'Shop Terminal',
    icon: 'pi pi-desktop',
    description: 'Shop floor interface for operators to view work packets and update job status.',
    route: '/mrp/shop',
    features: [
      'View assigned work',
      'Update job status',
      'Time tracking'
    ]
  }
]

function navigateTo(route: string) {
  router.push(route)
}

async function logout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="home-container">
    <header class="home-header">
      <div class="header-content">
        <h1>PDM Tools</h1>
        <p class="subtitle">Product Data Management & Manufacturing Resource Planning</p>
      </div>
      <div class="user-info" v-if="authStore.user">
        <span class="user-name">{{ authStore.user.username }}</span>
        <span class="user-role">{{ authStore.user.role }}</span>
        <button class="logout-btn" @click="logout">
          <i class="pi pi-sign-out"></i>
          Logout
        </button>
      </div>
    </header>

    <main class="home-main">
      <section class="tools-section">
        <h2>PDM Tools</h2>
        <div class="tools-grid">
          <div
            v-for="tool in pdmTools"
            :key="tool.title"
            class="tool-card"
            @click="navigateTo(tool.route)"
          >
            <div class="tool-icon">
              <i :class="tool.icon"></i>
            </div>
            <h3>{{ tool.title }}</h3>
            <p class="tool-description">{{ tool.description }}</p>
            <ul class="tool-features">
              <li v-for="feature in tool.features" :key="feature">{{ feature }}</li>
            </ul>
          </div>
        </div>
      </section>

      <section class="tools-section mrp-section">
        <h2>MRP Tools</h2>
        <div class="tools-grid">
          <div
            v-for="tool in mrpTools"
            :key="tool.title"
            class="tool-card"
            @click="navigateTo(tool.route)"
          >
            <div class="tool-icon">
              <i :class="tool.icon"></i>
            </div>
            <h3>{{ tool.title }}</h3>
            <p class="tool-description">{{ tool.description }}</p>
            <ul class="tool-features">
              <li v-for="feature in tool.features" :key="feature">{{ feature }}</li>
            </ul>
          </div>
        </div>
      </section>
    </main>

    <footer class="home-footer">
      <p>Connected to Supabase | Vue 3 + FastAPI</p>
    </footer>
  </div>
</template>

<style scoped>
.home-container {
  min-height: 100vh;
  background: #f5f5f5;
  color: #333;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.home-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 2rem;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.header-content h1 {
  font-size: 1.75rem;
  margin: 0;
  color: #333;
}

.subtitle {
  margin: 0.25rem 0 0 0;
  color: #666;
  font-size: 0.9rem;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.user-name {
  font-weight: 600;
  color: #333;
}

.user-role {
  background: #2563eb;
  color: #fff;
  padding: 0.25rem 0.75rem;
  border-radius: 1rem;
  font-size: 0.75rem;
  text-transform: uppercase;
}

.logout-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #fff;
  border: 1px solid #ccc;
  color: #666;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 0.85rem;
}

.logout-btn:hover {
  background: #f5f5f5;
  border-color: #999;
}

.home-main {
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.tools-section {
  margin-bottom: 2.5rem;
}

.tools-section h2 {
  font-size: 1.25rem;
  margin-bottom: 1.25rem;
  color: #333;
  border-bottom: 2px solid #2563eb;
  padding-bottom: 0.5rem;
  display: inline-block;
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.25rem;
}

.tool-card {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 0.75rem;
  padding: 1.25rem;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
}

.tool-card:hover {
  transform: translateY(-2px);
  border-color: #2563eb;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.15);
}

.tool-card.coming-soon {
  opacity: 0.6;
  cursor: not-allowed;
}

.tool-card.coming-soon:hover {
  transform: none;
  border-color: #e0e0e0;
  box-shadow: none;
}

.tool-icon {
  width: 50px;
  height: 50px;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  border-radius: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
}

.tool-icon i {
  font-size: 1.5rem;
  color: #fff;
}

.tool-card h3 {
  font-size: 1.1rem;
  margin: 0 0 0.5rem 0;
  color: #333;
}

.tool-description {
  color: #666;
  font-size: 0.85rem;
  line-height: 1.5;
  margin-bottom: 0.75rem;
}

.tool-features {
  list-style: none;
  padding: 0;
  margin: 0;
}

.tool-features li {
  color: #888;
  font-size: 0.8rem;
  padding: 0.2rem 0;
  padding-left: 1rem;
  position: relative;
}

.tool-features li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 5px;
  height: 5px;
  background: #2563eb;
  border-radius: 50%;
}

.badge {
  position: absolute;
  top: 1rem;
  right: 1rem;
  padding: 0.2rem 0.6rem;
  border-radius: 1rem;
  font-size: 0.65rem;
  text-transform: uppercase;
  font-weight: 600;
}

.coming-soon-badge {
  background: #f0f7ff;
  color: #2563eb;
  border: 1px solid #2563eb;
}

.mrp-section h2 {
  border-color: #059669;
}

.mrp-section .tool-icon {
  background: linear-gradient(135deg, #059669, #047857);
}

.mrp-section .tool-features li::before {
  background: #059669;
}

.home-footer {
  text-align: center;
  padding: 1.5rem;
  color: #888;
  font-size: 0.8rem;
  border-top: 1px solid #e0e0e0;
  background: #fff;
}
</style>
