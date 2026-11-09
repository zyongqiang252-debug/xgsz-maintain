import { createRouter, createWebHistory } from 'vue-router'
import { isHiddenRoute } from '../config/features'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      redirect: '/dashboard',
      children: [
        { path: 'dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '数据驾驶舱' } },
        { path: 'work-orders', name: 'LegacyWorkOrders', redirect: '/orders?tab=list', meta: { title: '维修报表' } },
        { path: 'orders', name: 'WorkOrderCenter', component: () => import('../views/WorkOrderCenter.vue'), meta: { title: '工单中心' } },
        { path: 'stock', name: 'StockCenter', component: () => import('../views/StockCenter.vue'), meta: { title: '库存中心' } },
        { path: 'dict', name: 'DictCenter', component: () => import('../views/DictCenter.vue'), meta: { title: '字典管理' } },
        { path: 'knowledge-center', name: 'KnowledgeCenter', component: () => import('../views/KnowledgeCenter.vue'), meta: { title: '知识中心' } },
        { path: 'sys', name: 'SysCenter', component: () => import('../views/SysCenter.vue'), meta: { title: '系统管理' } },
        { path: 'me', name: 'MeCenter', component: () => import('../views/MeCenter.vue'), meta: { title: '通知中心' } },
        { path: 'work-orders/new', name: 'WorkOrderCreate', component: () => import('../views/WorkOrderForm.vue'), meta: { title: '新建工单' } },
        { path: 'work-orders/:id', name: 'WorkOrderForm', component: () => import('../views/WorkOrderForm.vue'), meta: { title: '工单详情' } },
        { path: 'devices', name: 'Devices', component: () => import('../views/Devices.vue'), meta: { title: '设备监控' } },
        { path: 'devices/new', name: 'DeviceCreate', component: () => import('../views/DeviceForm.vue'), meta: { title: '新增设备' } },
        { path: 'devices/:id', name: 'DeviceForm', component: () => import('../views/DeviceForm.vue'), meta: { title: '设备详情' } },
        { path: 'maintenance', name: 'Maintenance', component: () => import('../views/Maintenance.vue'), meta: { title: '保养与点检' } },
        {
          path: 'knowledge',
          name: 'Knowledge',
          component: () => import('../views/KnowledgeLayout.vue'),
          redirect: '/knowledge/list',
          children: [
            { path: 'list', name: 'KnowledgeList', redirect: '/knowledge-center?tab=list', meta: { title: '知识列表' } },
            { path: 'manuals', name: 'KnowledgeManuals', redirect: '/knowledge-center?tab=manuals', meta: { title: '服务器手册' } },
            { path: 'new', name: 'KnowledgeCreate', component: () => import('../views/KnowledgeForm.vue'), meta: { title: '新增知识', knowledgeTab: 'list' } },
            { path: ':id', name: 'KnowledgeForm', component: () => import('../views/KnowledgeForm.vue'), meta: { title: '知识详情', knowledgeTab: 'list' } },
          ],
        },
        { path: 'spare-parts', name: 'LegacySpareParts', redirect: '/stock?tab=parts', meta: { title: '库存管理' } },
        { path: 'spare-parts/new', name: 'SparePartCreate', component: () => import('../views/SparePartForm.vue'), meta: { title: '新增备件' } },
        { path: 'spare-parts/:id', name: 'SparePartForm', component: () => import('../views/SparePartForm.vue'), meta: { title: '备件详情' } },
        { path: 'warehouse', name: 'LegacyWarehouse', redirect: '/stock?tab=warehouse', meta: { title: '仓库库存' } },
        { path: 'users', name: 'LegacyUsers', redirect: '/sys?tab=users', meta: { title: '用户管理' } },
        { path: 'system-settings', name: 'LegacySystemSettings', redirect: '/sys?tab=settings', meta: { title: '系统设置', roles: ['ADMIN'] } },
        { path: 'categories', name: 'LegacyCategories', redirect: '/dict?tab=categories', meta: { title: '分类管理' } },
        { path: 'search', redirect: '/ai-assistant' },
        { path: 'ai-assistant', name: 'LegacyAiAssistant', redirect: '/knowledge-center?tab=qa', meta: { title: 'AI 问答看板' } },
        { path: 'fault-codes', name: 'LegacyFaultCodes', redirect: '/dict?tab=faultcodes', meta: { title: '故障码管理' } },
        { path: 'work-order-imports', name: 'LegacyWorkOrderImports', redirect: '/orders?tab=import', meta: { title: '历史工单导入', roles: ['ADMIN', 'TECHNICIAN'] } },
        { path: 'profile', name: 'Profile', component: () => import('../views/Profile.vue'), meta: { title: '个人设置' } },
        { path: 'notifications', name: 'LegacyNotifications', redirect: '/me?tab=notifications', meta: { title: '通知中心' } },
        { path: 'leave', name: 'LegacyLeaveRequests', redirect: '/me?tab=leave', meta: { title: '我的请假' } },
        { path: 'security', name: 'Security', component: () => import('../views/Security.vue'), meta: { title: '账号安全' } },
        { path: 'help', name: 'LegacyHelp', redirect: '/me?tab=help', meta: { title: '帮助中心' } },
        { path: 'supervisor/dispatch', name: 'LegacySupervisorDispatch', redirect: '/orders?tab=dispatch', meta: { title: '派工中心', roles: ['SUPERVISOR', 'ADMIN'] } },
        { path: 'supervisor/progress', name: 'LegacySupervisorProgress', redirect: '/orders?tab=progress', meta: { title: '实时进度看板', roles: ['SUPERVISOR', 'ADMIN'] } },
        { path: 'supervisor/schedule', name: 'SupervisorSchedule', component: () => import('../views/SupervisorSchedule.vue'), meta: { title: '排班管理', roles: ['SUPERVISOR', 'ADMIN'] } },
      ]
    },
    // 登录页（独立于 MainLayout）
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/Login.vue'),
      meta: { title: '登录', noAuth: true },
    },
    // 移动端 H5 路由
    {
      path: '/m',
      component: () => import('../layouts/MobileLayout.vue'),
      redirect: '/m/report',
      children: [
        { path: 'report', name: 'MobileReport', component: () => import('../views/mobile/WorkerSubmit.vue'), meta: { title: '故障上报' } },
        { path: 'queue', name: 'TechQueue', component: () => import('../views/mobile/TechQueue.vue'), meta: { title: '我的工单' } },
        { path: 'detail/:id', name: 'TechDetail', component: () => import('../views/mobile/TechDetail.vue'), meta: { title: '工单详情' } },
        { path: 'leave', name: 'MobileLeave', component: () => import('../views/mobile/MobileLeave.vue'), meta: { title: '请假申请' } },
      ]
    }
  ]
})

// 全局导航守卫：未登录跳转登录页
router.beforeEach((to, from, next) => {
  // 功能开关：已隐藏的功能直接回驾驶舱
  if (isHiddenRoute(to.path)) return next('/dashboard')
  if (!to.meta.noAuth) {
    const token = localStorage.getItem('auth_token')
    const user = localStorage.getItem('current_user')
    if (!token && !user) {
      next('/login')
      return
    }
  }
  next()
})

export default router
