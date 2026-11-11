export const IMPACT_OPTIONS = [
  { value: 'CRITICAL', label: '业务中断', desc: 'GPU 掉卡、整机宕机、集群不可用' },
  { value: 'HIGH', label: '严重降级', desc: '降频、温度告警、单卡异常但业务可跑' },
  { value: 'MEDIUM', label: '一般', desc: '单次告警、性能轻微波动' },
  { value: 'LOW', label: '咨询 / 无影响', desc: '使用咨询、配置确认、外观问题' },
]

export const IMPACT_LABEL = IMPACT_OPTIONS.reduce((acc, item) => {
  acc[item.value] = item.label
  return acc
}, {})
