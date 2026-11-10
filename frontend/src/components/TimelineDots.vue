<template>
  <!-- 待派工：还没有进入流程，画一排灰点没有意义，只留一个标签 -->
  <div v-if="mode === 'pending'" class="tl-chip">待派工</div>

  <!-- 已完成 / 已归档：不再画过程点，直接给结论 -->
  <div v-else-if="mode === 'done'" class="tl-badge">
    <el-icon><CircleCheck /></el-icon>
    <span>{{ doneText }}</span>
  </div>

  <!-- 进行中：只画「已发生 + 当前」的节点，未来节点不画 -->
  <div v-else class="timeline-dots">
    <div
      v-for="step in steps"
      :key="step.key"
      class="tl-step"
      :class="{ 'tl-done': step.done, 'tl-current': step.current }"
      :title="step.title"
    >
      <span class="tl-dot"></span>
      <span v-if="step.current" class="tl-label">{{ step.label }}</span>
    </div>
    <span class="tl-ratio">{{ doneRank }}/6</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { CircleCheck } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const props = defineProps({
  wo: { type: Object, required: true },
})

// 流程 6 步；rank 用来判断"走到第几步"，不再依赖日志是否存在
const STEPS = [
  { key: 'ASSIGNED', label: '派工', rank: 1 },
  { key: 'ACCEPTED', label: '接受', rank: 2 },
  { key: 'ARRIVED', label: '到达', rank: 3 },
  { key: 'INSPECTING', label: '检查', rank: 4 },
  { key: 'IN_PROGRESS', label: '维修', rank: 5 },
  { key: 'COMPLETED', label: '完成', rank: 6 },
]

// 工单状态 → 流程第几步（历史/异常状态统一按 0 处理，不误导）
const STATUS_RANK = {
  DRAFT: 0,
  SUBMITTED: 0,
  ASSIGNED: 1,
  ACCEPTED: 2,
  ARRIVED: 3,
  INSPECTING: 4,
  IN_PROGRESS: 5,
  COMPLETED: 6,
  ARCHIVING: 6,
  ARCHIVED: 6,
}

const rank = computed(() => STATUS_RANK[props.wo?.status] ?? 0)

const mode = computed(() => {
  if (rank.value >= 6) return 'done'
  if (rank.value <= 0) return 'pending'
  return 'timeline'
})

const doneText = computed(() =>
  props.wo?.status === 'ARCHIVING' ? '维修完成 · 待归档' : '已完成 6/6',
)

// 日志只用来补时间（hover 看），不决定点亮
const timeMap = computed(() => {
  const map = {}
  for (const item of props.wo?.progress_timeline || []) {
    if (item?.status) map[item.status] = item.timestamp || item.created_at || ''
  }
  return map
})

const steps = computed(() =>
  STEPS.filter((s) => s.rank <= rank.value).map((s) => {
    const time = timeMap.value[s.key]
    return {
      ...s,
      done: s.rank < rank.value,
      current: s.rank === rank.value,
      title: time ? `${s.label} · ${dayjs(time).format('MM-DD HH:mm')}` : s.label,
    }
  }),
)

const doneRank = computed(() => Math.min(rank.value, 6))
</script>

<style scoped>
.timeline-dots {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 2px 0;
  margin-top: 8px;
  border-top: 1px dashed #F2F3F5;
}
.tl-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.tl-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid #C9CDD4;
  background: #fff;
  transition: all .2s;
}
.tl-done .tl-dot {
  background: #3491FA;
  border-color: #3491FA;
}
.tl-current .tl-dot {
  width: 14px;
  height: 14px;
  background: #3491FA;
  border-color: #3491FA;
  animation: dot-pulse 1.2s infinite;
}
.tl-label {
  font-size: 12px;
  line-height: 1.2;
  color: #3491FA;
  white-space: nowrap;
}
.tl-ratio {
  margin-left: auto;
  font-size: 12px;
  color: #86909C;
}
.tl-chip {
  margin-top: 10px;
  padding: 3px 10px;
  border-radius: 10px;
  background: #F2F3F5;
  color: #86909C;
  font-size: 12px;
  display: inline-block;
}
.tl-badge {
  margin-top: 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 10px;
  background: rgba(0, 180, 42, 0.08);
  color: #00B42A;
  font-size: 12px;
}
@keyframes dot-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(52, 145, 250, .35); }
  50% { box-shadow: 0 0 0 4px rgba(52, 145, 250, 0); }
}
</style>
