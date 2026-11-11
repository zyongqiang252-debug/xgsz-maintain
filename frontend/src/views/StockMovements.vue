<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">出入库流水</h2>
      <div style="display:flex;gap:8px">
        <el-button :loading="exporting" @click="handleExport">导出 Excel</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input
          v-model="keyword" placeholder="搜索备件编码/名称/SN/操作人" clearable style="width: 260px"
          @clear="handleSearch" @keyup.enter="handleSearch"
        />
        <el-select v-model="type" placeholder="类型" clearable style="width: 140px" @change="handleSearch">
          <el-option label="入库" value="IN" />
          <el-option label="出库（领用）" value="OUT" />
          <el-option label="退库入库" value="RETURN" />
          <el-option label="盘点调整" value="ADJUST" />
        </el-select>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe size="small" class="mv-table" @row-click="openDetail">
        <el-table-column label="时间" width="145">
          <template #default="{ row }">{{ fmt(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="类型" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="mvTag(row.movement_type)">{{ mvLabel(row.movement_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备件" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="part-cell">
              <span class="part-name">{{ row.part_name || '—' }}</span>
              <span class="part-sub">
                <span class="mono">{{ row.part_code }}</span>
                <span v-if="row.attachments && row.attachments.length" class="att-chip">
                  {{ row.attachments.length }} 张照片
                </span>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="增减" width="90" align="right">
          <template #default="{ row }">
            <span class="qty" :class="deltaOf(row) >= 0 ? 'plus' : 'minus'">{{ deltaText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="库存变化" width="130" align="center">
          <template #default="{ row }">{{ row.before_qty ?? '—' }} → {{ row.after_qty ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="金额" width="130" align="right">
          <template #default="{ row }">
            <span :class="{ 'amount-loss': amountOf(row) < 0 }">{{ money(amountOf(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联工单" width="100">
          <template #default="{ row }">
            <el-link v-if="row.work_order_id" type="primary" @click.stop="$router.push(`/work-orders/${row.work_order_id}`)">
              #{{ row.work_order_id }}
            </el-link>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="operator_name" label="操作人" width="100">
          <template #default="{ row }">{{ row.operator_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="76" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <EmptyState icon="search" title="没有符合条件的出入库记录" hint="试试调整类型或关键词后重新查询" />
        </template>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total"
                       layout="total, prev, pager, next" @current-change="load" />
      </div>
    </el-card>

    <!-- 单条流水详情：SN / 照片 / 备注等都收在这里，列表只做记录索引 -->
    <el-drawer v-model="detail.visible" title="出入库详情" size="520px">
      <template v-if="detail.row">
        <div class="detail-head">
          <el-tag size="small" :type="mvTag(detail.row.movement_type)">{{ mvLabel(detail.row.movement_type) }}</el-tag>
          <span class="detail-time">{{ fmt(detail.row.created_at) }}</span>
        </div>

        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="备件">
            {{ detail.row.part_name || '—' }}
            <span class="mono muted">（{{ detail.row.part_code }}）</span>
          </el-descriptions-item>
          <el-descriptions-item label="增减">
            <span class="qty" :class="deltaOf(detail.row) >= 0 ? 'plus' : 'minus'">{{ deltaText(detail.row) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="库存变化">{{ detail.row.before_qty ?? '—' }} → {{ detail.row.after_qty ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="单价">{{ money(detail.row.unit_price) }}</el-descriptions-item>
          <el-descriptions-item :label="amountLabel(detail.row)">{{ money(amountOf(detail.row)) }}</el-descriptions-item>
          <el-descriptions-item label="关联工单">
            <el-link v-if="detail.row.work_order_id" type="primary" @click="$router.push(`/work-orders/${detail.row.work_order_id}`)">
              #{{ detail.row.work_order_id }}
            </el-link>
            <span v-else class="muted">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="操作人">{{ detail.row.operator_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="备注">{{ detail.row.remark || '—' }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-block">
          <div class="detail-label">序列号 SN</div>
          <div v-if="detail.row.serial_no" class="sn-box">
            <el-tag v-for="sn in splitSerials(detail.row.serial_no)" :key="sn" size="small" type="info" effect="plain" class="sn-tag">
              {{ sn }}
            </el-tag>
          </div>
          <div v-else class="muted">本次流水未填 SN</div>
        </div>

        <div class="detail-block">
          <div class="detail-label">照片附件<span v-if="detail.row.attachments && detail.row.attachments.length" class="detail-count">{{ detail.row.attachments.length }} 张</span></div>
          <div v-if="detail.row.attachments && detail.row.attachments.length" class="photo-grid">
            <el-image
              v-for="(u, i) in detail.row.attachments" :key="u + i"
              :src="u" :preview-src-list="detail.row.attachments" :initial-index="i"
              fit="cover" preview-teleported class="photo-img"
            />
          </div>
          <div v-else class="muted">无照片附件</div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../api'
import { downloadFile } from '../utils/download'
import EmptyState from '../components/EmptyState.vue'

const rows = ref([])
// 流水四种类型：入库 / 出库 / 退库 / 盘点调整（以前非 OUT 全显示成"入库"，账容易看错）
const MV_TYPE = {
  IN: { label: '入库', tag: 'success' },
  OUT: { label: '出库', tag: 'warning' },
  RETURN: { label: '退库入库', tag: 'primary' },
  ADJUST: { label: '盘点调整', tag: 'info' },
}
const mvLabel = (t) => (MV_TYPE[t] || {}).label || t || '—'
const mvTag = (t) => (MV_TYPE[t] || {}).tag || 'info'
const detail = reactive({ visible: false, row: null })
const openDetail = (row) => {
  detail.row = row
  detail.visible = true
}
const fmt = (t) => (t ? String(t).replace('T', ' ').slice(0, 16) : '—')
const splitSerials = (raw) => String(raw || '')
  .replace(/[，、；;]/g, ',')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean)

// 统一按「库存变化」算增减：老数据里出入库的 quantity 符号不统一，直接用 after-before 最稳
const deltaOf = (row) => {
  const b = Number(row?.before_qty)
  const a = Number(row?.after_qty)
  if (Number.isFinite(b) && Number.isFinite(a)) return Number((a - b).toFixed(2))
  const q = Number(row?.quantity || 0)
  return row?.movement_type === 'OUT' ? -q : q
}
const deltaText = (row) => {
  const d = deltaOf(row)
  return `${d > 0 ? '+' : ''}${d}`
}
// 金额统一口径：入库/出库/退库按「|数量| × 单价」算正金额（出库是领用成本，不是负收入）；
// 盘点调整按差异方向算，盘亏为负。历史流水 amount 符号不统一，这里直接由数量和单价重算。
const amountOf = (row) => {
  const price = Number(row?.unit_price ?? 0)
  const qty = Number(row?.quantity || 0)
  if (row?.movement_type === 'ADJUST') {
    const v = price ? deltaOf(row) * price : Number(row?.amount || 0)
    return Number(v.toFixed(2))
  }
  const v = price ? Math.abs(qty) * price : Math.abs(Number(row?.amount || 0))
  return Number(v.toFixed(2))
}
const amountLabel = (row) => ({
  IN: '入库金额', OUT: '出库金额（领用成本）', RETURN: '退库金额', ADJUST: '调整金额',
}[row?.movement_type] || '金额')
const money = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  const s = Math.abs(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return (n < 0 ? '-¥' : '¥') + s
}

const loading = ref(false)
const exporting = ref(false)
const keyword = ref('')
const type = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)

const load = async () => {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (type.value) params.movement_type = type.value
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    const res = await request.get('/spare-parts/movements', { params })
    rows.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载流水失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => { page.value = 1; load() }

const reset = () => {
  keyword.value = ''
  type.value = ''
  page.value = 1
  load()
}

const handleExport = async () => {
  exporting.value = true
  try {
    await downloadFile('/export/stock-movements.xlsx', {}, '出入库流水.xlsx')
    ElMessage.success('已开始下载')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }
.mv-table :deep(tbody tr) { cursor: pointer; }
.mono { font-family: ui-monospace, Consolas, monospace; }
.muted { color: #86909C; }

.part-cell { display: flex; flex-direction: column; line-height: 1.35; }
.part-name { color: #1D2129; font-size: 13px; }
.part-sub { display: flex; align-items: center; gap: 8px; color: #86909C; font-size: 11px; }
.att-chip { color: #0FC6C2; }
.qty { font-variant-numeric: tabular-nums; }
.qty.plus { color: #00B42A; }
.qty.minus { color: #F53F3F; }
.amount-loss { color: #F53F3F; }

.detail-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.detail-time { font-size: 12px; color: #86909C; }
.detail-block { margin-top: 16px; }
.detail-label { font-size: 13px; color: #4E5969; margin-bottom: 8px; }
.detail-count { margin-left: 6px; font-size: 12px; color: #86909C; }
.sn-box { display: flex; flex-wrap: wrap; gap: 6px; }
.sn-tag { max-width: 100%; }
.photo-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.photo-img { width: 112px; height: 112px; border-radius: 6px; }
</style>
