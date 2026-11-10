<template>
  <div class="merged-page">
    <component v-if="tab === 'users'" :is="Users" />
    <component v-else-if="tab === 'customers'" :is="Customers" />
    <component v-else-if="tab === 'settings'" :is="SystemSettings" />
  </div>
</template>

<script setup>
import { ref, watch, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const Users = defineAsyncComponent(() => import('./Users.vue'))
const Customers = defineAsyncComponent(() => import('./Customers.vue'))
const SystemSettings = defineAsyncComponent(() => import('./SystemSettings.vue'))

const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const isAdmin = currentUser.role === 'ADMIN'

const VALID = isAdmin ? ['users', 'customers', 'settings'] : ['users']
const initial = String(route.query.tab || 'users')
const tab = ref(VALID.includes(initial) ? initial : 'users')

watch(() => route.query.tab, (v) => {
  const t = String(v || 'users')
  if (VALID.includes(t)) tab.value = t
  else {
    tab.value = 'users'
    router.replace({ path: '/sys', query: { tab: 'users' } })
  }
})
</script>

<style scoped>
.merged-page { padding: 0; }
</style>
