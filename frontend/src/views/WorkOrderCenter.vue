<template>
  <div class="merged-page">
    <el-tabs v-model="tab" class="merged-tabs" @tab-change="onTabChange">
      <el-tab-pane label="全部工单" name="list" lazy>
        <component :is="WorkOrders" />
      </el-tab-pane>
      <el-tab-pane v-if="canSupervise" label="进度看板" name="progress" lazy>
        <component :is="Progress" />
      </el-tab-pane>
      <el-tab-pane v-if="canSupervise || isTechnician" label="历史导入" name="import" lazy>
        <component :is="ImportWorkOrders" />
      </el-tab-pane>
      <el-tab-pane v-if="canSupervise" label="快速派工" name="dispatch" lazy>
        <component :is="Dispatch" />
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
.merged-tabs { margin-top: -10px; }
/* 内嵌页面自带 .page 内边距与标题，合并后去掉，避免双层留白与标题重复 */
.merged-tabs :deep(.page) { padding: 0; }
.merged-tabs :deep(.page-title) { display: none; }
.merged-tabs :deep(.el-tabs__header) { margin-bottom: 10px; border-bottom: 1px solid #F2F3F5; }
/* 操作行：只右对齐，不加底色，避免出现大片空白工具条 */
.merged-tabs :deep(.page-header) {
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  padding: 0;
  min-height: 32px;
}
</style>
