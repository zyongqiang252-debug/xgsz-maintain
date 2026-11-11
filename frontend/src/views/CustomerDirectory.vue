<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">客户</h2>
        <span class="page-sub">只读：可查看有哪些客户、客户名下的工单与负责人；客户资料由管理员/主管维护</span>
      </div>
    </div>

    <el-card class="filter-card" shadow="never">
      <div class="filter-bar">
        <el-input
          v-model="keyword" placeholder="搜索客户编码 / 名称 / 公司 / 电话" clearable class="filter-input"
          @clear="load" @keyup.enter="load"
        />
        <el-select v-model="level" placeholder="客户级别" clearable class="filter-select" @change="load">
          <el-option label="普通" value="NORMAL" />
          <el-option label="重点" value="KEY" />
          <el-option label="VIP" value="VIP" />
        </el-select>
        <el-select v-model="active" placeholder="状态" clearable class="filter-select" @change="load">
          <el-option label="启用" :value="true" />
          <el-option label="停用" :value="false" />
        </el-select>
        <el-button type="primary" class="action-btn" @click="load">查询</el-button>
        <el-button class="action-btn secondary-btn" @click="reset">重置</el-button>
      </div>
    </el-card>

    <el-card class="table-card" shadow="never">
      <el-table :data="list" v-loading="loading" stripe @row-click="openDrawer">
        <el-table-column label="客户 / 公司" min-width="210" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="cust-cell">
              <span class="cust-name">{{ row.company || row.name }}</span>
              <span class="cust-sub">
                <span class="mono">{{ row.code }}</span>
                <span v-if="row.company && row.name"> · {{ row.name }}</span>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="levelTag(row.level)" effect="plain">{{ row.level_label || row.level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="联系人 / 电话" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="cust-cell">
              <span>{{ row.name || '—' }}</span>
              <span class="cust-sub">{{ row.phone || '—' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="设备" width="64" align="right">
          <template #default="{ row }">{{ row.device_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="工单" width="96" align="center">
          <template #default="{ row }">
            <span class="order-count" :class="{ 'has-open': row.open_count > 0 }">
              在办 {{ row.open_count ?? 0 }} / 共 {{ row.order_count ?? 0 }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="最近报修" width="112">
          <template #default="{ row }">{{ fmt(row.last_order_at) }}</template>
        </el-table-column>
        <el-table-column label="满意度" width="76" align="center">
          <template #default="{ row }">
            <span v-if="row.avg_satisfaction" class="score">{{ row.avg_satisfaction }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <span class="status-dot" :class="row.is_active ? 'active' : 'inactive'">{{ row.is_active ? '启用' : '停用' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openDrawer(row)">查看工单</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState icon="search" title="没有找到符合条件的客户" hint="试试调整筛选条件，或清空搜索后重新查询" />
        </template>
      </el-table>
    </el-card>

    <!-- 客户工单抽屉 -->
    <el-drawer v-model="drawer.visible" :title="drawer.row ? `${drawer.row.company || drawer.row.name} · 工单` : '客户工单'" size="720px">
      <template v-if="drawer.row">
        <el-descriptions :column="2" border size="small" class="cust-desc">
          <el-descriptions-item label="客户编码">{{ drawer.row.code }}</el-descriptions-item>
          <el-descriptions-item label="客户级别">{{ drawer.row.level_label || drawer.row.level }}</el-descriptions-item>
          <el-descriptions-item label="联系人">{{ drawer.row.name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="联系电话">{{ drawer.row.phone || '—' }}</el-descriptions-item>
          <el-descriptions-item label="地址 / 机房" :span="2">{{ drawer.row.address || '—' }}</el-descriptions-item>
          <el-descriptions-item label="归属人">{{ drawer.row.owner_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="SLA">
            响应 {{ drawer.row.sla_response_hours ?? '—' }}h / 修复 {{ drawer.row.sla_resolve_hours ?? '—' }}h
          </el-descriptions-item>
        </el-descriptions>

        <div class="drawer-head">
          <span>工单共 <b>{{ drawer.total }}</b> 单<span v-if="drawer.row.open_count">（在办 {{ drawer.row.open_count }}）</span></span>
          <span class="drawer-sub">本人负责的可进入处理；其他人负责的仅只读查看</span>
        </div>
        <el-table :data="drawer.rows" v-loading="drawer.loading" stripe size="small" @row-click="openOrder">
          <el-table-column label="工单号" width="150" show-overflow-tooltip>
            <template #default="{ row }"><span class="mono">{{ row.work_order_no }}</span></template>
          </el-table-column>
          <el-table-column label="故障" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.fault_description || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="76">
            <template #default="{ row }">{{ statusLabel(row.status) }}</template>
          </el-table-column>
          <el-table-column label="负责人" width="88" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.technician_name">{{ row.technician_name }}</span>
              <span v-else class="muted">未指派</span>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="96">
            <template #default="{ row }">{{ fmt(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="76">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="openOrder(row)">
                {{ canOperate(row) ? '进入' : '只读' }}
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <EmptyState title="该客户还没有工单" hint="客户通过报修门户提交后会出现在这里" />
          </template>
        </el-table>
        <div v-if="drawer.total > drawer.pageSize" class="drawer-pager">
          <el-pagination
            v-model:current-page="drawer.page" :page-size="drawer.pageSize" :total="drawer.total"
            layout="prev, pager, next" small @current-change="loadOrders"
          />
        </div>
      </template>
    </el-drawer>

    <!-- 他人负责的工单：客户页内只读查看，不进入工单模块 -->
    <el-dialog
      v-model="readonly.visible" append-to-body width="760px"
      :title="readonly.data ? `工单 ${readonly.data.work_order_no}（只读）` : '工单详情（只读）'"
    >
      <div v-loading="readonly.loading" style="min-height:120px">
        <template v-if="readonly.data">
          <el-alert
            type="info" :closable="false" show-icon
            :title="`该工单由 ${readonly.data.technician_name || '未指派人员'} 负责，你只能查看处理过程，不能操作`"
          />
          <el-descriptions :column="2" border size="small" class="ro-desc">
            <el-descriptions-item label="状态">{{ statusLabel(readonly.data.status) }}</el-descriptions-item>
            <el-descriptions-item label="设备">{{ readonly.data.device_code || '—' }}</el-descriptions-item>
            <el-descriptions-item label="负责人">{{ readonly.data.technician_name || '未指派' }}</el-descriptions-item>
            <el-descriptions-item label="工时">{{ readonly.data.work_hours ?? '—' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ fmt(readonly.data.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="完成时间">{{ fmt(readonly.data.resolved_at) }}</el-descriptions-item>
            <el-descriptions-item label="故障描述" :span="2">{{ readonly.data.fault_description || '—' }}</el-descriptions-item>
            <el-descriptions-item label="故障现象" :span="2">{{ readonly.data.fault_phenomenon || '—' }}</el-descriptions-item>
            <el-descriptions-item label="根本原因" :span="2">{{ readonly.data.root_cause || '—' }}</el-descriptions-item>
            <el-descriptions-item label="处理步骤" :span="2">{{ readonly.data.solution_steps || '—' }}</el-descriptions-item>
            <el-descriptions-item label="维修结果" :span="2">{{ readonly.data.repair_result || '—' }}</el-descriptions-item>
          </el-descriptions>
          <div class="ro-title">处理过程</div>
          <el-timeline v-if="readonly.data.progress && readonly.data.progress.length">
            <el-timeline-item
              v-for="p in readonly.data.progress" :key="p.id"
              :timestamp="fmt(p.created_at)" placement="top"
            >
              <div class="ro-log">
                <span class="ro-log-status">{{ statusLabel(p.from_status) }} → {{ statusLabel(p.to_status) }}</span>
                <span class="ro-log-op">{{ p.operator_name || '系统' }}</span>
                <div v-if="p.remark" class="ro-log-remark">{{ p.remark }}</div>
              </div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无处理记录" :image-size="60" />
        </template>
      </div>
      <template #footer>
        <el-button plain @click="readonly.visible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import request from '../api'
import EmptyState from '../components/EmptyState.vue'

const router = useRouter()

const list = ref([])
const loading = ref(false)
const keyword = ref('')
const level = ref('')
const active = ref(null)
const drawer = reactive({
  visible: false, row: null, rows: [], total: 0, page: 1, pageSize: 20, loading: false,
})
const readonly = reactive({ visible: false, loading: false, data: null })
const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
// 本人负责（或管理员/主管）才能进入工单模块；其他人负责的工单只在客户页只读查看
const canOperate = (row) => {
  if (['ADMIN', 'SUPERVISOR'].includes(currentUser.role)) return true
  return !!currentUser.id && (row.technician_id === currentUser.id || row.assignee_id === currentUser.id)
}

const levelTag = (l) => ({ VIP: 'danger', KEY: 'warning', NORMAL: 'info' }[l] || 'info')
const fmt = (t) => (t ? String(t).replace('T', ' ').slice(5, 16) : '—')
const statusLabel = (s) => ({
  DRAFT: '草稿', SUBMITTED: '待派工', ASSIGNED: '已派单', ACCEPTED: '已接单',
  ARRIVED: '已到场', INSPECTING: '检查中', IN_PROGRESS: '处理中',
  COMPLETED: '已完成', ARCHIVING: '待归档', ARCHIVED: '已归档', REJECTED: '已退回',
}[s] || s || '—')

const load = async () => {
  loading.value = true
  try {
    const params = {}
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (level.value) params.level = level.value
    if (active.value !== null && active.value !== '') params.active = active.value
    const res = await request.get('/customers/', { params })
    list.value = res.items || []
  } catch { list.value = [] } finally { loading.value = false }
}
const reset = () => { keyword.value = ''; level.value = ''; active.value = null; load() }

const loadOrders = async () => {
  if (!drawer.row) return
  drawer.loading = true
  try {
    const res = await request.get(`/customers/${drawer.row.id}/orders`, {
      params: { page: drawer.page, page_size: drawer.pageSize },
    })
    drawer.rows = res.items || []
    drawer.total = res.total || 0
  } catch { drawer.rows = []; drawer.total = 0 } finally { drawer.loading = false }
}

const openDrawer = (row) => {
  drawer.row = row
  drawer.page = 1
  drawer.visible = true
  loadOrders()
}
const openOrder = (row) => {
  if (canOperate(row)) {
    drawer.visible = false
    router.push({ path: `/work-orders/${row.id}`, query: { from: 'customers' } })
    return
  }
  // 他人负责：留在客户页，只读弹窗
  readonly.visible = true
  readonly.loading = true
  readonly.data = null
  request.get(`/customers/${drawer.row.id}/orders/${row.id}`)
    .then((res) => { readonly.data = res })
    .catch(() => { readonly.visible = false })
    .finally(() => { readonly.loading = false })
}

onMounted(load)
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary, #1D2129); }
.page-sub { font-size: 12px; color: #86909C; }
.filter-card { margin-bottom: 12px; }
.filter-bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.filter-input { width: 280px; }
.filter-select { width: 130px; }
.action-btn { min-width: 64px; }
.secondary-btn { color: #4E5969; }

.cust-cell { display: flex; flex-direction: column; line-height: 1.35; }
.cust-name { color: #1D2129; font-size: 13px; }
.cust-sub { color: #86909C; font-size: 11px; }
.mono { font-family: ui-monospace, Consolas, monospace; }
.order-count { font-size: 12px; color: #4E5969; white-space: nowrap; }
.order-count.has-open { color: #F53F3F; }
.score { color: #FF7D00; font-weight: 600; }
.muted { color: #C9CDD4; }
.status-dot { font-size: 12px; color: #86909C; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.status-dot::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: #C9CDD4; }
.status-dot.active::before { background: #00B42A; }
.status-dot.inactive { color: #C9CDD4; }

.cust-desc { margin-bottom: 14px; }
.drawer-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 13px; color: #4E5969; }
.drawer-head b { color: #0FC6C2; font-size: 15px; }
.drawer-sub { font-size: 12px; color: #86909C; }
.drawer-pager { display: flex; justify-content: flex-end; margin-top: 10px; }

.ro-desc { margin-top: 12px; }
.ro-title { font-size: 14px; font-weight: 600; color: #1D2129; margin: 18px 0 10px; }
.ro-log-status { font-size: 13px; font-weight: 500; color: #1D2129; }
.ro-log-op { margin-left: 8px; font-size: 12px; color: #86909C; }
.ro-log-remark { margin-top: 4px; font-size: 12.5px; color: #4E5969; white-space: pre-wrap; line-height: 1.6; }
</style>
