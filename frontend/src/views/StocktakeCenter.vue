<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">盘点</h2>
      <div class="header-actions">
        <el-button @click="router.push('/stock?tab=movements')">盘点流水</el-button>
        <el-button v-if="isSupervisor" type="primary" @click="openCreate">新建盘点单</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-select v-model="filters.status" placeholder="全部状态" clearable style="width: 130px" @change="reload">
          <el-option v-for="s in STATUS" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-select v-model="filters.warehouse_id" placeholder="全部仓库" clearable style="width: 150px" @change="reload">
          <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
        </el-select>
        <el-button type="primary" @click="reload">查询</el-button>
        <div class="toolbar-tip">建单时锁定账面快照；审批时才按差异调整库存并记 ADJUST 流水</div>
      </div>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column label="盘点单号" width="190">
          <template #default="{ row }"><span class="mono">{{ row.take_no }}</span></template>
        </el-table-column>
        <el-table-column prop="warehouse_name" label="仓库" width="130" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTag(row.status)">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="120">
          <template #default="{ row }">
            <span :class="{ 'ok-text': row.item_count && row.counted_count === row.item_count }">
              {{ row.counted_count }} / {{ row.item_count }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="110">
          <template #default="{ row }">
            <span v-if="row.diff_count">{{ row.diff_count }} 项</span>
            <span v-else class="muted">无</span>
          </template>
        </el-table-column>
        <el-table-column label="差异金额" width="120" align="right">
          <template #default="{ row }">
            <span :class="row.diff_amount > 0 ? 'gain' : (row.diff_amount < 0 ? 'loss' : 'muted')">
              {{ row.diff_amount ? (row.diff_amount > 0 ? '+' : '') + row.diff_amount : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="created_by_name" label="创建人" width="100" />
        <el-table-column label="创建时间" width="140">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看 / 录入</el-button>
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

    <!-- 新建盘点单 -->
    <el-dialog v-model="create.visible" title="新建盘点单" width="520px" :close-on-click-modal="false">
      <el-form label-width="100px">
        <el-form-item label="盘点范围">
          <el-select v-model="create.warehouseId" clearable placeholder="全部仓库" style="width: 100%">
            <el-option v-for="w in warehouses" :key="w.id" :label="w.name" :value="w.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备类型">
          <el-input v-model="create.deviceType" placeholder="选填，例如 GPU服务器整机" />
        </el-form-item>
        <el-form-item label="备件关键词">
          <el-input v-model="create.keyword" placeholder="选填，按编码 / 名称过滤" />
        </el-form-item>
        <el-form-item label="含未归仓">
          <el-switch v-model="create.includeUnassigned" active-text="包含没设仓库的备件" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="create.remark" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="create.visible = false">取消</el-button>
        <el-button type="primary" :loading="create.submitting" @click="submitCreate">生成盘点单</el-button>
      </template>
    </el-dialog>

    <!-- 盘点详情 -->
    <el-drawer v-model="detail.visible" :title="detail.row ? `盘点单 ${detail.row.take_no}` : '盘点单'" size="72%">
      <template v-if="detail.row">
        <div class="detail-head">
          <div class="detail-meta">
            <span>仓库：<b>{{ detail.row.warehouse_name }}</b></span>
            <span>状态：<el-tag size="small" :type="statusTag(detail.row.status)">{{ detail.row.status_label }}</el-tag></span>
            <span>已盘：<b>{{ detail.row.counted_count }} / {{ detail.row.item_count }}</b></span>
            <span>差异：<b>{{ detail.row.diff_count }} 项</b></span>
            <span>差异金额：<b>{{ detail.row.diff_amount }}</b></span>
          </div>
          <div class="detail-actions">
            <el-button v-if="canCount" size="small" @click="saveCount">保存实盘</el-button>
            <el-button v-if="canCount" size="small" type="primary" @click="submitTake">提交盘点</el-button>
            <el-button v-if="detail.row.status === 'SUBMITTED' && isSupervisor" size="small" type="primary" @click="approveTake">审批通过</el-button>
            <el-button v-if="canCancel" size="small" type="danger" plain @click="cancelTake">作废</el-button>
          </div>
        </div>

        <el-table :data="detail.items" v-loading="detail.loading" stripe size="small" max-height="560">
          <el-table-column label="备件" min-width="200">
            <template #default="{ row }">
              <div class="cell-main">{{ row.part_name }}</div>
              <div class="cell-sub">{{ row.part_code }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="location_text" label="库位" width="110" />
          <el-table-column label="账面" width="90" align="right">
            <template #default="{ row }">{{ row.system_qty }}</template>
          </el-table-column>
          <el-table-column label="实盘" width="140" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="canCount" v-model="row.actual_qty" :min="0" :precision="2" size="small"
                :controls="false" style="width: 100%"
              />
              <span v-else>{{ row.actual_qty ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" width="90" align="right">
            <template #default="{ row }">
              <span v-if="row.actual_qty === null || row.actual_qty === undefined" class="muted">—</span>
              <span v-else :class="diffOf(row) > 0 ? 'gain' : (diffOf(row) < 0 ? 'loss' : '')">
                {{ diffOf(row) > 0 ? '+' : '' }}{{ diffOf(row) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="差异金额" width="100" align="right">
            <template #default="{ row }">
              <span v-if="row.actual_qty === null || row.actual_qty === undefined" class="muted">—</span>
              <span v-else>{{ (diffOf(row) * row.unit_price).toFixed(2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原因" min-width="150">
            <template #default="{ row }">
              <el-input v-if="canCount" v-model="row.reason" size="small" maxlength="100" placeholder="差异原因（选填）" />
              <span v-else>{{ row.reason || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="detail-foot">
          <span class="muted">审批通过后按「实盘 − 账面」生成 ADJUST 流水，盘亏时超出库存的预占会自动下调</span>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'

const router = useRouter()
const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const isSupervisor = currentUser.role === 'ADMIN' || currentUser.role === 'SUPERVISOR'

const STATUS = [
  { value: 'DRAFT', label: '草稿' },
  { value: 'COUNTING', label: '盘点中' },
  { value: 'SUBMITTED', label: '待审批' },
  { value: 'APPROVED', label: '已审批' },
  { value: 'CANCELLED', label: '已作废' },
]
const statusTag = (s) => ({
  DRAFT: 'info', COUNTING: 'warning', SUBMITTED: 'primary',
  APPROVED: 'success', CANCELLED: 'info',
}[s] || 'info')

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const warehouses = ref([])
const filters = reactive({ status: '', warehouse_id: null })

const fmt = (t) => (t ? String(t).replace('T', ' ').slice(0, 16) : '—')
const diffOf = (row) => Number(((row.actual_qty || 0) - row.system_qty).toFixed(2))

const load = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (filters.status) params.status = filters.status
    if (filters.warehouse_id) params.warehouse_id = filters.warehouse_id
    const res = await request.get('/stocktakes/', { params })
    rows.value = res.items || []
    total.value = res.total || 0
  } catch { /* ignore */ } finally { loading.value = false }
}
const reload = () => { page.value = 1; load() }

const loadWarehouses = async () => {
  try {
    const res = await request.get('/warehouses/')
    warehouses.value = res.items || []
  } catch { warehouses.value = [] }
}

// ---------- 新建 ----------
const create = reactive({
  visible: false, warehouseId: null, deviceType: '', keyword: '',
  includeUnassigned: true, remark: '', submitting: false,
})
const openCreate = () => {
  Object.assign(create, {
    visible: true, warehouseId: null, deviceType: '', keyword: '',
    includeUnassigned: true, remark: '', submitting: false,
  })
}
const submitCreate = async () => {
  create.submitting = true
  try {
    const res = await request.post('/stocktakes/', {
      warehouse_id: create.warehouseId || null,
      device_type: create.deviceType || null,
      keyword: create.keyword || null,
      include_unassigned: create.includeUnassigned,
      remark: create.remark || null,
    })
    ElMessage.success(`已生成盘点单 ${res.take_no}，共 ${res.item_count} 项`)
    create.visible = false
    reload()
  } catch { /* ignore */ } finally { create.submitting = false }
}

// ---------- 详情 / 录入 ----------
const detail = reactive({ visible: false, row: null, items: [], loading: false })
const canCount = computed(() => detail.row && ['DRAFT', 'COUNTING'].includes(detail.row.status))
const canCancel = computed(() => detail.row && ['DRAFT', 'COUNTING', 'SUBMITTED'].includes(detail.row.status) && isSupervisor)

const openDetail = async (row) => {
  detail.visible = true
  detail.row = row
  detail.loading = true
  try {
    const res = await request.get(`/stocktakes/${row.id}`)
    detail.row = res
    detail.items = (res.items || []).map((i) => ({ ...i }))
  } catch { detail.items = [] } finally { detail.loading = false }
}

const saveCount = async (silent = false) => {
  const items = detail.items
    .filter((i) => i.actual_qty !== null && i.actual_qty !== undefined)
    .map((i) => ({ item_id: i.id, actual_qty: i.actual_qty, reason: i.reason || null }))
  if (!items.length) {
    if (!silent) ElMessage.warning('还没有录入任何实盘数')
    return false
  }
  try {
    await request.post(`/stocktakes/${detail.row.id}/count`, { items })
    if (!silent) ElMessage.success(`已保存 ${items.length} 项实盘数`)
    return true
  } catch { return false }
}

const submitTake = async () => {
  try {
    await ElMessageBox.confirm('提交后不能再改实盘数，确认提交？', '提交盘点', { type: 'warning' })
  } catch { return }
  const ok = await saveCount(true)
  if (!ok) return
  try {
    await request.post(`/stocktakes/${detail.row.id}/submit`)
    ElMessage.success('已提交，等待审批')
    await openDetail(detail.row)
    load()
  } catch { /* ignore */ }
}

const approveTake = async () => {
  try {
    await ElMessageBox.confirm(
      '审批后会按差异调整库存并生成流水，这一步不可逆（只能走反向单据）。',
      '审批盘点单', { confirmButtonText: '确认审批', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  try {
    const res = await request.post(`/stocktakes/${detail.row.id}/approve`, {})
    ElMessage.success(`已审批，调整 ${res.adjusted_items} 项，差异金额 ${res.diff_amount}`)
    await openDetail(detail.row)
    load()
  } catch { /* ignore */ }
}

const cancelTake = async () => {
  try {
    await ElMessageBox.confirm('作废后这张盘点单不再生效，确定？', '作废盘点单', { type: 'warning' })
  } catch { return }
  try {
    await request.post(`/stocktakes/${detail.row.id}/cancel`)
    ElMessage.success('已作废')
    await openDetail(detail.row)
    load()
  } catch { /* ignore */ }
}

onMounted(async () => {
  await loadWarehouses()
  load()
})
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
.ok-text { color: #00B42A; font-weight: 600; }
.gain { color: #00B42A; }
.loss { color: #F53F3F; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 14px; }
.detail-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.detail-meta { display: flex; gap: 18px; align-items: center; font-size: 13px; color: #4E5969; flex-wrap: wrap; }
.detail-actions { display: flex; gap: 8px; }
.detail-foot { margin-top: 10px; font-size: 12px; }
</style>
