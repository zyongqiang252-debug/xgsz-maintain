<template>
  <div class="tbl-skeleton">
    <div v-for="i in rows" :key="i" class="tbl-skeleton__row">
      <div v-for="c in cols" :key="c" class="tbl-skeleton__cell"
           :style="{ width: widths[(c - 1) % widths.length] }"></div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 6 },
  cols: { type: Number, default: 5 },
  widths: { type: Array, default: () => ['14%', '28%', '12%', '14%', '10%'] },
})
</script>

<style scoped>
.tbl-skeleton { padding: 8px 0; }
.tbl-skeleton__row {
  display: flex; align-items: center; gap: 20px;
  height: 46px; padding: 0 12px;
  border-bottom: 1px solid #F4F5F7;
}
.tbl-skeleton__cell {
  height: 12px; border-radius: 6px;
  background: linear-gradient(90deg, #F2F4F7 25%, #E9ECF2 37%, #F2F4F7 63%);
  background-size: 400% 100%;
  animation: tbl-shimmer 1.4s ease infinite;
}
@keyframes tbl-shimmer {
  0% { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}
</style>
