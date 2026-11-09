<template>
  <div class="mobile-app">
    <!-- 顶部状态栏 -->
    <div class="mobile-header">
      <span class="header-back" v-if="showBack" @click="$router.back()">
        <el-icon><ArrowLeft /></el-icon>
      </span>
      <span class="header-title">{{ title }}</span>
      <span class="header-user" @click="showUserMenu = !showUserMenu">
        <span class="header-avatar">{{ (user.name || '用')[0] }}</span>
        {{ user.name || '用户' }}
      </span>
    </div>

    <!-- 主内容 -->
    <div class="mobile-body">
      <router-view />
    </div>

    <!-- 底部 Tab -->
    <div class="mobile-tabs" v-if="showTabs">
      <div class="tab-item" :class="{ active: route.path.startsWith('/m/report') }" @click="$router.push('/m/report')">
        <el-icon class="tab-icon"><EditPen /></el-icon>
        <span class="tab-label">故障上报</span>
      </div>
      <div class="tab-item" :class="{ active: route.path.startsWith('/m/queue') }" @click="$router.push('/m/queue')">
        <el-icon class="tab-icon"><Tickets /></el-icon>
        <span class="tab-label">我的工单</span>
      </div>
      <div class="tab-item" :class="{ active: route.path.startsWith('/m/leave') }" @click="$router.push('/m/leave')">
        <el-icon class="tab-icon"><Calendar /></el-icon>
        <span class="tab-label">请假</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, EditPen, Tickets, Calendar } from '@element-plus/icons-vue'

const route = useRoute()
const showBack = computed(() => !['/m/report', '/m/queue', '/m/leave'].includes(route.path))
const showTabs = computed(() => ['/m/report', '/m/queue', '/m/leave'].includes(route.path))
const title = computed(() => route.meta?.title || '维修助手')

const user = { name: '张工' } // 后续从钉钉免登获取
const showUserMenu = ref(false)
</script>

<style scoped>
.mobile-app {
  max-width: 430px;
  margin: 0 auto;
  min-height: 100vh;
  background: #F4F6F9;
  display: flex;
  flex-direction: column;
  position: relative;
  color: #1D2129;
}

/* 顶部：品牌青色渐变 */
.mobile-header {
  height: 52px;
  background: linear-gradient(135deg, #14C8C4 0%, #0AA9A5 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  font-size: 16px;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 20;
  box-shadow: 0 1px 6px rgba(10, 169, 165, .25);
}
.header-back { cursor: pointer; display: flex; align-items: center; font-size: 18px; }
.header-title { font-weight: 600; letter-spacing: .3px; }
.header-user {
  cursor: pointer; font-size: 13px;
  display: flex; align-items: center; gap: 6px;
  background: rgba(255,255,255,.16);
  padding: 3px 10px 3px 4px;
  border-radius: 14px;
}
.header-avatar {
  width: 20px; height: 20px; border-radius: 50%;
  background: rgba(255,255,255,.9); color: #0AA9A5;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700;
}

.mobile-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 12px 76px;
  -webkit-overflow-scrolling: touch;
}

/* 底部 Tab */
.mobile-tabs {
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 430px;
  height: calc(58px + env(safe-area-inset-bottom, 0px));
  padding-bottom: env(safe-area-inset-bottom, 0px);
  background: rgba(255,255,255,.96);
  backdrop-filter: blur(8px);
  border-top: 1px solid #EDEFF3;
  display: flex;
  z-index: 100;
  box-shadow: 0 -2px 10px rgba(16,24,40,.04);
}
.tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  cursor: pointer;
  color: #8A929E;
  transition: color .18s;
}
.tab-item.active { color: #0FC6C2; }
.tab-item.active .tab-icon { transform: translateY(-1px); }
.tab-icon { font-size: 21px; transition: transform .18s; }
.tab-label { font-size: 11px; }

/* 移动端卡片统一 */
.mobile-app :deep(.el-card) {
  border-radius: 12px !important;
  border-color: #EDEFF3 !important;
  box-shadow: 0 1px 3px rgba(16,24,40,.05) !important;
}
.mobile-app :deep(.el-card__body) { padding: 14px !important; }
.mobile-app :deep(.el-button) { border-radius: 10px; }
.mobile-app :deep(.el-input__wrapper),
.mobile-app :deep(.el-textarea__inner),
.mobile-app :deep(.el-select__wrapper) { border-radius: 10px; }
.mobile-app :deep(.el-form-item__label) { font-size: 13px; color: #4E5969; }
</style>
