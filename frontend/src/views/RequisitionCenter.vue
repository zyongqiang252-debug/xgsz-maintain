<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">领用审批</h2>
      <div class="header-actions">
        <el-button type="primary" @click="openCreate">提交领用申请</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-select v-model="status" placeholder="全部状态" clearable style="width: 150px" @change="reload">
          <el-option v-for="s in STATUS" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-checkbox v-model="mine" @change="reload">只看我的</el-checkbox>
        <div class="toolbar-tip">审批通过只预占库存，「出库」才真正扣减（与库存中心的出库是同一个动作）</div>
        <el-button style="margin-left: auto" @click="load">刷新</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="申请" width="70">
          <template #default="{ row }"><span class="mono">#{{ row.id }}</span></template>
        </el-table-column>
        <el-table-column label="备件" min-width="160">
          <template #default="{ row }">
            <div class="cell-main">{{ row.part_name }}</div>
            <div class="cell-sub">{{ row.part_code }}</div>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="80" align="right">
          <template #default="{ row }">{{ row.quantity }} {{ row.unit || '' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tooltip v-if="row.status === 'REJECTED' && row.reject_reason"
                        :content="`驳回原因：${row.reject_reason}`" placement="top">
              <el-tag size="small" :type="statusTag(row.status)" class="clickable-tag">
                {{ statusLabel(row.status) }}
              </el-tag>
            </el-tooltip>
            <el-tag v-else size="small" :type="statusTag(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="关联工单" width="100">
          <template #default="{ row }">
            <el-link v-if="row.work_order_id" type="primary" @click="router.push(`/work-orders/${row.work_order_id}`)">
              #{{ row.work_order_id }}
            </el-link>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="applicant_name" label="申请人" width="100" />
        <el-table-column label="审批人 / 时间" width="130">
          <template #default="{ row }">
            <div class="cell-main">{{ row.approver_name || '—' }}</div>
            <div class="cell-sub">{{ fmt(row.approved_at || row.created_at) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="事由" min-width="100" show-overflow-tooltip />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <div v-if="hasActions(row)" class="row-actions">
              <template v-if="isSupervisor && row.status === 'PENDING'">
                <el-button link type="primary" @click="approve(row)">通过</el-button>
              </template>
              <el-button v-if="canIssue(row)" link type="primary" @click="issue(row)">出库</el-button>
              <el-button
                v-if="isSupervisor && (row.status === 'PENDING' || row.status === 'APPROVED')"
                link type="danger" @click="reject(row)"
              >驳回</el-button>
              <el-button v-if="canCancel(row)" link type="info" @click="cancel(row)">撤销</el-button>
            </div>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page" :page-size="pageSize" :total="total"
          layout="total, prev, pager, next" @current-change="load"
        />
      </div>
    </el-card>

    <el-dialog v-model="create.visible" title="提交领用申请" width="540px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="备件" required>
          <el-select
            v-model="create.partId" filterable remote clearable
            :remote-method="searchParts" :loading="parts.loading"
            placeholder="输入编码 / 名称搜索" style="width: 100%" @change="onPartChange"
          >
            <el-option v-for="p in parts.options" :key="p.id" :label="`${p.part_code} ${p.part_name}`" :value="p.id">
              <div class="opt-row">
                <span class="opt-main">{{ p.part_code }} · {{ p.part_name }}</span>
                <span class="opt-meta">可用 {{ p.available_quantity ?? p.stock_quantity }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="领用数量" required>
          <el-input-number v-model="create.quantity" :min="0.01" :step="1" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="关联工单" :required="!isSupervisor">
          <el-select
            v-model="create.workOrderId" filterable remote clearable
            :remote-method="searchOrders" :loading="orders.loading"
            :placeholder="isSupervisor ? '选填，输入工单号 / 故障描述搜索' : '技术员必填：输入工单号 / 故障描述搜索'" style="width: 100%"
          >
            <el-option v-for="w in orders.options" :key="w.id" :label="`${w.work_order_no} · ${w.fault_description || ''}`" :value="w.id" />
          </el-select>
          <div v-if="!isSupervisor" class="field-tip">技术员领用必须关联工单，备件成本才会自动计入该维修单</div>
        </el-form-item>
        <el-form-item label="领用事由">
          <el-input v-model="create.reason" type="textarea" :rows="2" maxlength="200" placeholder="例如：GPU 服务器 Xid 48 更换显存" />
        </el-form-item>
        <div v-if="selectedPart" class="stock-hint">
          现存 <b>{{ selectedPart.stock_quantity }}</b> · 已预占 <b>{{ selectedPart.reserved_quantity || 0 }}</b> ·
          可用 <b>{{ selectedPart.available_quantity ?? selectedPart.stock_quantity }}</b> {{ selectedPart.unit || '' }}
        </div>
      </el-form>
      <template #footer>
        <el-button @click="create.visible = false">取消</el-button>
        <el-button type="primary" :loading="create.submitting" @click="submitCreate">提交申请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'

const router = useRouter()
const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const isSupervisor = currentUser.role === 'ADMIN' || currentUser.role === 'SUPERVISOR'

const STATUS = [
  { value: 'PENDING', label: '待审批' },
  { value: 'APPROVED', label: '已批准（已预占）' },
  { value: 'ISSUED', label: '已出库' },
  { value: 'REJECTED', label: '已驳回' },
  { value: 'CANCELLED', label: '已撤销' },
]

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const status = ref('')
const mine = ref(!isSupervisor)

const fmt = (t) => (t ? String(t).replace('T', ' ').slice(0, 16) : '—')
const statusLabel = (s) => ({
  PENDING: '待审批', APPROVED: '已预占', ISSUED: '已出库',
  REJECTED: '已驳回', CANCELLED: '已撤销',
}[s] || s)
const statusTag = (s) => ({
  PENDING: 'warning', APPROVED: 'primary', ISSUED: 'success',
  REJECTED: 'danger', CANCELLED: 'info',
}[s] || 'info')

const load = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (status.value) params.status = status.value
    if (mine.value) params.mine = true
    const res = await request.get('/spare-parts/requisitions/', { params })
    rows.value = res.items || []
    total.value = res.total || 0
  } catch { /* 拦截器已提示 */ } finally { loading.value = false }
}
const reload = () => { page.value = 1; load() }

// ---------- 新建申请 ----------
const parts = reactive({ options: [], loading: false })
const orders = reactive({ options: [], loading: false })
const selectedPart = ref(null)
const create = reactive({ visible: false, partId: null, quantity: 1, workOrderId: null, reason: '', submitting: false })

const searchParts = async (kw = '') => {
  parts.loading = true
  try {
    const res = await request.get('/spare-parts/', { params: { keyword: kw, page_size: 20 } })
    parts.options = res.items || []
  } catch { parts.options = [] } finally { parts.loading = false }
}
const searchOrders = async (kw = '') => {
  orders.loading = true
  try {
    const res = await request.get('/work-orders/', { params: { keyword: kw, page_size: 20 } })
    orders.options = res.items || []
  } catch { orders.options = [] } finally { orders.loading = false }
}
const onPartChange = (id) => {
  selectedPart.value = parts.options.find((p) => p.id === id) || null
}
const openCreate = () => {
  Object.assign(create, { visible: true, partId: null, quantity: 1, workOrderId: null, reason: '', submitting: false })
  selectedPart.value = null
  searchParts('')
}
const submitCreate = async () => {
  if (!create.partId) return ElMessage.warning('请选择备件')
  if (!(create.quantity > 0)) return ElMessage.warning('领用数量要大于 0')
  if (!isSupervisor && !create.workOrderId) return ElMessage.warning('技术员领用必须关联工单')
  create.submitting = true
  try {
    await request.post('/spare-parts/requisitions/', {
      part_id: create.partId,
      quantity: create.quantity,
      work_order_id: create.workOrderId || null,
      reason: create.reason || null,
    })
    ElMessage.success('已提交，等待主管审批')
    create.visible = false
    reload()
  } catch { /* 拦截器已提示 */ } finally { create.submitting = false }
}

// ---------- 审批 / 发料 / 撤销 ----------
const approve = async (row) => {
  try {
    await ElMessageBox.confirm(
      `通过后会给 ${row.part_name} 预占 ${row.quantity}${row.unit || ''}，库存暂不扣减。`,
      '审批通过', { confirmButtonText: '通过', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  try {
    const res = await request.post(`/spare-parts/requisitions/${row.id}/approve`)
    ElMessage.success(`已批准，当前可用 ${res.available_quantity}`)
    load()
  } catch { /* ignored */ }
}

const reject = async (row) => {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt('驳回后如已预占会立即释放', '驳回领用申请', {
      confirmButtonText: '确认驳回', cancelButtonText: '取消',
      inputType: 'textarea',
      inputValidator: (v) => (v && v.trim().length >= 2) || '请填写至少 2 个字的原因',
    })
    reason = value
  } catch { return }
  try {
    await request.post(`/spare-parts/requisitions/${row.id}/reject`, { reject_reason: reason.trim() })
    ElMessage.success('已驳回')
    load()
  } catch { /* ignored */ }
}

const issue = async (row) => {
  try {
    await ElMessageBox.confirm(
      `出库会扣减库存 ${row.quantity}${row.unit || ''} 并释放预占，同时计入工单成本。`,
      '出库确认', { confirmButtonText: '确认出库', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  try {
    const res = await request.post(`/spare-parts/requisitions/${row.id}/issue`, {})
    ElMessage.success(`已出库，现存 ${res.stock_quantity}`)
    load()
  } catch { /* ignored */ }
}

// 谁能出库：主管/管理员可代发；申请人本人可对自己的「已批准」单自助出库（与库存中心出库同一动作）
const canIssue = (row) =>
  row.status === 'APPROVED' && (isSupervisor || row.applicant_id === currentUser.id)


const hasActions = (row) =>
  canIssue(row) || canCancel(row) ||
  (isSupervisor && (row.status === 'PENDING' || row.status === 'APPROVED'))

const canCancel = (row) =>
  ['PENDING', 'APPROVED'].includes(row.status) &&
  (isSupervisor || row.applicant_id === currentUser.id)

const cancel = async (row) => {
  try {
    await ElMessageBox.confirm('撤销后如已预占会立即释放，确定撤销？', '撤销申请', { type: 'warning' })
  } catch { return }
  try {
    await request.post(`/spare-parts/requisitions/${row.id}/cancel`)
    ElMessage.success('已撤销')
    load()
  } catch { /* ignored */ }
}

onMounted(load)
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary, #1D2129); }
.header-actions { display: flex; gap: 8px; }
.toolbar { display: flex; gap: 10px; align-items: center; margin-bottom: 14px; flex-wrap: wrap; }
.toolbar-tip { font-size: 12px; color: #86909C; }
.mono { font-family: ui-monospace, Menlo, Consolas, monospace; color: #4E5969; }
.cell-main { font-size: 13px; color: #1D2129; line-height: 1.4; }
.cell-sub { font-size: 12px; color: #86909C; line-height: 1.4; }
.muted { color: #C9CDD4; }
.row-actions { display: flex; align-items: center; gap: 12px; flex-wrap: nowrap; white-space: nowrap; }
.row-actions :deep(.el-button) { margin-left: 0; padding: 0; height: auto; font-size: 13px; }
.row-actions :deep(.el-button + .el-button) { margin-left: 0; }
.clickable-tag { cursor: help; }
.stock-hint { margin: 4px 0 0 90px; padding: 8px 10px; background: #F7F8FA; border-radius: 6px; font-size: 12.5px; color: #4E5969; }
.field-tip { font-size: 12px; color: #FF7D00; line-height: 1.5; margin-top: 2px; }
.stock-hint b { color: #0FC6C2; }
.opt-row { display: flex; justify-content: space-between; gap: 12px; }
.opt-main { overflow: hidden; text-overflow: ellipsis; }
.opt-meta { color: #86909C; font-size: 12px; flex-shrink: 0; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 14px; }
</style>
