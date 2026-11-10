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
        <el-select v-model="type" placeholder="类型" clearable style="width: 120px">
          <el-option label="出库（领用）" value="OUT" />
          <el-option label="入库" value="IN" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" stripe size="small">
        <el-table-column label="时间" width="150">
          <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ').slice(0, 16) }}</template>
        </el-table-column>
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.movement_type === 'OUT' ? 'warning' : 'success'">
              {{ row.movement_type === 'OUT' ? '出库' : '入库' }}
            </el-tag>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../api'
import { downloadFile } from '../utils/download'

const rows = ref([])
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
</style>
