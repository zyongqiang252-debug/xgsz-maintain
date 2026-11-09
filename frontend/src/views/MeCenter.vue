<template>
  <div class="merged-page">
    <el-tabs v-model="tab" class="merged-tabs" @tab-change="onTabChange">
      <el-tab-pane label="我的请假" name="leave" lazy>
        <component :is="LeaveRequests" />
      </el-tab-pane>
      <el-tab-pane label="通知中心" name="notifications" lazy>
        <component :is="Notifications" />
      </el-tab-pane>
      <el-tab-pane label="帮助中心" name="help" lazy>
        <component :is="Help" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const LeaveRequests = defineAsyncComponent(() => import('./LeaveRequests.vue'))
const Notifications = defineAsyncComponent(() => import('./Notifications.vue'))
const Help = defineAsyncComponent(() => import('./Help.vue'))

const VALID = ['leave', 'notifications', 'help']
const tab = ref(VALID.includes(route.query.tab) ? String(route.query.tab) : 'leave')

const onTabChange = (name) => {
  router.replace({ path: '/me', query: { tab: name } })
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
