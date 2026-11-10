<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">备件入库</h2>
      <div class="header-actions">
        <el-button @click="router.push('/stock/movements')">全部流水</el-button>
        <el-button @click="router.push('/stock')">备件台账</el-button>
      </div>
    </div>

    <div class="io-layout">
      <el-card shadow="never" class="io-card">
        <template #header>
          <div class="card-head">
            <span>入库登记</span>
            <span class="card-sub">保存后自动写一条入库流水</span>
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
                  <span class="opt-meta">现存 {{ p.stock_quantity }}{{ p.unit || '' }}</span>
                </div>
              </el-option>
            </el-select>
          </el-form-item>

          <el-form-item label="入库数量" required>
            <el-input-number
              v-model="form.quantity"
              :min="0.01"
              :precision="needSn ? 0 : 2"
              :step="1"
              style="width: 100%"
            />
          </el-form-item>

          <el-form-item :label="snLabel" :required="needSn">
            <el-input v-model="form.serialNo" maxlength="500" :placeholder="snPlaceholder" />
            <div v-if="needSn" class="field-tip" :class="{ danger: snCount !== needCount }">
              该件按 SN 管理：需 <b>{{ needCount }}</b> 个 SN，当前 <b>{{ snCount }}</b> 个
              <span v-if="needCount > 0 && snCount === needCount" class="ok">已对齐</span>
            </div>
          </el-form-item>

          <el-form-item label="照片附件">
            <PhotoUpload v-model="form.attachments" />
          </el-form-item>

          <el-form-item label="本次单价（元）">
            <el-input-number v-model="form.unitPrice" :min="0" :precision="2" :step="10" style="width: 100%" />
            <div class="field-tip">不填则沿用备件台账上的单价</div>
          </el-form-item>

          <el-form-item label="备注">
            <el-input v-model="form.remark" maxlength="100" placeholder="选填，例如：采购到货 / 退料入库" />
          </el-form-item>

          <div v-if="selected" class="preview">
            <div>入库后库存 <b>{{ afterStock }}</b> {{ selected.unit || '' }}</div>
            <div class="preview-sub">
              现存 {{ selected.stock_quantity }} + 本次 {{ form.quantity || 0 }}，
              本次金额 {{ amount }} 元
            </div>
          </div>

          <el-button type="primary" class="submit-btn" :loading="submitting" @click="submit">确认入库</el-button>
        </el-form>
      </el-card>

      <el-card shadow="never" class="io-card io-list">
        <template #header>
          <div class="card-head">
            <span>入库流水</span>
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
          <el-table-column label="备件" min-width="130">
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
              <div class="cell-main">+{{ row.quantity }}</div>
              <div class="cell-sub">{{ row.before_qty }} → {{ row.after_qty }}</div>
            </template>
          </el-table-column>
          <el-table-column label="金额" width="75" align="right">
            <template #default="{ row }">{{ money(row.amount) }}</template>
          </el-table-column>
          <el-table-column prop="operator_name" label="操作人" width="70" show-overflow-tooltip />
          <el-table-column prop="remark" label="备注" min-width="80" show-overflow-tooltip />
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

const form = reactive({ partId: null, quantity: 1, serialNo: '', attachments: [], unitPrice: null, remark: '' })
const movements = reactive({ rows: [], total: 0, page: 1, pageSize: 10, loading: false })

const money = (v) => Number(v || 0).toFixed(2)

// 一个 SN 一件：填了 SN 后数量自动等于 SN 个数，避免一个 SN 对多件
watch(() => form.serialNo, (v) => {
  const arr = String(v || '').replace(/，/g, ',').replace(/、/g, ',')
    .split(',').map((s) => s.trim()).filter(Boolean)
  if (arr.length) form.quantity = arr.length
})

// 按 SN 追溯的件：入库必须逐件填 SN，数量与 SN 个数要对得上
const needSn = computed(() => !!selected.value?.need_sn)
const snCount = computed(() => {
  const set = new Set(
    String(form.serialNo || '')
      .replace(/[，、；;]/g, ',')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  )
  return set.size
})
const needCount = computed(() => Math.trunc(Number(form.quantity || 0)))
const snLabel = computed(() => (needSn.value ? '序列号 SN（必填，一物一码）' : '序列号 SN'))
const snPlaceholder = computed(() =>
  needSn.value ? `需 ${needCount.value} 个，多个用逗号分隔` : '选填，一物一码；多个用逗号分隔',
)

const afterStock = computed(() => {
  if (!selected.value) return '-'
  const base = Number(selected.value.stock_quantity || 0)
  return (base + Number(form.quantity || 0)).toFixed(2).replace(/\.00$/, '')
})

const amount = computed(() => {
  const price = Number(form.unitPrice ?? selected.value?.unit_price ?? 0)
  return (price * Number(form.quantity || 0)).toFixed(2)
})

const searchParts = async (keyword = '') => {
  partLoading.value = true
  try {
    const res = await request.get('/spare-parts/', {
      params: { page: 1, page_size: 20, keyword: keyword || undefined },
    })
    const list = res.items || []
    // 搜索会把当前选中项刷掉，补回来避免下拉显示空白
    if (selected.value && !list.some((p) => p.id === selected.value.id)) list.unshift(selected.value)
    partOptions.value = list
  } catch { /* 拦截器已提示 */ } finally {
    partLoading.value = false
  }
}

const onPartChange = (id) => {
  const hit = partOptions.value.find((p) => p.id === id)
  selected.value = hit || null
  form.unitPrice = hit ? Number(hit.unit_price || 0) : null
  form.serialNo = ''  // 不预填：台账上的 SN 是当前在库件，预填会把上次的 SN 重复录一遍
  if (onlySelected.value) loadMovements()
}

const submit = async () => {
  if (!form.partId) return ElMessage.warning('先选择要入库的备件')
  if (!form.quantity || Number(form.quantity) <= 0) return ElMessage.warning('入库数量要大于 0')
  if (needSn.value) {
    if (!Number.isInteger(Number(form.quantity))) {
      return ElMessage.warning('该件按 SN 管理，入库数量必须是整数')
    }
    if (snCount.value !== needCount.value) {
      return ElMessage.warning(`该件按 SN 管理：需填 ${needCount.value} 个 SN，当前 ${snCount.value} 个`)
    }
  }
  submitting.value = true
  try {
    const res = await request.post(`/spare-parts/${form.partId}/stock-in`, {
      quantity: Number(form.quantity),
      unit_price: form.unitPrice === null || form.unitPrice === '' ? null : Number(form.unitPrice),
      serial_no: form.serialNo.trim() || null,
      attachments: form.attachments,
      remark: form.remark || null,
    })
    ElMessage.success(`入库成功，当前库存 ${res.stock_quantity}`)
    if (selected.value) {
      selected.value.stock_quantity = res.stock_quantity
      if (form.unitPrice != null) selected.value.unit_price = Number(form.unitPrice)
    }
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
        movement_type: 'IN',
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

.field-tip { font-size: 12px; color: var(--color-text-tertiary); line-height: 1.4; margin-top: 2px; }
.field-tip.danger { color: var(--color-danger); }
.field-tip .ok { color: var(--color-success); margin-left: 6px; }
.preview { background: var(--color-primary-light); border-radius: 6px; padding: 10px 12px; margin: 2px 0 14px; }
.preview b { color: var(--color-primary); font-size: 16px; }
.preview-sub { font-size: 12px; color: var(--color-text-tertiary); margin-top: 2px; }
.submit-btn { width: 100%; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 12px; }

@media (max-width: 1400px) {
  .io-layout { flex-direction: column; }
  .io-card { flex: none; width: 100%; }
}
</style>
