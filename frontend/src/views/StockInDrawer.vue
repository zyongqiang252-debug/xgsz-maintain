<template>
  <el-drawer
    :model-value="modelValue" title="备件入库" size="460px" :close-on-click-modal="false"
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
              <span class="opt-meta">现存 {{ p.stock_quantity }}{{ p.unit || '' }}</span>
            </div>
          </el-option>
        </el-select>
      </el-form-item>

      <el-form-item label="入库数量" required>
        <el-input-number
          v-model="form.quantity" :min="0.01" :precision="needSn ? 0 : 2" :step="1"
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

      <el-form-item v-if="canSetPrice" label="本次单价（元）">
        <el-input-number v-model="form.unitPrice" :min="0" :precision="2" :step="10" style="width: 100%" />
        <div class="field-tip">不填则沿用备件台账上的单价</div>
      </el-form-item>

      <el-form-item label="备注">
        <el-input v-model="form.remark" maxlength="100" placeholder="选填，例如：采购到货 / 退料入库" />
      </el-form-item>

      <div v-if="selected" class="preview">
        <div>入库后库存 <b>{{ afterStock }}</b> {{ selected.unit || '' }}</div>
        <div class="preview-sub">
          现存 {{ selected.stock_quantity }} + 本次 {{ form.quantity || 0 }}，本次金额 {{ amount }} 元
        </div>
      </div>

      <el-button type="primary" class="submit-btn" :loading="submitting" @click="submit">确认入库</el-button>
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

// 单价属于成本口径：技术员入库不能改价，沿用台账单价
const canSetPrice = (() => {
  try {
    const role = JSON.parse(localStorage.getItem('current_user') || '{}').role
    return role === 'ADMIN' || role === 'SUPERVISOR'
  } catch { return false }
})()

const partOptions = ref([])
const partLoading = ref(false)
const selected = ref(null)
const submitting = ref(false)
const form = reactive({ partId: null, quantity: 1, serialNo: '', attachments: [], unitPrice: null, remark: '' })

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
    if (selected.value && !list.some((p) => p.id === selected.value.id)) list.unshift(selected.value)
    partOptions.value = list
  } catch { /* ignore */ } finally { partLoading.value = false }
}

const onPartChange = (id) => {
  const hit = partOptions.value.find((p) => p.id === id)
  selected.value = hit || null
  form.unitPrice = hit ? Number(hit.unit_price || 0) : null
  form.serialNo = ''
}

const reset = () => {
  Object.assign(form, { partId: null, quantity: 1, serialNo: '', attachments: [], unitPrice: null, remark: '' })
  selected.value = null
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
      form.unitPrice = Number(p.unit_price || 0)
      if (!partOptions.value.some((x) => x.id === p.id)) partOptions.value.unshift(p)
    } catch { /* ignore */ }
  }
})
</script>

<style scoped>
.opt-row { display: flex; justify-content: space-between; gap: 12px; }
.opt-main { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.opt-meta { color: #86909C; font-size: 12px; flex-shrink: 0; }
.field-tip { font-size: 12px; color: #86909C; line-height: 1.4; margin-top: 2px; }
.field-tip.danger { color: #F53F3F; }
.field-tip .ok { color: #00B42A; margin-left: 6px; }
.preview { background: rgba(15, 198, 194, .08); border-radius: 6px; padding: 10px 12px; margin: 2px 0 14px; }
.preview b { color: #0FC6C2; font-size: 16px; }
.preview-sub { font-size: 12px; color: #86909C; margin-top: 2px; }
.submit-btn { width: 100%; }
</style>
