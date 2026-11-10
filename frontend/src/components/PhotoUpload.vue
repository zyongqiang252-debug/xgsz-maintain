<template>
  <div class="photo-upload">
    <el-upload
      action="#"
      :show-file-list="false"
      :http-request="doUpload"
      :disabled="disabled || modelValue.length >= limit"
      accept="image/*"
      multiple
    >
      <div class="photo-add" :class="{ disabled: disabled || modelValue.length >= limit }">
        <span>+</span>
        <small>照片</small>
      </div>
    </el-upload>
    <div v-if="modelValue.length" class="photo-list">
      <div v-for="(url, i) in modelValue" :key="url + i" class="photo-item">
        <el-image
          :src="url"
          fit="cover"
          :preview-src-list="modelValue"
          :initial-index="i"
          preview-teleported
        />
        <span v-if="!disabled" class="photo-del" @click.stop="remove(i)">×</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ElMessage } from 'element-plus'
import request from '../api'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  limit: { type: Number, default: 6 },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const update = (list) => emit('update:modelValue', list)

const doUpload = async ({ file }) => {
  if (!file) return
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.warning('单张照片不能超过 20MB')
    return
  }
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await request.post('/upload/work-order-image', fd)
    update([...props.modelValue, res.url])
    ElMessage.success('照片已上传')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '照片上传失败')
  }
}

const remove = (i) => {
  const arr = [...props.modelValue]
  arr.splice(i, 1)
  update(arr)
}
</script>

<style scoped>
.photo-upload { display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap; }
.photo-add {
  width: 74px; height: 74px; border: 1px dashed #C9CDD4; border-radius: 8px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #86909C; cursor: pointer; background: #FAFBFC; transition: border-color .2s;
}
.photo-add:hover { border-color: #0FC6C2; color: #0FC6C2; }
.photo-add.disabled { cursor: not-allowed; opacity: .5; }
.photo-add span { font-size: 22px; line-height: 1; }
.photo-add small { font-size: 12px; margin-top: 4px; }
.photo-list { display: flex; gap: 8px; flex-wrap: wrap; }
.photo-item { position: relative; width: 74px; height: 74px; border-radius: 8px; overflow: hidden; }
.photo-item :deep(.el-image) { width: 100%; height: 100%; }
.photo-del {
  position: absolute; top: 2px; right: 2px; width: 18px; height: 18px; line-height: 16px;
  text-align: center; border-radius: 50%; background: rgba(0,0,0,.55); color: #fff;
  font-size: 14px; cursor: pointer;
}
</style>
