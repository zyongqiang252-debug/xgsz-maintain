/**
 * 功能开关（统一控制菜单 / 路由 / 标签页）
 *
 * 把某项改成 false，菜单、标签页、路由入口都会隐藏，页面代码保留；
 * 改回 true 即恢复，无需改其他文件。
 *
 * 2026-11-09 精简版：只保留「工单导入 / 工单生命周期 / 知识问答」主线
 */
export const FEATURES = {
  deviceMonitor: false,    // 服务器监控（无实时数据源）
  maintenance: false,      // 保养与点检（无实际使用）
  schedule: false,         // 排班管理（0 条排班）
  warehouse: false,        // 仓库库存（与备件台账重复）
  stockMovements: true,    // 出入库流水（独立页面 /stock/movements）
  manuals: false,          // 设备手册（与知识库重复）
  leave: false,            // 请假（HR 功能，PC + 移动端）
  help: false,             // 帮助中心（静态文案）
  dashboard: true,         // 数据驾驶舱
  stock: true,             // 库存中心（备件台账）
  knowledge: true,         // 知识中心
}

/** 路由级白名单：被隐藏功能的路径前缀 */
export const HIDDEN_ROUTE_PREFIXES = [
  ...(FEATURES.deviceMonitor ? [] : ['/devices']),
  ...(FEATURES.maintenance ? [] : ['/maintenance']),
  ...(FEATURES.schedule ? [] : ['/supervisor/schedule']),
  ...(FEATURES.leave ? [] : ['/me/leave', '/leave', '/m/leave']),
  ...(FEATURES.help ? [] : ['/help']),
]

/** 判断某路径是否属于已隐藏功能（含查询参数场景的容忍） */
export function isHiddenRoute(path) {
  if (!path) return false
  return HIDDEN_ROUTE_PREFIXES.some((p) => path === p || path.startsWith(p + '/') || path.startsWith(p + '?'))
}
