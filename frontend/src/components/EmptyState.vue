<template>
  <div class="empty-state">
    <div class="empty-state__icon">
      <el-icon :size="26"><component :is="iconComp" /></el-icon>
    </div>
    <div class="empty-state__title">{{ title }}</div>
    <div v-if="hint" class="empty-state__hint">{{ hint }}</div>
    <el-button v-if="actionText" type="primary" plain size="small" class="empty-state__action" @click="$emit('action')">
      {{ actionText }}
    </el-button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Box, Document, Search, User, Tools } from '@element-plus/icons-vue'

const props = defineProps({
  icon: { type: String, default: 'box' }, // box | doc | search | user | tools
  title: { type: String, default: '暂无数据' },
  hint: { type: String, default: '' },
  actionText: { type: String, default: '' },
})
defineEmits(['action'])

const MAP = { box: Box, doc: Document, search: Search, user: User, tools: Tools }
const iconComp = computed(() => MAP[props.icon] || Box)
</script>

<style scoped>
.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 40px 16px 44px;
  text-align: center;
}
.empty-state__icon {
  width: 56px; height: 56px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: #F4F6F9; color: #B4BAC4;
  margin-bottom: 12px;
}
.empty-state__title { font-size: 14px; font-weight: 500; color: #4E5969; }
.empty-state__hint { font-size: 12.5px; color: #9AA1AC; margin-top: 6px; max-width: 380px; line-height: 1.6; }
.empty-state__action { margin-top: 14px; }
</style>
