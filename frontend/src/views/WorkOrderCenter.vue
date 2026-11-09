<template>
  <div class="merged-page">
    <el-tabs v-model="tab" class="merged-tabs" @tab-change="onTabChange">
      <!-- 管理者：全部工单 -->
      <el-tab-pane v-if="canSupervise" label="全部工单" name="list" lazy>
        <component :is="WorkOrders" :key="'wo-list-' + refreshKey" />
      </el-tab-pane>
      <!-- 技术员：我的工单（默认）+ 工单池 -->
      <el-tab-pane v-if="isTechnician" label="我的工单" name="mine" lazy>
        <component :is="WorkOrders" default-mine="all" :key="'wo-mine-' + refreshKey" />
      </el-tab-pane>
      <el-tab-pane v-if="isTechnician" label="工单池" name="pool" lazy>
        <component :is="WorkOrders" pool-mode="1" :key="'wo-pool-' + refreshKey" />
      </el-tab-pane>
      <el-tab-pane v-if="canSupervise" label="进度看板" name="progress" lazy>
        <component :is="Progress" :key="'progress-' + refreshKey" />
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

// 角色可见页签：管理者看全部，技术员看自己的 + 工单池
const VALID = canSupervise
  ? ['list', 'progress', 'import', 'dispatch']
  : ['mine', 'pool', 'import']
const DEFAULT_TAB = canSupervise ? 'list' : 'mine'
const tab = ref(VALID.includes(String(route.query.tab)) ? String(route.query.tab) : DEFAULT_TAB)

const refreshKey = ref(0)

const onTabChange = (name) => {
  // 切换页签时刷新数据，避免「全部工单」与「我的工单」看到旧状态
  refreshKey.value += 1
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
