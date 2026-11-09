<template>
  <div class="merged-page">
    <el-tabs v-model="tab" class="merged-tabs" :class="{ 'hide-tabbar': singleTab }" @tab-change="onTabChange">
      <el-tab-pane label="备件台账" name="parts" lazy>
        <component :is="SpareParts" />
      </el-tab-pane>
      <el-tab-pane v-if="FEATURES.warehouse" label="仓库库存" name="warehouse" lazy>
        <component :is="Warehouse" />
      </el-tab-pane>
      <el-tab-pane v-if="FEATURES.stockMovements" label="出入库流水" name="movements" lazy>
        <component :is="StockMovements" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, defineAsyncComponent } from 'vue'
import { FEATURES } from '../config/features'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const SpareParts = defineAsyncComponent(() => import('./SpareParts.vue'))
const Warehouse = defineAsyncComponent(() => import('./Warehouse.vue'))
const StockMovements = defineAsyncComponent(() => import('./StockMovements.vue'))

const VALID_ALL = ['parts', 'warehouse', 'movements']
const VISIBLE_TABS = VALID_ALL.filter((t) => {
  if (t === 'warehouse') return FEATURES.warehouse
  if (t === 'movements') return FEATURES.stockMovements
  return true
})
const VALID = VISIBLE_TABS
const singleTab = computed(() => !FEATURES.warehouse && !FEATURES.stockMovements)

const DEFAULT_TAB = 'parts'
const tab = ref(VALID.includes(String(route.query.tab)) ? String(route.query.tab) : VALID[0])

const onTabChange = (name) => {
  router.replace({ path: '/stock', query: { tab: name } })
}
</script>

<style scoped>
.merged-page { padding: 0; }
.merged-tabs { margin-top: -10px; }
/* 内嵌页面自带 .page 内边距与标题，合并后去掉，避免双层留白与标题重复 */
.merged-tabs :deep(.page) { padding: 0; }
.merged-tabs :deep(.page-title) { display: none; }
.merged-tabs :deep(.el-tabs__header) { margin-bottom: 10px; border-bottom: 1px solid #F2F3F5; }
/* 操作行：只右对齐，不加底色，避免出现大片空白工具条 */
.merged-tabs :deep(.page-header) {
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  padding: 0;
  min-height: 32px;
}
.merged-tabs.hide-tabbar :deep(.el-tabs__header) { display: none; }
</style>
