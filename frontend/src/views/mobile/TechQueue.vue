<template>
  <div class="tech-queue">
    <!-- 状态切换：与 PC 状态机、后端分 tab 对齐 -->
    <div class="status-bar">
      <span
        v-for="tab in tabs"
        :key="tab.key"
        class="status-tab"
        :class="{ active: activeTab === tab.key }"
        @click="switchTab(tab.key)"
      >{{ tab.label }} ({{ tab.count }})</span>
    </div>

    <!-- 工单列表 -->
    <div class="order-list" v-if="list.length">
      <div
        v-for="wo in list"
        :key="wo.id"
        class="order-card"
        @click="$router.push(`/m/detail/${wo.id}`)"
      >
        <div class="card-header">
          <span class="card-no">{{ wo.work_order_no }}</span>
          <span class="card-status">{{ statusLabel(wo.status) }}</span>
        </div>
        <div class="card-body">{{ wo.fault_description }}</div>
        <div class="card-footer">
          <span class="card-device" v-if="wo.device_code">{{ wo.device_name || wo.device_code }}</span>
          <span class="card-location" v-if="wo.location">{{ wo.location }}</span>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <div class="empty-icon">+</div>
      <div class="empty-text">{{ activeTab === 'pool' ? '工单池暂时没有待领取的工单' : '暂无工单' }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '../../api'

const activeTab = ref('pending')
// 覆盖 PC 状态机全部相关状态：待接单 / 处理中 / 待归档 / 已完成 / 工单池
const tabs = ref([
  { key: 'pending', label: '待接单', count: 0 },
  { key: 'processing', label: '处理中', count: 0 },
  { key: 'archiving', label: '待归档', count: 0 },
  { key: 'completed', label: '已完成', count: 0 },
  { key: 'pool', label: '工单池', count: 0 },
])
const list = ref([])

const STATUS_LABEL = {
  DRAFT: '草稿', SUBMITTED: '待派工', ASSIGNED: '待接单', ACCEPTED: '已接单',
  ARRIVED: '已到场', INSPECTING: '检查中', IN_PROGRESS: '维修中',
  ARCHIVING: '待归档', ARCHIVED: '已归档', COMPLETED: '已完成', REJECTED: '已退回',
}
const statusLabel = (s) => STATUS_LABEL[s] || s

const switchTab = (key) => {
  activeTab.value = key
  fetchData()
}

const fetchData = async () => {
  try {
    const res = await request.get('/m/v1/queue', {
      params: { tab: activeTab.value, page_size: 50 },
    })
    list.value = res.items || []
    const counts = res.counts || {}
    tabs.value.forEach((t) => { t.count = counts[t.key] || 0 })
  } catch { /* handled */ }
}

onMounted(fetchData)
</script>

<style scoped>
.tech-queue { padding: 16px; }

.status-bar { display: flex; margin-bottom: 16px; background: #fff; border-radius: 8px; overflow-x: auto; scrollbar-width: none; }
.status-bar::-webkit-scrollbar { display: none; }
.status-tab {
  flex: 1 1 0; min-width: 0; text-align: center; padding: 11px 2px; font-size: 12px;
  color: #86909C; cursor: pointer; border-bottom: 2px solid transparent; white-space: nowrap;
}
.status-tab.active { color: #0FC6C2; border-bottom-color: #0FC6C2; font-weight: 500; }

.order-list { display: flex; flex-direction: column; gap: 12px; }
.order-card {
  background: #fff; border-radius: 10px; padding: 14px; cursor: pointer;
  border-left: 3px solid #D9D9D9; transition: box-shadow .2s;
}
.order-card:active { box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.card-no { font-size: 14px; font-weight: 600; color: #1D2129; font-family: monospace; }
.card-status { font-size: 12px; color: #0FC6C2; background: #E8FFFE; padding: 2px 8px; border-radius: 10px; }
.card-body { font-size: 14px; color: #4E5969; line-height: 1.45; margin-bottom: 8px; }
.card-footer { display: flex; gap: 12px; font-size: 12px; color: #86909C; }

.empty-state { text-align: center; padding: 60px 0; color: #86909C; }
.empty-icon { font-size: 36px; margin-bottom: 8px; }
.empty-text { font-size: 14px; }
</style>
