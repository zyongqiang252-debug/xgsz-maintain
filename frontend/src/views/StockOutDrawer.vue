<template>
  <el-drawer
    :model-value="modelValue" title="备件出库" size="480px" :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form label-position="top" @submit.prevent>
      <!-- 出库方式：领用单出库是常规路径；直接出库是管理员/主管的例外通道 -->
      <el-radio-group v-if="!isTechnician" v-model="mode" class="mode-switch" @change="onModeChange">
        <el-radio-button value="REQUISITION">按领用单出库</el-radio-button>
        <el-radio-button value="DIRECT">直接出库（例外）</el-radio-button>
      </el-radio-group>

      <el-alert
        v-if="isTechnician" class="tech-tip" type="info" show-icon :closable="false"
        title="领用要先提交申请，主管批准后再到这里出库；出库即扣减库存"
      />
      <el-alert
        v-else-if="mode === 'DIRECT'" class="tech-tip" type="warning" show-icon :closable="false"
        title="直接出库会跳过审批、必须填事由，并通知其他主管留痕；常规领用请用「按领用单出库」"
      />

      <!-- ============ 模式一：按领用单出库 ============ -->
      <template v-if="mode === 'REQUISITION'">
        <el-form-item label="待出库的领用单" required>
          <el-select
            v-model="reqId" filterable clearable :loading="reqLoading"
            :placeholder="isTechnician ? '选择已批准的领用申请' : '选择已批准的领用单（可代发）'"
            style="width: 100%" @change="onReqChange"
          >
            <el-option v-for="r in reqOptions" :key="r.id" :label="reqLabel(r)" :value="r.id">
              <div class="opt-row">
                <span class="opt-main">{{ reqLabel(r) }}</span>
                <span class="opt-meta">申请人 {{ r.applicant_name || '—' }}</span>
              </div>
            </el-option>
          </el-select>
          <div v-if="!reqLoading && reqOptions.length === 0" class="field-tip warning">
            {{ isTechnician ? '没有待出库的领用单：请先到「领用审批」提交申请，等主管批准' : '当前没有已批准、待发料的领用单' }}
          </div>
        </el-form-item>

        <template v-if="selectedReq">
          <div class="stock-line">
            <span>备件 <b>{{ selectedReq.part_code }}</b></span>
            <span>数量 <b>{{ selectedReq.quantity }}{{ selectedReq.unit || '' }}</b></span>
            <span>关联工单 <b>{{ selectedReq.work_order_id ? '#' + selectedReq.work_order_id : '无' }}</b></span>
            <span>现存 <b>{{ selectedPart ? selectedPart.stock_quantity : '—' }}</b></span>
          </div>

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

          <el-form-item label="照片附件（选填，坏件伤情 / 拆机现场）">
            <PhotoUpload v-model="form.attachments" />
          </el-form-item>

          <el-form-item label="出库备注（选填）">
            <el-input v-model="form.remark" maxlength="100" placeholder="例如：现场更换完成，旧件已拆回" />
          </el-form-item>

          <el-button
            type="primary" class="submit-btn" :loading="submitting"
            :disabled="!reqId" @click="submitRequisition"
          >确认出库</el-button>
        </template>
      </template>

      <!-- ============ 模式二：直接出库（例外） ============ -->
      <template v-else>
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
          <span>本次金额 <b>{{ money(amount) }}</b></span>
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

        <el-form-item label="出库事由（必填）">
          <el-input v-model="form.remark" maxlength="100" placeholder="必填，例如：GPU 卡故障紧急更换 / 客户现场抢修" />
          <div class="field-tip">直接出库会跳过审批，事由会写进流水并通知其他主管</div>
        </el-form-item>

        <el-button
          type="primary" class="submit-btn" :loading="submitting"
          :disabled="!form.partId || !form.remark.trim() || Number(available) <= 0" @click="submitDirect"
        >确认出库</el-button>
      </template>
    </el-form>
  </el-drawer>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'
import PhotoUpload from '../components/PhotoUpload.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  partId: { type: Number, default: null },
})
const emit = defineEmits(['update:modelValue', 'done'])

const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const isTechnician = currentUser.role === 'TECHNICIAN'

// 出库方式：技术员只能按领用单出库；管理员/主管默认也走领用单，直出是例外
const mode = ref('REQUISITION')

const partOptions = ref([])
const partLoading = ref(false)
const selected = ref(null)
const submitting = ref(false)
const woOptions = ref([])
const woLoading = ref(false)
const form = reactive({ partId: null, quantity: 1, workOrderId: null, serialNo: '', serials: [], attachments: [], remark: '' })
const snOptions = ref([])
const snLoading = ref(false)

// 领用单模式
const reqOptions = ref([])
const reqLoading = ref(false)
const reqId = ref(null)
const selectedReq = ref(null)
const selectedPart = ref(null)

const needSn = computed(() => !!selectedPart.value?.need_sn)
const needCount = computed(() => Math.trunc(Number(selectedReq.value?.quantity || form.quantity || 0)))
const availableOf = (p) =>
  Number(p.available_quantity ?? (Number(p.stock_quantity || 0) - Number(p.reserved_quantity || 0)))
const available = computed(() => (selected.value ? availableOf(selected.value) : 0))
const amount = computed(() =>
  Number(selected.value?.unit_price || 0) * Number(form.quantity || 0))
const money = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return '¥' + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
const woLabel = (wo) =>
  [wo.work_order_no, wo.device_code, (wo.fault_description || '').slice(0, 14)].filter(Boolean).join('｜')
const reqLabel = (r) =>
  `#${r.id} ${r.part_code} ${r.part_name} × ${r.quantity}${r.unit || ''}`

const loadRequisitions = async () => {
  reqLoading.value = true
  try {
    const res = await request.get('/spare-parts/requisitions/', {
      params: { status: 'APPROVED', mine: isTechnician ? true : undefined, page_size: 100 },
    })
    reqOptions.value = res.items || []
  } catch { reqOptions.value = [] } finally { reqLoading.value = false }
}

const onReqChange = async (id) => {
  form.serials = []
  form.attachments = []
  form.remark = ''
  snOptions.value = []
  selectedReq.value = reqOptions.value.find((r) => r.id === id) || null
  selectedPart.value = null
  if (!selectedReq.value) return
  try {
    selectedPart.value = await request.get(`/spare-parts/${selectedReq.value.part_id}`)
  } catch { selectedPart.value = null }
  if (selectedPart.value?.need_sn) loadStockedSerials(selectedPart.value.id)
}

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
  selectedReq.value = null
  selectedPart.value = null
  reqId.value = null
  snOptions.value = []
  mode.value = 'REQUISITION'
}

const checkSerials = () => {
  if (needSn.value && form.serials.length !== needCount.value) {
    ElMessage.warning(`该件按 SN 管理：需选 ${needCount.value} 个 SN，当前 ${form.serials.length} 个`)
    return false
  }
  return true
}

// 按领用单出库：扣库存 + 释放预占 + 划 SN + 回写工单成本（与主管发料同一个接口）
const submitRequisition = async () => {
  if (!selectedReq.value) return ElMessage.warning('先选择要出库的领用单')
  if (!checkSerials()) return
  try {
    await ElMessageBox.confirm(
      `确认出库 ${selectedReq.value.part_code} ${selectedReq.value.part_name} × ${selectedReq.value.quantity}${selectedReq.value.unit || ''}？出库后立即扣减库存。`,
      '按领用单出库',
      { confirmButtonText: '确认出库', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  submitting.value = true
  try {
    const res = await request.post(`/spare-parts/requisitions/${selectedReq.value.id}/issue`, {
      remark: form.remark.trim() || null,
    })
    ElMessage.success(`出库成功，剩余库存 ${res.stock_quantity ?? '已更新'}`)
    emit('done', selectedReq.value.part_id)
    emit('update:modelValue', false)
    reset()
  } catch { /* ignore */ } finally { submitting.value = false }
}

// 直接出库（例外通道，仅管理员/主管）
const submitDirect = async () => {
  if (isTechnician) return ElMessage.warning('请按领用单出库')
  if (!form.partId) return ElMessage.warning('先选择要出库的备件')
  if (!form.remark.trim()) return ElMessage.warning('直接出库必须填写出库事由')
  if (!form.quantity || Number(form.quantity) <= 0) return ElMessage.warning('出库数量要大于 0')
  if (Number(form.quantity) > Number(available.value)) {
    return ElMessage.warning(`最多可出库 ${available.value}${selected.value?.unit || ''}`)
  }
  if (!checkSerials()) return
  try {
    await ElMessageBox.confirm(
      `直接出库会跳过领用审批并立即扣减库存，确认出库 ${form.quantity}${selected.value?.unit || ''}？`,
      '直接出库（例外通道）',
      { confirmButtonText: '确认出库', cancelButtonText: '取消', type: 'warning' },
    )
  } catch { return }
  submitting.value = true
  try {
    const res = await request.post(`/spare-parts/${form.partId}/consume`, {
      quantity: Number(form.quantity),
      work_order_id: form.workOrderId || null,
      serial_no: needSn.value ? (form.serials.join(',') || null) : (form.serialNo.trim() || null),
      attachments: form.attachments,
      remark: form.remark.trim(),
    })
    ElMessage.success(`出库成功，剩余库存 ${res.stock_quantity}`)
    emit('done', form.partId)
    emit('update:modelValue', false)
    reset()
  } catch { /* ignore */ } finally { submitting.value = false }
}

const onModeChange = async (val) => {
  if (val === 'REQUISITION') {
    await loadRequisitions()
  } else {
    reset()
    mode.value = 'DIRECT'
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
  }
}

watch(() => props.modelValue, async (open) => {
  if (!open) return
  reset()
  if (isTechnician) {
    await loadRequisitions()
    return
  }
  // 主管/管理员：默认也是按领用单出库；从台账行内点「出库」时仍进直出模式并预选该备件
  await loadRequisitions()
  if (props.partId) {
    mode.value = 'DIRECT'
    await searchParts('')
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
.tech-tip { margin-bottom: 14px; }
.opt-main { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.opt-meta { color: #86909C; font-size: 12px; flex-shrink: 0; }
.mode-switch { margin-bottom: 14px; }
.stock-line { display: flex; flex-wrap: wrap; gap: 6px 14px; margin: -4px 0 12px; padding: 8px 10px; background: #F7F8FA; border-radius: 6px; font-size: 12.5px; color: #4E5969; }
.stock-line b { color: #1D2129; }
.stock-line b.ok { color: #00B42A; }
.field-tip { font-size: 12px; color: #86909C; line-height: 1.4; margin-top: 2px; }
.field-tip.danger { color: #F53F3F; }
.field-tip.warning { color: #FF7D00; }
.field-tip .ok { color: #00B42A; margin-left: 6px; }
.submit-btn { width: 100%; }
</style>
