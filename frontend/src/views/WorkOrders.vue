<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">维修报表</h2>
      <div style="display:flex;gap:8px">
        <el-button :loading="exporting" @click="handleExport">导出 Excel</el-button>
        <el-button type="primary" @click="$router.push('/work-orders/new')">新建工单</el-button>
      </div>
    </div>

    <el-card class="filter-card" shadow="never">
      <div class="filter-bar">
        <el-input v-model="keyword" placeholder="搜索工单编号/故障描述" clearable class="filter-input" @clear="handleSearch" @keyup.enter="handleSearch" />
        <el-select v-model="statusFilter" placeholder="工单状态" clearable class="filter-select" @change="handleSearch">
          <el-option label="草稿" value="DRAFT" />
          <el-option label="维修中" value="IN_PROGRESS" />
          <el-option label="待归档" value="ARCHIVING" />
          <el-option label="已归档" value="ARCHIVED" />
          <el-option label="已完成" value="COMPLETED" />
        </el-select>
        <el-select v-model="orderTypeFilter" placeholder="工单类型" clearable class="filter-select" @change="handleSearch">
          <el-option label="报修工单" value="REPAIR" />
          <el-option label="保养工单" value="MAINTENANCE" />
          <el-option label="点检工单" value="INSPECTION" />
          <el-option label="导入工单" value="IMPORT" />
        </el-select>
        <el-select v-model="alertLevelFilter" placeholder="告警级别" clearable class="filter-select" @change="handleSearch">
          <el-option label="P0 严重" value="P0" />
          <el-option label="P1 重要" value="P1" />
          <el-option label="P2 一般" value="P2" />
          <el-option label="P3 提示" value="P3" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          class="filter-date"
          @change="handleSearch"
          clearable
        />
        <el-button type="primary" @click="handleSearch" class="action-btn">查询</el-button>
        <el-button class="action-btn secondary-btn" @click="handleReset">重置</el-button>
      </div>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table :data="list" v-loading="loading" stripe class="wo-table">
        <el-table-column label="工单编号" width="176" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="wo-no">{{ row.work_order_no }}</span>
            <el-tag v-if="row.order_type && row.order_type !== 'REPAIR'" size="small" effect="plain" style="margin-left:4px">
              {{ orderTypeLabel(row.order_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="fault_description" label="故障描述" min-width="170" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span class="status-tag" :class="'status-' + row.status">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="86" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.alert_level" size="small" :type="alertLevelMeta(row.alert_level).type" effect="plain">
              {{ row.alert_level }}
            </el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="时效" width="110" align="center">
          <template #default="{ row }">
            <el-tooltip :content="slaTooltip(row)" placement="top">
              <el-tag size="small" :type="slaTagType(row)" effect="light">{{ slaLabel(row) }}</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="成本" width="90" align="right">
          <template #default="{ row }">
            <span v-if="row.total_cost">{{ row.total_cost.toFixed(0) }} 元</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="130">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230">
          <template #default="{ row }">
            <div class="col-actions">
              <div class="action-row">
                <el-button link type="primary" @click="$router.push(`/work-orders/${row.id}`)">查看</el-button>
                <el-dropdown v-if="hasMoreActions(row)" trigger="click" @command="(cmd) => onRowCommand(cmd, row)">
                  <el-button link type="primary">更多<el-icon style="margin-left:2px"><ArrowDown /></el-icon></el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-if="rowActionText(row)" command="dispatch" :disabled="claiming === row.id">
                        {{ rowActionText(row) }}
                      </el-dropdown-item>
                      <el-dropdown-item v-if="!isSupervisor" command="edit" :disabled="!canEditRow(row)">编辑</el-dropdown-item>
                      <el-dropdown-item v-if="!isSupervisor" command="delete" :disabled="!canDeleteRow(row)" divided>删除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
              <div class="action-row progress-row" v-if="canOperateProgress(row)">
                <el-button
                  v-if="row.status === 'DRAFT'"
                  size="small"
                  type="primary"
                  :disabled="!isCreatedByMe(row) && !isAdmin"
                  :loading="transitionLoading[`${row.id}_SUBMITTED`]"
                  @click="handleTransition(row, 'SUBMITTED')"
                >提交报修</el-button>
                <el-button
                  v-if="row.status === 'ASSIGNED'"
                  size="small"
                  type="primary"
                  :disabled="!isAssignedTech(row) && !isSupervisor"
                  :loading="transitionLoading[`${row.id}_ACCEPTED`]"
                  @click="handleTransition(row, 'ACCEPTED')"
                >接受任务</el-button>
                <el-button
                  v-if="row.status === 'ACCEPTED'"
                  size="small"
                  type="primary"
                  :disabled="!isAssignedTech(row) && !isSupervisor"
                  :loading="transitionLoading[`${row.id}_ARRIVED`]"
                  @click="handleTransition(row, 'ARRIVED')"
                >已到达现场</el-button>
                <el-button
                  v-if="row.status === 'ARRIVED'"
                  size="small"
                  type="primary"
                  :disabled="!isAssignedTech(row) && !isSupervisor"
                  :loading="transitionLoading[`${row.id}_INSPECTING`]"
                  @click="handleTransition(row, 'INSPECTING')"
                >开始检查</el-button>
                <el-button
                  v-if="row.status === 'INSPECTING'"
                  size="small"
                  type="primary"
                  :disabled="!isAssignedTech(row) && !isSupervisor"
                  :loading="transitionLoading[`${row.id}_IN_PROGRESS`]"
                  @click="handleTransition(row, 'IN_PROGRESS')"
                >开始维修</el-button>
                <el-button
                  v-if="row.status === 'IN_PROGRESS'"
                  size="small"
                  type="success"
                  :loading="transitionLoading[`${row.id}_ARCHIVING`]"
                  @click="handleFinishRepair(row)"
                >完成维修</el-button>
                <el-button
                  v-if="row.status === 'ARCHIVING'"
                  size="small"
                  type="primary"
                  @click="$router.push(`/work-orders/${row.id}?edit=1`)"
                >去归档</el-button>
              </div>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchData"
        />
      </div>
    </el-card>

    <!-- 派工 -->
    <el-dialog v-model="dispatch.visible" :title="dispatchTitle" width="460px">
      <el-form label-width="80px">
        <el-form-item label="工单">
          <span>{{ dispatch.row?.work_order_no }}</span>
        </el-form-item>
        <el-form-item label="故障">
          <span class="ellipsis-1">{{ dispatch.row?.fault_description }}</span>
        </el-form-item>
        <el-form-item label="维修员" required>
          <el-select v-model="dispatch.technicianId" filterable placeholder="选择维修员" style="width:100%">
            <el-option
              v-for="t in dispatch.technicians" :key="t.id"
              :label="`${t.real_name}（在办 ${t.current_workload_count} · 近7天完成 ${t.recent7d_completed}）`"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="dispatch.remark" type="textarea" :rows="2" maxlength="100"
                    placeholder="选填，例如：优先处理、带好备件" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dispatch.visible = false">取消</el-button>
        <el-button type="primary" :loading="dispatch.submitting" @click="submitDispatch">{{ dispatchConfirmText }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import request from '../api'
import { downloadFile } from '../utils/download'
import { workOrderTransition } from '../api/supervisor'
import dayjs from 'dayjs'

const router = useRouter()

const flattenTree = (nodes, result = []) => {
  for (const node of nodes) {
    result.push({ label: node.name, value: node.name })
    if (node.children && node.children.length > 0) flattenTree(node.children, result)
  }
  return result
}
const deviceTypeOptions = ref([])

// 当前登录用户（用于权限判断：仅创建者或管理员可编辑）
const currentUser = (() => {
  try {
    const raw = localStorage.getItem('current_user')
    return raw ? JSON.parse(raw) : {}
  } catch { return {} }
})()
const isAdmin = currentUser.role === 'ADMIN'
const isSupervisor = currentUser.role === 'SUPERVISOR' || isAdmin
const isTechnician = currentUser.role === 'TECHNICIAN'
const isCreatedByMe = (row) => {
  if (row.created_by_employee_id && currentUser.employee_id) {
    return row.created_by_employee_id === currentUser.employee_id
  }
  return !!row.created_by && row.created_by === currentUser.id
}
const isAssignedTech = (row) => {
  const tid = row.technician_id || row.assigned_technician_id
  if (!tid) return false
  return tid === currentUser.id
}
const canOperateProgress = (row) => isAssignedTech(row) || row.status === 'DRAFT'

// ===== 派工（把 SUBMITTED 指派给维修员 → ASSIGNED）=====
const dispatch = reactive({ visible: false, row: null, technicianId: null, remark: '', technicians: [], submitting: false })
const isSelfDispatch = computed(() => {
  const r = dispatch.row
  if (!r) return false
  const mine = (r.technician_id || r.assigned_technician_id) === currentUser.id
  return mine && !isSupervisor
})
const dispatchTitle = computed(() => {
  if (isSelfDispatch.value) return '转派工单'
  return dispatch.row?.status === 'ASSIGNED' ? '工单改派' : '工单派工'
})
const dispatchConfirmText = computed(() => {
  if (isSelfDispatch.value) return '确认转派'
  return dispatch.row?.status === 'ASSIGNED' ? '确认改派' : '确认派工'
})
const canEditRow = (row) =>
  !['COMPLETED', 'ARCHIVED'].includes(row.status) &&
  (isCreatedByMe(row) || isAdmin || isAssignedTech(row))

const canDeleteRow = (row) =>
  !['COMPLETED', 'ARCHIVED'].includes(row.status) &&
  (isCreatedByMe(row) || isAdmin)

// 一行里可能存在的「非主操作」动作文案：派工/改派/领取/转派
const rowActionText = (row) => {
  if (['SUBMITTED', 'ASSIGNED'].includes(row.status) && isSupervisor) {
    return row.status === 'ASSIGNED' ? '改派' : '派工'
  }
  if (row.status === 'SUBMITTED' && isTechnician) return '领取'
  if (row.status === 'ASSIGNED' && isAssignedTech(row)) return '转派'
  return ''
}

const hasMoreActions = (row) =>
  !!rowActionText(row) || (!isSupervisor && (canEditRow(row) || canDeleteRow(row)))

const onRowCommand = (cmd, row) => {
  if (cmd === 'edit') {
    router.push(`/work-orders/${row.id}?edit=1`)
  } else if (cmd === 'delete') {
    handleDelete(row)
  } else if (cmd === 'dispatch') {
    if (row.status === 'SUBMITTED' && isTechnician) claimTask(row)
    else openDispatch(row)
  }
}

const claiming = ref(null)
// 维修员主动领取（抢单）
const claimTask = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确认领取工单 ${row.work_order_no}？领取后由你负责。`, '领取任务',
      { type: 'info', confirmButtonText: '确认领取' })
  } catch { return }
  claiming.value = row.id
  try {
    await request.post(`/work-orders/${row.id}/transition`, {
      to_status: 'ASSIGNED',
      technician_id: currentUser.id,
      source: 'TECH_CLAIM',
    })
    ElMessage.success('领取成功，工单已归你负责')
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '领取失败')
  } finally {
    claiming.value = null
  }
}

const openDispatch = async (row) => {
  Object.assign(dispatch, { visible: true, row, technicianId: null, remark: '', submitting: false })
  try {
    const res = await request.get('/dispatch/technicians')
    const all = Array.isArray(res) ? res : (res.items || [])
    dispatch.technicians = isSupervisor ? all : all.filter((t) => t.id !== currentUser.id)
  } catch (e) {
    dispatch.technicians = []
    ElMessage.error('获取维修员列表失败')
  }
}
const submitDispatch = async () => {
  if (!dispatch.technicianId) return ElMessage.warning('请选择维修员')
  dispatch.submitting = true
  try {
    await request.post(`/work-orders/${dispatch.row.id}/transition`, {
      to_status: 'ASSIGNED',
      technician_id: dispatch.technicianId,
      source: 'SUPERVISOR_DISPATCH',
      remark: dispatch.remark || null,
    })
    ElMessage.success(isSelfDispatch.value ? '转派成功' : (dispatch.row?.status === 'ASSIGNED' ? '改派成功' : '派工成功'))
    dispatch.visible = false
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '派工失败')
  } finally {
    dispatch.submitting = false
  }
}
const transitionLoading = ref({})

const handleTransition = async (row, toStatus, source = 'TECH_PROGRESS') => {
  try {
    transitionLoading.value[`${row.id}_${toStatus}`] = true
    await workOrderTransition(row.id, {
      to_status: toStatus,
      source,
      remark: undefined,
    })
    await fetchData()
  } catch {
    // handled
  } finally {
    transitionLoading.value[`${row.id}_${toStatus}`] = false
  }
}

const handleFinishRepair = async (row) => {
  await handleTransition(row, 'ARCHIVING')
  router.push(`/work-orders/${row.id}?edit=1`)
}

const list = ref([])
const loading = ref(false)
const keyword = ref('')
const statusFilter = ref('')
const orderTypeFilter = ref('')
const alertLevelFilter = ref('')
const ORDER_TYPE_LABEL = { REPAIR: '报修', MAINTENANCE: '保养', INSPECTION: '点检', IMPORT: '导入' }
const orderTypeLabel = (t) => ORDER_TYPE_LABEL[(t || 'REPAIR').toUpperCase()] || t
const deviceTypeFilter = ref('')
const dateRange = ref(null)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

const statusMap = {
  DRAFT: '草稿',
  SUBMITTED: '待派工',
  ASSIGNED: '已派单',
  ACCEPTED: '已接单',
  ARRIVED: '已到达',
  INSPECTING: '检查中',
  IN_PROGRESS: '维修中',
  ARCHIVING: '待归档',
  ARCHIVED: '已归档',
  COMPLETED: '已完成',
  REJECTED: '已退回',
}

const LEVELS = {
  P0: { label: '严重', type: 'danger' },
  P1: { label: '重要', type: 'warning' },
  P2: { label: '一般', type: 'warning' },
  P3: { label: '提示', type: 'info' },
}
const alertLevelMeta = (lv) => LEVELS[(lv || 'P2').toUpperCase()] || LEVELS.P2

const statusLabel = (s) => statusMap[s] || s
const formatTime = (t) => t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'

// ===== SLA 展示 =====
const slaLabel = (row) => {
  const st = row.sla_status
  if (row.status === 'COMPLETED' || row.status === 'ARCHIVED') {
    return st === 'OVERDUE' ? '超时完成' : '按时完成'
  }
  if (st === 'OVERDUE') return '已超时'
  if (st === 'AT_RISK') return '即将超时'
  if (row.resolve_due_at) {
    const left = dayjs(row.resolve_due_at).diff(dayjs(), 'hour', true)
    return left >= 24 ? `剩 ${Math.floor(left / 24)} 天` : `剩 ${Math.max(0, Math.round(left))} 小时`
  }
  return '—'
}
const slaTagType = (row) => {
  const st = row.sla_status
  if (st === 'OVERDUE') return 'danger'
  if (st === 'AT_RISK') return 'warning'
  if (row.status === 'COMPLETED' || row.status === 'ARCHIVED') return st === 'OVERDUE' ? 'danger' : 'success'
  return 'success'
}
const slaTooltip = (row) => {
  const parts = []
  if (row.response_due_at) parts.push(`响应截止 ${formatTime(row.response_due_at)}`)
  if (row.resolve_due_at) parts.push(`修复截止 ${formatTime(row.resolve_due_at)}`)
  if (row.satisfaction_score) parts.push(`满意度 ${row.satisfaction_score} 分`)
  return parts.join('　') || '无 SLA 信息'
}

const STORAGE_KEY = 'workorders_filter'

const fetchData = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (statusFilter.value) params.status = statusFilter.value
    if (deviceTypeFilter.value) params.device_type = deviceTypeFilter.value
    if (dateRange.value) {
      params.date_from = dayjs(dateRange.value[0]).format('YYYY-MM-DD')
      params.date_to = dayjs(dateRange.value[1]).format('YYYY-MM-DD')
    }
    const res = await request.get('/work-orders/', { params })
    list.value = res.items
    total.value = res.total

    // 保存筛选条件到 sessionStorage，返回列表时恢复
    saveFilter()
  } catch { /* handled by interceptor */ }
  finally { loading.value = false }
}

const saveFilter = () => {
  const data = {}
  if (keyword.value) data.keyword = keyword.value
  if (statusFilter.value) data.status = statusFilter.value
  if (deviceTypeFilter.value) data.device_type = deviceTypeFilter.value
  if (dateRange.value) {
    data.date_from = dayjs(dateRange.value[0]).format('YYYY-MM-DD')
    data.date_to = dayjs(dateRange.value[1]).format('YYYY-MM-DD')
  }
  if (page.value > 1) data.page = page.value
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data))
}

const handleSearch = () => { page.value = 1; fetchData() }
const handleReset = () => {
  keyword.value = ''
  statusFilter.value = ''
  orderTypeFilter.value = ''
  alertLevelFilter.value = ''
  dateRange.value = null
  page.value = 1
  sessionStorage.removeItem(STORAGE_KEY)
  fetchData()
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定删除该工单？', '删除确认', { type: 'warning' })
    await request.delete(`/work-orders/${row.id}`)
    ElMessage.success('删除成功')
    fetchData()
  } catch { /* cancelled */ }
}

onMounted(() => {
  // 从 sessionStorage 恢复筛选条件
  const raw = sessionStorage.getItem(STORAGE_KEY)
  if (raw) {
    try {
      const data = JSON.parse(raw)
      if (data.keyword) keyword.value = data.keyword
      if (data.status) statusFilter.value = data.status
      if (data.device_type) deviceTypeFilter.value = data.device_type
      if (data.date_from && data.date_to) {
        dateRange.value = [new Date(data.date_from), new Date(data.date_to)]
      }
      if (data.page) page.value = data.page
    } catch { /* ignore bad data */ }
  }
  // 拉取设备类型选项
  request.get('/categories/', { params: { category_type: 'DEVICE_TYPE', page_size: 1000 } })
    .then(res => { deviceTypeOptions.value = flattenTree(res.items || []) })
    .catch(() => {})
  fetchData()
})

// ===== 导出 Excel =====
const exporting = ref(false)
const handleExport = async () => {
  exporting.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    if (keyword.value) params.keyword = keyword.value
    await downloadFile('/export/work-orders.xlsx', params, '工单.xlsx')
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.page-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary); }
.filter-card { margin-bottom: 16px; }
.filter-bar { display: flex; gap: 8px; flex-wrap: nowrap; align-items: center; }
.filter-bar :deep(.el-date-editor) { flex: 1; min-width: 240px; }
.filter-input { width: 200px; }
.filter-select { width: 128px; }
.action-btn { flex-shrink: 0; }
.secondary-btn { background: #fff; border-color: #d9d9d9; color: #333; }
.table-card { min-height: 300px; overflow: hidden; }
.muted { color: #C9CDD4; }
/* 表格统一行高，避免按钮把行撑高 */
.wo-table :deep(.el-table__cell) { padding: 8px 0; }
.wo-table :deep(.el-button.is-link) { padding: 0 2px; height: auto; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }
.col-actions { display: flex; align-items: center; gap: 4px; white-space: nowrap; }
.action-row { display: contents; }
.progress-row { display: contents; }

.status-tag { display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 500; }
.status-DRAFT { background: #F2F3F5; color: #4E5969; }
.status-IN_PROGRESS { background: #FFF3E8; color: #FF7D00; }
.status-ARCHIVING { background: #FFF7E8; color: #FF8800; }
.status-ARCHIVED { background: #E8F8EE; color: #00B42A; }
.status-COMPLETED { background: #E8F8EE; color: #00B42A; }
.filter-date { width: 240px; }
.ellipsis-1 { display:inline-block; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
</style>
