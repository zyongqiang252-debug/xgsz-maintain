<template>
  <div class="page" v-loading="loading">
    <div class="page-header">
      <div class="header-left">
        <el-button link @click="$router.push('/sys?tab=customers')">← 返回客户列表</el-button>
        <h2 class="page-title">{{ c.company || c.name }}</h2>
        <span class="cust-code">{{ c.code }}</span>
        <el-tag size="small" :type="levelType(c.level)" effect="plain">{{ c.level_label }}</el-tag>
        <el-tag v-for="t in c.tags" :key="t" size="small" effect="plain" class="tag-gap">{{ t }}</el-tag>
        <el-tag size="small" :type="c.is_active ? 'success' : 'info'" effect="plain">
          {{ c.is_active ? '启用' : '停用' }}
        </el-tag>
      </div>
      <div class="header-actions">
        <el-button :loading="exporting" @click="exportReport">导出服务报告</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <div class="stat-card"><div class="stat-num">{{ c.order_count || 0 }}</div><div class="stat-label">累计工单</div></div>
      <div class="stat-card"><div class="stat-num warning">{{ c.open_count || 0 }}</div><div class="stat-label">未完成</div></div>
      <div class="stat-card"><div class="stat-num success">{{ c.archived_count || 0 }}</div><div class="stat-label">已归档</div></div>
      <div class="stat-card"><div class="stat-num danger">{{ c.overdue_count || 0 }}</div><div class="stat-label">已超时</div></div>
      <div class="stat-card"><div class="stat-num score">{{ c.avg_satisfaction || '—' }}</div><div class="stat-label">平均满意度</div></div>
    </div>

    <el-row :gutter="16">
      <el-col :span="9">
        <el-card shadow="never" class="info-card">
          <template #header><span class="card-title">客户信息</span></template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="联系人">{{ c.name }}</el-descriptions-item>
            <el-descriptions-item label="手机号">{{ c.phone }}</el-descriptions-item>
            <el-descriptions-item label="地址 / 机房">{{ c.address || '—' }}</el-descriptions-item>
            <el-descriptions-item label="归属人">{{ c.owner_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="上级客户">{{ c.parent_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="合同号">{{ c.contract_no || '—' }}</el-descriptions-item>
            <el-descriptions-item label="服务期限">
              {{ c.service_start || '—' }} ~ {{ c.service_end || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="合同 SLA">
              响应 {{ c.sla_response_hours != null ? c.sla_response_hours + ' 小时' : '—' }} ·
              修复 {{ c.sla_resolve_hours != null ? c.sla_resolve_hours + ' 小时' : '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="绑定设备">{{ c.device_count }} 台</el-descriptions-item>
            <el-descriptions-item label="备注">{{ c.remark || '—' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="15">
        <el-card shadow="never">
          <el-tabs v-model="tab">
            <el-tab-pane label="工单记录" name="orders">
              <el-table :data="orders" size="small" stripe v-loading="ordersLoading">
                <el-table-column prop="work_order_no" label="工单号" width="160">
                  <template #default="{ row }">
                    <el-link type="primary" @click="$router.push(`/work-orders/${row.id}`)">{{ row.work_order_no }}</el-link>
                  </template>
                </el-table-column>
                <el-table-column prop="device_code" label="设备" width="120" show-overflow-tooltip />
                <el-table-column prop="fault_description" label="故障描述" min-width="180" show-overflow-tooltip />
                <el-table-column label="状态" width="86">
                  <template #default="{ row }">
                    <el-tag size="small" :type="statusType(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="technician_name" label="负责人" width="90" />
                <el-table-column label="提交时间" width="140">
                  <template #default="{ row }">{{ fmt(row.created_at) }}</template>
                </el-table-column>
              </el-table>
              <div class="pager">
                <el-pagination v-model:current-page="orderPage" :page-size="10" :total="orderTotal"
                               layout="total, prev, pager, next" @current-change="loadOrders" />
              </div>
            </el-tab-pane>

            <el-tab-pane label="设备" name="devices">
              <el-table :data="c.devices" size="small" stripe>
                <el-table-column prop="device_code" label="设备编号" width="150" />
                <el-table-column prop="device_name" label="设备名称" min-width="180" />
                <el-table-column prop="location" label="位置" min-width="160" />
                <el-table-column label="操作" width="80">
                  <template #default="{ row }">
                    <el-link type="primary" @click="$router.push(`/devices/${row.id}`)">查看</el-link>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="机房 / 站点" name="sites">
              <div class="contacts-head">
                <span class="card-title">机房 / 站点</span>
                <el-button type="primary" size="small" @click="openSite()">新增机房</el-button>
              </div>
              <el-table :data="sites" size="small" stripe>
                <el-table-column prop="name" label="名称" width="140">
                  <template #default="{ row }">
                    {{ row.name }}
                    <el-tag v-if="row.is_default" size="small" type="success" effect="plain">默认</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="address" label="地址" min-width="220" show-overflow-tooltip />
                <el-table-column label="现场联系人" width="160">
                  <template #default="{ row }">{{ row.contact_name || '—' }} {{ row.contact_phone || '' }}</template>
                </el-table-column>
                <el-table-column label="操作" width="120">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="openSite(row)">编辑</el-button>
                    <el-button link type="danger" @click="removeSite(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="联系人" name="contacts">
              <div class="contacts-head">
                <span class="card-title">联系人列表</span>
                <el-button type="primary" size="small" @click="openContact()">新增联系人</el-button>
              </div>
              <el-table :data="contacts" size="small" stripe>
                <el-table-column prop="name" label="姓名" width="110">
                  <template #default="{ row }">
                    {{ row.name }}
                    <el-tag v-if="row.is_primary" size="small" type="success" effect="plain">主</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="title" label="职务" width="100" />
                <el-table-column prop="phone" label="电话" width="130" />
                <el-table-column prop="email" label="邮箱" min-width="150" show-overflow-tooltip />
                <el-table-column label="操作" width="120">
                  <template #default="{ row }">
                    <el-button link type="primary" @click="openContact(row)">编辑</el-button>
                    <el-button v-if="!row.is_primary" link type="danger" @click="removeContact(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="siteDlg.visible" :title="siteDlg.id ? '编辑机房' : '新增机房'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="名称" required><el-input v-model="siteDlg.name" maxlength="50" placeholder="例如：A 机房 / 北京亦庄" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="siteDlg.address" maxlength="200" /></el-form-item>
        <el-form-item label="现场联系人"><el-input v-model="siteDlg.contact_name" maxlength="50" /></el-form-item>
        <el-form-item label="联系电话"><el-input v-model="siteDlg.contact_phone" maxlength="20" /></el-form-item>
        <el-form-item label="默认机房"><el-switch v-model="siteDlg.is_default" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="siteDlg.remark" type="textarea" :rows="2" maxlength="200" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="siteDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="siteDlg.saving" @click="saveSite">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="contactDlg.visible" :title="contactDlg.id ? '编辑联系人' : '新增联系人'" width="480px">
      <el-form label-width="80px">
        <el-form-item label="姓名" required><el-input v-model="contactDlg.name" maxlength="50" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="contactDlg.phone" maxlength="20" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="contactDlg.email" maxlength="100" /></el-form-item>
        <el-form-item label="职务"><el-input v-model="contactDlg.title" maxlength="50" /></el-form-item>
        <el-form-item label="主联系人"><el-switch v-model="contactDlg.is_primary" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="contactDlg.remark" type="textarea" :rows="2" maxlength="200" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="contactDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="contactDlg.saving" @click="saveContact">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'
import { downloadFile } from '../utils/download'

const route = useRoute()
const id = route.params.id
const loading = ref(false)
const exporting = ref(false)
const c = ref({ devices: [], tags: [], contacts: [] })
const orders = ref([])
const orderTotal = ref(0)
const orderPage = ref(1)
const ordersLoading = ref(false)
const contacts = ref([])
const sites = ref([])
const tab = ref('orders')

const contactDlg = reactive({
  visible: false, id: null, name: '', phone: '', email: '', title: '',
  is_primary: false, remark: '', saving: false,
})
const siteDlg = reactive({
  visible: false, id: null, name: '', address: '', contact_name: '',
  contact_phone: '', is_default: false, remark: '', saving: false,
})

const STATUS = {
  DRAFT: '草稿', SUBMITTED: '待派工', ASSIGNED: '已派单', ACCEPTED: '已接单',
  ARRIVED: '已到场', INSPECTING: '检查中', IN_PROGRESS: '维修中',
  ARCHIVING: '待归档', ARCHIVED: '已归档', REJECTED: '已退回',
}
const statusLabel = (s) => STATUS[s] || s
const statusType = (s) => ({
  SUBMITTED: 'warning', ASSIGNED: 'primary', ACCEPTED: 'primary',
  ARRIVED: 'primary', INSPECTING: 'warning', IN_PROGRESS: 'warning',
  ARCHIVING: 'warning', ARCHIVED: 'success', REJECTED: 'danger',
}[s] || 'info')
const levelType = (lv) => ({ VIP: 'danger', KEY: 'warning', NORMAL: 'info' }[lv] || 'info')
const fmt = (t) => t ? t.replace('T', ' ').slice(0, 16) : '—'

const load = async () => {
  loading.value = true
  try {
    c.value = await request.get(`/customers/${id}`)
    contacts.value = c.value.contacts || []
    sites.value = c.value.sites || []
    await loadOrders()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载客户失败')
  } finally { loading.value = false }
}

const loadOrders = async () => {
  ordersLoading.value = true
  try {
    const res = await request.get(`/customers/${id}/orders`, {
      params: { page: orderPage.value, page_size: 10 },
    })
    orders.value = res.items || []
    orderTotal.value = res.total || 0
  } catch { /* ignore */ }
  finally { ordersLoading.value = false }
}

const exportReport = async () => {
  exporting.value = true
  try {
    await downloadFile(`/customers/${id}/export`, {}, `客户-${c.value.code || id}.xlsx`)
    ElMessage.success('报告已导出')
  } catch {
    ElMessage.error('导出失败')
  } finally { exporting.value = false }
}

const openSite = (row = null) => {
  Object.assign(siteDlg, {
    visible: true, id: row?.id || null, name: row?.name || '', address: row?.address || '',
    contact_name: row?.contact_name || '', contact_phone: row?.contact_phone || '',
    is_default: !!row?.is_default, remark: row?.remark || '', saving: false,
  })
}
const saveSite = async () => {
  if (!siteDlg.name.trim()) return ElMessage.warning('请填写机房名称')
  siteDlg.saving = true
  try {
    const payload = {
      name: siteDlg.name.trim(), address: siteDlg.address || null,
      contact_name: siteDlg.contact_name || null, contact_phone: siteDlg.contact_phone || null,
      is_default: siteDlg.is_default, remark: siteDlg.remark || null,
    }
    if (siteDlg.id) await request.put(`/customers/${id}/sites/${siteDlg.id}`, payload)
    else await request.post(`/customers/${id}/sites`, payload)
    ElMessage.success('已保存')
    siteDlg.visible = false
    const res = await request.get(`/customers/${id}/sites`)
    sites.value = res.items || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally { siteDlg.saving = false }
}
const removeSite = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除机房「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/customers/${id}/sites/${row.id}`)
    ElMessage.success('已删除')
    const res = await request.get(`/customers/${id}/sites`)
    sites.value = res.items || []
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '删除失败') }
}

const openContact = (row = null) => {
  Object.assign(contactDlg, {
    visible: true, id: row?.id || null, name: row?.name || '', phone: row?.phone || '',
    email: row?.email || '', title: row?.title || '', is_primary: !!row?.is_primary,
    remark: row?.remark || '', saving: false,
  })
}
const saveContact = async () => {
  if (!contactDlg.name.trim()) return ElMessage.warning('请填写联系人姓名')
  contactDlg.saving = true
  try {
    const payload = {
      name: contactDlg.name.trim(), phone: contactDlg.phone || null,
      email: contactDlg.email || null, title: contactDlg.title || null,
      is_primary: contactDlg.is_primary, remark: contactDlg.remark || null,
    }
    if (contactDlg.id) await request.put(`/customers/${id}/contacts/${contactDlg.id}`, payload)
    else await request.post(`/customers/${id}/contacts`, payload)
    ElMessage.success('已保存')
    contactDlg.visible = false
    const res = await request.get(`/customers/${id}/contacts`)
    contacts.value = res.items || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally { contactDlg.saving = false }
}
const removeContact = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除联系人「${row.name}」？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/customers/${id}/contacts/${row.id}`)
    ElMessage.success('已删除')
    const res = await request.get(`/customers/${id}/contacts`)
    contacts.value = res.items || []
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.header-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.page-title { margin: 0; font-size: 20px; font-weight: 600; color: #1D2129; }
.cust-code { color: #86909C; font-size: 13px; }
.tag-gap { margin-left: 4px; }
.stat-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-card { background: #fff; border-radius: 10px; padding: 14px 18px; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
.stat-num { font-size: 24px; font-weight: 700; color: #1D2129; }
.stat-num.warning { color: #FF7D00; }
.stat-num.success { color: #00B42A; }
.stat-num.danger { color: #F53F3F; }
.stat-num.score { color: #722ED1; }
.stat-label { font-size: 12px; color: #86909C; margin-top: 4px; }
.card-title { font-weight: 600; color: #1D2129; }
.info-card { margin-bottom: 16px; }
.contacts-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
</style>
