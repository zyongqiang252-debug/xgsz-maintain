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
.merged-tabs { margin-top: -6px; }
.merged-tabs :deep(.page) { padding: 0; }
.merged-tabs :deep(.page-header) { margin-top: 4px; }
</style>
