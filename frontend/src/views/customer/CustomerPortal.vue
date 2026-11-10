<template>
  <div class="cp-page">
    <header class="cp-header">
      <div class="cp-brand">
        <img src="/logo-icon.png" alt="芯光智数" />
        <div>
          <div class="cp-name">芯光智数</div>
          <div class="cp-sub">客户报修中心</div>
        </div>
      </div>
      <div class="cp-user">
        <span>{{ customer.name }}<em v-if="customer.company"> · {{ customer.company }}</em></span>
        <el-button text type="primary" @click="logout">退出</el-button>
      </div>
    </header>

    <main class="cp-main">
      <section class="cp-section">
        <div class="cp-section-head">
          <h2>我的服务器</h2>
          <span class="cp-count">共 {{ devices.length }} 台</span>
        </div>
        <div v-if="!devices.length" class="cp-empty">暂无绑定设备，请联系管理员分配</div>
        <div v-else class="cp-devices">
          <div v-for="d in devices" :key="d.id" class="cp-device">
            <div class="cp-device-head">
              <span class="cp-device-name">{{ d.device_name || d.device_code }}</span>
              <el-tag size="small" :type="runStatusType(d.run_status)" effect="plain">
                {{ runStatusLabel(d.run_status) }}
              </el-tag>
            </div>
            <div class="cp-device-meta">
              <span>SN/编号：{{ d.device_code || '-' }}</span>
              <span>型号：{{ d.model || '-' }}</span>
              <span>位置：{{ d.location || '-' }}</span>
            </div>
            <el-button type="primary" size="small" @click="openReport(d)">报修</el-button>
          </div>
        </div>
      </section>

      <section class="cp-section">
        <div class="cp-section-head">
          <h2>我的报修</h2>
          <el-button size="small" @click="loadReports">刷新</el-button>
        </div>
        <el-table :data="reports" v-loading="loadingReports" size="small" stripe>
          <el-table-column prop="work_order_no" label="报修单号" width="170" />
          <el-table-column prop="device_code" label="设备" width="140" show-overflow-tooltip />
          <el-table-column prop="fault_description" label="故障描述" min-width="220" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)" effect="plain">{{ row.status_label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="验收" width="150">
            <template #default="{ row }">
              <template v-if="row.status === 'ARCHIVING'">
                <el-button size="small" type="success" plain @click="acceptReport(row, true)">确认解决</el-button>
                <el-button size="small" type="danger" link @click="acceptReport(row, false)">未解决</el-button>
              </template>
              <span v-else-if="row.customer_accept_status === 'ACCEPTED'" class="accept-done">已确认</span>
              <span v-else class="rate-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="评价" width="120">
            <template #default="{ row }">
              <span v-if="row.satisfaction_score" class="rate-done">{{ row.satisfaction_score }} 分</span>
              <el-button v-else-if="row.can_rate" size="small" type="primary" plain
                         @click="openRate(row)">评价</el-button>
              <span v-else class="rate-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="提交时间" width="160">
            <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ').slice(0, 16) }}</template>
          </el-table-column>
        </el-table>
      </section>
    </main>

    <el-dialog v-model="dlg.visible" title="提交报修" width="520px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="设备">
          <span>{{ dlg.device?.device_name }}（{{ dlg.device?.device_code }}）</span>
        </el-form-item>
        <el-form-item label="故障描述" required>
          <el-input v-model="dlg.faultDescription" type="textarea" :rows="4" maxlength="500"
                    show-word-limit placeholder="请描述现象，例如：开机后 GPU 风扇全速、BMC 报 ECC 错误" />
        </el-form-item>
        <el-form-item label="故障现象">
          <el-input v-model="dlg.faultPhenomenon" type="textarea" :rows="2" maxlength="500"
                    placeholder="选填：报错信息、指示灯状态、发生时间等" />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="dlg.contactName" maxlength="50" />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="dlg.contactPhone" maxlength="20" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="dlg.submitting" @click="submitReport">提交报修</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="rate.visible" title="服务评价" width="420px">
      <div class="rate-order">{{ rate.row?.work_order_no }} · {{ rate.row?.device_code }}</div>
      <div class="rate-line">
        <span class="rate-label">服务评分</span>
        <el-rate v-model="rate.score" />
      </div>
      <el-input v-model="rate.comment" type="textarea" :rows="3" maxlength="300" show-word-limit
                placeholder="选填：说说这次服务的感受" style="margin-top:12px" />
      <template #footer>
        <el-button @click="rate.visible = false">取消</el-button>
        <el-button type="primary" :loading="rate.saving" :disabled="!rate.score" @click="submitRate">提交评价</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import customerRequest from '../../api/customer'

const router = useRouter()
const customer = (() => {
  try { return JSON.parse(localStorage.getItem('customer_user') || '{}') } catch { return {} }
})()
const devices = ref([])
const reports = ref([])
const loadingReports = ref(false)

const dlg = reactive({
  visible: false, device: null, faultDescription: '', faultPhenomenon: '',
  contactName: customer.name || '', contactPhone: customer.phone || '',
  submitting: false,
})
const rate = reactive({ visible: false, row: null, score: 5, comment: '', saving: false })

const runStatusLabel = (s) => ({
  ONLINE: '运行中', ALARM: '告警', FAULT: '故障', OFFLINE: '离线', UNKNOWN: '未知',
}[s] || '未知')
const runStatusType = (s) => ({
  ONLINE: 'success', ALARM: 'warning', FAULT: 'danger', OFFLINE: 'info', UNKNOWN: 'info',
}[s] || 'info')

const statusType = (s) => ({
  SUBMITTED: 'warning', ASSIGNED: 'primary', ACCEPTED: 'primary',
  ARRIVED: 'primary', INSPECTING: 'warning', IN_PROGRESS: 'warning',
  ARCHIVING: 'warning', ARCHIVED: 'success', REJECTED: 'danger',
}[s] || 'info')

const loadDevices = async () => {
  try {
    const res = await customerRequest.get('/customer/devices')
    devices.value = res.items || []
  } catch (e) {
    if (e?.response?.status === 401 || e?.response?.status === 403) logout()
    ElMessage.error('加载设备失败')
  }
}

const loadReports = async () => {
  loadingReports.value = true
  try {
    const res = await customerRequest.get('/customer/reports')
    reports.value = res.items || []
  } catch { /* ignore */ }
  finally { loadingReports.value = false }
}

const openReport = (device) => {
  dlg.device = device
  dlg.faultDescription = ''
  dlg.faultPhenomenon = ''
  dlg.contactName = customer.name || ''
  dlg.contactPhone = customer.phone || ''
  dlg.visible = true
}

const submitReport = async () => {
  if (!dlg.faultDescription.trim()) {
    ElMessage.warning('请填写故障描述')
    return
  }
  dlg.submitting = true
  try {
    const res = await customerRequest.post('/customer/reports', {
      device_id: dlg.device.id,
      fault_description: dlg.faultDescription.trim(),
      fault_phenomenon: dlg.faultPhenomenon.trim() || null,
      contact_name: dlg.contactName.trim() || null,
      contact_phone: dlg.contactPhone.trim() || null,
    })
    ElMessage.success(`报修已提交，单号 ${res.work_order_no}`)
    dlg.visible = false
    loadReports()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    dlg.submitting = false
  }
}

const acceptReport = async (row, accepted) => {
  let remark = null
  if (accepted) {
    try {
      await ElMessageBox.confirm(
        `确认工单 ${row.work_order_no} 已解决？确认后服务方才能归档。`, '确认解决',
        { type: 'success', confirmButtonText: '确认解决' })
    } catch { return }
  } else {
    try {
      const res = await ElMessageBox.prompt('请说明未解决的原因，服务方会重新处理', '反馈未解决', {
        inputType: 'textarea', inputPlaceholder: '例如：重启后仍报错',
        inputValidator: (v) => (v && v.trim() ? true : '请填写原因'),
      })
      remark = res.value
    } catch { return }
  }
  try {
    const res = await customerRequest.post(`/customer/reports/${row.id}/accept`, {
      accepted, remark,
    })
    ElMessage.success(res.message || '已提交')
    loadReports()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  }
}

const openRate = (row) => {  rate.row = row
  rate.score = 5
  rate.comment = ''
  rate.visible = true
}
const submitRate = async () => {
  if (!rate.score) return ElMessage.warning('请选择评分')
  rate.saving = true
  try {
    await customerRequest.post(`/customer/reports/${rate.row.id}/rating`, {
      score: rate.score, comment: rate.comment.trim() || null,
    })
    ElMessage.success('感谢评价')
    rate.visible = false
    loadReports()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '评价失败')
  } finally { rate.saving = false }
}

const logout = () => {  localStorage.removeItem('customer_token')
  localStorage.removeItem('customer_user')
  router.replace('/c/login')
}

onMounted(() => {
  if (!localStorage.getItem('customer_token')) {
    router.replace('/c/login')
    return
  }
  loadDevices()
  loadReports()
})
</script>

<style scoped>
.cp-page { min-height: 100vh; background: #F5F7FA; }
.cp-header { height: 64px; background: #fff; display: flex; align-items: center;
  justify-content: space-between; padding: 0 28px; box-shadow: 0 2px 8px rgba(0,0,0,.04); }
.cp-brand { display: flex; align-items: center; gap: 10px; }
.cp-brand img { width: 34px; height: 34px; object-fit: contain; }
.cp-name { font-size: 16px; font-weight: 600; color: #1D2129; }
.cp-sub { font-size: 12px; color: #86909C; }
.cp-user { display: flex; align-items: center; gap: 10px; color: #4E5969; font-size: 14px; }
.cp-user em { font-style: normal; color: #86909C; font-size: 12px; }
.cp-main { max-width: 1100px; margin: 0 auto; padding: 24px 20px 48px; }
.cp-section { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
.cp-section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.cp-section-head h2 { margin: 0; font-size: 17px; color: #1D2129; }
.cp-count { color: #86909C; font-size: 13px; }
.cp-empty { color: #86909C; padding: 24px 0; text-align: center; }
.cp-devices { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.cp-device { border: 1px solid #EDEFF3; border-radius: 10px; padding: 14px; background: #FAFBFC; }
.cp-device-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.cp-device-name { font-weight: 600; color: #1D2129; }
.cp-device-meta { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: #86909C; margin-bottom: 12px; }
@media (max-width: 640px) {
  .cp-header { padding: 0 14px; }
  .cp-user span { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
}
.rate-done { color: #FF7D00; font-weight: 600; }
.accept-done { color: #00B42A; font-weight: 600; }
.rate-muted { color: #C9CDD4; }
.rate-order { color: #86909C; font-size: 13px; margin-bottom: 14px; }
.rate-line { display: flex; align-items: center; gap: 14px; }
.rate-label { color: #4E5969; font-size: 14px; }
</style>
