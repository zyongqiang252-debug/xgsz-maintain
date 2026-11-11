<template>
  <div class="tech-detail" v-if="wo">
    <!-- 工单头部 -->
    <div class="detail-header">
      <div class="header-top">
        <span class="wo-no">{{ wo.work_order_no }}</span>
        <span class="header-status">{{ statusLabel(wo.status) }}</span>
      </div>
      <div class="header-desc">{{ wo.fault_description }}</div>
    </div>

    <!-- 基本信息（与 PC 端工单详情一致） -->
    <div class="info-section">
      <h3>基本信息</h3>
      <div class="info-row"><span>服务器</span><span>{{ wo.device_name || wo.device_code || '-' }}<template v-if="wo.device_name && wo.device_code">（{{ wo.device_code }}）</template></span></div>
      <div class="info-row" v-if="wo.device_type"><span>服务器类型</span><span>{{ wo.device_type }}</span></div>
      <div class="info-row" v-if="wo.location"><span>机房位置</span><span>{{ wo.location }}</span></div>
      <div class="info-row" v-if="wo.fault_object"><span>涉及对象</span><span>{{ wo.fault_object }}</span></div>
      <div class="info-row" v-if="wo.service_mode"><span>服务方式</span><span>{{ serviceModeLabel(wo.service_mode) }}</span></div>
      <div class="info-row" v-if="wo.reporter_name"><span>报修人</span><span>{{ wo.reporter_name }}</span></div>
      <div class="info-row" v-if="wo.customer_name"><span>客户</span><span>{{ wo.customer_name }}</span></div>
      <div class="info-row" v-if="wo.technician_name"><span>技术员</span><span>{{ wo.technician_name }}</span></div>
      <div class="info-row" v-if="wo.first_response_at"><span>领取时间</span><span>{{ formatTime(wo.first_response_at) }}</span></div>
      <div class="info-row"><span>上报时间</span><span>{{ formatTime(wo.created_at) }}</span></div>
    </div>

    <!-- 故障信息 -->
    <div class="info-section">
      <h3>故障信息</h3>
      <div class="info-row" v-if="wo.fault_code"><span>故障码</span><span>{{ wo.fault_code }}</span></div>
      <div class="info-row" v-if="wo.fault_category"><span>故障类别</span><span>{{ wo.fault_category }}</span></div>
      <div class="info-row"><span>故障描述</span><span>{{ wo.fault_description }}</span></div>
      <div class="info-row" v-if="wo.fault_phenomenon"><span>故障现象</span><span>{{ wo.fault_phenomenon }}</span></div>
    </div>

    <!-- 诊断与维修（有内容才展示） -->
    <div class="info-section" v-if="wo.root_cause || wo.solution_steps || wo.work_hours || wo.repair_result">
      <h3>诊断与维修</h3>
      <div class="info-row" v-if="wo.root_cause"><span>原因分析</span><span>{{ wo.root_cause }}</span></div>
      <div class="info-row" v-if="wo.solution_steps"><span>处理步骤</span><span class="pre-wrap">{{ wo.solution_steps }}</span></div>
      <div class="info-row" v-if="wo.repair_result"><span>维修结果</span><span>{{ repairResultLabel(wo.repair_result) }}</span></div>
      <div class="info-row" v-if="wo.work_hours"><span>工时</span><span>{{ wo.work_hours }} 小时</span></div>
    </div>

    <!-- AI 分析（只保留置信度，根因/方案已在上面） -->
    <div class="info-section" v-if="wo.analysis_result && wo.confidence != null">
      <h3>AI 分析</h3>
      <div class="info-row"><span>置信度</span><span>{{ (wo.confidence * 100).toFixed(0) }}%</span></div>
    </div>

    <!-- 报修人提交的照片 -->
    <div class="info-section" v-if="reporterMedia.length">
      <h3>报修人提交的照片</h3>
      <div class="media-grid">
        <img v-for="(m, i) in reporterMedia" :key="'rm' + i" :src="m.url" class="media-img" />
      </div>
    </div>

    <!-- 维修人员现场附件 -->
    <div class="info-section" v-if="repairMedia.length">
      <h3>现场附件（维修）</h3>
      <div class="media-grid">
        <img v-for="(m, i) in repairMedia" :key="'rp' + i" :src="m.url" class="media-img" />
      </div>
    </div>

    <!-- 库存关联 -->
    <div class="info-section" v-if="inventory?.items?.length">
      <h3>备件库存</h3>
      <div class="stock-item" v-for="sp in inventory.items" :key="sp.id">
        <span class="stock-name">{{ sp.part_name }}</span>
        <span class="stock-qty" :class="{ out: sp.stock_quantity <= 0, low: sp.stock_quantity <= sp.low_stock }">
          库存 {{ sp.stock_quantity }}
        </span>
      </div>
    </div>

    <!-- 操作按钮：按状态机逐步推进（接单 → 到场 → 检查 → 维修中 → 完成报告） -->
    <div class="action-bar" v-if="primaryAction">
      <button class="action-btn primary" @click="handleAction" :disabled="loading">
        {{ loading ? '处理中...' : primaryAction.label }}
      </button>
    </div>

    <!-- 已完成工单的报告展示 -->
    <div class="info-section" v-if="wo.completion_report">
      <h3>完成报告</h3>
      <div class="info-row"><span>处理时长</span><span>{{ wo.completion_report.work_hours || 0 }}h</span></div>
      <div class="info-row"><span>处理描述</span><span>{{ wo.completion_report.solution_desc || '-' }}</span></div>
    </div>

    <!-- 完成报告弹窗 -->
    <div class="report-modal" v-if="showReport" @click.self="showReport = false">
      <div class="report-panel">
        <h3>完成报告</h3>

        <label>工时（小时）</label>
        <input v-model.number="reportForm.work_hours" type="number" step="0.5" min="0" class="report-input" />

        <label>维修结果</label>
        <div class="result-options">
          <span v-for="opt in resultOptions" :key="opt.value"
                class="result-chip" :class="{ active: reportForm.repair_result === opt.value }"
                @click="reportForm.repair_result = opt.value">{{ opt.label }}</span>
        </div>

        <label>处理说明</label>
        <textarea v-model="reportForm.solution_desc" class="report-textarea" rows="3" placeholder="描述处理过程和结果..."></textarea>

        <label>现场拍照</label>
        <div class="report-photos">
          <div class="add-photo" @click="pickPhoto" :class="{ uploading }">{{ uploading ? '...' : '+' }}</div>
          <img v-for="(url, i) in reportForm.completion_photos" :key="i" :src="url" class="photo-thumb" />
        </div>
        <input ref="photoInput" type="file" accept="image/*" capture="environment" multiple
               style="display:none" @change="onPhotoPicked" />

        <div class="report-actions">
          <button class="btn-cancel" @click="showReport = false">取消</button>
          <button class="btn-submit" @click="handleComplete" :disabled="completing">
            {{ completing ? '提交中...' : '提交' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '../../api'

const route = useRoute()
const router = useRouter()
const wo = ref(null)
const inventory = ref(null)
const loading = ref(false)
const completing = ref(false)
const showReport = ref(false)

const reportForm = ref({ work_hours: 1.0, solution_desc: '', repair_result: 'PERMANENT_FIX', completion_photos: [] })
const photoInput = ref(null)
const uploading = ref(false)
const resultOptions = [
  { value: 'PERMANENT_FIX', label: '彻底修复' },
  { value: 'TEMPORARY_FIX', label: '临时措施' },
  { value: 'UNABLE_FIX', label: '未能修复' },
]

const STATUS_LABEL = {
  DRAFT: '草稿', SUBMITTED: '待派工', ASSIGNED: '待接单', ACCEPTED: '已接单',
  ARRIVED: '已到场', INSPECTING: '检查中', IN_PROGRESS: '维修中',
  ARCHIVING: '待归档', ARCHIVED: '已归档', COMPLETED: '已完成', REJECTED: '已退回',
}
const statusLabel = (s) => STATUS_LABEL[s] || s || '-'
const serviceModeLabel = (v) => ({ REMOTE: '远程处理', SITE: '现场处理', RMA: '返厂维修', VENDOR: '第三方现场' }[v] || v)
const repairResultLabel = (v) => ({ PERMANENT_FIX: '彻底修复', TEMPORARY_FIX: '临时措施', UNABLE_FIX: '未能修复' }[v] || v)
const formatTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

// 附件兼容「字符串 URL」和「{url,name,type,source}」两种格式
const normalizeMedia = (list) => (Array.isArray(list) ? list : [])
  .map((x) => (typeof x === 'string' ? { url: x } : x))
  .filter((x) => x && x.url)
const reporterMedia = computed(() => normalizeMedia(wo.value?.fault_media))
const repairMedia = computed(() => normalizeMedia(wo.value?.attachments))

const fetchData = async () => {
  try {
    const res = await request.get(`/m/v1/wo/${route.params.id}`)
    wo.value = res
    inventory.value = res.inventory
  } catch { /* handled */ }
}

// 当前状态对应的主操作（与后端 VALID_TRANSITIONS 对齐）
const primaryAction = computed(() => {
  const w = wo.value
  if (!w) return null
  const assigned = w.technician_name || w.status !== 'SUBMITTED'
  if (w.status === 'SUBMITTED' && !assigned) return { label: '领取工单', action: 'claim' }
  if (w.status === 'ASSIGNED') return { label: '接单', action: 'accept' }
  if (w.status === 'ACCEPTED') return { label: '到场签到', action: 'arrive' }
  if (w.status === 'ARRIVED') return { label: '开始检查', action: 'inspect' }
  if (w.status === 'INSPECTING') return { label: '开始维修', action: 'start' }
  if (w.status === 'IN_PROGRESS') return { label: '提交完成报告', action: 'report' }
  return null
})

const handleAction = async () => {
  if (!primaryAction.value) return
  if (primaryAction.value.action === 'report') {
    showReport.value = true
    return
  }
  loading.value = true
  try {
    if (primaryAction.value.action === 'claim') {
      await request.post(`/m/v1/wo/${route.params.id}/claim`)
      ElMessage.success('已领取工单，请接单')
    } else {
      const map = { accept: 'ACCEPTED', arrive: 'ARRIVED', inspect: 'INSPECTING', start: 'IN_PROGRESS' }
      const to = map[primaryAction.value.action]
      await request.post(`/m/v1/wo/${route.params.id}/transition`, {
        to_status: to, remark: `移动端${primaryAction.value.label}`,
      })
      ElMessage.success(primaryAction.value.label + '成功')
    }
    await fetchData()
  } catch { /* handled */ }
  finally { loading.value = false }
}

const pickPhoto = () => {
  if (!uploading.value) photoInput.value?.click()
}

const onPhotoPicked = async (e) => {
  const files = Array.from(e.target.files || [])
  e.target.value = ''
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      const fd = new FormData()
      fd.append('file', file)
      const res = await request.post('/upload/work-order-image', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      reportForm.value.completion_photos.push(res.url)
    }
  } catch {
    ElMessage.error('照片上传失败')
  } finally {
    uploading.value = false
  }
}

const handleComplete = async () => {
  completing.value = true
  try {
    await request.post(`/m/v1/wo/${route.params.id}/complete`, {
      work_hours: reportForm.value.work_hours,
      solution_desc: reportForm.value.solution_desc,
      repair_result: reportForm.value.repair_result,
      completion_photos: reportForm.value.completion_photos,
    })
    ElMessage.success('完成报告已提交')
    showReport.value = false
    router.push('/m/queue')
  } catch { /* handled */ }
  finally { completing.value = false }
}

onMounted(fetchData)
</script>

<style scoped>
.tech-detail { padding: 16px; padding-bottom: 80px; }

.detail-header {
  background: linear-gradient(135deg, #14C8C4, #0AA9A5);
  border-radius: 12px; padding: 18px; color: #fff; margin-bottom: 16px;
}
.header-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.wo-no { font-size: 18px; font-weight: 600; font-family: monospace; }
.header-status { font-size: 14px; opacity: 0.95; background: rgba(255,255,255,.18); padding: 2px 8px; border-radius: 10px; }
.header-desc { font-size: 13px; opacity: 0.92; line-height: 1.45; }

.info-section {
  background: #fff; border-radius: 10px; padding: 14px; margin-bottom: 12px;
}
.info-section h3 { font-size: 15px; font-weight: 600; color: #1D2129; margin-bottom: 10px; }
.info-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #F5F6F8; font-size: 13px; gap: 12px; }
.info-row:last-child { border-bottom: none; }
.info-row span:first-child { color: #86909C; min-width: 60px; flex-shrink: 0; }
.info-row span:last-child { color: #1D2129; text-align: right; flex: 1; word-break: break-all; }
.pre-wrap { white-space: pre-wrap; }

.media-grid { display: flex; gap: 8px; overflow-x: auto; }
.media-img { width: 100px; height: 75px; border-radius: 6px; object-fit: cover; flex-shrink: 0; }

.stock-item { display: flex; justify-content: space-between; padding: 6px 0; font-size: 13px; }
.stock-qty { color: #00B42A; font-weight: 500; }
.stock-qty.low { color: #FF7D00; }
.stock-qty.out { color: #F53F3F; }

.action-bar { position: fixed; bottom: 0; left: 0; right: 0; padding: 12px 16px; background: #fff; box-shadow: 0 -2px 8px rgba(0,0,0,.06); max-width: 430px; margin: 0 auto; }
.action-btn {
  width: 100%; padding: 14px; border: none; border-radius: 8px;
  font-size: 16px; font-weight: 500; cursor: pointer;
}
.action-btn.primary { background: #0FC6C2; color: #fff; }
.action-btn:disabled { opacity: 0.5; }

/* 报告弹窗 */
.report-modal {
  position: fixed; inset: 0; background: rgba(0,0,0,.45);
  display: flex; align-items: flex-end; justify-content: center; z-index: 100;
}
.report-panel {
  background: #fff; width: 100%; max-width: 430px; border-radius: 14px 14px 0 0;
  padding: 20px 10px; box-sizing: border-box;
}
.report-panel h3 { font-size: 16px; margin-bottom: 12px; }
.report-panel label { display: block; font-size: 14px; color: #4E5969; margin: 12px 0 6px; }
.report-input, .report-textarea {
  width: 100%; box-sizing: border-box; border: 1px solid #E5E6EB;
  border-radius: 6px; padding: 10px; font-size: 14px;
}
.result-options { display: flex; gap: 8px; }
.result-chip {
  flex: 1; text-align: center; padding: 8px 4px; border-radius: 6px;
  background: #F2F3F5; color: #4E5969; font-size: 13px; cursor: pointer;
}
.result-chip.active { background: #0FC6C2; color: #fff; }
.report-photos { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; }
.add-photo, .photo-thumb {
  width: 64px; height: 64px; border-radius: 6px; border: 1px dashed #C9CDD4;
  display: flex; align-items: center; justify-content: center; color: #86909C; font-size: 22px;
}
.photo-thumb { border: none; object-fit: cover; }
.report-actions { display: flex; gap: 12px; margin-top: 18px; }
.btn-cancel, .btn-submit {
  flex: 1; padding: 12px; border: none; border-radius: 8px; font-size: 15px;
}
.btn-cancel { background: #F2F3F5; color: #4E5969; }
.btn-submit { background: #0FC6C2; color: #fff; }
</style>
