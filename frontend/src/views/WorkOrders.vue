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

      <!-- 状态快捷筛选（独立一行，无「我的」分组） -->
      <div v-if="!isPoolView" class="quick-bar">
        <span class="qb-label">状态</span>
        <div class="qb-group">
          <span class="chip" :class="{ active: !statusFilter }" @click="pickStatus('')">全部</span>
          <span v-for="opt in visibleStatusOptions" :key="opt.value"
                class="chip" :class="{ active: statusFilter === opt.value }"
                @click="pickStatus(opt.value)">{{ opt.label }}</span>
        </div>
        <el-popover placement="top-start" :width="360" trigger="hover" popper-class="status-help-pop">
          <template #reference>
            <el-icon class="qb-help"><QuestionFilled /></el-icon>
          </template>
          <div class="status-help-title">工单状态说明（按流转顺序）</div>
          <div class="status-help-row" v-for="opt in visibleStatusOptions" :key="opt.value">
            <span class="status-tag" :class="'status-' + opt.value">{{ opt.label }}</span>
            <span class="status-help-desc">{{ opt.desc }}</span>
          </div>
        </el-popover>
      </div>
    </el-card>

    <!-- 首屏加载骨架 -->
    <el-card v-if="loading && !list.length" class="table-card" shadow="never">
      <TableSkeleton :rows="8" :cols="6" :widths="['16%','26%','10%','8%','12%','10%']" />
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table :data="list" stripe class="wo-table" :row-class-name="rowClassName" @row-click="onRowClick">
        <el-table-column label="工单编号" width="166" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="wo-no">{{ row.work_order_no }}</span>
            <el-tag v-if="row.customer_name" size="small" type="success" effect="plain"
                    :title="`客户报修：${row.customer_name}`" style="margin-left:4px">客户</el-tag>
            <el-tag v-if="row.order_type && row.order_type !== 'REPAIR'" size="small" effect="plain" style="margin-left:4px">
              {{ orderTypeLabel(row.order_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="设备 / 故障" min-width="240">
          <template #default="{ row }">
            <div class="fault-cell" :title="row.fault_description || ''">
              <div class="fault-device">{{ row.device_code || row.device_name || '未指定设备' }}</div>
              <div class="fault-desc">{{ row.fault_description || '-' }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="86">
          <template #default="{ row }">
            <span class="status-tag" :class="'status-' + (row.status_group || row.status)">{{ row.status_group_label || statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.technician_name">{{ row.technician_name }}</span>
            <span v-else class="muted">未指派</span>
            <el-tag
              v-if="row.transfer_from_name"
              size="small" type="warning" effect="plain"
              :title="`由 ${row.transfer_from_name} 转派给你`"
              style="margin-left:4px"
            >转派</el-tag>
            <div v-if="row.collaborators && row.collaborators.length" class="collab-line">
              协：{{ row.collaborators.map(c => c.name).join('、') }}
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="140">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="212" header-align="left">
          <template #default="{ row }">
            <div class="op-cell">
              <div class="op-actions">
                <IconAction :icon="PrinterIcon" title="打印 / PDF" @click="onRowCommand('print', row)" />
                <template v-if="!isSupervisor || isAdmin">
                  <IconAction
                    :icon="EditIcon"
                    :title="canEditRow(row) ? '编辑' : editDenyReason(row)"
                    :disabled="!canEditRow(row)"
                    @click="onRowCommand('edit', row)"
                  />
                  <IconAction
                    :icon="DeleteIcon"
                    :title="canDeleteRow(row) ? '删除' : deleteDenyReason(row)"
                    type="danger"
                    :disabled="!canDeleteRow(row)"
                    @click="onRowCommand('delete', row)"
                  />
                </template>
              </div>
              <div class="op-primary" v-if="hasPrimaryAction(row)">
                <el-button
                  v-if="isSupervisor && ['SUBMITTED', 'ASSIGNED', 'ACCEPTED', 'ARRIVED', 'INSPECTING'].includes(row.status)"
                  size="small" type="primary" @click="openDispatch(row)"
                >{{ row.status === 'SUBMITTED' ? '派工' : '改派' }}</el-button>
                <el-button
                  v-else-if="rowActionText(row) === '转派'"
                  size="small" type="primary" @click="onRowCommand('dispatch', row)"
                >转派</el-button>
                <el-button
                  v-else-if="rowActionText(row) === '领取' && !isPoolView"
                  size="small" type="primary"
                  :loading="claiming === row.id" @click="claimTask(row)"
                >领取</el-button>
                <template v-else-if="canOperateProgress(row)">
                  <el-button
                    v-if="isPoolView && row.status === 'SUBMITTED' && isTechnician"
                    size="small" type="primary"
                    :loading="claiming === row.id" @click="claimTask(row)"
                  >领取</el-button>
                  <el-button
                    v-if="row.status === 'DRAFT'"
                    size="small" type="primary"
                    :disabled="!isCreatedByMe(row) && !isAdmin"
                    :loading="transitionLoading[`${row.id}_SUBMITTED`]"
                    @click="handleTransition(row, 'SUBMITTED')"
                  >提交报修</el-button>
                  <!-- 已派单：接受 / 拒收（拒收回待派工池） -->
                  <el-button
                    v-if="row.status === 'ASSIGNED' && isAssignedTech(row) && (isTechnician || isAdmin)"
                    size="small" type="primary"
                    :loading="startingId === row.id"
                    @click="acceptAssignment(row)"
                  >接受</el-button>
                  <el-button
                    v-if="row.status === 'ASSIGNED' && isAssignedTech(row) && (isTechnician || isAdmin)"
                    size="small" type="danger" plain
                    @click="rejectAssignment(row)"
                  >拒收</el-button>
                  <!-- 已接单/已到场/检查中：一键进入下一步（中间步骤自动记入进度） -->
                  <el-button
                    v-if="['ACCEPTED', 'ARRIVED', 'INSPECTING'].includes(row.status)"
                    size="small" type="primary"
                    :disabled="!isAssignedTech(row) && !isSupervisor"
                    :loading="startingId === row.id"
                    @click="handleStart(row)"
                  >{{ startActionLabel(row) }}</el-button>
                  <el-button
                    v-if="row.status === 'IN_PROGRESS'"
                    size="small" type="success"
                    :loading="transitionLoading[`${row.id}_ARCHIVING`]"
                    @click="handleFinishRepair(row)"
                  >完成维修</el-button>
                  <el-button
                    v-if="row.status === 'ARCHIVING'"
                    size="small" type="primary"
                    @click="$router.push(`/work-orders/${row.id}?edit=1`)"
                  >去归档</el-button>
                </template>
              </div>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState icon="search" title="没有找到符合条件的记录" hint="试试调整筛选条件，或清空搜索后重新查询" />
        </template>
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
        <el-form-item label="协作人">
          <el-select v-model="dispatch.collaboratorIds" multiple filterable placeholder="可选，多人一起处理时选择" style="width:100%">
            <el-option
              v-for="t in dispatch.technicians" :key="t.id"
              :label="t.real_name" :value="t.id"
              :disabled="t.id === dispatch.technicianId"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="dispatchNeedsReason ? '改派原因' : '备注'" :required="dispatchNeedsReason">
          <el-input v-model="dispatch.remark" type="textarea" :rows="2" maxlength="100"
                    :placeholder="dispatchNeedsReason ? '必填，例如：维修员不熟悉该设备/临时请假' : '选填，例如：优先处理、带好备件'" />
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
const props = defineProps({
  defaultMine: { type: String, default: '' },
  poolMode: { type: [String, Boolean], default: '' },
})
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { QuestionFilled, Printer as PrinterIcon, Edit as EditIcon, Delete as DeleteIcon } from '@element-plus/icons-vue'
import request from '../api'
import { downloadFile } from '../utils/download'
import { workOrderTransition } from '../api/supervisor'
import dayjs from 'dayjs'

import EmptyState from '../components/EmptyState.vue'
import TableSkeleton from '../components/TableSkeleton.vue'
import IconAction from '../components/IconAction.vue'
const router = useRouter()

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
const canOperateProgress = (row) =>
  isAssignedTech(row) || row.status === 'DRAFT' ||
  (isPoolView && row.status === 'SUBMITTED' && isTechnician)

// 操作列是否渲染「主操作」按钮（派工/改派、领取/转派、流程推进）
const hasPrimaryAction = (row) =>
  (isSupervisor && ['SUBMITTED', 'ASSIGNED', 'ACCEPTED', 'ARRIVED', 'INSPECTING'].includes(row.status)) ||
  !!rowActionText(row) ||
  canOperateProgress(row)

// ===== 派工（把 SUBMITTED 指派给维修员 → ASSIGNED）=====
const dispatch = reactive({ visible: false, row: null, technicianId: null, collaboratorIds: [], remark: '', technicians: [], submitting: false })
const isSelfDispatch = computed(() => {
  const r = dispatch.row
  if (!r) return false
  const mine = (r.technician_id || r.assigned_technician_id) === currentUser.id
  return mine && !isSupervisor
})
const dispatchTitle = computed(() => {
  if (isSelfDispatch.value) return '转派工单'
  return dispatch.row?.status === 'SUBMITTED' ? '工单派工' : '工单改派'
})
// 接单/到场/检查中阶段改派必须填写原因
const dispatchNeedsReason = computed(() =>
  ['ACCEPTED', 'ARRIVED', 'INSPECTING'].includes(dispatch.row?.status))
const dispatchConfirmText = computed(() => {
  if (isSelfDispatch.value) return '确认转派'
  return dispatch.row?.status === 'SUBMITTED' ? '确认派工' : '确认改派'
})
const editDenyReason = (row) => {
  if (row.status === 'COMPLETED') return '已完成工单不可编辑'
  if (row.status === 'ARCHIVED') return '已归档工单仅管理员可修改'
  return '仅创建者、被指派人或管理员可编辑'
}

const deleteDenyReason = (row) => {
  if (['COMPLETED', 'ARCHIVED'].includes(row.status)) return '已归档/已完成，不可删除'
  return '仅创建者或管理员可删除'
}

const canEditRow = (row) => {
  if (row.status === 'COMPLETED') return false
  // 已归档：仅管理员可改（改动会写入修改记录）
  if (row.status === 'ARCHIVED') return isAdmin
  return isCreatedByMe(row) || isAdmin || isAssignedTech(row)
}

const canDeleteRow = (row) =>
  !['COMPLETED', 'ARCHIVED'].includes(row.status) &&
  (isCreatedByMe(row) || isAdmin)

// 处理中各行按当前节点显示下一步动作，避免已接单/已到场还写“开始处理”
const startActionLabel = (row) => ({
  ASSIGNED: '开始处理',
  ACCEPTED: '到场',
  ARRIVED: '开始检查',
  INSPECTING: '开始维修',
}[row.status] || '开始处理')

// 一行里可能存在的「非主操作」动作文案：派工/改派/领取/转派
const rowActionText = (row) => {
  if (row.status === 'SUBMITTED' && isTechnician) return '领取'
  if (row.status === 'ASSIGNED' && isAssignedTech(row)) return '转派'
  return ''
}

const onRowCommand = (cmd, row) => {
  if (cmd === 'edit') {
    router.push(`/work-orders/${row.id}?edit=1`)
  } else if (cmd === 'delete') {
    handleDelete(row)
  } else if (cmd === 'copy') {
    navigator.clipboard?.writeText(row.work_order_no)
      .then(() => ElMessage.success('工单号已复制'))
      .catch(() => ElMessage.warning('复制失败，请手动选择'))
  } else if (cmd === 'archiveCheck') {
    request.post(`/work-orders/${row.id}/archive-check`)
      .then((d) => {
        if (!d) return
        if (d.passed) ElMessage.success(`归档字段齐全（${d.total_fields ?? 6} 项，完成度 ${Math.round((d.completeness || 1) * 100)}%）`)
        else ElMessage.warning(`还缺 ${(d.missing_fields || []).length} 项：${(d.missing_fields || []).join('、')}`)
      })
      .catch(() => ElMessage.error('归档检查失败'))
  } else if (cmd === 'print') {
    downloadFile(`/work-orders/${row.id}/pdf`, {}, `工单-${row.work_order_no}.pdf`)
      .catch(() => ElMessage.error('PDF 生成失败'))
  } else if (cmd === 'dispatch') {
    if (row.status === 'SUBMITTED' && isTechnician) claimTask(row)
    else openDispatch(row)
  }
}

// 接受派工：ASSIGNED → ACCEPTED
const acceptAssignment = async (row) => {
  startingId.value = row.id
  try {
    await request.post(`/work-orders/${row.id}/transition`, {
      to_status: 'ACCEPTED', source: 'TECH_ACCEPT',
    })
    ElMessage.success('已接单')
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '接单失败')
  } finally {
    startingId.value = null
  }
}

// 拒收：ASSIGNED → SUBMITTED（退回待派工池，必须填原因）
const rejectAssignment = async (row) => {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt(
      '工单将退回「待派工」池，由主管重新派工', '拒收工单',
      {
        confirmButtonText: '确认拒收', cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '必填，例如：不熟悉该设备 / 手头工单已满 / 不在现场',
        inputValidator: (v) => (v && v.trim().length >= 2) || '请填写至少 2 个字的拒收原因',
      },
    )
    reason = value.trim()
  } catch { return }
  try {
    await request.post(`/work-orders/${row.id}/transition`, {
      to_status: 'SUBMITTED', remark: reason, source: 'TECH_REJECT',
    })
    ElMessage.success('已拒收，工单已回到待派工池')
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '拒收失败')
  }
}

const startingId = ref(null)
// 一键开始处理：ASSIGNED/ACCEPTED/ARRIVED/INSPECTING → IN_PROGRESS
const handleStart = async (row) => {
  startingId.value = row.id
  try {
    await request.post(`/work-orders/${row.id}/start`)
    ElMessage.success('已开始处理')
    fetchData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    startingId.value = null
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
  Object.assign(dispatch, {
    visible: true, row, technicianId: null,
    collaboratorIds: (row.collaborators || []).map((c) => c.id),
    remark: '', submitting: false,
  })
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
  if (dispatchNeedsReason.value && !String(dispatch.remark || '').trim()) {
    return ElMessage.warning('接单后改派必须填写原因')
  }
  // 已派单/已接单/已到场/检查中为同状态改派；待派工/草稿走正常派工
  const reassignStatuses = ['ASSIGNED', 'ACCEPTED', 'ARRIVED', 'INSPECTING']
  const toStatus = reassignStatuses.includes(dispatch.row?.status) ? dispatch.row.status : 'ASSIGNED'
  dispatch.submitting = true
  try {
    await request.post(`/work-orders/${dispatch.row.id}/transition`, {
      to_status: toStatus,
      technician_id: dispatch.technicianId,
      collaborator_ids: dispatch.collaboratorIds,
      source: 'SUPERVISOR_DISPATCH',
      remark: dispatch.remark || null,
    })
    ElMessage.success(isSelfDispatch.value ? '转派成功'
      : (dispatch.row?.status === 'SUBMITTED' ? '派工成功' : '改派成功'))
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
const isMineView = !!props.defaultMine
const isPoolView = !!props.poolMode
const statusFilter = ref('')
const orderTypeFilter = ref('')
const alertLevelFilter = ref('')
const ORDER_TYPE_LABEL = { REPAIR: '报修', MAINTENANCE: '保养', INSPECTION: '点检', IMPORT: '导入' }
const orderTypeLabel = (t) => ORDER_TYPE_LABEL[(t || 'REPAIR').toUpperCase()] || t
const dateRange = ref(null)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)

const statusOptions = [
  { value: 'DRAFT', label: '草稿', desc: '已建单未提交，可修改或删除' },
  { value: 'SUBMITTED', label: '待派工', desc: '已提交报修，等待派单或维修员领取' },
  { value: 'PROCESSING', label: '处理中', desc: '已派单、已接单、已到场、检查中、维修中，统一视为处理中' },
  { value: 'ARCHIVING', label: '待归档', desc: '维修完成，补齐 6 项归档字段后归档' },
  { value: 'ARCHIVED', label: '已归档', desc: '已结案，只读，可打印 PDF' },
  { value: 'REJECTED', label: '已退回', desc: '派单被退回或工单作废' },
]


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

const GROUP_LABEL = {
  DRAFT: '草稿',
  SUBMITTED: '待派工',
  ASSIGNED: '处理中', ACCEPTED: '处理中', ARRIVED: '处理中',
  INSPECTING: '处理中', IN_PROGRESS: '处理中',
  ARCHIVING: '待归档', COMPLETED: '待归档',
  ARCHIVED: '已归档', REJECTED: '已退回',
}
const statusLabel = (s) => statusMap[s] || GROUP_LABEL[s] || s
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

// 不同视图（全部工单 / 我的工单）各自独立记忆筛选，避免互相污染
const STORAGE_KEY = props.poolMode ? 'workorders_filter_pool'
  : (props.defaultMine ? `workorders_filter_${props.defaultMine}` : 'workorders_filter')

const fetchData = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (isPoolView) params.mine = 'pool'            // 工单池：我的 + 待领的
    else if (isMineView) params.mine = 'all'        // 我的工单：只看自己
    if (statusFilter.value) params.status_group = statusFilter.value
    if (orderTypeFilter.value) params.order_type = orderTypeFilter.value
    if (alertLevelFilter.value) params.alert_level = alertLevelFilter.value
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
  if (orderTypeFilter.value) data.order_type = orderTypeFilter.value
  if (alertLevelFilter.value) data.alert_level = alertLevelFilter.value
  if (dateRange.value) {
    data.date_from = dayjs(dateRange.value[0]).format('YYYY-MM-DD')
    data.date_to = dayjs(dateRange.value[1]).format('YYYY-MM-DD')
  }
  if (page.value > 1) data.page = page.value
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data))
}

// 我的工单视图（技术员）

// 我的工单（技术员视角）只保留与自己干活相关的状态
const MINE_STATUS_VALUES = ['PROCESSING', 'ARCHIVING', 'ARCHIVED']
const visibleStatusOptions = computed(() => {
  if (isPoolView) return statusOptions.filter((o) => o.value === 'SUBMITTED')
  if (isMineView) return statusOptions.filter((o) => MINE_STATUS_VALUES.includes(o.value))
  return statusOptions
})

const pickStatus = (val) => {
  statusFilter.value = val
  page.value = 1
  fetchData()
}

const handleSearch = () => { page.value = 1; fetchData() }

// P0 / 已超时的行加底色，列表里不用点开就能发现
const rowClassName = ({ row }) =>
  (row.alert_level === 'P0' || row.sla_status === 'OVERDUE') ? 'row-urgent' : ''

// 整行点击查看详情；点在操作按钮上时不跳转
const onRowClick = (row, column, event) => {
  const el = event?.target
  if (el?.closest?.('.op-cell, button, a, .el-dropdown')) return
  if (window.getSelection?.()?.toString()) return // 用户正在选文字
  router.push(`/work-orders/${row.id}`)
}
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
      if (data.order_type) orderTypeFilter.value = data.order_type
      if (data.alert_level) alertLevelFilter.value = data.alert_level
      if (data.date_from && data.date_to) {
        dateRange.value = [new Date(data.date_from), new Date(data.date_to)]
      }
      if (data.page) page.value = data.page
    } catch { /* ignore bad data */ }
  }
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
.filter-card { margin-bottom: 14px; }
.filter-bar { display: flex; gap: 8px; flex-wrap: nowrap; align-items: center; }
.filter-bar :deep(.el-date-editor) { flex: 0 0 232px; width: 232px; }
.filter-input { width: 200px; }
.filter-select { width: 128px; }
.action-btn { flex-shrink: 0; }
.secondary-btn { background: #fff; border-color: #d9d9d9; color: #333; }
.table-card { min-height: 300px; overflow: hidden; }
.muted { color: #C9CDD4; }
.collab-line { font-size: 11px; color: #86909C; line-height: 1.4; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fault-cell { display: flex; flex-direction: column; gap: 2px; line-height: 1.4; }
.fault-device { font-size: 12px; color: #86909C; }
.fault-desc { font-size: 13px; color: #1D2129; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.prio-cell { display: flex; align-items: center; gap: 6px; }
.wo-table :deep(.el-table__row.row-urgent) > td { background: #FFF6F6 !important; }
/* 表格统一行高，避免按钮把行撑高 */
.wo-table :deep(.el-table__cell) { padding: 8px 0; }
.wo-table :deep(.el-table__row) { cursor: pointer; }
.wo-table :deep(.el-table__row td:last-child) { cursor: default; }
.wo-table :deep(.el-button.is-link) { padding: 0 2px; height: auto; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }
.op-cell { display: flex; align-items: center; min-height: 28px; white-space: nowrap; }
.op-primary { display: flex; align-items: center; gap: 6px; margin-right: 0; }
.op-primary:empty { display: none; }
.op-actions { display: flex; align-items: center; gap: 4px; margin-right: 12px; }

.status-tag { display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 500; }
.status-DRAFT { background: #F2F3F5; color: #4E5969; }
.status-IN_PROGRESS { background: #FFF3E8; color: #FF7D00; }
.status-ARCHIVING { background: #FFF7E8; color: #FF8800; }
.status-ARCHIVED { background: #E8F8EE; color: #00B42A; }
.status-COMPLETED { background: #E8F8EE; color: #00B42A; }

.ellipsis-1 { display:inline-block; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

.status-help-icon {
  font-size: 16px;
  color: var(--ui-text-3, #86909C);
  cursor: help;
  margin-left: -4px;
  transition: color .15s;
}
.status-help-icon:hover { color: var(--color-primary, #0FC6C2); }
.status-help-title { font-size: 13px; font-weight: 600; margin-bottom: 8px; color: #1D2129; }
.status-help-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.status-help-desc { font-size: 12px; color: #4E5969; line-height: 1.5; }


/* 状态快捷筛选（独立一行，嵌在查询卡片内） */
.quick-bar {
  display: flex; align-items: center; flex-wrap: wrap;
  gap: 8px 10px;
  margin: 12px 0 0;
  padding: 10px 0 0;
  border-top: 1px dashed #EDEFF3;
}
.qb-label { font-size: 12.5px; color: #86909C; font-weight: 500; flex-shrink: 0; }
.qb-group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.quick-bar .chip {
  padding: 3px 11px; border-radius: 13px;
  font-size: 12.5px; line-height: 1.5;
  color: #4E5969; cursor: pointer;
  background: #F7F8FA; border: 1px solid transparent;
  transition: all .16s; white-space: nowrap;
}
.quick-bar .chip:hover { background: #fff; border-color: #0FC6C2; color: #0FC6C2; }
.quick-bar .chip.active {
  background: rgba(15,198,194,.12);
  border-color: rgba(15,198,194,.45);
  color: #0B9B98; font-weight: 600;
}
.quick-bar .qb-help { font-size: 14px; color: #C9CDD4; cursor: help; transition: color .15s; }
.quick-bar .qb-help:hover { color: #0FC6C2; }

/* 输入控件恢复原宽度 */
.filter-input { width: 200px !important; }
.filter-select { width: 128px !important; }
.filter-bar { gap: 8px !important; flex-wrap: nowrap; }
.filter-bar :deep(.el-date-editor) { flex: 1; min-width: 240px; }
.filter-date { width: auto !important; }

</style>
