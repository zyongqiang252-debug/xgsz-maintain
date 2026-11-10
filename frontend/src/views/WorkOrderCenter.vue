<template>
  <div class="merged-page">
    <component v-if="tab === 'list'" :is="WorkOrders" :key="'wo-list-' + refreshKey" />
    <component v-else-if="tab === 'mine'" :is="WorkOrders" default-mine="all" :key="'wo-mine-' + refreshKey" />
    <component v-else-if="tab === 'pool'" :is="WorkOrders" pool-mode="1" :key="'wo-pool-' + refreshKey" />
    <component v-else-if="tab === 'progress'" :is="Progress" :key="'progress-' + refreshKey" />
    <component v-else-if="tab === 'import'" :is="ImportWorkOrders" />
    <component v-else-if="tab === 'dispatch'" :is="Dispatch" />
  </div>
</template>

<script setup>
import { ref, watch, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const WorkOrders = defineAsyncComponent(() => import('./WorkOrders.vue'))
const Dispatch = defineAsyncComponent(() => import('./SupervisorDispatch.vue'))
const Progress = defineAsyncComponent(() => import('./SupervisorProgress.vue'))
const ImportWorkOrders = defineAsyncComponent(() => import('./ImportWorkOrders.vue'))

const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const isAdmin = currentUser.role === 'ADMIN'
const canSupervise = currentUser.role === 'SUPERVISOR' || isAdmin
const isTechnician = currentUser.role === 'TECHNICIAN'

// 角色可见页面：管理者 4 项，技术员 3 项
const VALID = canSupervise
  ? ['list', 'progress', 'import', 'dispatch']
  : ['mine', 'pool', 'import']
const DEFAULT_TAB = canSupervise ? 'list' : 'mine'
const initial = String(route.query.tab || '')
const tab = ref(VALID.includes(initial) ? initial : DEFAULT_TAB)
const refreshKey = ref(0)

// 左侧菜单切换时只变 query，这里同步并刷新数据
watch(() => route.query.tab, (v) => {
  const t = String(v || '')
  if (!VALID.includes(t)) {
    tab.value = DEFAULT_TAB
    return
  }
  if (t !== tab.value) {
    tab.value = t
    refreshKey.value += 1
  }
})
</script>

<style scoped>
.merged-page { padding: 0; }
</style>
