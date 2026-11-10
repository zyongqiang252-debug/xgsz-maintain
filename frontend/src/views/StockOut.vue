<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">备件出库</h2>
      <div class="header-actions">
        <el-button @click="router.push('/stock/movements')">全部流水</el-button>
        <el-button @click="router.push('/stock')">备件台账</el-button>
      </div>
    </div>

    <div class="io-layout">
      <el-card shadow="never" class="io-card">
        <template #header>
          <div class="card-head">
            <span>出库登记</span>
            <span class="card-sub">保存后自动写一条出库流水</span>
          </div>
        </template>

        <el-form label-position="top" @submit.prevent>
          <el-form-item label="备件" required>
            <el-select
              v-model="form.partId"
              filterable
              remote
              clearable
              :remote-method="searchParts"
              :loading="partLoading"
              placeholder="输入编码 / 名称搜索"
              style="width: 100%"
              @change="onPartChange"
            >
              <el-option v-for="p in partOptions" :key="p.id" :label="`${p.part_code} ${p.part_name}`" :value="p.id">
                <div class="opt-row">
                  <span class="opt-main">{{ p.part_code }} · {{ p.part_name }}</span>
                  <span class="opt-meta">可用 {{ availableOf(p) }}{{ p.unit || '' }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>

          <div v-if="selected" class="stock-line">
            <span>现存 <b>{{ selected.stock_quantity }}</b></span>
            <span>已预占 <b>{{ selected.reserved_quantity || 0 }}</b></span>
            <span>可用 <b class="ok">{{ available }}</b></span>
          </div>

          <el-form-item label="出库数量" required>
            <el-input-number
              v-model="form.quantity"
              :min="0.01"
              :max="selected ? Math.max(Number(available), 0.01) : 99999"
              :precision="2"
              :step="1"
              style="width: 100%"
            />
            <div v-if="selected && Number(form.quantity) > Number(available)" class="field-tip danger">
              超过可用库存（可用 {{ available }}）
            </div>
          </el-form-item>

          <el-form-item label="序列号 SN（选填，换下来的件建议填）">
            <el-input v-model="form.serialNo" maxlength="500" placeholder="一物一码；多个用逗号分隔" />
          <div class="field-tip">一个 SN 只能对应一件，填几个 SN 就出库几件</div>
          </el-form-item>

          <el-form-item label="照片附件（选填，坏件伤情 / 拆机现场）">
            <PhotoUpload v-model="form.attachments" />
          </el-form-item>

          <el-form-item label="关联工单（选填，会自动计入该工单备件成本）">
            <el-select
              v-model="form.workOrderId"
              filterable
              remote
              clearable
              :remote-method="searchWorkOrders"
              :loading="woLoading"
              placeholder="输入工单号 / 设备编码搜索"
              style="width: 100%"
            >
              <el-option v-for="wo in woOptions" :key="wo.id" :label="woLabel(wo)" :value="wo.id" />
            </el-select>
          </el-form-item>

          <el-form-item label="出库事由">
            <el-input v-model="form.remark" maxlength="100" placeholder="选填，例如：GPU 卡故障更换 / 抢修领用" />
          </el-form-item>

          <el-button
            type="primary"
            class="submit-btn"
            :loading="submitting"
            :disabled="!form.partId || Number(available) <= 0"
            @click="submit"
          >确认出库</el-button>
        </el-form>
      </el-card>

      <el-card shadow="never" class="io-card io-list">
        <template #header>
          <div class="card-head">
            <span>出库流水</span>
            <div class="list-tools">
              <el-checkbox v-model="onlySelected" :disabled="!form.partId" @change="reload">只看所选备件</el-checkbox>
              <el-button link type="primary" @click="loadMovements">刷新</el-button>
            </div>
          </div>
        </template>

        <el-table :data="movements.rows" v-loading="movements.loading" stripe size="small">
          <el-table-column label="时间" width="92">
            <template #default="{ row }">
              <div class="cell-main">{{ (row.created_at || '').slice(0, 10) }}</div>
              <div class="cell-sub">{{ (row.created_at || '').slice(11, 16) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="备件" min-width="120">
            <template #default="{ row }">
              <div class="cell-main">{{ row.part_name }}</div>
              <div class="cell-sub">{{ row.part_code }}</div>
            </template>
          </el-table-column>
          <el-table-column label="SN" width="108">
            <template #default="{ row }">
              <span v-if="row.serial_no" class="sn-cell" :title="row.serial_no">{{ row.serial_no }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="照片" width="44" align="center">
            <template #default="{ row }">
              <el-image
                v-if="row.attachments && row.attachments.length"
                :src="row.attachments[0]" :preview-src-list="row.attachments"
                fit="cover" preview-teleported style="width:26px;height:26px;border-radius:4px"
              />
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column label="数量" width="95">
            <template #default="{ row }">
              <div class="cell-main">{{ row.quantity }}</div>
              <div class="cell-sub">{{ row.before_qty }} → {{ row.after_qty }}</div>
            </template>
          </el-table-column>
          <el-table-column label="关联工单" width="76">
            <template #default="{ row }">
              <el-link v-if="row.work_order_id" type="primary" @click="router.push(`/work-orders/${row.work_order_id}`)">
                #{{ row.work_order_id }}
              </el-link>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="operator_name" label="操作人" width="60" show-overflow-tooltip />
          <el-table-column prop="remark" label="备注" min-width="68" show-overflow-tooltip />
        </el-table>

        <div class="pagination-wrap">
          <el-pagination
            v-model:current-page="movements.page"
            :page-size="movements.pageSize"
            :total="movements.total"
            layout="total, prev, pager, next"
            small
            @current-change="loadMovements"
          />
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '../api'
import PhotoUpload from '../components/PhotoUpload.vue'

const router = useRouter()

const partOptions = ref([])
const partLoading = ref(false)
const selected = ref(null)
const submitting = ref(false)
const onlySelected = ref(false)

const woOptions = ref([])
const woLoading = ref(false)

const form = reactive({ partId: null, quantity: 1, workOrderId: null, serialNo: '', attachments: [], remark: '' })
watch(() => form.serialNo, (v) => {
  const arr = String(v || '').replace(/[，、；;]/g, ',').split(',').map((s) => s.trim()).filter(Boolean)
  if (arr.length) form.quantity = arr.length
})
const movements = reactive({ rows: [], total: 0, page: 1, pageSize: 10, loading: false })

const money = (v) => Number(v || 0).toFixed(2)
const availableOf = (p) =>
  Number(p.available_quantity ?? (Number(p.stock_quantity || 0) - Number(p.reserved_quantity || 0)))
const available = computed(() => (selected.value ? availableOf(selected.value) : 0))
const woLabel = (wo) =>
  [wo.work_order_no, wo.device_code, (wo.fault_description || '').slice(0, 14)].filter(Boolean).join('｜')

const searchParts = async (keyword = '') => {
  partLoading.value = true
  try {
    const res = await request.get('/spare-parts/', {
      params: { page: 1, page_size: 20, keyword: keyword || undefined },
    })
    const list = res.items || []
    if (selected.value && !list.some((p) => p.id === selected.value.id)) list.unshift(selected.value)
    partOptions.value = list
  } catch { /* 拦截器已提示 */ } finally {
    partLoading.value = false
  }
}

const onPartChange = (id) => {
  const hit = partOptions.value.find((p) => p.id === id)
  selected.value = hit || null
  if (hit && Number(availableOf(hit)) > 0 && Number(form.quantity) > Number(availableOf(hit))) {
    form.quantity = Number(availableOf(hit))
  }
  if (onlySelected.value) loadMovements()
}

const searchWorkOrders = async (keyword = '') => {
  woLoading.value = true
  try {
    const res = await request.get('/work-orders/', {
      params: { page: 1, page_size: 20, keyword: keyword || undefined },
    })
    woOptions.value = res.items || []
  } catch { /* 拦截器已提示 */ } finally {
    woLoading.value = false
  }
}

const submit = async () => {
  if (!form.partId) return ElMessage.warning('先选择要出库的备件')
  if (!form.quantity || Number(form.quantity) <= 0) return ElMessage.warning('出库数量要大于 0')
  if (Number(form.quantity) > Number(available.value)) {
    return ElMessage.warning(`最多可出库 ${available.value}${selected.value?.unit || ''}`)
  }
  submitting.value = true
  try {
    const res = await request.post(`/spare-parts/${form.partId}/consume`, {
      quantity: Number(form.quantity),
      work_order_id: form.workOrderId || null,
      serial_no: form.serialNo.trim() || null,
      attachments: form.attachments,
      remark: form.remark || null,
    })
    ElMessage.success(`出库成功，剩余库存 ${res.stock_quantity}`)
    if (selected.value) selected.value.stock_quantity = res.stock_quantity
    form.quantity = 1
    form.serialNo = ''
    form.attachments = []
    form.remark = ''
    loadMovements()
  } catch { /* 拦截器已提示 */ } finally {
    submitting.value = false
  }
}

const loadMovements = async () => {
  movements.loading = true
  try {
    const res = await request.get('/spare-parts/movements', {
      params: {
        page: movements.page,
        page_size: movements.pageSize,
        movement_type: 'OUT',
        part_id: onlySelected.value && form.partId ? form.partId : undefined,
      },
    })
    movements.rows = res.items || []
    movements.total = res.total || 0
  } catch { /* 拦截器已提示 */ } finally {
    movements.loading = false
  }
}

const reload = () => {
  movements.page = 1
  loadMovements()
}

onMounted(() => {
  searchParts()
  searchWorkOrders()
  loadMovements()
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary); }
.header-actions { display: flex; gap: 8px; }

.io-layout { display: flex; gap: 16px; align-items: flex-start; }
.io-card { flex: 0 0 380px; }
.io-list { flex: 1; min-width: 0; }

.cell-main { color: var(--color-text-primary); line-height: 1.3; }
.cell-sub { color: var(--color-text-tertiary); font-size: 12px; line-height: 1.3; }
.sn-cell { display: block; color: var(--color-text-secondary); font-size: 12px; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.muted { color: var(--color-text-disabled); }

.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-sub { font-size: 12px; color: var(--color-text-tertiary); }
.list-tools { display: flex; align-items: center; gap: 12px; }

.opt-row { display: flex; justify-content: space-between; gap: 12px; }
.opt-main { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.opt-meta { color: var(--color-text-tertiary); font-size: 12px; flex-shrink: 0; }

.stock-line {
  display: flex; gap: 16px; flex-wrap: wrap;
  background: var(--color-bg-page); border-radius: 6px;
  padding: 8px 12px; margin: 0 0 12px;
  font-size: 13px; color: var(--color-text-secondary);
}
.stock-line b { color: var(--color-text-primary); font-size: 15px; }
.stock-line b.ok { color: var(--color-primary); }

.field-tip { font-size: 12px; color: var(--color-text-tertiary); line-height: 1.4; margin-top: 2px; }
.field-tip.danger { color: var(--color-danger); }
.submit-btn { width: 100%; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 12px; }

@media (max-width: 1400px) {
  .io-layout { flex-direction: column; }
  .io-card { flex: none; width: 100%; }
}
</style>
