<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">客户管理</h2>
      <el-button type="primary" @click="openCreate">新建客户</el-button>
    </div>

    <el-card class="filter-card" shadow="never">
      <div class="filter-bar">
        <el-input v-model="keyword" placeholder="搜索编码/公司/联系人/手机" clearable
                  class="filter-input" @clear="load" @keyup.enter="load" />
        <el-select v-model="levelFilter" placeholder="客户级别" clearable class="filter-select" @change="load">
          <el-option label="普通" value="NORMAL" />
          <el-option label="重点" value="KEY" />
          <el-option label="VIP" value="VIP" />
        </el-select>
        <el-select v-model="activeFilter" placeholder="状态" clearable class="filter-select" @change="load">
          <el-option label="启用" :value="true" />
          <el-option label="停用" :value="false" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="reset">重置</el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table :data="customers" v-loading="loading" stripe class="cust-table" @row-click="openDetail">
        <el-table-column prop="code" label="客户编码" width="100" />
        <el-table-column label="客户 / 公司" min-width="170">
          <template #default="{ row }">
            <div class="cust-name">{{ row.company || row.name }}</div>
            <div class="cust-company">{{ row.name }} · {{ row.phone }}</div>
          </template>
        </el-table-column>
        <el-table-column label="级别 / 标签" min-width="140">
          <template #default="{ row }">
            <el-tag size="small" :type="levelType(row.level)" effect="plain">{{ row.level_label }}</el-tag>
            <el-tag v-for="t in (row.tags || []).slice(0, 2)" :key="t" size="small" effect="plain" class="tag-gap">{{ t }}</el-tag>
            <span v-if="(row.tags || []).length > 2" class="muted">+{{ row.tags.length - 2 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="设备" width="70" align="center">
          <template #default="{ row }">{{ row.device_count }}</template>
        </el-table-column>
        <el-table-column label="工单" width="132">
          <template #default="{ row }">
            <el-tooltip placement="top" :show-after="300"
                        :content="`共 ${row.order_count} 单 · 未完成 ${row.open_count} 单 · 已归档 ${row.archived_count} 单`">
              <div class="order-cell" :class="{ 'is-zero': !row.order_count }">
                <span class="order-total">{{ row.order_count }}</span>
                <span class="order-unit">单</span>
                <span v-if="row.open_count" class="order-divider"></span>
                <span v-if="row.open_count" class="order-open">未完成 {{ row.open_count }}</span>
                <span v-else-if="row.order_count" class="order-done">全部完成</span>
              </div>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="最近报修" width="140">
          <template #default="{ row }">{{ fmt(row.last_order_at) }}</template>
        </el-table-column>
        <el-table-column label="满意度" width="80" align="center">
          <template #default="{ row }">
            <span v-if="row.avg_satisfaction" class="score">{{ row.avg_satisfaction }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="70">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'" effect="plain">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" header-align="left">
          <template #default="{ row }">
            <div class="cust-op">
              <IconAction :icon="Edit" title="编辑" @click="openEdit(row)" />
              <IconAction :icon="Link" title="绑定设备" @click="openBind(row)" />
              <IconAction v-if="row.is_active" :icon="SwitchButton" title="停用" type="danger" @click="deactivate(row)" />
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建/编辑 -->
    <el-dialog v-model="form.visible" :title="form.id ? '编辑客户' : '新建客户'" width="720px" :close-on-click-modal="false">
      <el-form label-width="96px">
        <el-divider content-position="left">基本信息</el-divider>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="公司名称"><el-input v-model="form.company" maxlength="100" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="联系人" required><el-input v-model="form.name" maxlength="50" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="手机号" required><el-input v-model="form.phone" maxlength="20" /></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item :label="form.id ? '重置密码' : '登录密码'">
              <el-input v-model="form.password" type="password" show-password maxlength="72"
                        :placeholder="form.id ? '留空不修改' : '不填默认 123456'" />
            </el-form-item>
          </el-col>
        </el-row>
        <p class="pwd-hint">
          客户用「手机号 + 登录密码」在<b>客户报修中心</b>登录（<span class="mono">{{ portalUrl }}</span>），
          不是在主站登录页。忘记密码可在此重置。
        </p>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="客户级别">
              <el-select v-model="form.level" style="width:100%">
                <el-option label="普通" value="NORMAL" /><el-option label="重点" value="KEY" /><el-option label="VIP" value="VIP" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="归属人">
              <el-select v-model="form.owner_id" clearable filterable style="width:100%">
                <el-option v-for="u in users" :key="u.id" :label="`${u.real_name}（${u.username}）`" :value="u.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="客户标签">
          <el-select v-model="form.tags" multiple filterable allow-create default-first-option
                     placeholder="输入后回车，例如：GPU集群 / 年框客户" style="width:100%" />
        </el-form-item>
        <el-form-item label="上级客户">
          <el-select v-model="form.parent_id" clearable filterable placeholder="选填，集团/母公司" style="width:100%">
            <el-option v-for="c in parentOptions" :key="c.id" :label="`${c.code} ${c.company || c.name}`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="地址 / 机房"><el-input v-model="form.address" maxlength="300" /></el-form-item>

        <el-divider content-position="left">合同与 SLA</el-divider>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="合同号"><el-input v-model="form.contract_no" maxlength="100" /></el-form-item></el-col>
          <el-col :span="12">
            <el-form-item label="服务期限">
              <el-date-picker v-model="form.serviceRange" type="daterange" value-format="YYYY-MM-DD"
                              start-placeholder="开始" end-placeholder="到期" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12"><el-form-item label="响应时限(h)"><el-input-number v-model="form.sla_response_hours" :min="0" :max="720" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="修复时限(h)"><el-input-number v-model="form.sla_resolve_hours" :min="0" :max="720" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" maxlength="500" /></el-form-item>
        <el-form-item label="状态"><el-switch v-model="form.is_active" active-text="启用" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="form.visible = false">取消</el-button>
        <el-button type="primary" :loading="form.saving" @click="saveCustomer">保存</el-button>
      </template>
    </el-dialog>

    <!-- 绑定设备 -->
    <el-dialog v-model="bind.visible" :title="`绑定设备 · ${bind.customerName}`" width="560px" :close-on-click-modal="false">
      <el-select v-model="bind.deviceIds" multiple filterable placeholder="选择该客户名下的服务器"
                 style="width:100%" :loading="bind.loading">
        <el-option v-for="d in devices" :key="d.id"
                   :label="`${d.device_name || d.device_code}（${d.device_code}）`" :value="d.id" />
      </el-select>
      <p class="bind-hint">一台设备只能绑定一个客户；保存后按本次选择覆盖。</p>
      <template #footer>
        <el-button @click="bind.visible = false">取消</el-button>
        <el-button type="primary" :loading="bind.saving" @click="saveBind">保存绑定</el-button>
      </template>
    </el-dialog>

    <!-- 新建成功后：把「客户从哪登录、账号密码是什么」直接给管理员 -->
    <el-dialog v-model="created.visible" title="客户已开通" width="520px">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="客户">{{ created.company || created.name }}</el-descriptions-item>
        <el-descriptions-item label="登录入口"><span class="mono">{{ portalUrl }}</span></el-descriptions-item>
        <el-descriptions-item label="登录账号"><span class="mono">{{ created.phone }}</span></el-descriptions-item>
        <el-descriptions-item label="登录密码">
          <span class="mono">{{ created.password }}</span>
          <span class="muted" style="margin-left:8px">（请让客户首次登录后尽快修改）</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert type="info" :closable="false" show-icon style="margin-top:12px"
                title="客户账号与内部员工账号是两套体系：客户请勿在主站 /login 登录，那边会提示去客户报修中心。" />
      <template #footer>
        <el-button @click="created.visible = false">关闭</el-button>
        <el-button type="primary" @click="copyCustomerLogin">复制登录信息</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Delete, Link, SwitchButton } from '@element-plus/icons-vue'
import request from '../api'
import IconAction from '../components/IconAction.vue'

const router = useRouter()
const customers = ref([])
const devices = ref([])
const users = ref([])
const loading = ref(false)
const keyword = ref('')
const levelFilter = ref('')
const activeFilter = ref(null)

const form = reactive({
  visible: false, id: null, name: '', phone: '', password: '', company: '',
  address: '', level: 'NORMAL', tags: [], owner_id: null, parent_id: null,
  contract_no: '', serviceRange: [], sla_response_hours: null, sla_resolve_hours: null,
  remark: '', is_active: true, saving: false,
})
const bind = reactive({
  visible: false, customerId: null, customerName: '', deviceIds: [], loading: false, saving: false,
})
// 客户门户地址：客户账号只在 /c/login 登录
const portalUrl = `${window.location.origin}/c/login`
const created = reactive({ visible: false, name: '', company: '', phone: '', password: '' })

const copyCustomerLogin = async () => {
  const text = [
    `客户报修中心：${portalUrl}`,
    `登录账号：${created.phone}`,
    `登录密码：${created.password}`,
  ].join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制，可直接发给客户')
  } catch {
    ElMessage.warning(`请手动复制：${text.replace(/\n/g, '；')}`)
  }
}

const levelType = (lv) => ({ VIP: 'danger', KEY: 'warning', NORMAL: 'info' }[lv] || 'info')
const fmt = (t) => t ? t.replace('T', ' ').slice(0, 16) : '—'

const parentOptions = ref([])

const load = async () => {
  loading.value = true
  try {
    const res = await request.get('/customers/', {
      params: {
        keyword: keyword.value || undefined,
        level: levelFilter.value || undefined,
        active: activeFilter.value === null ? undefined : activeFilter.value,
      },
    })
    customers.value = res.items || []
    parentOptions.value = customers.value.filter((c) => c.is_active)
  } catch { /* ignore */ }
  finally { loading.value = false }
}

const loadUsers = async () => {
  try {
    const res = await request.get('/users/', { params: { page: 1, page_size: 200 } })
    users.value = res.items || []
  } catch { users.value = [] }
}

const loadDevices = async () => {
  try {
    const res = await request.get('/devices/', { params: { page: 1, page_size: 300 } })
    devices.value = res.items || []
  } catch { devices.value = [] }
}

const reset = () => {
  keyword.value = ''
  levelFilter.value = ''
  activeFilter.value = null
  load()
}

const openCreate = () => {
  Object.assign(form, {
    visible: true, id: null, name: '', phone: '', password: '', company: '',
    address: '', level: 'NORMAL', tags: [], owner_id: null, parent_id: null,
    contract_no: '', serviceRange: [], sla_response_hours: null, sla_resolve_hours: null,
    remark: '', is_active: true, saving: false,
  })
}
const openEdit = (row) => {
  Object.assign(form, {
    visible: true, id: row.id, name: row.name, phone: row.phone, password: '',
    company: row.company || '', address: row.address || '', level: row.level || 'NORMAL',
    tags: [...(row.tags || [])], owner_id: row.owner_id, parent_id: row.parent_id,
    contract_no: row.contract_no || '',
    serviceRange: row.service_start && row.service_end ? [row.service_start, row.service_end] : [],
    sla_response_hours: row.sla_response_hours, sla_resolve_hours: row.sla_resolve_hours,
    remark: row.remark || '', is_active: !!row.is_active, saving: false,
  })
}

const saveCustomer = async () => {
  if (!form.name.trim() || !form.phone.trim()) {
    ElMessage.warning('请填写联系人和手机号')
    return
  }
  form.saving = true
  try {
    const payload = {
      name: form.name.trim(), phone: form.phone.trim(), company: form.company || null,
      address: form.address || null, level: form.level, tags: form.tags || [],
      owner_id: form.owner_id || null, parent_id: form.parent_id || null,
      contract_no: form.contract_no || null,
      service_start: form.serviceRange?.[0] || null,
      service_end: form.serviceRange?.[1] || null,
      sla_response_hours: form.sla_response_hours,
      sla_resolve_hours: form.sla_resolve_hours,
      remark: form.remark || null, is_active: form.is_active,
    }
    if (form.password) payload.password = form.password
    const isCreate = !form.id
    if (form.id) await request.put(`/customers/${form.id}`, payload)
    else await request.post('/customers/', payload)
    ElMessage.success('保存成功')
    form.visible = false
    load()
    // 新建客户后立刻把登录入口/账号/密码摆给管理员，避免「创建完不知道客户怎么登」
    if (isCreate) {
      Object.assign(created, {
        visible: true, name: form.name, company: form.company || '',
        phone: form.phone, password: form.password || '123456',
      })
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally { form.saving = false }
}

const openDetail = (row, column, event) => {
  if (event?.target?.closest('.cust-op')) return
  router.push(`/customers/${row.id}`)
}

const openBind = async (row) => {
  bind.customerId = row.id
  bind.customerName = row.company || row.name
  bind.deviceIds = (row.devices || []).map((d) => d.id)
  bind.visible = true
  bind.loading = true
  await loadDevices()
  bind.loading = false
}
const saveBind = async () => {
  bind.saving = true
  try {
    await request.put(`/customers/${bind.customerId}/devices`, { device_ids: bind.deviceIds })
    ElMessage.success('绑定已保存')
    bind.visible = false
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '绑定失败')
  } finally { bind.saving = false }
}

const deactivate = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定停用客户「${row.company || row.name}」？停用后客户无法登录门户，历史工单与设备绑定保留。`,
      '停用确认', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/customers/${row.id}`)
    ElMessage.success('已停用')
    load()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '操作失败') }
}

onMounted(() => { load(); loadUsers() })
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-title { margin: 0; font-size: 20px; font-weight: 600; color: #1D2129; }
.filter-bar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.filter-input { width: 240px; }
.filter-select { width: 130px; }
.filter-card { margin-bottom: 14px; }
.cust-table :deep(tbody tr) { cursor: pointer; }
.cust-name { font-weight: 600; color: var(--color-text-primary); }
.cust-company { font-size: 12px; color: var(--color-text-tertiary); margin-top: 2px; }
.tag-gap { margin-left: 4px; }
.muted { color: #C9CDD4; }
/* 工单列：单行排版，数字 + 单位 + 状态同基线，列宽固定不抖 */
.order-cell {
  display: flex;
  align-items: baseline;
  gap: 4px;
  width: 100%;
  line-height: 1.2;
  white-space: nowrap;
}
.order-total {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}
.order-unit { font-size: 11px; color: #86909C; }
.order-divider {
  align-self: center;
  width: 1px;
  height: 10px;
  background: #E5E6EB;
  margin: 0 2px;
}
.order-open { font-size: 12px; color: var(--color-warning-text, #FF7D00); }
.order-done { font-size: 12px; color: #00B42A; }
.order-cell.is-zero .order-total,
.order-cell.is-zero .order-unit { color: #C9CDD4; }
.score { color: #FF7D00; font-weight: 600; }
.cust-op { display: flex; align-items: center; gap: 4px; }
.bind-hint { margin: 10px 0 0; font-size: 12px; color: #86909C; }
.pwd-hint { margin: -4px 0 14px; font-size: 12px; line-height: 1.6; color: #86909C; }
.pwd-hint b { color: #0FC6C2; font-weight: 600; }
.mono { font-family: ui-monospace, Consolas, monospace; }
</style>
