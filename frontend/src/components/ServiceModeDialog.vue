<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="430px"
    append-to-body
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-if="workOrderNo" class="sm-wo">工单 {{ workOrderNo }}</div>
    <div class="sm-label">服务方式</div>
    <el-radio-group v-model="mode" class="sm-radios">
      <el-radio label="REMOTE">远程处理</el-radio>
      <el-radio label="SITE">现场处理</el-radio>
      <el-radio label="RMA">返厂维修</el-radio>
    </el-radio-group>
    <el-input
      v-model="remark"
      type="textarea"
      :rows="2"
      maxlength="200"
      show-word-limit
      placeholder="备注（选填），例如：先远程排查，需到场再改现场"
      style="margin-top:12px"
    />
    <template #footer>
      <el-button plain @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="confirm">{{ confirmText }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '确认接单' },
  confirmText: { type: String, default: '确认接单' },
  workOrderNo: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'confirm'])
const mode = ref('REMOTE')
const remark = ref('')

watch(() => props.modelValue, (v) => {
  if (v) {
    mode.value = 'REMOTE'
    remark.value = ''
  }
})

const confirm = () => {
  emit('confirm', { service_mode: mode.value, remark: remark.value.trim() || null })
}
</script>

<style scoped>
.sm-wo { font-size: 13px; color: #86909C; margin-bottom: 12px; }
.sm-label { font-size: 13px; color: #1D2129; margin-bottom: 8px; font-weight: 500; }
.sm-radios { display: flex; gap: 18px; flex-wrap: wrap; }
</style>
