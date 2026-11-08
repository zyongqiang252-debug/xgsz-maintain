<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">我的请假</h2>
      <el-button type="primary" @click="openSubmit">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>提交请假申请
      </el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <div class="filter-bar">
        <el-select v-model="statusFilter" placeholder="全部状态" clearable class="filter-select" @change="handleSearch">
          <el-option label="待审批" value="PENDING" />
          <el-option label="已批准" value="APPROVED" />
          <el-option label="已驳回" value="REJECTED" />
          <el-option label="已撤销" value="CANCELLED" />
        </el-select>
        <el-button class="action-btn" @click="handleSearch">查询</el-button>
        <el-button class="action-btn" @click="handleReset">重置</el-button>
        <span class="tips">请假申请提交后由主管审批，审批结果可在本页查看</span>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table :data="list" v-loading="loading" style="width: 100%">
        <el-table-column label="请假类型" width="100">
          <template #default="{ row }">{{ typeLabel(row.leave_type) }}</template>
        </el-table-column>
        <el-table-column label="请假日期" min-width="220">
          <template #default="{ row }">
            <span v-if="!row.details || row.details.length === 0">—</span>
            <span v-else>{{ formatDetails(row.details) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leave_reason" label="事由" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <span class="status-tag" :class="'st-' + row.status">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="submitted_at" label="提交时间" width="160">
          <template #default="{ row }">{{ fmt(row.submitted_at) }}</template>
        </el-table-column>
        <el-table-column label="审批信息" min-width="180">
          <template #default="{ row }">
            <div v-if="row.approver_name || row.approver_comment" class="approve-info">
              <div v-if="row.approver_name">{{ row.approver_name }}</div>
              <div v-if="row.approver_comment" class="comment">{{ row.approver_comment }}</div>
            </div>
            <span v-else style="color: #C9CDD4">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" >
          <template #default="{ row }">
            <el-button v-if="row.status === 'PENDING'" size="small" type="danger" text @click="handleCancel(row)">
              撤销
            </el-button>
            <span v-else style="color: #C9CDD4">—</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager" v-if="total > pageSize">
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total"
                       layout="total, prev, pager, next" @current-change="fetchData" />
      </div>
    </el-card>

    <!-- 提交弹窗 -->
    <el-dialog v-model="dialog.visible" title="提交请假申请" width="560px" destroy-on-close>
      <el-form :model="form" label-width="90px">
        <el-form-item label="请假类型" required>
          <el-select v-model="form.leave_type" style="width: 100%">
            <el-option v-for="t in leaveTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="请假日期" required>
          <el-date-picker v-model="form.range" type="daterange" value-format="YYYY-MM-DD"
                          start-placeholder="开始日期" end-placeholder="结束日期"
                          style="width: 100%" @change="handlePreCheck" />
        </el-form-item>
        <el-form-item label="请假班次">
          <el-radio-group v-model="form.shift_of_range" @change="handlePreCheck">
            <el-radio value="ALL_DAY">全天</el-radio>
            <el-radio value="MORNING" :disabled="isMultiDay">上午</el-radio>
            <el-radio value="AFTERNOON" :disabled="isMultiDay">下午</el-radio>
          </el-radio-group>
          <div v-if="isMultiDay" class="field-tip">跨天请假仅支持全天，分时段请分开提交</div>
        </el-form-item>
        <el-form-item label="请假事由">
          <el-input v-model="form.leave_reason" type="textarea" :rows="3" maxlength="200" show-word-limit
                    placeholder="请简要说明请假原因" />
        </el-form-item>

        <!-- 预检结果 -->
        <el-form-item v-if="precheck" label="冲突预检">
          <div class="precheck-box">
            <el-alert v-if="precheck.pending_work_orders?.length" type="warning" :closable="false" show-icon
                      :title="`有 ${precheck.pending_work_orders.length} 个未完成工单与请假日期重叠`"
                      style="margin-bottom: 8px" />
            <div v-if="precheck.pending_work_orders?.length" class="wo-list">
              <div v-for="wo in precheck.pending_work_orders" :key="wo.work_order_id" class="wo-item">
                {{ wo.work_order_no }} · {{ wo.overlap_date }} · {{ wo.fault_description || '—' }}
              </div>
            </div>
            <el-alert v-if="precheck.need_substitute" type="error" :closable="false" show-icon
                      :title="`值班人数将不足（最低 ${precheck.min_guard_count} 人），需主管指定顶岗人`" />
            <div v-if="precheck.daily_on_duty_after && Object.keys(precheck.daily_on_duty_after).length" class="duty-list">
              <span v-for="(v, d) in precheck.daily_on_duty_after" :key="d" class="duty-item"
                    :class="{ danger: v < precheck.min_guard_count }">
                {{ d }}：{{ v }} 人在岗
              </span>
            </div>
            <div v-if="!precheck.pending_work_orders?.length && !precheck.need_substitute" class="ok-tip">
              未发现工单冲突，值班人数充足
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.submitting" @click="handleSubmit">提交申请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import request from '../api'
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
const statusMap = { PENDING: '待审批', APPROVED: '已批准', REJECTED: '已驳回', CANCELLED: '已撤销' }
const shiftMap = { ALL_DAY: '全天', MORNING: '上午', AFTERNOON: '下午' }

const list = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const statusFilter = ref('')
const precheck = ref(null)

const dialog = reactive({ visible: false, submitting: false })
const form = reactive({
  leave_type: 'ANNUAL',
  range: [],
  shift_of_range: 'ALL_DAY',
  leave_reason: '',
})

const currentUserId = computed(() => {
  try {
    const u = JSON.parse(localStorage.getItem('current_user') || '{}')
    return u.id || null
  } catch { return null }
})

const isMultiDay = computed(() => {
  if (!form.range || form.range.length !== 2) return false
  return new Date(form.range[1]).getTime() > new Date(form.range[0]).getTime()
})

const typeLabel = (v) => (leaveTypes.find(t => t.value === v)?.label) || v
const statusLabel = (v) => statusMap[v] || v
const fmt = (s) => (s ? dayjs(s).format('YYYY-MM-DD HH:mm') : '—')
const formatDetails = (details) => details
  .map(d => `${d.leave_date} ${shiftMap[d.leave_shift] || d.leave_shift || '全天'}`)
  .join('、')

const fetchData = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (statusFilter.value) params.status = statusFilter.value
    const res = await request.get('/leave-requests/my', { params })
    list.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('请假记录加载失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => { page.value = 1; fetchData() }
const handleReset = () => { statusFilter.value = ''; page.value = 1; fetchData() }

const openSubmit = () => {
  form.leave_type = 'ANNUAL'
  form.range = []
  form.shift_of_range = 'ALL_DAY'
  form.leave_reason = ''
  precheck.value = null
  dialog.visible = true
}

const handlePreCheck = async () => {
  precheck.value = null
  if (!form.range || form.range.length !== 2 || !currentUserId.value) return
  try {
    const res = await request.get('/leave-requests/check-conflicts', {
      params: {
        requester_id: currentUserId.value,
        date_from: form.range[0],
        date_to: form.range[1],
        shift: form.shift_of_range,
      }
    })
    precheck.value = res
  } catch (e) {
    // 预检失败不阻塞提交
  }
}

const newCorrelationId = () => {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  return `web-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const handleSubmit = async () => {
  if (!form.range || form.range.length !== 2) {
    ElMessage.warning('请选择请假日期')
    return
  }
  if (isMultiDay.value && form.shift_of_range !== 'ALL_DAY') {
    ElMessage.warning('跨天请假仅支持全天')
    return
  }
  dialog.submitting = true
  try {
    await request.post('/leave-requests/', {
      leave_type: form.leave_type,
      leave_reason: form.leave_reason || null,
      date_from: form.range[0],
      date_to: form.range[1],
      shift_of_range: form.shift_of_range,
      correlation_id: newCorrelationId(),
    })
    ElMessage.success('请假申请已提交，等待主管审批')
    dialog.visible = false
    page.value = 1
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    dialog.submitting = false
  }
}

const handleCancel = async (row) => {
  try {
    await ElMessageBox.confirm('确定撤销这条请假申请吗？撤销后需重新提交。', '撤销确认', { type: 'warning' })
  } catch { return }
  try {
    await request.post(`/leave-requests/${row.id}/cancel`)
    ElMessage.success('已撤销')
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '撤销失败')
  }
}

onMounted(fetchData)
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-title { margin: 0; font-size: 20px; font-weight: 600; color: #1D2129; }
.filter-card { margin-bottom: 12px; border-radius: 8px; }
.filter-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.filter-select { width: 140px; }
.tips { font-size: 12px; color: #86909C; margin-left: auto; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
.status-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.st-PENDING { background: #FFF3E8; color: #FF7D00; }
.st-APPROVED { background: #E8F8EE; color: #00B42A; }
.st-REJECTED { background: #FFECEC; color: #F53F3F; }
.st-CANCELLED { background: #F2F3F5; color: #86909C; }
.approve-info { font-size: 12px; color: #4E5969; line-height: 1.6; }
.approve-info .comment { color: #86909C; }
.field-tip { font-size: 12px; color: #FF7D00; margin-top: 4px; }
.precheck-box { width: 100%; background: #F7F8FA; border-radius: 6px; padding: 10px; }
.wo-list { margin-bottom: 8px; }
.wo-item { font-size: 12px; color: #4E5969; line-height: 1.8; }
.duty-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.duty-item { font-size: 12px; color: #4E5969; background: #fff; border: 1px solid #E5E6EB; border-radius: 4px; padding: 2px 6px; }
.duty-item.danger { color: #F53F3F; border-color: #FBC4C4; background: #FFF5F5; }
.ok-tip { font-size: 12px; color: #00B42A; }
</style>
