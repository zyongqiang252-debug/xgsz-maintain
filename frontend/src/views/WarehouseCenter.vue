<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">仓库与库位</h2>
      <div class="header-actions">
        <el-button @click="router.push('/stock?tab=parts')">备件台账</el-button>
        <el-button v-if="isSupervisor" type="primary" @click="openWarehouseDialog()">新建仓库</el-button>
      </div>
    </div>

    <div class="wh-layout">
      <el-card shadow="never" class="wh-card">
        <template #header>
          <div class="card-head">
            <span>仓库</span>
            <span class="card-sub">备件台账上的仓库指向这里</span>
          </div>
        </template>
        <el-table
          :data="warehouses" v-loading="loading" stripe highlight-current-row
          :row-class-name="({ row }) => (row.id === currentId ? 'is-current' : '')"
          @row-click="selectWarehouse"
        >
          <el-table-column label="仓库" min-width="170">
            <template #default="{ row }">
              <div class="cell-main">{{ row.name }}</div>
              <div class="cell-sub">{{ row.code }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="manager_name" label="负责人" width="90" />
          <el-table-column label="库位" width="60" align="right">
            <template #default="{ row }">{{ row.location_count ?? 0 }}</template>
          </el-table-column>
          <el-table-column label="备件" width="60" align="right">
            <template #default="{ row }">{{ row.part_count ?? 0 }}</template>
          </el-table-column>
          <el-table-column label="状态" width="70">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column v-if="isSupervisor" label="操作" width="110">
            <template #default="{ row }">
              <div class="row-actions" @click.stop>
                <el-button link type="primary" @click="openWarehouseDialog(row)">编辑</el-button>
                <el-button link type="danger" @click="removeWarehouse(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="loc-card">
        <template #header>
          <div class="card-head">
            <span>库位{{ current ? ' · ' + current.name : '' }}</span>
            <el-button v-if="isSupervisor" size="small" type="primary" :disabled="!current" @click="openLocationDialog()">新建库位</el-button>
          </div>
        </template>
        <el-empty v-if="!current" description="先选择左侧仓库" :image-size="80" />
        <el-table v-else :data="locations" v-loading="locLoading" stripe size="small">
          <el-table-column label="库位" min-width="140">
            <template #default="{ row }">
              <div class="cell-main">{{ row.code }}</div>
              <div class="cell-sub">{{ row.name || '—' }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="rack" label="货架" width="70" />
          <el-table-column label="状态" width="70">
            <template #default="{ row }">
              <el-tag size="small" :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="100" show-overflow-tooltip />
          <el-table-column v-if="isSupervisor" label="操作" width="96">
            <template #default="{ row }">
              <div class="row-actions">
                <el-button link type="primary" @click="openLocationDialog(row)">编辑</el-button>
                <el-button link type="danger" @click="removeLocation(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 仓库弹窗 -->
    <el-dialog v-model="wh.visible" :title="wh.id ? '编辑仓库' : '新建仓库'" width="500px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="编码" required><el-input v-model="wh.code" maxlength="50" placeholder="如 MAIN / SITE-A" /></el-form-item>
        <el-form-item label="名称" required><el-input v-model="wh.name" maxlength="200" /></el-form-item>
        <el-form-item label="负责人"><el-input v-model="wh.manager_name" maxlength="100" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="wh.phone" maxlength="50" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="wh.address" maxlength="300" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="wh.is_active" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="wh.remark" type="textarea" :rows="2" maxlength="200" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="wh.visible = false">取消</el-button>
        <el-button type="primary" :loading="wh.submitting" @click="saveWarehouse">保存</el-button>
      </template>
    </el-dialog>

    <!-- 库位弹窗 -->
    <el-dialog v-model="loc.visible" :title="loc.id ? '编辑库位' : '新建库位'" width="460px" :close-on-click-modal="false">
      <el-form label-width="90px">
        <el-form-item label="编码" required><el-input v-model="loc.code" maxlength="50" placeholder="如 A-01 / 货架A-第1层" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="loc.name" maxlength="100" /></el-form-item>
        <el-form-item label="货架"><el-input v-model="loc.rack" maxlength="50" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="loc.is_active" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="loc.remark" type="textarea" :rows="2" maxlength="200" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="loc.visible = false">取消</el-button>
        <el-button type="primary" :loading="loc.submitting" @click="saveLocation">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'

const router = useRouter()

// 仓库与库位属于库存主数据：只有管理员/主管可维护，技术员只读（能查库位，不能增删改）
const isSupervisor = (() => {
  try {
    const role = JSON.parse(localStorage.getItem('current_user') || '{}').role
    return role === 'ADMIN' || role === 'SUPERVISOR'
  } catch { return false }
})()

const warehouses = ref([])
const loading = ref(false)
const currentId = ref(null)
const current = computed(() => warehouses.value.find((w) => w.id === currentId.value) || null)

const locations = ref([])
const locLoading = ref(false)

const loadWarehouses = async (keep = true) => {
  loading.value = true
  try {
    const res = await request.get('/warehouses/', { params: { include_inactive: true } })
    warehouses.value = res.items || []
    if (!keep || !currentId.value || !warehouses.value.some((w) => w.id === currentId.value)) {
      currentId.value = warehouses.value[0]?.id || null
    }
    await loadLocations()
  } catch { /* ignore */ } finally { loading.value = false }
}

const loadLocations = async () => {
  if (!currentId.value) { locations.value = []; return }
  locLoading.value = true
  try {
    const res = await request.get(`/warehouses/${currentId.value}/locations`)
    locations.value = res.items || []
  } catch { locations.value = [] } finally { locLoading.value = false }
}

const selectWarehouse = (row) => {
  currentId.value = row.id
  loadLocations()
}

// ---------- 仓库增改删 ----------
const wh = reactive({ visible: false, id: null, code: '', name: '', manager_name: '', phone: '', address: '', is_active: true, remark: '', submitting: false })
const openWarehouseDialog = (row) => {
  Object.assign(wh, {
    visible: true, id: row?.id || null,
    code: row?.code || '', name: row?.name || '',
    manager_name: row?.manager_name || '', phone: row?.phone || '',
    address: row?.address || '', is_active: row?.is_active ?? true,
    remark: row?.remark || '', submitting: false,
  })
}
const saveWarehouse = async () => {
  if (!wh.code.trim() || !wh.name.trim()) return ElMessage.warning('编码和名称必填')
  wh.submitting = true
  try {
    const payload = {
      code: wh.code.trim(), name: wh.name.trim(),
      manager_name: wh.manager_name || null, phone: wh.phone || null,
      address: wh.address || null, is_active: wh.is_active, remark: wh.remark || null,
    }
    if (wh.id) await request.put(`/warehouses/${wh.id}`, payload)
    else await request.post('/warehouses/', payload)
    ElMessage.success('已保存')
    wh.visible = false
    await loadWarehouses()
  } catch { /* ignore */ } finally { wh.submitting = false }
}
const removeWarehouse = async (row) => {
  try {
    await ElMessageBox.confirm(`删除仓库「${row.name}」？仓内还有备件或实例时不能删。`, '删除仓库', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/warehouses/${row.id}`)
    ElMessage.success('已删除')
    if (currentId.value === row.id) currentId.value = null
    await loadWarehouses(false)
  } catch { /* ignore */ }
}

// ---------- 库位增改删 ----------
const loc = reactive({ visible: false, id: null, code: '', name: '', rack: '', is_active: true, remark: '', submitting: false })
const openLocationDialog = (row) => {
  Object.assign(loc, {
    visible: true, id: row?.id || null,
    code: row?.code || '', name: row?.name || '', rack: row?.rack || '',
    is_active: row?.is_active ?? true, remark: row?.remark || '', submitting: false,
  })
}
const saveLocation = async () => {
  if (!loc.code.trim()) return ElMessage.warning('库位编码必填')
  if (!currentId.value) return ElMessage.warning('先选择仓库')
  loc.submitting = true
  try {
    const payload = {
      code: loc.code.trim(), name: loc.name || null, rack: loc.rack || null,
      is_active: loc.is_active, remark: loc.remark || null,
    }
    if (loc.id) await request.put(`/warehouses/locations/${loc.id}`, payload)
    else await request.post(`/warehouses/${currentId.value}/locations`, payload)
    ElMessage.success('已保存')
    loc.visible = false
    await Promise.all([loadLocations(), loadWarehouses()])
  } catch { /* ignore */ } finally { loc.submitting = false }
}
const removeLocation = async (row) => {
  try {
    await ElMessageBox.confirm(`删除库位「${row.code}」？还挂着实物时不能删。`, '删除库位', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/warehouses/locations/${row.id}`)
    ElMessage.success('已删除')
    await Promise.all([loadLocations(), loadWarehouses()])
  } catch { /* ignore */ }
}

onMounted(() => loadWarehouses(false))
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary, #1D2129); }
.header-actions { display: flex; gap: 8px; }
.wh-layout { display: grid; grid-template-columns: minmax(520px, 1.1fr) minmax(360px, 1fr); gap: 14px; align-items: start; }
.wh-card :deep(.el-table__row) { cursor: pointer; }
.wh-card :deep(.is-current) { background: rgba(15, 198, 194, .08) !important; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-sub { font-size: 12px; color: #86909C; }
.cell-main { font-size: 13px; color: #1D2129; line-height: 1.4; }
.cell-sub { font-size: 12px; color: #86909C; line-height: 1.4; }
.row-actions { display: flex; align-items: center; gap: 4px; }
</style>
