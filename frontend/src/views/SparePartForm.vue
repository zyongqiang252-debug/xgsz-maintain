<template>
  <div class="page">
    <div class="page-header">
      <h2 class="page-title">{{ isNew ? '新增备件' : (canManage ? '编辑备件' : '备件详情') }}</h2>
    </div>

    <el-card shadow="never">
      <el-form :model="form" label-width="100px" style="max-width: 800px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="备件编码" required>
              <el-input v-model="form.part_code" placeholder="如 P-001" :disabled="!isNew" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="备件名称" required>
              <el-input v-model="form.part_name" placeholder="如 轴承 6205-2RS" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="规格型号">
              <el-input v-model="form.specification" placeholder="规格型号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="单位">
              <el-input v-model="form.unit" placeholder="个/套/台" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="库存数量">
              <el-input-number v-model="form.stock_quantity" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="安全库存">
              <el-input-number v-model="form.safety_stock" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="单价">
              <el-input-number v-model="form.unit_price" :min="0" :precision="2" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="适用设备">
              <el-input v-model="form.device_type" placeholder="适用设备类型" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="存放位置">
              <el-input v-model="form.location" placeholder="仓库/货架位置" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="供应商">
          <el-input v-model="form.supplier" placeholder="供应商名称" />
        </el-form-item>
        <el-form-item>
          <el-button v-if="canManage" type="primary" @click="handleSave" :loading="saving">保存</el-button>
          <el-button @click="$router.push('/spare-parts')">返回列表</el-button>
          <span v-if="!canManage" class="readonly-tip">备件台账由管理员/主管维护，当前为只读视图</span>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import request from '../api'

const route = useRoute()
const router = useRouter()
const isNew = computed(() => !route.params.id || route.params.id === 'new')
const saving = ref(false)

// 备件台账维护权限：仅管理员/主管
const canManage = computed(() => {
  try {
    const role = JSON.parse(localStorage.getItem('current_user') || '{}').role
    return role === 'ADMIN' || role === 'SUPERVISOR'
  } catch { return false }
})

const form = ref({
  part_code: '', part_name: '', specification: '', unit: '个',
  stock_quantity: 0, safety_stock: 0, unit_price: 0,
  device_type: '', location: '', supplier: ''
})

const loadData = async () => {
  if (isNew.value) return
  const res = await request.get(`/spare-parts/${route.params.id}`)
  Object.assign(form.value, res)
}

const handleSave = async () => {
  saving.value = true
  try {
    const data = { ...form.value }
    if (isNew.value) {
      await request.post('/spare-parts/', data)
      ElMessage.success('创建成功')
    } else {
      await request.put(`/spare-parts/${route.params.id}`, data)
      ElMessage.success('更新成功')
    }
    router.push('/spare-parts')
  } finally { saving.value = false }
}

onMounted(() => {
  if (isNew.value && !canManage.value) {
    ElMessage.warning('仅管理员/主管可新增备件')
    router.push('/spare-parts')
    return
  }
  loadData()
})
</script>

<style scoped>
.readonly-tip { margin-left: 12px; font-size: 12px; color: #86909C; }
</style>
