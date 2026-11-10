<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">用户管理</h2>
      <el-button type="primary" @click="dialogVisible = true">添加用户</el-button>
    </div>

    <el-card class="table-card" shadow="never">
      <el-table :data="list" v-loading="loading" stripe>
        <el-table-column label="用户" min-width="160">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 8px;">
              <el-avatar :size="32" icon="UserFilled" />
              <span>{{ row.real_name }}</span>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="employee_id" label="工号" width="100">
          <template #default="{ row }">{{ row.employee_id || '—' }}</template>
        </el-table-column>
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <span class="role-tag" :class="'role-' + row.role">{{ roleLabel(row.role) }}</span>
          </template>
        </el-table-column>
        
        <el-table-column prop="phone" label="手机" width="120" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <span class="status-dot" :class="row.is_active ? 'active' : 'inactive'">
              {{ row.is_active ? '启用' : '禁用' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="钉钉" width="90">
          <template #default="{ row }">
            <span v-if="row.dingtalk_userid" class="dt-bound-tag">已绑定</span>
            <span v-else class="dt-unbound-tag">未绑定</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="140">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" header-align="left">
          <template #default="{ row }">
            <div class="user-op">
              <IconAction :icon="Edit" title="编辑" @click="handleEdit(row)" />
              <IconAction :icon="Key" title="重置密码" type="warning" @click="handleResetPwd(row)" />
              <IconAction :icon="Delete" title="删除" type="danger" @click="handleDelete(row)" />
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="fetchData"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog :title="editingId ? '编辑用户' : '添加用户'" v-model="dialogVisible" width="500px" destroy-on-close>
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item v-if="!editingId" label="密码" required>
          <el-input v-model="form.password" type="password" placeholder="初始密码" show-password autocomplete="new-password" name="new-user-initial-password" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="form.real_name" placeholder="真实姓名" />
        </el-form-item>
        <el-form-item label="工号">
          <el-input v-model="form.employee_id" placeholder="选填，用于报表和考勤对应" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="邮箱地址" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="form.phone" placeholder="手机号" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="维修员（技术员）" value="TECHNICIAN" />
            <el-option label="主管" value="SUPERVISOR" />
            <el-option label="管理员" value="ADMIN" />
          </el-select>
          <div class="role-tip">维修员会被列入派工候选名单，可在移动端接单和填报</div>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit, Key, Delete } from '@element-plus/icons-vue'
import IconAction from '../components/IconAction.vue'
import request from '../api'
import dayjs from 'dayjs'

const list = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const dialogVisible = ref(false)
const editingId = ref(null)
const saving = ref(false)

const form = ref({
  username: '', password: '', real_name: '', employee_id: '', email: '', phone: '',
  role: 'TECHNICIAN', is_active: true
})

const roleMap = { ADMIN: '管理员', TECHNICIAN: '维修员', SUPERVISOR: '主管' }
const roleLabel = (r) => roleMap[r] || r
const formatTime = (t) => t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'

const fetchData = async () => {
  loading.value = true
  try {
    const res = await request.get('/users/', { params: { page: page.value, page_size: pageSize.value } })
    list.value = res.items
    total.value = res.total
  } catch { /* handled */ }
  finally { loading.value = false }
}

const resetForm = () => {
  editingId.value = null
  form.value = { username: '', password: '', real_name: '', employee_id: '', email: '', phone: '', role: 'TECHNICIAN', is_active: true }
}

const handleEdit = (row) => {
  editingId.value = row.id
  form.value = { ...row, password: '' }
  dialogVisible.value = true
}

const handleResetPwd = async (row) => {
  try {
    const { value } = await ElMessageBox.prompt('请输入新密码', '重置密码', { inputType: 'password' })
    if (value) {
      await request.put(`/users/${row.id}`, { password: value })
      ElMessage.success('密码重置成功')
    }
  } catch { /* cancelled */ }
}

const handleSave = async () => {
  saving.value = true
  try {
    const data = { ...form.value }
    if (editingId.value && !data.password) delete data.password
    if (editingId.value) {
      await request.put(`/users/${editingId.value}`, data)
      ElMessage.success('更新成功')
    } else {
      await request.post('/users/', data)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } finally { saving.value = false }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定删除该用户？', '删除确认', { type: 'warning' })
    await request.delete(`/users/${row.id}`)
    ElMessage.success('删除成功')
    fetchData()
  } catch { /* cancelled */ }
}

onMounted(fetchData)
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary); }
.table-card { flex: 1; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }
.user-op { display: flex; align-items: center; justify-content: flex-start; gap: 4px; white-space: nowrap; }

.role-tag {
  display: inline-block; padding: 2px 10px; border-radius: 4px; font-size: 12px; font-weight: 500; line-height: 20px;
}
.role-ADMIN { background: #FFECEC; color: #F53F3F; }
.role-SUPERVISOR { background: #FFF3E8; color: #FF7D00; }
.role-TECHNICIAN { background: #E8F9F9; color: #0FC6C2; }
.role-tip { font-size: 12px; color: #86909C; line-height: 1.6; margin-top: 2px; }

.status-dot { display: inline-flex; align-items: center; gap: 4px; font-size: 13px; }
.status-dot::before { content: ''; width: 6px; height: 6px; border-radius: 50%; }
.status-dot.active { color: #00B42A; }
.status-dot.active::before { background: #00B42A; }
.status-dot.inactive { color: #C9CDD4; }
.status-dot.inactive::before { background: #C9CDD4; }
.dt-bound-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  color: #0089FF;
  background: #E8F3FF;
}
.dt-unbound-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  color: #86909C;
  background: #F2F3F5;
}

/* 钉钉扫码绑定弹窗 */
.dt-scan-area {
  padding: 8px 0;
}
.dt-qr-box {
  width: 220px;
  height: 220px;
  margin: 0 auto 16px;
  padding: 14px;
  background: #fff;
  border: 2px solid #E5E6EB;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: border-color .2s;
}
.dt-qr-box.expired {
  border-color: #C9CDD4;
}
.dt-qr-box svg, .dt-qr-box canvas {
  max-width: 100%;
  max-height: 100%;
}
.dt-qr-loading, .dt-qr-expired {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: #86909C;
  font-size: 13px;
  text-align: center;
}
.dt-qr-expired { cursor: pointer; }
.dt-qr-scanned {
  position: absolute;
  inset: 0;
  background: rgba(255,255,255,0.95);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.dt-qr-scanned-text {
  text-align: center;
}
.dt-qr-scanned-text > div:first-child {
  font-size: 16px;
  font-weight: 600;
  color: #1D2129;
}
.dt-qr-countdown {
  font-size: 12px;
  color: #0FC6C2;
  text-align: center;
  margin-bottom: 8px;
}
.dt-scan-tip {
  font-size: 13px;
  color: #4E5969;
  text-align: center;
  margin-bottom: 16px;
}
.dt-scan-actions {
  margin-bottom: 8px;
  text-align: center;
}
</style>