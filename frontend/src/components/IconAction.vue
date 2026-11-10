<template>
  <el-tooltip :content="title" placement="top" :show-after="300" :disabled="!title">
    <span class="icon-action" @click="onClick">
      <el-button
        text
        circle
        size="small"
        :type="type || undefined"
        :icon="icon"
        :disabled="disabled"
      />
    </span>
  </el-tooltip>
</template>

<script setup>
const props = defineProps({
  icon: { type: [Object, Function], required: true },
  title: { type: String, default: '' },
  type: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['click'])
const onClick = () => {
  if (!props.disabled) emit('click')
}
</script>

<style scoped>
.icon-action { display: inline-flex; }
.icon-action :deep(.el-button) {
  width: 26px;
  height: 26px;
  padding: 0;
  margin: 0;
  color: #4E5969;
  font-size: 15px;
}
.icon-action :deep(.el-button:hover) { color: #0FC6C2; background: #F2F3F5; }
.icon-action :deep(.el-button.is-disabled) { color: #C9CDD4; background: transparent; }
.icon-action :deep(.el-button.el-button--danger) { color: #F53F3F; }
.icon-action :deep(.el-button.el-button--danger:hover) { color: #F53F3F; background: #FFF1F0; }
.icon-action :deep(.el-button.is-disabled.el-button--danger) { color: #F7C5C5; }
.icon-action :deep(.el-button.el-button--warning) { color: #FF7D00; }
.icon-action :deep(.el-button.el-button--success) { color: #00B42A; }
</style>
