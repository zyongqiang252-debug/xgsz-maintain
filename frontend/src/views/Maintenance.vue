<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">保养与点检</h2>
      <div style="display:flex;gap:8px">
        <el-button v-if="tab === 'plan' && canManage" type="primary" @click="openPlan()">新建保养计划</el-button>
        <el-button v-if="tab === 'check'" type="primary" @click="openCheck()">发起点检</el-button>
      </div>
    </div>

    <!-- 概览 -->
    <div class="stat-row">
      <div class="stat-card" :class="{ danger: stats.overdue > 0 }">
        <div class="stat-num">{{ stats.overdue }}</div>
        <div class="stat-label">超期未保养</div>
      </div>
      <div class="stat-card" :class="{ warn: stats.due_soon > 0 }">
        <div class="stat-num">{{ stats.due_soon }}</div>
        <div class="stat-label">3 天内到期</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.total }}</div>
        <div class="stat-label">进行中计划</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.done_last_30d }}</div>
        <div class="stat-label">近 30 天已完成</div>
      </div>
    </div>

    <el-tabs v-model="tab" @tab-change="onTabChange">
      <!-- ===== 保养计划 ===== -->
      <el-tab-pane label="保养计划" name="plan">
        <el-card shadow="never">
          <div class="toolbar">
            <el-checkbox v-model="onlyDue" @change="loadPlans">只看超期/临期</el-checkbox>
            <el-button text @click="loadPlans">刷新</el-button>
          </div>
          <el-table :data="plans" v-loading="loadingPlans" stripe size="small">
            <el-table-column prop="plan_name" label="保养项目" min-width="180" show-overflow-tooltip />
            <el-table-column prop="device_code" label="设备" width="120" />
            <el-table-column label="周期" width="90">
              <template #default="{ row }">每 {{ row.cycle_value }} 天</template>
            </el-table-column>
            <el-table-column label="下次到期" width="150">
              <template #default="{ row }">{{ fmt(row.next_due_at) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="dueType(row)">{{ dueText(row) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="responsible_name" label="负责人" width="100" />
            <el-table-column prop="items" label="保养内容" min-width="200" show-overflow-tooltip />
            <el-table-column label="操作" width="230" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="openDone(row)">执行保养</el-button>
                <el-button v-if="canManage" size="small" @click="openPlan(row)">编辑</el-button>
                <el-button v-if="canManage" size="small" type="danger" @click="removePlan(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!plans.length" class="empty-hint">还没有保养计划，点右上角「新建保养计划」</div>
        </el-card>
      </el-tab-pane>

      <!-- ===== 点检 ===== -->
      <el-tab-pane label="点检记录" name="check">
        <el-card shadow="never">
          <el-table :data="checkRecords" v-loading="loadingChecks" stripe size="small">
            <el-table-column label="时间" width="150">
              <template #default="{ row }">{{ fmt(row.created_at) }}</template>
            </el-table-column>
            <el-table-column prop="device_code" label="设备" width="120" />
            <el-table-column prop="template_name" label="点检表" min-width="160" />
            <el-table-column prop="inspector_name" label="点检人" width="100" />
            <el-table-column label="结果" width="110">
              <template #default="{ row }">
                <el-tag size="small" :type="row.result === 'OK' ? 'success' : 'danger'">
                  {{ row.result === 'OK' ? '正常' : `异常 ${row.abnormal_count} 项` }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
            <el-table-column label="处理工单" width="100">
              <template #default="{ row }">
                <el-link v-if="row.work_order_id" type="primary" @click="$router.push(`/work-orders/${row.work_order_id}`)">
                  #{{ row.work_order_id }}
                </el-link>
                <span v-else>—</span>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!checkRecords.length" class="empty-hint">还没有点检记录</div>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 新建/编辑计划 -->
    <el-dialog v-model="planDlg.visible" :title="planDlg.id ? '编辑保养计划' : '新建保养计划'" width="560px">
      <el-form label-width="90px">
        <el-form-item label="保养项目" required>
          <el-input v-model="planDlg.plan_name" placeholder="例如：主轴润滑与皮带检查" maxlength="100" />
        </el-form-item>
        <el-form-item label="设备">
          <el-select v-model="planDlg.device_code" filterable clearable placeholder="选择设备" style="width:100%">
            <el-option v-for="d in devices" :key="d.device_code" :label="`${d.device_code} · ${d.device_name}`" :value="d.device_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="保养内容">
          <el-input v-model="planDlg.items" type="textarea" :rows="3" placeholder="每行一项，例如：&#10;1. 检查润滑脂&#10;2. 检查皮带张紧" />
        </el-form-item>
        <el-form-item label="周期">
          <el-input-number v-model="planDlg.cycle_value" :min="1" :max="3650" />
          <span style="margin-left:8px">天</span>
        </el-form-item>
        <el-form-item label="下次到期">
          <el-date-picker v-model="planDlg.next_due_at" type="datetime" placeholder="不填则按周期自动算" style="width:100%" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="planDlg.responsible_id" clearable placeholder="默认自己" style="width:100%">
            <el-option v-for="u in users" :key="u.id" :label="u.real_name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="planDlg.remark" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="planDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="planDlg.saving" @click="savePlan">保存</el-button>
      </template>
    </el-dialog>

    <!-- 执行保养 -->
    <el-dialog v-model="doneDlg.visible" title="执行保养" width="480px">
      <el-form label-width="90px">
        <el-form-item label="保养项目">
          <span>{{ doneDlg.row?.plan_name }}</span>
        </el-form-item>
        <el-form-item label="结果">
          <el-radio-group v-model="doneDlg.result">
            <el-radio label="OK">正常完成</el-radio>
            <el-radio label="ABNORMAL">发现异常</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="费用">
          <el-input-number v-model="doneDlg.cost" :min="0" :precision="2" />
          <span style="margin-left:8px">元</span>
        </el-form-item>
        <el-form-item v-if="doneDlg.result === 'ABNORMAL'" label="自动建单">
          <el-switch v-model="doneDlg.create_work_order" />
          <span class="hint">勾选后自动生成一张处理工单</span>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="doneDlg.remark" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="doneDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="doneDlg.saving" @click="submitDone">确认提交</el-button>
      </template>
    </el-dialog>

    <!-- 发起点检 -->
    <el-dialog v-model="checkDlg.visible" title="发起点检" width="620px">
      <el-form label-width="90px">
        <el-form-item label="点检表">
          <el-select v-model="checkDlg.template_id" placeholder="选择点检表" style="width:100%" @change="onTemplateChange">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="设备">
          <el-select v-model="checkDlg.device_code" filterable placeholder="选择设备" style="width:100%">
            <el-option v-for="d in devices" :key="d.device_code" :label="`${d.device_code} · ${d.device_name}`" :value="d.device_code" />
          </el-select>
        </el-form-item>
        <el-form-item label="点检项">
          <div class="check-items">
            <div v-for="(it, i) in checkDlg.results" :key="i" class="check-item">
              <el-checkbox v-model="it.ok">正常</el-checkbox>
              <span class="check-name">{{ it.name }}</span>
              <span class="check-std">{{ it.standard }}</span>
              <el-input v-if="!it.ok" v-model="it.remark" size="small" placeholder="异常说明" style="width:160px" />
            </div>
            <div v-if="!checkDlg.results.length" class="empty-hint">请先选择点检表</div>
          </div>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="checkDlg.remark" type="textarea" :rows="2" maxlength="200" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="checkDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="checkDlg.saving" @click="submitCheck">提交点检</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import request from '../api'

const tab = ref('plan')
const loadingPlans = ref(false)
const loadingChecks = ref(false)
const plans = ref([])
const checkRecords = ref([])
const templates = ref([])
const devices = ref([])
const users = ref([])
const onlyDue = ref(false)

const currentUser = computed(() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})
const canManage = computed(() => ['ADMIN', 'SUPERVISOR'].includes(currentUser.value?.role))

const stats = reactive({ total: 0, overdue: 0, due_soon: 0, done_last_30d: 0 })

const fmt = (t) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-')
const dueType = (row) => (row.overdue ? 'danger' : row.due_state === 'DUE_SOON' ? 'warning' : 'success')
const dueText = (row) => {
  if (row.overdue) {
    return row.days_left != null ? `已超 ${Math.abs(row.days_left)} 天` : '已超期'
  }
  if (row.days_left === 0) return '今天到期'
  return row.days_left != null ? `剩 ${row.days_left} 天` : '—'
}

const loadStats = async () => {
  try { Object.assign(stats, await request.get('/maintenance/stats')) } catch { /* 忽略 */ }
}
const loadPlans = async () => {
  loadingPlans.value = true
  try {
    const res = await request.get('/maintenance/plans', { params: { only_due: onlyDue.value, page_size: 100 } })
    plans.value = res.items || []
  } catch (e) { ElMessage.error('加载保养计划失败') } finally { loadingPlans.value = false }
}
const loadChecks = async () => {
  loadingChecks.value = true
  try {
    const res = await request.get('/inspections/records', { params: { page_size: 100 } })
    checkRecords.value = res.items || []
  } catch (e) { ElMessage.error('加载点检记录失败') } finally { loadingChecks.value = false }
}
const loadBase = async () => {
  try {
    const [d, t, u] = await Promise.all([
      request.get('/devices/', { params: { page_size: 200 } }),
      request.get('/inspections/templates'),
      request.get('/users/', { params: { page_size: 200 } }),
    ])
    devices.value = d.items || []
    templates.value = t.items || []
    users.value = u.items || []
  } catch { /* 忽略 */ }
}

const onTabChange = () => {
  if (tab.value === 'plan') loadPlans()
  else loadChecks()
}

// ---- 计划 ----
const planDlg = reactive({
  visible: false, id: null, plan_name: '', device_code: '', items: '',
  cycle_value: 30, next_due_at: null, responsible_id: null, remark: '', saving: false,
})
const openPlan = (row) => {
  Object.assign(planDlg, {
    visible: true, id: row?.id || null,
    plan_name: row?.plan_name || '', device_code: row?.device_code || '',
    items: row?.items || '', cycle_value: row?.cycle_value || 30,
    next_due_at: row?.next_due_at ? new Date(row.next_due_at) : null,
    responsible_id: row?.responsible_id || null, remark: row?.remark || '', saving: false,
  })
}
const savePlan = async () => {
  if (!planDlg.plan_name.trim()) return ElMessage.warning('请填写保养项目')
  planDlg.saving = true
  try {
    const payload = {
      plan_name: planDlg.plan_name, device_code: planDlg.device_code || null,
      items: planDlg.items || null, cycle_type: 'DAYS', cycle_value: planDlg.cycle_value,
      next_due_at: planDlg.next_due_at ? dayjs(planDlg.next_due_at).format('YYYY-MM-DDTHH:mm:ss') : null,
      responsible_id: planDlg.responsible_id || null, remark: planDlg.remark || null,
    }
    if (planDlg.id) await request.put(`/maintenance/plans/${planDlg.id}`, payload)
    else await request.post('/maintenance/plans', payload)
    ElMessage.success('已保存')
    planDlg.visible = false
    loadPlans(); loadStats()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally { planDlg.saving = false }
}
const removePlan = async (row) => {
  try {
    await ElMessageBox.confirm(`删除保养计划「${row.plan_name}」？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await request.delete(`/maintenance/plans/${row.id}`)
    ElMessage.success('已删除')
    loadPlans(); loadStats()
  } catch { ElMessage.error('删除失败') }
}

// ---- 执行保养 ----
const doneDlg = reactive({ visible: false, row: null, result: 'OK', cost: 0, remark: '', create_work_order: true, saving: false })
const openDone = (row) => {
  Object.assign(doneDlg, { visible: true, row, result: 'OK', cost: 0, remark: '', create_work_order: true, saving: false })
}
const submitDone = async () => {
  doneDlg.saving = true
  try {
    const res = await request.post(`/maintenance/plans/${doneDlg.row.id}/done`, {
      result: doneDlg.result, cost: doneDlg.cost, remark: doneDlg.remark || null,
      create_work_order: doneDlg.result === 'ABNORMAL' && doneDlg.create_work_order,
    })
    ElMessage.success(`已记录，下次到期 ${fmt(res.next_due_at)}` + (res.work_order_id ? `，已建工单 #${res.work_order_id}` : ''))
    doneDlg.visible = false
    loadPlans(); loadStats()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally { doneDlg.saving = false }
}

// ---- 点检 ----
const checkDlg = reactive({ visible: false, template_id: null, device_code: '', results: [], remark: '', saving: false })
const openCheck = async () => {
  if (!templates.value.length) await loadBase()
  Object.assign(checkDlg, { visible: true, template_id: null, device_code: '', results: [], remark: '', saving: false })
}
const onTemplateChange = (id) => {
  const tpl = templates.value.find((t) => t.id === id)
  checkDlg.results = (tpl?.items || []).map((it) => ({
    name: it.name, standard: it.standard || '', ok: true, value: null, remark: '',
  }))
}
const submitCheck = async () => {
  if (!checkDlg.template_id) return ElMessage.warning('请选择点检表')
  if (!checkDlg.device_code) return ElMessage.warning('请选择设备')
  checkDlg.saving = true
  try {
    const res = await request.post('/inspections/records', {
      template_id: checkDlg.template_id,
      device_code: checkDlg.device_code,
      results: checkDlg.results.map((r) => ({ name: r.name, ok: r.ok, value: r.value, remark: r.remark || null })),
      remark: checkDlg.remark || null,
      create_work_order_on_abnormal: true,
    })
    ElMessage.success(res.abnormal_count ? `已提交，异常 ${res.abnormal_count} 项，已自动建工单 #${res.work_order_id}` : '点检完成，一切正常')
    checkDlg.visible = false
    loadChecks()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally { checkDlg.saving = false }
}

onMounted(async () => {
  await loadBase()
  await Promise.all([loadPlans(), loadStats(), loadChecks()])
})
</script>

<style scoped>
.stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 12px; }
.stat-card {
  background: #fff; border: 1px solid #E5E6EB; border-radius: 8px;
  padding: 14px 16px; text-align: center;
}
.stat-card.danger { border-color: #F53F3F; background: #FFF5F5; }
.stat-card.warn { border-color: #FF7D00; background: #FFF9F0; }
.stat-num { font-size: 26px; font-weight: 700; color: #1F2329; }
.stat-card.danger .stat-num { color: #F53F3F; }
.stat-card.warn .stat-num { color: #FF7D00; }
.stat-label { font-size: 12px; color: #86909C; margin-top: 4px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.empty-hint { text-align: center; color: #86909C; font-size: 13px; padding: 18px 0; }
.hint { font-size: 12px; color: #86909C; margin-left: 8px; }
.check-items { width: 100%; max-height: 300px; overflow-y: auto; }
.check-item { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px dashed #F2F3F5; }
.check-name { min-width: 110px; font-weight: 500; }
.check-std { flex: 1; font-size: 12px; color: #86909C; }
</style>
