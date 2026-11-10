<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">客户管理</h2>
      <el-button type="primary" @click="openCreate">新建客户</el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="customers" v-loading="loading" stripe>
        <el-table-column label="客户" min-width="140">
          <template #default="{ row }">
            <div class="cust-name">{{ row.name }}</div>
            <div class="cust-company">{{ row.company || '-' }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="手机号" width="140" />
        <el-table-column label="绑定设备" min-width="240">
          <template #default="{ row }">
            <span v-if="row.devices && row.devices.length" class="dev-list">
              {{ row.devices.map(d => d.device_code).join('、') }}
            </span>
            <span v-else class="muted">未绑定</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'" effect="plain">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" header-align="left">
          <template #default="{ row }">
            <div class="cust-op">
              <IconAction :icon="Edit" title="编辑" @click="openEdit(row)" />
              <IconAction :icon="Link" title="绑定设备" @click="openBind(row)" />
              <IconAction :icon="Delete" title="删除" type="danger" @click="removeCustomer(row)" />
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="form.visible" :title="form.id ? '编辑客户' : '新建客户'" width="480px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="联系人" required><el-input v-model="form.name" maxlength="50" /></el-form-item>
        <el-form-item label="手机号" required><el-input v-model="form.phone" maxlength="20" /></el-form-item>
        <el-form-item :label="form.id ? '重置密码' : '登录密码'">
          <el-input v-model="form.password" type="password" show-password maxlength="72"
                    :placeholder="form.id ? '留空则不修改' : '不填默认 123456'" />
        </el-form-item>
        <el-form-item label="公司"><el-input v-model="form.company" maxlength="100" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="状态"><el-switch v-model="form.is_active" active-text="启用" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="form.visible = false">取消</el-button>
        <el-button type="primary" :loading="form.saving" @click="saveCustomer">保存</el-button>
      </template>
    </el-dialog>

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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Delete, Link } from '@element-plus/icons-vue'
import request from '../api'
import IconAction from '../components/IconAction.vue'

const customers = ref([])
const devices = ref([])
const loading = ref(false)

const form = reactive({
  visible: false, id: null, name: '', phone: '', password: '',
  company: '', remark: '', is_active: true, saving: false,
})
const bind = reactive({
  visible: false, customerId: null, customerName: '', deviceIds: [], loading: false, saving: false,
})

const load = async () => {
  loading.value = true
  try {
    const res = await request.get('/customers/')
    customers.value = res.items || []
  } catch { /* ignore */ }
  finally { loading.value = false }
}

const loadDevices = async () => {
  try {
    const res = await request.get('/devices/', { params: { page: 1, page_size: 200 } })
    devices.value = res.items || []
  } catch { devices.value = [] }
}

const openCreate = () => {
  Object.assign(form, {
    visible: true, id: null, name: '', phone: '', password: '',
    company: '', remark: '', is_active: true,
  })
}
const openEdit = (row) => {
  Object.assign(form, {
    visible: true, id: row.id, name: row.name, phone: row.phone, password: '',
    company: row.company || '', remark: row.remark || '', is_active: !!row.is_active,
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
      remark: form.remark || null, is_active: form.is_active,
    }
    if (form.password) payload.password = form.password
    if (form.id) await request.put(`/customers/${form.id}`, payload)
    else await request.post('/customers/', payload)
    ElMessage.success('保存成功')
    form.visible = false
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally { form.saving = false }
}

const openBind = async (row) => {
  bind.customerId = row.id
  bind.customerName = row.name
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

const removeCustomer = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除客户「${row.name}」？设备绑定会一并解除。`, '删除确认',
      { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/customers/${row.id}`)
    ElMessage.success('已删除')
    load()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '删除失败') }
}

onMounted(load)
</script>

<style scoped>
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.page-title { margin: 0; font-size: 20px; font-weight: 600; color: #1D2129; }
.cust-name { font-weight: 600; color: #1D2129; }
.cust-company { font-size: 12px; color: #86909C; margin-top: 2px; }
.dev-list { font-size: 13px; color: #4E5969; }
.muted { color: #C9CDD4; }
.cust-op { display: flex; align-items: center; gap: 4px; }
.bind-hint { margin: 10px 0 0; font-size: 12px; color: #86909C; }
</style>
