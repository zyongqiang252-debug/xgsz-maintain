<template>
  <el-drawer
    :model-value="modelValue" title="备件出库" size="480px" :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="备件" required>
        <el-select
          v-model="form.partId" filterable remote clearable
          :remote-method="searchParts" :loading="partLoading"
          placeholder="输入编码 / 名称搜索" style="width: 100%" @change="onPartChange"
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
          v-model="form.quantity" :min="0.01" :max="selected ? Math.max(Number(available), 0.01) : 99999"
          :precision="2" :step="1" style="width: 100%"
        />
        <div v-if="selected && Number(form.quantity) > Number(available)" class="field-tip danger">
          超过可用库存（可用 {{ available }}）
        </div>
      </el-form-item>

      <el-form-item v-if="needSn" :label="`序列号 SN（必选 ${needCount} 个）`" required>
        <el-select
          v-model="form.serials" multiple filterable collapse-tags :max-collapse-tags="2"
          :loading="snLoading" placeholder="从在库 SN 里选要出库的件" style="width: 100%"
        >
          <el-option
            v-for="i in snOptions" :key="i.id"
            :label="`${i.sn}${i.location_text ? ' · ' + i.location_text : ''}`" :value="i.sn"
          />
        </el-select>
        <div class="field-tip" :class="{ danger: form.serials.length !== needCount }">
          需选 <b>{{ needCount }}</b> 个 SN，已选 <b>{{ form.serials.length }}</b> 个
          <span v-if="needCount > 0 && form.serials.length === needCount" class="ok">已对齐</span>
        </div>
      </el-form-item>
      <el-form-item v-else label="序列号 SN（选填，换下来的件建议填）">
        <el-input v-model="form.serialNo" maxlength="500" placeholder="一物一码；多个用逗号分隔" />
        <div class="field-tip">一个 SN 只能对应一件，填几个 SN 就出库几件</div>
      </el-form-item>

      <el-form-item label="照片附件（选填，坏件伤情 / 拆机现场）">
        <PhotoUpload v-model="form.attachments" />
      </el-form-item>

      <el-form-item label="关联工单（选填，会自动计入该工单备件成本）">
        <el-select
          v-model="form.workOrderId" filterable remote clearable
          :remote-method="searchWorkOrders" :loading="woLoading"
          placeholder="输入工单号 / 设备编码搜索" style="width: 100%"
        >
          <el-option v-for="wo in woOptions" :key="wo.id" :label="woLabel(wo)" :value="wo.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="出库事由">
        <el-input v-model="form.remark" maxlength="100" placeholder="选填，例如：GPU 卡故障更换 / 抢修领用" />
      </el-form-item>

      <el-button
        type="primary" class="submit-btn" :loading="submitting"
        :disabled="!form.partId || Number(available) <= 0" @click="submit"
      >确认出库</el-button>
    </el-form>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import request from '../api'
import PhotoUpload from '../components/PhotoUpload.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  partId: { type: Number, default: null },
})
const emit = defineEmits(['update:modelValue', 'done'])

const partOptions = ref([])
const partLoading = ref(false)
const selected = ref(null)
const submitting = ref(false)
const woOptions = ref([])
const woLoading = ref(false)
const form = reactive({ partId: null, quantity: 1, workOrderId: null, serialNo: '', serials: [], attachments: [], remark: '' })
const snOptions = ref([])
const snLoading = ref(false)

const needSn = computed(() => !!selected.value?.need_sn)
const needCount = computed(() => Math.trunc(Number(form.quantity || 0)))
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
  } catch { /* ignore */ } finally { partLoading.value = false }
}

const loadStockedSerials = async (partId) => {
  snLoading.value = true
  try {
    const res = await request.get('/part-instances/', {
      params: { part_id: partId, status: 'IN_STOCK', page_size: 200 },
    })
    snOptions.value = res.items || []
  } catch { snOptions.value = [] } finally { snLoading.value = false }
}

const onPartChange = (id) => {
  const hit = partOptions.value.find((p) => p.id === id)
  selected.value = hit || null
  form.serials = []
  if (hit && Number(availableOf(hit)) > 0 && Number(form.quantity) > Number(availableOf(hit))) {
    form.quantity = Number(availableOf(hit))
  }
  if (hit?.need_sn) loadStockedSerials(hit.id)
  else snOptions.value = []
}

const searchWorkOrders = async (keyword = '') => {
  woLoading.value = true
  try {
    const res = await request.get('/work-orders/', {
      params: { page: 1, page_size: 20, keyword: keyword || undefined },
    })
    woOptions.value = res.items || []
  } catch { /* ignore */ } finally { woLoading.value = false }
}

const reset = () => {
  Object.assign(form, { partId: null, quantity: 1, workOrderId: null, serialNo: '', serials: [], attachments: [], remark: '' })
  selected.value = null
  snOptions.value = []
}

const submit = async () => {
  if (!form.partId) return ElMessage.warning('先选择要出库的备件')
  if (!form.quantity || Number(form.quantity) <= 0) return ElMessage.warning('出库数量要大于 0')
  if (Number(form.quantity) > Number(available.value)) {
    return ElMessage.warning(`最多可出库 ${available.value}${selected.value?.unit || ''}`)
  }
  if (needSn.value && form.serials.length !== needCount.value) {
    return ElMessage.warning(`该件按 SN 管理：需选 ${needCount.value} 个 SN，当前 ${form.serials.length} 个`)
  }
  submitting.value = true
  try {
    const res = await request.post(`/spare-parts/${form.partId}/consume`, {
      quantity: Number(form.quantity),
      work_order_id: form.workOrderId || null,
      serial_no: needSn.value ? (form.serials.join(',') || null) : (form.serialNo.trim() || null),
      attachments: form.attachments,
      remark: form.remark || null,
    })
    ElMessage.success(`出库成功，剩余库存 ${res.stock_quantity}`)
    emit('done', form.partId)
    emit('update:modelValue', false)
    reset()
  } catch { /* ignore */ } finally { submitting.value = false }
}

watch(() => props.modelValue, async (open) => {
  if (!open) return
  reset()
  await searchParts('')
  if (props.partId) {
    try {
      const p = await request.get(`/spare-parts/${props.partId}`)
      selected.value = p
      form.partId = p.id
      if (!partOptions.value.some((x) => x.id === p.id)) partOptions.value.unshift(p)
      if (p.need_sn) loadStockedSerials(p.id)
    } catch { /* ignore */ }
  }
})
</script>

<style scoped>
.opt-row { display: flex; justify-content: space-between; gap: 12px; }
.opt-main { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.opt-meta { color: #86909C; font-size: 12px; flex-shrink: 0; }
.stock-line { display: flex; gap: 16px; margin: -4px 0 12px; padding: 8px 10px; background: #F7F8FA; border-radius: 6px; font-size: 12.5px; color: #4E5969; }
.stock-line b { color: #1D2129; }
.stock-line b.ok { color: #00B42A; }
.field-tip { font-size: 12px; color: #86909C; line-height: 1.4; margin-top: 2px; }
.field-tip.danger { color: #F53F3F; }
.field-tip .ok { color: #00B42A; margin-left: 6px; }
.submit-btn { width: 100%; }
</style>
