<template>
  <div class="worker-submit">
    <!-- 扫码区 -->
    <div class="scan-area" @click="handleScan">
      <div class="scan-icon">📷</div>
      <div class="scan-text">扫码识别服务器</div>
      <div class="scan-code" v-if="form.device_code">{{ form.device_code }}</div>
    </div>

    <!-- 设备档案（扫码/输入编码后带出） -->
    <div v-if="deviceInfo" class="device-card">
      <div class="device-title">{{ deviceInfo.device_name }}（{{ deviceInfo.device_code }}）</div>
      <div class="device-line">型号：{{ deviceInfo.model || '-' }}　SN：{{ deviceInfo.serial_no || '-' }}</div>
      <div class="device-line">位置：{{ deviceInfo.location || [deviceInfo.room, deviceInfo.rack_no].filter(Boolean).join(' / ') || '-' }}</div>
    </div>

    <!-- 故障描述 -->
    <div class="form-section">
      <label class="form-label">故障描述 *</label>
      <textarea
        v-model="form.fault_description"
        class="fault-input"
        placeholder="请描述故障现象..."
        rows="4"
      ></textarea>
    </div>

    <!-- 快捷选项 -->
    <div class="quick-options">
      <span class="option-label">常见故障：</span>
      <span
        v-for="opt in quickOptions"
        :key="opt"
        class="option-chip"
        @click="form.fault_description = opt"
      >{{ opt }}</span>
    </div>

    <!-- 拍照/相册（真实上传） -->
    <div class="media-toolbar">
      <div class="media-btn" @click="pickPhoto" :class="{ disabled: uploading }">
        <span>📷</span>
        <span>拍照</span>
      </div>
      <div class="media-btn" @click="pickPhoto" :class="{ disabled: uploading }">
        <span>🖼</span>
        <span>相册</span>
      </div>
    </div>
    <input ref="photoInput" type="file" accept="image/*" capture="environment" multiple
           style="display:none" @change="onPhotoPicked" />
    <div v-if="uploading" class="uploading-tip">照片上传中...</div>

    <!-- 媒体预览 -->
    <div class="media-preview" v-if="mediaList.length">
      <img v-for="(url, i) in mediaList" :key="i" :src="url" class="preview-img" />
    </div>

    <!-- 位置 -->
    <div class="form-section">
      <label class="form-label">故障位置</label>
      <input v-model="form.location" class="form-input" placeholder="点击自动定位" @focus="getLocation" />
    </div>

    <!-- 提交按钮 -->
    <button class="submit-btn" @click="handleSubmit" :disabled="submitting || !form.fault_description.trim()">
      {{ submitting ? '提交中...' : '提交工单' }}
    </button>

    <!-- 提交结果 -->
    <div v-if="result" class="result-card">
      <div class="result-icon">✓</div>
      <div class="result-title">上报成功</div>
      <div class="result-no">{{ result.work_order_no }}</div>
      <div class="result-msg">{{ result.message }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../../api'

const route = useRoute()

const form = reactive({
  device_code: '',
  device_id: null,
  fault_device_sn: '',
  fault_description: '',
  location: '',
  media: [],
})

const mediaList = ref([])
const photoInput = ref(null)
const uploading = ref(false)
const submitting = ref(false)
const currentUser = (() => {
  try { return JSON.parse(localStorage.getItem('current_user') || '{}') } catch { return {} }
})()
const result = ref(null)

const quickOptions = [
  'GPU 掉卡',
  'Xid 报错',
  'GPU 温度过高',
  '显存 ECC 错误',
  '训练任务失败',
  'IB 链路异常',
]

// 扫码报修：/m/report?device=EQ-001 直接带出设备
onMounted(async () => {
  const code = route.query.device || route.query.device_code
  if (!code) return
  form.device_code = String(code)
  try {
    const list = await request.get('/devices/', { params: { page: 1, page_size: 500 } })
    const dev = (list.items || []).find((d) => d.device_code === form.device_code)
    if (dev) {
      form.device_code = dev.device_code
      if (!form.location && dev.location) form.location = dev.location
    }
  } catch { /* 带不出信息不影响报修 */ }
})

// 扫码/输入设备编码 → 按编码或 SN 查设备档案，自动带出机房/机柜/型号/SN
const deviceInfo = ref(null)

const applyDevice = (d) => {
  if (!d) return
  deviceInfo.value = d
  form.device_code = d.device_code || ''
  if (d.id) form.device_id = d.id
  if (d.serial_no) form.fault_device_sn = d.serial_no
  const rack = [d.room, d.rack_no].filter(Boolean).join(' / ')
  if (!form.location) form.location = d.location || rack || ''
}

const handleScan = async () => {
  let code = ''
  try {
    const { value } = await ElMessageBox.prompt(
      '输入或扫描设备编码 / SN（设备资产标签上的二维码/条码）',
      '扫码识别服务器', { confirmButtonText: '查询', cancelButtonText: '取消', inputPlaceholder: '如 GPU-SRV-001' },
    )
    code = (value || '').trim()
  } catch { return }
  if (!code) return
  try {
    const d = await request.get(`/devices/by-code/${encodeURIComponent(code)}`)
    applyDevice(d)
    ElMessage.success(`已带出：${d.device_name || d.device_code}`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '未找到该设备，请核对编码/SN')
  }
}

const pickPhoto = () => {
  if (!uploading.value) photoInput.value?.click()
}

// 真实拍照/选图：先传 /upload/work-order-image，再把 URL 随工单提交
const onPhotoPicked = async (e) => {
  const files = Array.from(e.target.files || [])
  e.target.value = ''
  if (!files.length) return
  uploading.value = true
  try {
    for (const file of files) {
      const fd = new FormData()
      fd.append('file', file)
      const res = await request.post('/upload/work-order-image', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      mediaList.value.push(res.url)
      form.media.push(res.url)
    }
  } catch {
    ElMessage.error('照片上传失败，请重试')
  } finally {
    uploading.value = false
  }
}

const getLocation = () => {
  if (!navigator.geolocation) return
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude, longitude } = pos.coords
      form.location = `经纬度 ${latitude.toFixed(5)}, ${longitude.toFixed(5)}`
    },
    () => { /* 拒绝定位就留空，允许手填 */ },
    { timeout: 5000 },
  )
}

const handleSubmit = async () => {
  submitting.value = true
  try {
    const payload = {
      device_code: form.device_code,
      device_id: form.device_id,
      fault_device_sn: form.fault_device_sn,
      fault_description: form.fault_description,
      media: form.media,
      location: form.location,
      reporter_id: currentUser.id || undefined,
    }
    const res = await request.post('/m/v1/report', payload)
    result.value = res
    // 重置表单
    form.device_code = ''
    form.device_id = null
    form.fault_device_sn = ''
    form.fault_description = ''
    form.location = ''
    form.media = []
    mediaList.value = []
    deviceInfo.value = null
    // 3秒后隐藏结果
    setTimeout(() => { result.value = null }, 3000)
  } catch { /* handled */ }
  finally { submitting.value = false }
}
</script>

<style scoped>
.worker-submit { padding: 16px; }

.scan-area {
  background: linear-gradient(135deg, #14C8C4, #0AA9A5);
  border-radius: 12px;
  padding: 24px;
  text-align: center;
  color: #fff;
  cursor: pointer;
  margin-bottom: 16px;
}
.scan-icon { font-size: 36px; margin-bottom: 8px; }
.scan-text { font-size: 15px; opacity: 0.9; }
.scan-code { margin-top: 8px; font-size: 18px; font-weight: 600; font-family: monospace; }

.form-section { margin-bottom: 14px; }
.device-card { background: #fff; border-radius: 10px; padding: 12px 14px; margin-bottom: 14px; border-left: 3px solid #0FC6C2; }
.device-title { font-size: 14px; font-weight: 600; color: #1D2129; margin-bottom: 6px; }
.device-line { font-size: 12.5px; color: #86909C; line-height: 1.6; }
.form-label { display: block; font-size: 14px; font-weight: 500; color: #1D2129; margin-bottom: 6px; }
.fault-input {
  width: 100%; min-height: 100px; padding: 12px;
  border: 1px solid #D9D9D9; border-radius: 8px;
  font-size: 14px; resize: vertical; box-sizing: border-box;
  outline: none; transition: border-color .2s;
}
.fault-input:focus { border-color: #0FC6C2; }
.form-input {
  width: 100%; padding: 10px 12px;
  border: 1px solid #D9D9D9; border-radius: 8px;
  font-size: 14px; box-sizing: border-box; outline: none;
}
.form-input:focus { border-color: #0FC6C2; }

.quick-options { margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.option-label { font-size: 13px; color: #86909C; }
.option-chip {
  background: rgba(15, 198, 194, .12); color: #0FC6C2; padding: 4px 12px;
  border-radius: 16px; font-size: 13px; cursor: pointer;
}
.option-chip:active { background: #BCD1F0; }

.media-toolbar {
  display: flex; gap: 12px; margin-bottom: 16px;
}
.media-btn {
  flex: 1; text-align: center; padding: 14px 0;
  background: #fff; border: 1px dashed #D9D9D9;
  border-radius: 8px; cursor: pointer; font-size: 13px; color: #4E5969;
}
.media-btn span { display: block; }
.media-btn span:first-child { font-size: 24px; margin-bottom: 4px; }
.media-btn:active { background: #F5F6F8; }

.media-preview { display: flex; gap: 8px; margin-bottom: 16px; overflow-x: auto; }
.preview-img { width: 80px; height: 60px; border-radius: 6px; object-fit: cover; flex-shrink: 0; }

.submit-btn {
  width: 100%; padding: 14px; background: #0FC6C2; color: #fff;
  border: none; border-radius: 8px; font-size: 16px; font-weight: 500;
  cursor: pointer; margin-top: 8px;
}
.submit-btn:disabled { background: #C9CDD4; cursor: not-allowed; }
.submit-btn:active { opacity: 0.9; }

.result-card {
  margin-top: 16px; padding: 24px; background: #E8F8EE;
  border-radius: 12px; text-align: center;
}
.result-icon { font-size: 40px; color: #00B42A; margin-bottom: 8px; }
.result-title { font-size: 18px; font-weight: 600; color: #00B42A; margin-bottom: 8px; }
.result-no { font-size: 16px; font-weight: 600; color: #1D2129; font-family: monospace; }
.result-msg { font-size: 13px; color: #86909C; margin-top: 4px; }
</style>
