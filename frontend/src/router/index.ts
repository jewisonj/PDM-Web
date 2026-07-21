import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      name: 'home',
      component: () => import('../views/HomeView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/pdm-browser',
      name: 'pdm-browser',
      component: () => import('../views/ItemsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/items/:itemNumber',
      name: 'item-detail',
      component: () => import('../views/ItemDetailView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/part-numbers',
      name: 'part-numbers',
      component: () => import('../views/PartNumbersView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/projects',
      name: 'projects',
      component: () => import('../views/ProjectsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/tasks',
      name: 'tasks',
      component: () => import('../views/TasksView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/dashboard',
      name: 'mrp-dashboard',
      component: () => import('../views/MrpDashboardView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/routing',
      name: 'mrp-routing',
      component: () => import('../views/MrpRoutingView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/shop',
      name: 'mrp-shop',
      component: () => import('../views/MrpShopView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/parts',
      name: 'mrp-parts',
      component: () => import('../views/MrpPartLookupView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/tracking',
      name: 'mrp-tracking',
      component: () => import('../views/MrpProjectTrackingView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/tracker/:projectCode',
      name: 'mrp-build-tracker',
      component: () => import('../views/MrpBuildTrackerView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/book/:projectCode',
      name: 'mrp-build-book',
      component: () => import('../views/MrpBuildBookView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/design-books',
      name: 'mrp-design-books',
      component: () => import('../views/DesignBooksIndexView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/design-book/:bookCode',
      name: 'mrp-design-book',
      component: () => import('../views/MasterDesignBookView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/materials',
      name: 'mrp-materials',
      component: () => import('../views/MrpRawMaterialsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/purchased-parts',
      name: 'mrp-purchased-parts',
      component: () => import('../views/PurchasedPartsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/settings',
      name: 'mrp-settings',
      component: () => import('../views/MrpCostSettingsView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/design-book-images',
      name: 'mrp-design-book-images',
      component: () => import('../views/MrpDesignBookImagesView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/design-book/:bookCode/images',
      name: 'mrp-design-book-images-for-book',
      component: () => import('../views/MrpDesignBookImagesView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/cost-report',
      name: 'mrp-cost-report',
      component: () => import('../views/MrpCostReportView.vue'),
      meta: { requiresAuth: true }
    },
    {
      path: '/mrp/assistant',
      name: 'mrp-assistant',
      component: () => import('../views/MrpAssistantView.vue'),
      meta: { requiresAuth: true }
    },
    // Print Lookup removed - using Part Lookup instead
    // {
    //   path: '/mrp/print-lookup',
    //   name: 'mrp-print-lookup',
    //   component: () => import('../views/MrpPrintLookupView.vue'),
    //   meta: { requiresAuth: true }
    // },
  ]
})

// Navigation guard
router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  // Always wait for auth to initialize before making decisions
  await authStore.initialize()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'login' && authStore.isAuthenticated) {
    return { name: 'home' }
  }
})

export default router
