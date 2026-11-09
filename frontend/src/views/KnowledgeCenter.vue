<template>
  <div class="merged-page">
    <el-tabs v-model="tab" class="merged-tabs" @tab-change="onTabChange">
      <el-tab-pane label="AI 问答" name="qa" lazy>
        <component :is="AiAssistant" />
      </el-tab-pane>
      <el-tab-pane label="知识列表" name="list" lazy>
        <component :is="Knowledge" />
      </el-tab-pane>
      <el-tab-pane label="服务器手册" name="manuals" lazy>
        <component :is="ManualCodes" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const AiAssistant = defineAsyncComponent(() => import('./AiAssistant.vue'))
const Knowledge = defineAsyncComponent(() => import('./Knowledge.vue'))
const ManualCodes = defineAsyncComponent(() => import('./ManualCodes.vue'))

const VALID = ['qa', 'list', 'manuals']
const tab = ref(VALID.includes(route.query.tab) ? String(route.query.tab) : 'qa')

const onTabChange = (name) => {
  router.replace({ path: '/knowledge-center', query: { tab: name } })
}
</script>

<style scoped>
.merged-page { padding: 0; }
.merged-tabs { margin-top: -6px; }
.merged-tabs :deep(.page) { padding: 0; }
.merged-tabs :deep(.page-header) { margin-top: 4px; }
</style>
