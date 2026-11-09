<template>
  <div class="merged-page">
    <el-tabs v-model="tab" class="merged-tabs" @tab-change="onTabChange">
      <el-tab-pane label="设备/业务分类" name="categories" lazy>
        <component :is="Categories" />
      </el-tab-pane>
      <el-tab-pane label="故障码字典" name="faultcodes" lazy>
        <component :is="FaultCodes" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const Categories = defineAsyncComponent(() => import('./Categories.vue'))
const FaultCodes = defineAsyncComponent(() => import('./FaultCodes.vue'))

const VALID = ['categories', 'faultcodes']
const tab = ref(VALID.includes(route.query.tab) ? String(route.query.tab) : 'categories')

const onTabChange = (name) => {
  router.replace({ path: '/dict', query: { tab: name } })
}
</script>

<style scoped>
.merged-page { padding: 0; }
.merged-tabs { margin-top: -6px; }
.merged-tabs :deep(.page) { padding: 0; }
.merged-tabs :deep(.page-header) { margin-top: 4px; }
</style>
