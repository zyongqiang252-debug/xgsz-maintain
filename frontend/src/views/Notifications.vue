<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">通知中心</h2>
      <div class="header-actions">
        <el-switch v-model="unreadOnly" active-text="只看未读" @change="handleSearch" style="margin-right: 12px" />
        <el-button :disabled="unreadCount === 0" @click="handleReadAll">全部标为已读</el-button>
      </div>
    </div>

    <el-card shadow="never" class="msg-card" v-loading="loading">
      <div v-if="list.length === 0 && !loading" class="empty-wrap">
        <el-empty description="暂无通知" />
      </div>

      <div v-else class="msg-list">
        <div
          v-for="item in list"
          :key="item.id"
          class="msg-item"
          :class="{ unread: !item.is_read }"
          @click="handleOpen(item)"
        >
          <div class="msg-icon" :class="'type-' + (item.type || 'SYSTEM')">
            <el-icon :size="18"><component :is="iconOf(item.type)" /></el-icon>
          </div>
          <div class="msg-body">
            <div class="msg-top">
              <span class="msg-title">{{ item.title }}</span>
              <span v-if="!item.is_read" class="dot"></span>
              <span class="msg-time">{{ item.created_at }}</span>
            </div>
            <div class="msg-content">{{ item.content }}</div>
            <div class="msg-foot" v-if="item.work_order_id">
              关联工单 #{{ item.work_order_id }} · 点击查看详情
            </div>
          </div>
        </div>
      </div>

      <div class="pager" v-if="total > pageSize">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchData"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Document, Warning, Box, ChatDotRound } from '@element-plus/icons-vue'
import request from '../api'

const router = useRouter()
const list = ref([])
const loading = ref(false)
const unreadOnly = ref(false)
const unreadCount = ref(0)
const page = ref(1)
const pageSize = 20
const total = ref(0)

const iconOf = (type) => {
  const t = (type || '').toUpperCase()
  if (t.includes('WORK_ORDER') || t.includes('DISPATCH')) return Document
  if (t.includes('ALERT') || t.includes('TIMEOUT') || t.includes('WARN')) return Warning
  if (t.includes('STOCK') || t.includes('PART')) return Box
  if (t.includes('KNOWLEDGE')) return ChatDotRound
  return Bell
}

const fetchUnreadCount = async () => {
  try {
    const res = await request.get('/notifications/unread-count')
    unreadCount.value = res.count || 0
  } catch (e) { /* 静默 */ }
}

const fetchData = async () => {
  loading.value = true
  try {
    const res = await request.get('/notifications/', {
      params: {
          page: page.value, page_size: pageSize, unread_only: unreadOnly.value,
        },
    })
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('通知加载失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  page.value = 1
  fetchData()
}

const handleOpen = async (item) => {
  if (!item.is_read) {
    try {
      await request.post(`/notifications/${item.id}/read`)
      item.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch (e) { /* 静默 */ }
  }
  if (item.work_order_id) {
    router.push(`/work-orders/${item.work_order_id}`)
  }
}

const handleReadAll = async () => {
  try {
    await request.post('/notifications/read-all')
    ElMessage.success('已全部标为已读')
    unreadCount.value = 0
    fetchData()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

const onLiveNotification = () => {
  fetchData()
  fetchUnreadCount()
}

onMounted(() => {
  fetchData()
  fetchUnreadCount()
  window.addEventListener('xgsz:notification', onLiveNotification)
})

onUnmounted(() => {
  window.removeEventListener('xgsz:notification', onLiveNotification)
})
</script>

<style scoped>
.page { padding: 4px 0; display: flex; flex-direction: column; min-height: calc(100vh - 150px); }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; flex-shrink: 0; }
.page-title { margin: 0; font-size: 20px; font-weight: 600; color: #1D2129; }
.header-actions { display: flex; align-items: center; }
.msg-card { border-radius: 8px; flex: 1; display: flex; flex-direction: column; min-height: 0; }
.msg-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.empty-wrap { flex: 1; display: flex; align-items: center; justify-content: center; padding: 40px 0; }
.msg-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; min-height: 0; }
.msg-item {
  display: flex; gap: 12px; padding: 14px 16px; border-radius: 8px; cursor: pointer; flex-shrink: 0;
  border-bottom: 1px solid #F2F3F5; transition: background .15s;
}
.msg-item:last-child { border-bottom: none; }
.msg-item:hover { background: #F7F8FA; }
.msg-item.unread { background: #F2FBFB; }
.msg-item.unread:hover { background: #EAF8F8; }
.msg-icon {
  width: 34px; height: 34px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: #E8F9F9; color: #0FC6C2;
}
.msg-icon.type-ALERT, .msg-icon.type-WARNING { background: #FFF3E8; color: #FF7D00; }
.msg-icon.type-STOCK { background: #EEF3FF; color: #4080FF; }
.msg-icon.type-KNOWLEDGE { background: #F5F0FF; color: #7B61FF; }
.msg-body { flex: 1; min-width: 0; }
.msg-top { display: flex; align-items: center; gap: 6px; }
.msg-title { font-size: 14px; font-weight: 600; color: #1D2129; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: #F53F3F; }
.msg-time { margin-left: auto; font-size: 12px; color: #86909C; }
.msg-content { margin-top: 4px; font-size: 13px; color: #4E5969; line-height: 1.6; }
.msg-foot { margin-top: 4px; font-size: 12px; color: #0FC6C2; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; flex-shrink: 0; }
</style>
