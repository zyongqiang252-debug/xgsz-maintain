<template>
  <div class="m-page">
    <!-- 提交区 -->
    <div class="card">
      <div class="card-title">
        <span>申请请假</span>
        <span class="link" @click="toggleForm">{{ showForm ? '收起' : '填写' }}</span>
      </div>

      <div v-if="showForm" class="form">
        <div class="field">
          <label>请假类型</label>
          <select v-model="form.leave_type">
            <option v-for="t in leaveTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>请假日期</label>
          <input v-model="form.leave_date" type="date" :min="today" @change="handlePreCheck" />
        </div>
        <div class="field">
          <label>班次</label>
          <div class="seg">
            <span v-for="s in shifts" :key="s.value" class="seg-item"
                  :class="{ active: form.leave_shift === s.value }" @click="form.leave_shift = s.value; handlePreCheck()">
              {{ s.label }}
            </span>
          </div>
        </div>
        <div class="field">
          <label>事由</label>
          <textarea v-model="form.leave_reason" rows="2" maxlength="200" placeholder="简要说明请假原因"></textarea>
        </div>

        <!-- 预检提示 -->
        <div v-if="precheck" class="precheck">
          <div v-if="precheck.pending_work_orders?.length" class="warn">
            有 {{ precheck.pending_work_orders.length }} 个未完成工单与该日期重叠：
            <div v-for="wo in precheck.pending_work_orders" :key="wo.work_order_id" class="wo">
              {{ wo.work_order_no }} · {{ wo.fault_description || '—' }}
            </div>
          </div>
          <div v-if="precheck.need_substitute" class="danger">
            当日值班人数将不足（最低 {{ precheck.min_guard_count }} 人），主管需安排顶岗
          </div>
          <div v-if="!precheck.pending_work_orders?.length && !precheck.need_substitute" class="ok">
            未发现冲突，可以提交
          </div>
        </div>

        <button class="submit-btn" :disabled="submitting" @click="handleSubmit">
          {{ submitting ? '提交中…' : '提交申请' }}
        </button>
        <div class="hint">跨天请假请在电脑端提交</div>
      </div>
    </div>

    <!-- 我的记录 -->
    <div class="card">
      <div class="card-title"><span>我的请假记录</span></div>
      <div v-if="loading" class="empty">加载中…</div>
      <div v-else-if="list.length === 0" class="empty">暂无请假记录</div>
      <div v-else class="record-list">
        <div v-for="item in list" :key="item.id" class="record">
          <div class="record-top">
            <span class="record-type">{{ typeLabel(item.leave_type) }}</span>
            <span class="record-status" :class="'st-' + item.status">{{ statusLabel(item.status) }}</span>
          </div>
          <div class="record-dates">{{ formatDetails(item.details) }}</div>
          <div v-if="item.leave_reason" class="record-reason">{{ item.leave_reason }}</div>
          <div v-if="item.approver_comment" class="record-comment">审批意见：{{ item.approver_comment }}</div>
          <div class="record-foot">
            <span class="record-time">{{ fmt(item.submitted_at) }}</span>
            <span v-if="item.status === 'PENDING'" class="cancel" @click="handleCancel(item)">撤销</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'
import dayjs from 'dayjs'

const leaveTypes = [
  { value: 'ANNUAL', label: '年假' },
  { value: 'SICK', label: '病假' },
  { value: 'PERSONAL', label: '事假' },
  { value: 'COMPENSATION', label: '调休' },
  { value: 'MARRIAGE', label: '婚假' },
  { value: 'MATERNITY', label: '产假' },
  { value: 'FUNERAL', label: '丧假' },
  { value: 'OTHER', label: '其他' },
]
const shifts = [
  { value: 'ALL_DAY', label: '全天' },
  { value: 'MORNING', label: '上午' },
  { value: 'AFTERNOON', label: '下午' },
]
const statusMap = { PENDING: '待审批', APPROVED: '已批准', REJECTED: '已驳回', CANCELLED: '已撤销' }
const shiftMap = { ALL_DAY: '全天', MORNING: '上午', AFTERNOON: '下午' }

const list = ref([])
const loading = ref(false)
const submitting = ref(false)
const showForm = ref(true)
const precheck = ref(null)
const today = dayjs().format('YYYY-MM-DD')

const form = reactive({
  leave_type: 'ANNUAL',
  leave_date: dayjs().format('YYYY-MM-DD'),
  leave_shift: 'ALL_DAY',
  leave_reason: '',
})

const currentUserId = computed(() => {
  try {
    const u = JSON.parse(localStorage.getItem('current_user') || '{}')
    return u.id || null
  } catch { return null }
})

const typeLabel = (v) => (leaveTypes.find(t => t.value === v)?.label) || v
const statusLabel = (v) => statusMap[v] || v
const fmt = (s) => (s ? dayjs(s).format('MM-DD HH:mm') : '')
const formatDetails = (details) => (details && details.length)
  ? details.map(d => `${d.leave_date} ${shiftMap[d.leave_shift] || ''}`).join('、')
  : '—'

const toggleForm = () => { showForm.value = !showForm.value }

const fetchData = async () => {
  loading.value = true
  try {
    const res = await request.get('/leave-requests/my', { params: { page: 1, page_size: 20 } })
    list.value = res.items || []
  } catch (e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const handlePreCheck = async () => {
  precheck.value = null
  if (!form.leave_date || !currentUserId.value) return
  try {
    const res = await request.get('/leave-requests/check-conflicts', {
      params: {
        requester_id: currentUserId.value,
        date_from: form.leave_date,
        date_to: form.leave_date,
        shift: form.leave_shift,
      }
    })
    precheck.value = res
  } catch (e) { /* 预检失败不阻塞 */ }
}

const newCorrelationId = () => {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  return `h5-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const handleSubmit = async () => {
  if (!form.leave_date) { ElMessage.warning('请选择请假日期'); return }
  submitting.value = true
  try {
    await request.post('/leave-requests/', {
      leave_type: form.leave_type,
      leave_reason: form.leave_reason || null,
      date_from: form.leave_date,
      date_to: form.leave_date,
      shift_of_range: form.leave_shift,
      correlation_id: newCorrelationId(),
    })
    ElMessage.success('已提交，等待主管审批')
    form.leave_reason = ''
    precheck.value = null
    showForm.value = false
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

const handleCancel = async (item) => {
  try {
    await ElMessageBox.confirm('确定撤销这条请假申请吗？', '撤销确认', { type: 'warning' })
  } catch { return }
  try {
    await request.post(`/leave-requests/${item.id}/cancel`)
    ElMessage.success('已撤销')
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '撤销失败')
  }
}

onMounted(fetchData)
</script>

<style scoped>
.m-page { padding: 12px; padding-bottom: 80px; }
.card { background: #fff; border-radius: 10px; padding: 14px; margin-bottom: 12px; }
.card-title { display: flex; justify-content: space-between; align-items: center; font-size: 15px; font-weight: 600; color: #1D2129; }
.link { font-size: 13px; color: #1677FF; font-weight: 400; cursor: pointer; }
.form { margin-top: 12px; }
.field { margin-bottom: 12px; }
.field label { display: block; font-size: 13px; color: #4E5969; margin-bottom: 6px; }
.field select, .field input, .field textarea {
  width: 100%; box-sizing: border-box; border: 1px solid #E5E6EB; border-radius: 8px;
  padding: 9px 10px; font-size: 14px; background: #FAFBFC; outline: none;
}
.field textarea { resize: none; }
.seg { display: flex; gap: 8px; }
.seg-item {
  flex: 1; text-align: center; padding: 8px 0; border: 1px solid #E5E6EB; border-radius: 8px;
  font-size: 13px; color: #4E5969; background: #FAFBFC;
}
.seg-item.active { border-color: #1677FF; color: #1677FF; background: #F0F7FF; }
.precheck { background: #F7F8FA; border-radius: 8px; padding: 10px; margin-bottom: 12px; font-size: 12px; line-height: 1.7; }
.precheck .warn { color: #FF7D00; }
.precheck .danger { color: #F53F3F; }
.precheck .ok { color: #00B42A; }
.precheck .wo { color: #4E5969; margin-top: 2px; }
.submit-btn {
  width: 100%; height: 44px; border: none; border-radius: 22px; background: #1677FF;
  color: #fff; font-size: 15px; font-weight: 500;
}
.submit-btn:disabled { background: #9EC5FF; }
.hint { text-align: center; font-size: 12px; color: #86909C; margin-top: 8px; }
.empty { text-align: center; color: #86909C; font-size: 13px; padding: 24px 0; }
.record { border-bottom: 1px solid #F2F3F5; padding: 10px 0; }
.record:last-child { border-bottom: none; }
.record-top { display: flex; justify-content: space-between; align-items: center; }
.record-type { font-size: 14px; font-weight: 600; color: #1D2129; }
.record-status { font-size: 12px; padding: 1px 8px; border-radius: 4px; }
.st-PENDING { background: #FFF3E8; color: #FF7D00; }
.st-APPROVED { background: #E8F8EE; color: #00B42A; }
.st-REJECTED { background: #FFECEC; color: #F53F3F; }
.st-CANCELLED { background: #F2F3F5; color: #86909C; }
.record-dates { font-size: 13px; color: #4E5969; margin-top: 4px; }
.record-reason { font-size: 12px; color: #86909C; margin-top: 2px; }
.record-comment { font-size: 12px; color: #FF7D00; margin-top: 4px; }
.record-foot { display: flex; justify-content: space-between; margin-top: 6px; }
.record-time { font-size: 12px; color: #C9CDD4; }
.cancel { font-size: 12px; color: #F53F3F; }
</style>
