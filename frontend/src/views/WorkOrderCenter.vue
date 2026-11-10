<template>
  <div class="merged-page">
    <component v-if="tab === 'list'" :is="WorkOrders" :key="'wo-list-' + refreshKey" />
    <component v-else-if="tab === 'mine'" :is="WorkOrders" default-mine="all" :key="'wo-mine-' + refreshKey" />
    <component v-else-if="tab === 'pool'" :is="WorkOrders" pool-mode="1" :key="'wo-pool-' + refreshKey" />
    <component v-else-if="tab === 'progress'" :is="Progress" :key="'progress-' + refreshKey" />
    <component v-else-if="tab === 'import'" :is="ImportWorkOrders" />
  </div>
</template>

<script setup>
import { ref, watch, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const WorkOrders = defineAsyncComponent(() => import('./WorkOrders.vue'))
const Progress = defineAsyncComponent(() => import('./SupervisorProgress.vue'))
const ImportWorkOrders = defineAsyncComponent(() => import('./ImportWorkOrders.vue'))

const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const isAdmin = currentUser.role === 'ADMIN'
const canSupervise = currentUser.role === 'SUPERVISOR' || isAdmin
const isTechnician = currentUser.role === 'TECHNICIAN'

// 角色可见页面：管理者 3 项，技术员 3 项
const VALID = canSupervise
  ? ['list', 'progress', 'import']
  : ['mine', 'pool', 'import']
const DEFAULT_TAB = canSupervise ? 'list' : 'mine'
const initial = String(route.query.tab || '')
const tab = ref(VALID.includes(initial) ? initial : DEFAULT_TAB)
const refreshKey = ref(0)
if (initial === 'dispatch') router.replace({ path: '/orders', query: { tab: DEFAULT_TAB } })

// 左侧菜单切换时只变 query，这里同步并刷新数据
watch(() => route.query.tab, (v) => {
  const t = String(v || '')
  // 快速派工已下线，旧链接回到全部工单
  if (t === 'dispatch') {
    router.replace({ path: '/orders', query: { tab: DEFAULT_TAB } })
    return
  }
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
