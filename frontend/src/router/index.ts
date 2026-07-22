import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useSupplierAuthStore } from '../stores/supplierAuth'

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

    // === Supplier Portal Routes ===
    {
      path: '/supplier-login',
      name: 'supplier-login',
      component: () => import('../views/supplier/SupplierLoginView.vue'),
      meta: { requiresAuth: false, supplierRoute: true }
    },
    {
      path: '/supplier/portal',
      name: 'supplier-portal',
      component: () => import('../views/supplier/SupplierPortalView.vue'),
      meta: { requiresSupplierAuth: true }
    },
    {
      path: '/supplier/item/:itemNumber',
      name: 'supplier-item',
      component: () => import('../views/supplier/SupplierItemView.vue'),
      meta: { requiresSupplierAuth: true }
    },

    // === Admin Supplier Management ===
    {
      path: '/admin/suppliers',
      name: 'admin-suppliers',
      component: () => import('../views/admin/AdminSuppliersView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
    {
      path: '/admin/suppliers/:id',
      name: 'admin-supplier-detail',
      component: () => import('../views/admin/AdminSupplierDetailView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true }
    },
  ]
})

// Navigation guard
router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  const supplierAuthStore = useSupplierAuthStore()

  // Initialize both auth stores
  await authStore.initialize()
  supplierAuthStore.initialize()

  // Supplier routes - check supplier auth
  if (to.meta.requiresSupplierAuth) {
    if (!supplierAuthStore.isAuthenticated) {
      return { name: 'supplier-login', query: { redirect: to.fullPath } }
    }
    return // Allow access
  }

  // Redirect authenticated supplier away from supplier login
  if (to.name === 'supplier-login' && supplierAuthStore.isAuthenticated) {
    return { name: 'supplier-portal' }
  }

  // Admin routes - check internal auth + admin role
  if (to.meta.requiresAdmin) {
    if (!authStore.isAuthenticated) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
    if (!authStore.isAdmin) {
      return { name: 'home' }
    }
    return // Allow access
  }

  // Regular internal routes - check internal auth
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Redirect authenticated internal user away from login
  if (to.name === 'login' && authStore.isAuthenticated) {
    return { name: 'home' }
  }
})

export default router
