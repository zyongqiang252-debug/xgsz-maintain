<template>
  <div class="settings-page">
    <div class="page-header">
      <h2 class="page-title">系统设置</h2>
      <p class="page-desc">第三方服务接入：保存即生效，配置存在数据库里，重启不会丢</p>
    </div>

    <!-- ================= AI 大模型 ================= -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">AI 大模型（DeepSeek）</span>
          <el-tag :type="ai.configured ? 'success' : 'info'" size="small">
            {{ ai.configured ? `已配置 ${ai.api_key_masked}` : '未配置' }}
          </el-tag>
        </div>
      </template>

      <el-alert type="info" :closable="false" show-icon class="tip">
        配置后解锁：AI 问答回答、专家模式/追踪维修、工单 AI 校验、PDF 智能抽取、归档自动收录知识、知识去重
      </el-alert>

      <el-form label-width="110px" class="settings-form">
        <el-form-item label="API Key">
          <el-input
            v-model="form.apiKey"
            type="password"
            show-password
            clearable
            :placeholder="ai.configured ? `已配置 ${ai.api_key_masked}，留空表示不修改` : '粘贴 sk- 开头的密钥'"
          />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="form.baseUrl" placeholder="https://api.deepseek.com" />
        </el-form-item>
        <el-form-item label="模型">
          <el-select
            v-model="form.model"
            style="width: 280px"
            filterable
            allow-create
            default-first-option
            placeholder="deepseek-chat"
          >
            <el-option label="deepseek-chat（通用，便宜）" value="deepseek-chat" />
            <el-option label="deepseek-reasoner（推理，较慢较贵）" value="deepseek-reasoner" />
            <el-option label="deepseek-flash（快，按量计费）" value="deepseek-flash" />
          </el-select>
          <span class="hint">可手动输入其他模型名</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingAI" @click="saveAI">保存并生效</el-button>
          <el-button :loading="testingAI" @click="testAI">测试连接</el-button>
          <el-button v-if="ai.configured" text type="danger" @click="clearKey">清除 Key</el-button>
        </el-form-item>
        <el-form-item v-if="aiTest">
          <el-alert
            :type="aiTest.ok ? 'success' : 'error'"
            :closable="false"
            :title="aiTest.ok
              ? `连通正常 · ${aiTest.latency_ms}ms · 模型 ${aiTest.model}` + (aiTest.tested_unsaved ? '（用的是输入框里未保存的 Key，记得点保存）' : '')
              : aiTest.msg"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ================= 钉钉群机器人 ================= -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">钉钉群机器人（工单事件推群）</span>
          <el-tag :type="group.enabled ? 'success' : 'info'" size="small">
            {{ group.enabled ? '已配置' : '未配置' }}
          </el-tag>
        </div>
      </template>

      <el-alert type="info" :closable="false" show-icon class="tip">
        群设置 → 智能群助手 → 添加机器人 → 自定义 → 勾「加签」，把 Webhook 和密钥填这里。新工单/派工/归档会自动推群。
      </el-alert>

      <el-form label-width="110px" class="settings-form">
        <el-form-item label="Webhook">
          <el-input
            v-model="groupForm.webhook"
            clearable
            :placeholder="group.enabled ? `已配置 ${group.webhook_masked}，留空表示不修改` : 'https://oapi.dingtalk.com/robot/send?access_token=...'"
          />
        </el-form-item>
        <el-form-item label="加签密钥">
          <el-input
            v-model="groupForm.secret"
            type="password"
            show-password
            clearable
            :placeholder="group.signed ? '已配置，留空表示不修改' : 'SEC 开头的加签密钥（可不填）'"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingGroup" @click="saveGroup">保存并生效</el-button>
          <el-button :loading="testingGroup" @click="testGroup">发测试消息</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ================= 其他接入状态 ================= -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">其他接入（只读，需改 .env 后重启）</span>
        </div>
      </template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="短信验证码">
          <el-tag :type="overview.sms?.enabled ? 'success' : 'info'" size="small">
            {{ overview.sms?.enabled ? '已开启真实短信' : '未开启（验证码写后端日志）' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="钉钉扫码登录">
          <el-tag :type="overview.dingtalk?.mock_mode ? 'warning' : 'success'" size="small">
            {{ overview.dingtalk?.mock_mode ? '模拟模式（真机扫不了）' : '真实模式' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="向量检索（Milvus）">
          <span class="mono">{{ overview.milvus?.host }}:{{ overview.milvus?.port }}</span>
          <span class="hint">未部署时自动降级 BM25</span>
        </el-descriptions-item>
        <el-descriptions-item label="接口文档">
          <a href="/docs" target="_blank" class="link">/docs</a>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'

const ai = reactive({ configured: false, api_key_masked: '', base_url: '', model: '' })
const group = reactive({ enabled: false, webhook_masked: '', signed: false })
const overview = reactive({})
const form = reactive({ apiKey: '', baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' })
const groupForm = reactive({ webhook: '', secret: '' })
const aiTest = ref(null)
const savingAI = ref(false)
const testingAI = ref(false)
const savingGroup = ref(false)
const testingGroup = ref(false)

const loadAll = async () => {
  try {
    const [ov, aiRes, gr] = await Promise.all([
      request.get('/system-settings/overview'),
      request.get('/system-settings/ai'),
      request.get('/system-settings/dingtalk-group'),
    ])
    Object.assign(overview, ov)
    Object.assign(ai, aiRes)
    form.baseUrl = aiRes.base_url || 'https://api.deepseek.com'
    form.model = aiRes.model || 'deepseek-chat'
    Object.assign(group, gr)
  } catch (e) {
    ElMessage.error('读取配置失败')
  }
}

const saveAI = async () => {
  savingAI.value = true
  aiTest.value = null
  try {
    const payload = { base_url: form.baseUrl, model: form.model }
    if (form.apiKey.trim()) payload.api_key = form.apiKey.trim()
    const res = await request.put('/system-settings/ai', payload)
    Object.assign(ai, res.current)
    form.apiKey = ''
    ElMessage.success('已保存并生效')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingAI.value = false
  }
}

const testAI = async () => {
  testingAI.value = true
  aiTest.value = null
  try {
    // 把输入框里当前的值带过去：没保存也能先测
    const payload = { base_url: form.baseUrl, model: form.model }
    if (form.apiKey.trim()) payload.api_key = form.apiKey.trim()
    const res = await request.post('/system-settings/ai/test', payload, { timeout: 40000 })
    aiTest.value = { ok: true, ...res }
  } catch (e) {
    aiTest.value = { ok: false, msg: e?.response?.data?.detail || '测试失败' }
  } finally {
    testingAI.value = false
  }
}

const clearKey = async () => {
  try {
    await ElMessageBox.confirm('清除后 AI 相关功能会立即失效，确认？', '清除 API Key', { type: 'warning' })
  } catch { return }
  try {
    const res = await request.put('/system-settings/ai', { api_key: '' })
    Object.assign(ai, res.current)
    ElMessage.success('已清除')
  } catch (e) {
    ElMessage.error('清除失败')
  }
}

const saveGroup = async () => {
  savingGroup.value = true
  try {
    const payload = {}
    if (groupForm.webhook.trim()) payload.webhook = groupForm.webhook.trim()
    if (groupForm.secret.trim()) payload.secret = groupForm.secret.trim()
    if (!Object.keys(payload).length) {
      ElMessage.warning('没有要保存的内容')
      return
    }
    const res = await request.put('/system-settings/dingtalk-group', payload)
    Object.assign(group, res.current)
    groupForm.webhook = ''
    groupForm.secret = ''
    ElMessage.success('已保存并生效')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    savingGroup.value = false
  }
}

const testGroup = async () => {
  testingGroup.value = true
  try {
    await request.post('/system-settings/dingtalk-group/test', null, { timeout: 30000 })
    ElMessage.success('测试消息已发送，去群里看看')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '发送失败')
  } finally {
    testingGroup.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.settings-page { padding: 4px 0 24px; }
.page-header { margin-bottom: 16px; }
.page-title { margin: 0; font-size: 20px; color: #1F2329; }
.page-desc { margin: 6px 0 0; font-size: 13px; color: #86909C; }
.section-card { margin-bottom: 16px; border-radius: 8px; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 15px; font-weight: 600; color: #1F2329; }
.settings-form { max-width: 640px; margin-top: 8px; }
.tip { margin-bottom: 12px; }
.mono { font-family: Consolas, monospace; }
.hint { margin-left: 8px; color: #86909C; font-size: 12px; }
.link { color: #0FC6C2; }
</style>
