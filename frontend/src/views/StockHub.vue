<template>
  <div class="hub">
    <el-tabs v-model="tab" class="hub-tabs" @tab-change="onTabChange">
      <el-tab-pane label="备件台账" name="parts" lazy>
        <component :is="Parts" ref="partsRef" />
      </el-tab-pane>
      <el-tab-pane label="出入库流水" name="movements" lazy>
        <component :is="Movements" :key="'mv-' + rev.movements" />
      </el-tab-pane>
      <el-tab-pane label="领用审批" name="requisitions" lazy>
        <component :is="Requisitions" :key="'rq-' + rev.requisitions" />
      </el-tab-pane>
      <el-tab-pane v-if="isSupervisor" label="盘点" name="stocktakes" lazy>
        <component :is="Stocktakes" :key="'st-' + rev.stocktakes" />
      </el-tab-pane>
      <el-tab-pane v-if="isSupervisor" label="仓库与库位" name="warehouses" lazy>
        <component :is="Warehouses" :key="'wh-' + rev.warehouses" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const Parts = defineAsyncComponent(() => import('./SpareParts.vue'))
const Movements = defineAsyncComponent(() => import('./StockMovements.vue'))
const Requisitions = defineAsyncComponent(() => import('./RequisitionCenter.vue'))
const Stocktakes = defineAsyncComponent(() => import('./StocktakeCenter.vue'))
const Warehouses = defineAsyncComponent(() => import('./WarehouseCenter.vue'))

const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const isSupervisor = currentUser.role === 'ADMIN' || currentUser.role === 'SUPERVISOR'

const TABS = computed(() =>
  isSupervisor
    ? ['parts', 'movements', 'requisitions', 'stocktakes', 'warehouses']
    : ['parts', 'movements', 'requisitions'],
)
const initial = String(route.query.tab || '')
const tab = ref(TABS.value.includes(initial) ? initial : 'parts')

// 跨 tab 联动：非台账 tab 每次激活都重新挂载拉新数据；台账 tab 保留筛选，只调它的 refresh()
const rev = reactive({ movements: 0, requisitions: 0, stocktakes: 0, warehouses: 0 })
const partsRef = ref(null)
const activate = (name) => {
  if (name === 'parts') {
    partsRef.value?.refresh?.()
    return
  }
  if (rev[name] !== undefined) rev[name] += 1
}

watch(() => route.query.tab, (v) => {
  const t = String(v || '')
  if (TABS.value.includes(t) && t !== tab.value) {
    tab.value = t
    activate(t)
  }
})

const onTabChange = (name) => {
  router.replace({ path: '/stock', query: { tab: name } })
  activate(name)
}
</script>

<style scoped>
.hub-tabs { margin-top: -6px; }
/* 内嵌页面：去掉自身标题和内边距，只保留右上角操作按钮 */
.hub-tabs :deep(.page),
.hub-tabs :deep(.merged-page) { padding: 0; }
.hub-tabs :deep(.page-title) { display: none; }
.hub-tabs :deep(.page-header) {
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  padding: 0;
  min-height: 32px;
}
.hub-tabs :deep(.el-tabs__header) { margin-bottom: 10px; border-bottom: 1px solid #F2F3F5; }
</style>
