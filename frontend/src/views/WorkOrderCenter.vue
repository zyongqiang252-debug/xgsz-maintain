<template>
  <div class="merged-page">
    <el-tabs v-model="tab" class="merged-tabs" @tab-change="onTabChange">
      <el-tab-pane label="全部工单" name="list" lazy>
        <component :is="WorkOrders" />
      </el-tab-pane>
      <el-tab-pane v-if="canSupervise" label="派工" name="dispatch" lazy>
        <component :is="Dispatch" />
      </el-tab-pane>
      <el-tab-pane v-if="canSupervise" label="进度看板" name="progress" lazy>
        <component :is="Progress" />
      </el-tab-pane>
      <el-tab-pane v-if="canSupervise || isTechnician" label="历史导入" name="import" lazy>
        <component :is="ImportWorkOrders" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

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

const VALID = ['list', 'dispatch', 'progress', 'import']
const tab = ref(VALID.includes(route.query.tab) ? String(route.query.tab) : 'list')

const onTabChange = (name) => {
  router.replace({ path: '/orders', query: { tab: name } })
}
</script>

<style scoped>
.merged-page { padding: 0; }
.merged-tabs { margin-top: -6px; }
/* 内嵌页面自带 .page 内边距，合并后去掉，避免双层留白 */
.merged-tabs :deep(.page) { padding: 0; }
.merged-tabs :deep(.page-header) { margin-top: 4px; }
</style>
