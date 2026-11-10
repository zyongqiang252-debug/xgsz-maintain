<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">库存管理</h2>
      <div class="header-actions">
        <el-button v-if="canManage" type="primary" plain @click="openIn()">入库</el-button>
        <el-button v-if="canManage" type="warning" plain @click="openOut()">出库</el-button>
        <el-button v-if="canManage" @click="importDialog.visible = true">进货单导入</el-button>
        <div style="display:flex;gap:8px">
        <el-button :loading="exporting" @click="handleExport">导出 Excel</el-button>
        <el-button v-if="canManage" type="primary" @click="$router.push('/spare-parts/new')">新增备件</el-button>
      </div>
      </div>
    </div>

    <!-- 库存预警横幅 -->
    <div v-if="alerts.alert_count > 0" class="alert-banner">
      <el-alert
        :title="`库存预警：${alerts.out_of_stock_count} 项缺货、${alerts.low_stock_count} 项低库存，共 ${alerts.alert_count} 项需关注`"
        type="warning"
        show-icon
        :closable="false"
      >
        <template #default>
          <el-button size="small" type="warning" plain @click="showAlerts = true; handleAlertFilter()">查看详情</el-button>
        </template>
      </el-alert>
    </div>

    <!-- 筛选栏 -->
    <el-card class="filter-card" shadow="never">
      <div class="filter-bar">
        <el-input v-model="keyword" placeholder="搜索编码/名称/规格" clearable class="filter-input" @clear="handleSearch" @keyup.enter="handleSearch" />
        <el-select v-model="typeFilter" placeholder="设备类型" clearable class="filter-select" @change="handleSearch">
          <el-option v-for="d in deviceTypeOptions" :key="d.value" :label="d.label" :value="d.value" />
        </el-select>
        <el-select v-model="stockFilter" placeholder="库存状态" clearable class="filter-select" @change="handleSearch">
          <el-option label="库存充足" value="sufficient" />
          <el-option label="库存不足" value="low_stock" />
          <el-option label="已缺货" value="out_of_stock" />
        </el-select>
        <el-select
          v-model="snSearchValue" filterable remote clearable reserve-keyword
          :remote-method="searchInstances" :loading="snSearching"
          placeholder="按 SN / 设备搜实物" class="sn-search" @change="jumpToInstance"
        >
          <el-option
            v-for="i in snOptions" :key="i.id"
            :label="`${i.sn || '散件#' + i.id} · ${i.part_code}`" :value="i.id"
          >
            <div class="sn-opt">
              <span class="sn-main">{{ i.sn || ('散件 #' + i.id) }}</span>
              <span class="sn-meta">
                {{ i.part_code }} · {{ i.status_label }}<template v-if="i.device_code"> · {{ i.device_code }}</template>
              </span>
            </div>
          </el-option>
          <template #empty>
            <div class="sn-empty">输入至少 2 个字符，按 SN / 备件编码 / 设备编码搜索</div>
          </template>
        </el-select>
        <el-button type="primary" @click="handleSearch" class="action-btn">查询</el-button>
        <el-button class="action-btn secondary-btn" @click="handleReset">重置</el-button>
      </div>
    </el-card>

    <!-- 数据表格 -->
    <el-card class="table-card" shadow="never">
      <el-table ref="tableRef" :data="list" stripe class="sp-table" @sort-change="onSortChange" @row-click="onPartRowClick">
        <el-table-column prop="part_code" label="备件编码" width="128" show-overflow-tooltip />
        <el-table-column prop="part_name" label="备件名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="specification" label="规格型号" width="118" show-overflow-tooltip />
        <el-table-column prop="unit" label="单位" width="52" align="center" />
        <el-table-column
          prop="stock_quantity" label="库存" width="88" align="right"
          sortable="custom" :sort-orders="['ascending', 'descending', null]"
        >
          <template #header>
            <span class="stock-sort" :class="stockSortOrder || 'none'" title="点击切换升序 / 降序">
              库存
              <el-icon class="sort-arrow">
                <SortUp v-if="stockSortOrder === 'ascending'" />
                <SortDown v-else-if="stockSortOrder === 'descending'" />
                <Sort v-else />
              </el-icon>
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="safety_stock" label="安全库存" width="76" align="right" />
        <el-table-column label="状态" width="72" align="center">
          <template #default="{ row }">
            <span class="soft-tag" :class="stockSoftClass(row)">{{ stockLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unit_price" label="单价" width="96" align="right" />
        <el-table-column prop="location" label="存放位置" width="106" show-overflow-tooltip />
        <el-table-column label="操作" width="150" header-align="left">
          <template #default="{ row }">
            <div class="action-group">
              <IconAction :icon="Tickets" title="SN 明细" @click="openInstances(row)" />
              <IconAction
                v-if="canManage"
                :icon="Edit" title="编辑"
                @click="router.push(`/spare-parts/${row.id}`)"
              />
              <IconAction
                v-else
                :icon="View" title="查看"
                @click="router.push(`/spare-parts/${row.id}`)"
              />
              <IconAction
                v-if="canManage"
                :icon="Delete" title="删除" type="danger"
                @click="handleDelete(row)"
              />
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
        />      </div>
    </el-card>

    <!-- 库存预警详情弹窗 -->
    <el-dialog v-model="showAlerts" title="库存预警详情" width="700px">
      <template v-if="alerts.out_of_stock_items.length">
        <h4 style="color: #F53F3F; margin-bottom: 8px">缺货备件 ({{ alerts.out_of_stock_count }})</h4>
        <el-table :data="alerts.out_of_stock_items" size="small" style="margin-bottom: 16px">
          <el-table-column prop="part_code" label="编码" width="100" />
          <el-table-column prop="part_name" label="名称" min-width="140" />
          <el-table-column prop="stock_quantity" label="库存" width="60" />
          <el-table-column prop="safety_stock" label="安全库存" width="70" />
          <el-table-column prop="location" label="位置" width="100" />
        </el-table>
      </template>
      <template v-if="alerts.low_stock_items.length">
        <h4 style="color: #FF7D00; margin-bottom: 8px">低库存备件 ({{ alerts.low_stock_count }})</h4>
        <el-table :data="alerts.low_stock_items" size="small">
          <el-table-column prop="part_code" label="编码" width="100" />
          <el-table-column prop="part_name" label="名称" min-width="140" />
          <el-table-column prop="stock_quantity" label="库存" width="60" />
          <el-table-column prop="safety_stock" label="安全库存" width="70" />
          <el-table-column prop="location" label="位置" width="100" />
        </el-table>
      </template>
      <el-empty v-if="alerts.alert_count === 0" description="暂无库存预警" />
    </el-dialog>

    <!-- 进货单导入弹窗 -->
    <el-dialog v-model="importDialog.visible" title="进货单导入" width="700px" destroy-on-close>
      <el-alert
        title="批量导入备件进货数据，支持新增备件和更新已有备件库存"
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom: 16px"
      />

      <!-- 手动输入模式 -->
      <div style="margin-bottom: 12px">
        <el-button size="small" @click="addImportRow" :disabled="importDialog.items.length >= 50">
          添加一行
        </el-button>
        <el-button size="small" @click="clearImportRows" :disabled="importDialog.items.length === 0">
          清空
        </el-button>
        <span style="margin-left: 12px; color: #86909C; font-size: 13px">
          共 {{ importDialog.items.length }} 项
        </span>
      </div>

      <div style="max-height: 400px; overflow-y: auto">
        <el-table :data="importDialog.items" size="small" border>
          <el-table-column label="#" width="40">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column label="备件编码" width="120">
            <template #default="{ row }">
              <el-input v-model="row.part_code" size="small" placeholder="必填" />
            </template>
          </el-table-column>
          <el-table-column label="名称" width="130">
            <template #default="{ row }">
              <el-input v-model="row.part_name" size="small" placeholder="可选" />
            </template>
          </el-table-column>
          <el-table-column label="数量" width="80">
            <template #default="{ row }">
              <el-input-number v-model="row.quantity" :min="1" size="small" style="width: 70px" />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="80">
            <template #default="{ row }">
              <el-input-number v-model="row.unit_price" :min="0" :precision="2" size="small" style="width: 70px" />
            </template>
          </el-table-column>
          <el-table-column label="供应商" width="110">
            <template #default="{ row }">
              <el-input v-model="row.supplier" size="small" placeholder="可选" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ $index }">
              <el-button text type="danger" size="small" @click="importDialog.items.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <template #footer>
        <el-button @click="importDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="handleImport" :loading="importDialog.loading" :disabled="importDialog.items.length === 0">
          导入 ({{ importDialog.items.length }}项)
        </el-button>
      </template>
    </el-dialog>

    <!-- 导入结果弹窗 -->
    <el-dialog v-model="importResult.visible" title="导入结果" width="480px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="总条目">{{ importResult.data.total || 0 }}</el-descriptions-item>
        <el-descriptions-item label="新增备件">
          <span style="color: #00B42A; font-weight: 600">{{ importResult.data.created || 0 }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="更新库存">
          <span style="color: #3491FA; font-weight: 600">{{ importResult.data.updated || 0 }}</span>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="importResult.visible = false; fetchData(); fetchAlerts()">确定</el-button>
      </template>
    </el-dialog>

    <!-- 领用 -->
    <!-- SN 明细 -->
    <el-dialog v-model="instances.visible" :title="`SN 明细 · ${instances.row?.part_name || ''}`" width="1000px">
      <div class="inst-summary">
        {{ instances.row?.part_code }} · 总库存 {{ instances.row?.stock_quantity }} {{ instances.row?.unit || '' }}
        · 已登记 SN {{ instances.rows.length }} 件
        <span class="inst-tip">在库件可直接装机 / 报废；装机的件可拆回或标记待返厂</span>
      </div>
      <el-table :data="instances.rows" v-loading="instances.loading" size="small" stripe>
        <el-table-column prop="sn" label="序列号 SN" width="130" show-overflow-tooltip />
        <el-table-column label="入库照片" width="120">
          <template #default="{ row }">
            <div v-if="row.inbound_attachments && row.inbound_attachments.length" class="inst-photos">
              <el-image
                v-for="(u, i) in row.inbound_attachments.slice(0, 3)" :key="u + i"
                :src="u" :preview-src-list="row.inbound_attachments" :initial-index="i"
                fit="cover" preview-teleported class="inst-thumb"
              />
              <span v-if="row.inbound_attachments.length > 3" class="inst-more">+{{ row.inbound_attachments.length - 3 }}</span>
            </div>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="instStatusType(row.status)" effect="plain">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="location_text" label="库位" width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ row.location_text || '—' }}</template>
        </el-table-column>
        <el-table-column prop="device_code" label="装机设备" width="110" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_code || '—' }}</template>
        </el-table-column>
        <el-table-column label="关联工单" width="100">
          <template #default="{ row }">
            <el-link v-if="row.work_order_id" type="primary" @click="router.push(`/work-orders/${row.work_order_id}`)">
              #{{ row.work_order_id }}
            </el-link>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="入库时间" width="130">
          <template #default="{ row }">{{ (row.inbound_at || row.created_at || '').replace('T', ' ').slice(0, 16) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="inst-actions">
              <el-button v-if="row.status === 'IN_STOCK'" link type="primary" @click="openInstall(row)">装机</el-button>
              <el-button v-if="['INSTALLED', 'RMA'].includes(row.status)" link type="primary" @click="returnInstance(row)">拆回</el-button>
              <el-button v-if="row.status === 'INSTALLED'" link type="warning" @click="rmaInstance(row)">返厂</el-button>
              <el-button v-if="['IN_STOCK', 'RMA'].includes(row.status)" link type="danger" @click="scrapInstance(row)">报废</el-button>
              <span v-if="['ISSUED', 'SCRAPPED'].includes(row.status)" class="muted">—</span>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!instances.loading && !instances.rows.length" class="inst-empty">
        还没有按 SN 登记的实物。入库时填写「序列号 SN」会自动生成，每个 SN 一条记录。
      </div>
    </el-dialog>

    <!-- 入库 / 出库抽屉（原独立页面收进台账） -->
    <StockInDrawer v-model="inDrawer.visible" :part-id="drawerPartId" @done="onDrawerDone" />
    <StockOutDrawer v-model="outDrawer.visible" :part-id="drawerPartId" @done="onDrawerDone" />

    <!-- 装机 -->
    <el-dialog v-model="installDlg.visible" title="装机" width="480px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="实例">
          <span>{{ installDlg.row?.sn || `#${installDlg.row?.id}` }} · {{ installDlg.row?.part_name }}</span>
        </el-form-item>
        <el-form-item label="设备" required>
          <el-select v-model="installDlg.deviceId" filterable placeholder="选择设备" style="width: 100%">
            <el-option
              v-for="d in deviceOptions" :key="d.id"
              :label="`${d.device_code} ${d.device_name || ''}`" :value="d.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="GPU 序号">
          <el-input-number v-model="installDlg.gpuIndex" :min="0" :max="15" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="installDlg.remark" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="installDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="installDlg.submitting" @click="submitInstall">确认装机</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, View, Delete, Sort, SortUp, SortDown, Tickets } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import request from '../api'
import { downloadFile } from '../utils/download'

import EmptyState from '../components/EmptyState.vue'
import IconAction from '../components/IconAction.vue'
import StockInDrawer from './StockInDrawer.vue'
import StockOutDrawer from './StockOutDrawer.vue'
const router = useRouter()

// 备件台账维护权限：仅管理员/主管可增删改，维修员只读
const canManage = computed(() => {
  try {
    const role = JSON.parse(localStorage.getItem('current_user') || '{}').role
    return role === 'ADMIN' || role === 'SUPERVISOR'
  } catch { return false }
})

const list = ref([])
const loading = ref(false)
const keyword = ref('')
const typeFilter = ref('')
const deviceTypeOptions = ref([])
const stockFilter = ref('')
const stockSortOrder = ref('')
const tableRef = ref(null)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const showAlerts = ref(false)

// ===== 入库 / 出库抽屉（原独立页面收进台账）=====
const inDrawer = reactive({ visible: false })
const outDrawer = reactive({ visible: false })
const drawerPartId = ref(null)
const openIn = (row) => { drawerPartId.value = row?.id || null; inDrawer.visible = true }
const openOut = (row) => { drawerPartId.value = row?.id || null; outDrawer.visible = true }
const onDrawerDone = () => { fetchData(); fetchAlerts() }

// ===== SN 明细 =====
const instances = reactive({ visible: false, row: null, rows: [], loading: false })
const instStatusType = (s) => ({
  IN_STOCK: 'success', ISSUED: 'primary', INSTALLED: 'primary', RMA: 'warning', SCRAPPED: 'info',
}[s] || 'info')
const openInstances = async (row) => {  instances.row = row
  instances.rows = []
  instances.visible = true
  instances.loading = true
  try {
    const res = await request.get('/part-instances/', {
      params: { part_id: row.id, page_size: 200 },
    })
    instances.rows = res.items || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载 SN 明细失败')
  } finally {
    instances.loading = false
  }
}

// 点整行看 SN 明细；点操作按钮不触发
const onPartRowClick = (row, column, event) => {
  if (event?.target?.closest('.action-group')) return
  openInstances(row)
}

// ===== 实例操作：装机 / 拆回 / 待返厂 / 报废 =====
const deviceOptions = ref([])
const installDlg = reactive({ visible: false, row: null, deviceId: null, gpuIndex: null, remark: '', submitting: false })

const loadDevices = async () => {
  if (deviceOptions.value.length) return
  try {
    const res = await request.get('/devices/', { params: { page_size: 500 } })
    deviceOptions.value = res.items || []
  } catch { deviceOptions.value = [] }
}

const refreshAfterInstanceChange = async () => {
  if (instances.row) await openInstances(instances.row)
  fetchData()
  fetchAlerts()
}

const openInstall = async (row) => {
  Object.assign(installDlg, {
    visible: true, row, deviceId: null, gpuIndex: null, remark: '', submitting: false,
  })
  await loadDevices()
}

const submitInstall = async () => {
  if (!installDlg.deviceId) return ElMessage.warning('请选择设备')
  installDlg.submitting = true
  try {
    const res = await request.post(`/part-instances/${installDlg.row.id}/install`, {
      device_id: installDlg.deviceId,
      gpu_index: installDlg.gpuIndex,
      remark: installDlg.remark || null,
    })
    ElMessage.success(`已装机到 ${res.device_code}`)
    installDlg.visible = false
    await refreshAfterInstanceChange()
  } catch { /* ignore */ } finally { installDlg.submitting = false }
}

const returnInstance = async (row) => {
  try {
    await ElMessageBox.confirm('拆回后这件会回到「在库」，之前扣过库存的会自动 +1。', '拆回入库', {
      confirmButtonText: '确认拆回', cancelButtonText: '取消',
    })
  } catch { return }
  try {
    await request.post(`/part-instances/${row.id}/return-in`, {})
    ElMessage.success('已拆回入库')
    await refreshAfterInstanceChange()
  } catch { /* ignore */ }
}

const rmaInstance = async (row) => {
  try {
    await ElMessageBox.confirm('标记为待返厂后库存不变，等寄回供应商。', '标记待返厂', { type: 'warning' })
  } catch { return }
  try {
    await request.post(`/part-instances/${row.id}/rma`, {})
    ElMessage.success('已标记待返厂')
    await refreshAfterInstanceChange()
  } catch { /* ignore */ }
}

const scrapInstance = async (row) => {
  let remark = ''
  try {
    const { value } = await ElMessageBox.prompt('报废原因（选填）', '报废确认', {
      confirmButtonText: '确认报废', cancelButtonText: '取消', inputType: 'textarea',
    })
    remark = value || ''
  } catch { return }
  try {
    await request.post(`/part-instances/${row.id}/scrap`, { remark: remark || null })
    ElMessage.success('已报废')
    await refreshAfterInstanceChange()
  } catch { /* ignore */ }
}

const alerts = reactive({
  alert_count: 0,
  low_stock_count: 0,
  out_of_stock_count: 0,
  low_stock_items: [],
  out_of_stock_items: [],
})

const importDialog = reactive({
  visible: false,
  loading: false,
  items: [],
})

const importResult = reactive({
  visible: false,
  data: {},
})

const stockLabel = (row) => {
  if (row.stock_quantity <= 0) return '缺件'
  if (row.stock_quantity <= row.safety_stock) return '紧张'
  return '充足'
}
const stockSoftClass = (row) => {
  const s = stockClass(row)
  if (s === 'stock-out') return 'soft-tag--p0'
  if (s === 'stock-low') return 'soft-tag--p1'
  return 'soft-tag--ok'
}

const stockClass = (row) => {
  if (row.stock_quantity <= 0) return 'stock-out'
  if (row.stock_quantity <= row.safety_stock) return 'stock-low'
  return 'stock-ok'
}

const onSortChange = ({ prop, order }) => {
  if (prop !== 'stock_quantity') return
  stockSortOrder.value = order || ''
  page.value = 1
  fetchData()
}

const fetchData = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (typeFilter.value) params.device_type = typeFilter.value
    if (stockFilter.value) params.stock_status = stockFilter.value
    if (stockSortOrder.value) {
      params.sort_by = 'stock_quantity'
      params.sort_order = stockSortOrder.value === 'ascending' ? 'asc' : 'desc'
    }
    const res = await request.get('/spare-parts/', { params })
    list.value = res.items
    total.value = res.total
  } catch { /* handled */ }
  finally { loading.value = false }
}

const fetchAlerts = async () => {
  try {
    const res = await request.get('/spare-parts/alerts')
    Object.assign(alerts, res)
  } catch { /* handled */ }
}

const handleSearch = () => { page.value = 1; fetchData() }
const handleReset = () => { keyword.value = ''; typeFilter.value = ''; stockFilter.value = ''; stockSortOrder.value = ''; tableRef.value?.clearSort?.(); page.value = 1; fetchData() }
const handleAlertFilter = () => { stockFilter.value = 'out_of_stock'; page.value = 1; fetchData() }

const handleDelete = async (row) => {  try {
    await ElMessageBox.confirm('确定删除该备件？', '删除确认', { type: 'warning' })
    await request.delete(`/spare-parts/${row.id}`)
    ElMessage.success('删除成功')
    fetchData()
    fetchAlerts()
  } catch { /* cancelled */ }
}

// 进货单导入
const addImportRow = () => {
  importDialog.items.push({
    part_code: '', part_name: '', quantity: 1, unit_price: 0,
    supplier: '', device_type: '', location: '',
  })
}
const clearImportRows = () => { importDialog.items = [] }

const handleImport = async () => {
  // 校验：编码必填
  const invalid = importDialog.items.some(item => !item.part_code.trim())
  if (invalid) {
    ElMessage.warning('请输入所有备件的编码')
    return
  }
  importDialog.loading = true
  try {
    const payload = { items: importDialog.items.map(item => ({
      part_code: item.part_code.trim(),
      part_name: item.part_name?.trim() || undefined,
      quantity: item.quantity,
      unit_price: item.unit_price,
      supplier: item.supplier?.trim() || undefined,
    }))}
    const res = await request.post('/spare-parts/import', payload)
    importResult.data = res
    importResult.visible = true
    importDialog.visible = false
    importDialog.items = []
  } catch { /* handled */ }
  finally { importDialog.loading = false }
}

const flattenTree = (nodes, result = []) => {
  for (const node of nodes) {
    result.push({ label: node.name, value: node.name })
    if (node.children && node.children.length > 0) flattenTree(node.children, result)
  }
  return result
}

const fetchDeviceTypes = async () => {
  try {
    const res = await request.get('/categories/', { params: { category_type: 'DEVICE_TYPE', page_size: 1000 } })
    deviceTypeOptions.value = flattenTree(res.items || [])
  } catch { /* fallback to empty */ }
}

// ===== 全局实物检索：按 SN / 设备定位到备件，直接打开该件的 SN 明细 =====
const snOptions = ref([])
const snSearching = ref(false)
const snSearchValue = ref(null)

const searchInstances = async (kw = '') => {
  const q = String(kw || '').trim()
  if (q.length < 2) { snOptions.value = []; return }
  snSearching.value = true
  try {
    const res = await request.get('/part-instances/', { params: { keyword: q, page_size: 20 } })
    snOptions.value = res.items || []
  } catch { snOptions.value = [] } finally { snSearching.value = false }
}

const jumpToInstance = async (instId) => {
  const hit = snOptions.value.find((i) => i.id === instId)
  snSearchValue.value = null
  if (!hit) return
  try {
    const part = await request.get(`/spare-parts/${hit.part_id}`)
    await openInstances(part)
  } catch { ElMessage.error('打不开这个备件的实例列表') }
}

onMounted(() => {
  fetchDeviceTypes()
  fetchData()
  fetchAlerts()
  // 预填一行进货单
  addImportRow()
})

// ===== 导出 Excel =====
const exporting = ref(false)
const handleExport = async () => {
  exporting.value = true
  try {
    await downloadFile('/export/spare-parts.xlsx', {}, '备件台账.xlsx')
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

// 供外层库存中心在切回台账 tab 时刷新（跨 tab 数据联动）
defineExpose({ refresh: () => { fetchData(); fetchAlerts() } })
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary); }
.part-thumb { width: 36px; height: 36px; border-radius: 4px; vertical-align: middle; }
.inst-empty { margin-top: 12px; padding: 14px; background: #F7F8FA; border-radius: 6px;
  color: #86909C; font-size: 13px; text-align: center; }
.inst-summary { margin: -4px 0 10px; color: #86909C; font-size: 13px; }
.inst-tip { margin-left: 8px; font-size: 12px; color: #C9CDD4; }
.inst-actions { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.inst-photos { display: flex; align-items: center; gap: 4px; }
.inst-thumb { width: 30px; height: 30px; border-radius: 4px; }
.inst-more { font-size: 12px; color: #86909C; }
.sp-table :deep(tbody tr) { cursor: pointer; }
.header-actions { display: flex; gap: 12px; }

.alert-banner { margin-bottom: 16px; }

.filter-card { margin-bottom: 16px; }
.filter-bar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
.sn-search { width: 210px; }
.sn-opt { display: flex; flex-direction: column; line-height: 1.35; padding: 2px 0; }
.sn-main { color: #1D2129; font-size: 13px; }
.sn-meta { color: #86909C; font-size: 12px; }
.sn-empty { padding: 8px 12px; color: #86909C; font-size: 12px; }
.table-card { flex: 1; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }

.stock-status {
  display: inline-flex; align-items: center; gap: 4px; font-size: 13px;
}
.stock-status::before { content: ''; width: 6px; height: 6px; border-radius: 50%; }
.stock-ok::before { background: #00B42A; }
.stock-ok { color: #00B42A; }
.stock-low::before { background: #FF7D00; }
.stock-low { color: #FF7D00; }
.stock-out::before { background: #F53F3F; }
.stock-out { color: #F53F3F; }

.action-group { display: flex; gap: 4px; align-items: center; justify-content: flex-start; white-space: nowrap; }
/* 库存列表头排序：单图标替代默认双三角，状态更直观 */
.sp-table :deep(.el-table__header .caret-wrapper) { display: none; }
.stock-sort { display: inline-flex; align-items: center; gap: 3px; cursor: pointer; user-select: none; }
.stock-sort .sort-arrow { font-size: 14px; color: #86909C; transition: color .15s; }
.stock-sort:hover { color: #0FC6C2; }
.stock-sort:hover .sort-arrow,
.stock-sort.ascending .sort-arrow,
.stock-sort.descending .sort-arrow { color: #0FC6C2; }
.sp-table :deep(.el-table__cell) { padding: 8px 0; }
.sp-table :deep(.el-button.is-link) { padding: 0 2px; height: auto; }
</style>
