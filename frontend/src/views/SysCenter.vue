<template>
  <div class="merged-page">
    <el-tabs v-model="tab" class="merged-tabs" @tab-change="onTabChange">
      <el-tab-pane label="用户管理" name="users" lazy>
        <component :is="Users" />
      </el-tab-pane>
      <el-tab-pane v-if="isAdmin" label="系统设置" name="settings" lazy>
        <component :is="SystemSettings" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const Users = defineAsyncComponent(() => import('./Users.vue'))
const SystemSettings = defineAsyncComponent(() => import('./SystemSettings.vue'))

const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const isAdmin = currentUser.role === 'ADMIN'

const VALID = ['users', 'settings']
const tab = ref(VALID.includes(route.query.tab) ? String(route.query.tab) : 'users')

const onTabChange = (name) => {
  router.replace({ path: '/sys', query: { tab: name } })
}
</script>

<style scoped>
.merged-page { padding: 0; }
.merged-tabs { margin-top: -6px; }
.merged-tabs :deep(.page) { padding: 0; }
.merged-tabs :deep(.page-header) { margin-top: 4px; }
</style>
