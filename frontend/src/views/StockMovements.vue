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
        <el-input v-model="keyword" placeholder="搜索备件编码/名称" clearable style="width: 220px" @keyup.enter="load" />
        <el-select v-model="type" placeholder="类型" clearable style="width: 130px">
          <el-option label="入库" value="IN" />
          <el-option label="出库（领用）" value="OUT" />
          <el-option label="退库入库" value="RETURN" />
          <el-option label="盘点调整" value="ADJUST" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe size="small" class="mv-table" @row-click="openDetail">
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ').slice(0, 16) }}</template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="mvTag(row.movement_type)">{{ mvLabel(row.movement_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="part_code" label="备件编码" width="130" show-overflow-tooltip />
        <el-table-column prop="part_name" label="备件名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="serial_no" label="序列号 SN" width="160" show-overflow-tooltip />
        <el-table-column label="照片" width="76" align="center">
          <template #default="{ row }">
            <el-image
              v-if="row.attachments && row.attachments.length"
              :src="row.attachments[0]" :preview-src-list="row.attachments"
              fit="cover" preview-teleported style="width:34px;height:34px;border-radius:4px"
            />
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="80" align="right" />
        <el-table-column label="库存变化" width="120" align="center">
          <template #default="{ row }">{{ row.before_qty }} → {{ row.after_qty }}</template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="90" align="right" />
        <el-table-column label="关联工单" width="100">
          <template #default="{ row }">
            <el-link v-if="row.work_order_id" type="primary" @click="$router.push(`/work-orders/${row.work_order_id}`)">
              #{{ row.work_order_id }}
            </el-link>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="operator_name" label="操作人" width="100" />
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
      </el-table>

      <div class="pagination-wrap">
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total"
                       layout="total, prev, pager, next" @current-change="load" />
      </div>
    </el-card>

    <el-drawer v-model="detail.visible" title="出入库详情" size="440px">
      <template v-if="detail.row">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="类型">
            <el-tag size="small" :type="mvTag(detail.row.movement_type)">{{ mvLabel(detail.row.movement_type) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="备件">{{ detail.row.part_name }}（{{ detail.row.part_code }}）</el-descriptions-item>
          <el-descriptions-item label="数量">{{ detail.row.quantity }}</el-descriptions-item>
          <el-descriptions-item label="库存变化">{{ detail.row.before_qty }} → {{ detail.row.after_qty }}</el-descriptions-item>
          <el-descriptions-item label="序列号 SN">{{ detail.row.serial_no || '—' }}</el-descriptions-item>
          <el-descriptions-item label="金额">{{ detail.row.amount }}</el-descriptions-item>
          <el-descriptions-item label="关联工单">
            <el-link v-if="detail.row.work_order_id" type="primary" @click="$router.push(`/work-orders/${detail.row.work_order_id}`)">
              #{{ detail.row.work_order_id }}
            </el-link>
            <span v-else>—</span>
          </el-descriptions-item>
          <el-descriptions-item label="操作人">{{ detail.row.operator_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ (detail.row.created_at || '').replace('T', ' ').slice(0, 16) }}</el-descriptions-item>
          <el-descriptions-item label="备注">{{ detail.row.remark || '—' }}</el-descriptions-item>
        </el-descriptions>
        <div v-if="detail.row.attachments && detail.row.attachments.length" class="detail-photos">
          <div class="detail-label">照片附件</div>
          <div class="photo-grid">
            <el-image
              v-for="(u, i) in detail.row.attachments" :key="u + i"
              :src="u" :preview-src-list="detail.row.attachments" :initial-index="i"
              fit="cover" preview-teleported class="photo-img"
            />
          </div>
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
    const res = await request.get('/spare-parts/movements', { params: { page: page.value, page_size: pageSize.value } })
    let items = res.items || []
    if (type.value) items = items.filter((x) => x.movement_type === type.value)
    if (keyword.value) {
      const k = keyword.value.trim().toLowerCase()
      items = items.filter((x) => `${x.part_code} ${x.part_name}`.toLowerCase().includes(k))
    }
    rows.value = items
    total.value = res.total || items.length
  } catch (e) {
    ElMessage.error('加载流水失败')
  } finally {
    loading.value = false
  }
}

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
.detail-photos { margin-top: 16px; }
.detail-label { font-size: 13px; color: #4E5969; margin-bottom: 8px; }
.photo-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.photo-img { width: 96px; height: 96px; border-radius: 6px; }
</style>
