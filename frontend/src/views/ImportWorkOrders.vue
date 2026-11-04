<template>
  <div class="import-page">
    <div class="page-header">
      <h2>历史工单导入</h2>
      <span class="sub-title">支持 Excel/CSV 台账、PDF 工单、纸质工单拍照三种来源，解析后人工确认入库并收录知识库</span>
    </div>

    <!-- 上传区：三种导入方式 -->
    <el-card shadow="never" class="upload-card">
      <el-tabs v-model="importMode">
        <!-- Excel / CSV 台账 -->
        <el-tab-pane label="Excel 台账导入" name="EXCEL">
          <div class="excel-toolbar">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".xlsx,.xlsm,.csv"
              :on-change="handleExcelChange"
            >
              <el-button type="primary" plain :loading="excelInspecting">选择台账文件</el-button>
            </el-upload>
            <el-button link type="primary" @click="downloadTemplate">下载导入模板</el-button>
            <span v-if="excelFile" class="file-name">已选：{{ excelFile.name }}（{{ excelRowCount }} 行数据）</span>
          </div>

          <div v-if="excelHeaders.length" class="mapping-block">
            <div class="mapping-title">
              字段映射
              <span class="mapping-tip">系统已自动匹配 {{ mappedCount }} / {{ excelFields.length }} 个字段，可手动调整</span>
            </div>
            <el-table :data="excelFields" size="small" border max-height="300" class="mapping-table">
              <el-table-column label="系统字段" width="150">
                <template #default="{ row }">
                  {{ row.label }}
                  <el-tag v-if="row.required" type="danger" size="small" effect="plain">必填</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="对应台账列">
                <template #default="{ row }">
                  <el-select v-model="excelMapping[row.key]" clearable filterable size="small"
                             placeholder="不导入" style="width: 100%">
                    <el-option v-for="h in excelHeaders" :key="h" :label="h" :value="h" />
                  </el-select>
                </template>
              </el-table-column>
            </el-table>

            <div class="preview-title">前 5 行预览</div>
            <el-table :data="excelPreview" size="small" border max-height="220">
              <el-table-column v-for="h in excelHeaders" :key="h" :label="h" min-width="130" show-overflow-tooltip>
                <template #default="{ row }">{{ row[h] }}</template>
              </el-table-column>
            </el-table>

            <div class="upload-actions">
              <el-button type="primary" :loading="excelUploading" @click="handleExcelUpload">
                {{ excelUploading ? '导入中…' : `确认导入（${excelRowCount} 行）` }}
              </el-button>
              <el-button @click="resetExcel">取消</el-button>
            </div>
          </div>
          <el-empty v-else-if="!excelInspecting" description="选择 Excel/CSV 台账文件后自动识别表头，可手动调整字段映射"
                    :image-size="70" />
        </el-tab-pane>

        <!-- PDF 工单 -->
        <el-tab-pane label="PDF 工单导入" name="PDF">
          <el-upload
            drag
            multiple
            :auto-upload="false"
            :limit="50"
            accept=".pdf"
            :on-change="handleFileChange"
            :on-remove="handleFileRemove"
            :file-list="fileList"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽 PDF 到此处，或<em>点击选择文件</em>（支持多选）</div>
            <template #tip>
              <div class="el-upload__tip">仅支持 .pdf，单次最多 50 份；电子版自动提取文字，扫描件自动 OCR</div>
            </template>
          </el-upload>
          <div class="upload-actions">
            <el-button type="primary" :loading="uploading" :disabled="fileList.length === 0" @click="handleUpload">
              {{ uploading ? 'AI 解析抽取中…' : `开始导入（${fileList.length} 份）` }}
            </el-button>
            <el-button v-if="fileList.length" @click="fileList = []">清空</el-button>
          </div>
        </el-tab-pane>

        <!-- 图片 OCR -->
        <el-tab-pane label="图片 OCR 导入" name="IMAGE">
          <el-upload
            drag
            multiple
            :auto-upload="false"
            :limit="30"
            accept=".jpg,.jpeg,.png,.bmp,.webp"
            :on-change="handleImageChange"
            :on-remove="handleImageRemove"
            :file-list="imageList"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖拽工单照片/扫描件到此处，或<em>点击选择图片</em></div>
            <template #tip>
              <div class="el-upload__tip">
                支持 jpg/png/bmp/webp，单次最多 30 张；本地 OCR 识别（不需要联网），识别结果需人工核对
              </div>
            </template>
          </el-upload>
          <div class="upload-actions">
            <el-button type="primary" :loading="imageUploading" :disabled="imageList.length === 0" @click="handleImageUpload">
              {{ imageUploading ? 'OCR 识别中…' : `开始识别（${imageList.length} 张）` }}
            </el-button>
            <el-button v-if="imageList.length" @click="imageList = []">清空</el-button>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- Excel 逐行结果 -->
    <el-card v-if="excelResult" shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>台账导入结果：{{ excelResult.batch_no }}</span>
          <el-tag :type="excelResult.failed ? 'warning' : 'success'" size="small">
            待确认 {{ excelResult.pending }} 行 / 失败 {{ excelResult.failed }} 行
          </el-tag>
        </div>
      </template>
      <el-table :data="excelResult.results" size="small" max-height="260">
        <el-table-column prop="row_no" label="行号" width="80" />
        <el-table-column prop="work_order_no" label="工单号" width="160" />
        <el-table-column prop="fault_description" label="故障描述" min-width="220" show-overflow-tooltip />
        <el-table-column label="结果" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'PENDING' ? 'success' : 'danger'" size="small">
              {{ row.status === 'PENDING' ? '待确认' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>

    <!-- 上传批次结果 -->
    <el-card v-if="lastBatch" shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>批次结果：{{ lastBatch.batch_no }}</span>
          <el-tag :type="lastBatch.status === 'DONE' ? 'success' : 'warning'" size="small">
            {{ lastBatch.status === 'DONE' ? '全部完成' : '部分失败' }}
          </el-tag>
        </div>
      </template>
      <el-table :data="lastBatch.results" size="small" max-height="260">
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column label="结果" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === 'PENDING' ? 'success' : 'danger'" size="small">
              {{ row.status === 'PENDING' ? '待确认' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="说明" min-width="200" show-overflow-tooltip />
        <el-table-column prop="elapsed" label="耗时(s)" width="90" />
      </el-table>
    </el-card>

    <!-- 待确认清单 -->
    <el-card shadow="never" class="list-card">
      <template #header>
        <div class="card-header">
          <span>抽取记录</span>
          <el-radio-group v-model="activeTab" size="small" @change="loadItems">
            <el-radio-button value="PENDING">待确认（{{ countMap.PENDING ?? 0 }}）</el-radio-button>
            <el-radio-button value="CONFIRMED">已入库</el-radio-button>
            <el-radio-button value="REJECTED">已拒绝</el-radio-button>
            <el-radio-button value="ERROR">解析失败</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <el-table v-loading="loading" :data="items" size="small">
        <el-table-column label="文件 / 工单号" min-width="180">
          <template #default="{ row }">
            <div class="cell-main">{{ row.file_name }}</div>
            <div class="cell-sub">{{ row.extracted_data?.work_order_no || '—' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain"
                    :type="row.source === 'EXCEL' ? 'success' : row.source === 'IMAGE' ? 'warning' : 'info'">
              {{ row.source === 'EXCEL' ? 'Excel' : row.source === 'IMAGE' ? '图片' : 'PDF' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="原图" width="70">
          <template #default="{ row }">
            <img v-if="row.image_url" :src="row.image_url" class="thumb"
                 title="点击查看大图" @click="openPreview(row.image_url)" />
            <span v-else style="color: #C9CDD4">—</span>
          </template>
        </el-table-column>
        <el-table-column label="设备" width="120">
          <template #default="{ row }">{{ row.extracted_data?.device_code || '—' }}</template>
        </el-table-column>
        <el-table-column label="故障描述" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.extracted_data?.fault_description || '—' }}</template>
        </el-table-column>
        <el-table-column label="故障码" width="110">
          <template #default="{ row }">{{ row.extracted_data?.fault_code || '—' }}</template>
        </el-table-column>
        <el-table-column label="维修员" width="90">
          <template #default="{ row }">{{ row.extracted_data?.technician_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="工时" width="70">
          <template #default="{ row }">{{ row.extracted_data?.work_hours ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="校验" width="160">
          <template #default="{ row }">
            <el-tooltip v-if="row.validate_warnings?.length" :content="row.validate_warnings.join('；')" placement="top">
              <el-tag type="warning" size="small">⚠ {{ row.validate_warnings.length }} 项</el-tag>
            </el-tooltip>
            <el-tag v-else-if="row.status === 'PENDING'" type="success" size="small">通过</el-tag>
            <el-tag v-else-if="row.status === 'ERROR'" type="danger" size="small">失败</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="activeTab === 'CONFIRMED'" label="工单" width="170">
          <template #default="{ row }">
            <el-link type="primary" @click="goWorkOrder(row.work_order_id)">{{ row.work_order_id }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'PENDING'">
              <el-button type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button type="success" size="small" :loading="confirmingId === row.id" @click="confirmItem(row)">确认入库</el-button>
              <el-button size="small" @click="rejectItem(row)">拒绝</el-button>
            </template>
            <el-button v-else-if="row.status === 'ERROR' && activeTab === 'ERROR'" size="small" type="danger" plain
                       @click="showError(row)">查看原因</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && items.length === 0" description="暂无记录" :image-size="80" />
      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadItems"
        />
      </div>
    </el-card>

    <!-- 原图预览 -->
    <el-dialog v-model="previewVisible" title="原图查看" width="900px" append-to-body destroy-on-close>
      <div class="preview-wrap">
        <img v-if="previewUrl" :src="previewUrl" class="preview-img" />
      </div>
      <template #footer>
        <el-button v-if="previewUrl" type="primary" plain @click="openInNewTab(previewUrl)">新窗口打开</el-button>
        <el-button @click="previewVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editVisible" title="编辑抽取结果" width="720px" destroy-on-close>
      <div v-if="editWarnings.length" class="warn-box">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ editWarnings.join('；') }}</span>
      </div>
      <el-form label-width="90px" label-position="left" size="small">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="工单号"><el-input v-model="form.work_order_no" placeholder="留空自动生成" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="设备编码"><el-input v-model="form.device_code" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="故障描述">
          <el-input v-model="form.fault_description" type="textarea" :rows="2" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="故障码"><el-input v-model="form.fault_code" placeholder="6位数字，多个逗号分隔" /></el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="优先级">
              <el-select v-model="form.priority" style="width: 100%">
                <el-option label="低" value="LOW" /><el-option label="中" value="MEDIUM" />
                <el-option label="高" value="HIGH" /><el-option label="紧急" value="CRITICAL" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="工时"><el-input-number v-model="form.work_hours" :min="0" :step="0.5" style="width: 100%" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="维修员"><el-input v-model="form.technician_name" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="报修人"><el-input v-model="form.reporter_name" /></el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="报修时间"><el-input v-model="form.start_time" placeholder="YYYY-MM-DD HH:MM" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="完工时间"><el-input v-model="form.end_time" placeholder="YYYY-MM-DD HH:MM" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="位置"><el-input v-model="form.location" /></el-form-item>
        <el-form-item label="故障大类"><el-input v-model="form.fault_category" /></el-form-item>
        <el-form-item label="故障现象"><el-input v-model="form.fault_phenomenon" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="根本原因"><el-input v-model="form.root_cause" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="解决步骤"><el-input v-model="form.solution_steps" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="维修结果">
          <el-select v-model="form.repair_result" style="width: 100%">
            <el-option label="彻底修复" value="PERMANENT_FIX" />
            <el-option label="临时处理" value="TEMPORARY_FIX" />
            <el-option label="无法修复" value="UNABLE_FIX" />
          </el-select>
        </el-form-item>
        <el-form-item label="备件(JSON)">
          <el-input v-model="form.used_parts_text" type="textarea" :rows="2" placeholder='[{"name": "保险丝", "count": 2}]' />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import request from '../api'

const router = useRouter()
const fileList = ref([])
const uploading = ref(false)
const lastBatch = ref(null)
const activeTab = ref('PENDING')
const items = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const countMap = reactive({})
const confirmingId = ref(null)
const editVisible = ref(false)
const saving = ref(false)
const editWarnings = ref([])
const form = reactive({})

// ---- 原图预览 ----
const previewVisible = ref(false)
const previewUrl = ref('')
function openPreview(url) {
  previewUrl.value = url
  previewVisible.value = true
}
function openInNewTab(url) {
  window.open(url, '_blank')
}

// ---- Excel 台账导入 ----
const importMode = ref('EXCEL')
const excelFile = ref(null)
const excelInspecting = ref(false)
const excelUploading = ref(false)
const excelHeaders = ref([])
const excelPreview = ref([])
const excelFields = ref([])
const excelMapping = reactive({})
const excelRowCount = ref(0)
const excelResult = ref(null)
const mappedCount = computed(() => Object.values(excelMapping).filter(Boolean).length)

async function downloadTemplate() {
  try {
    const blob = await request.get('/work-order-imports/template', { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = '工单导入模板.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    // 拦截器已提示
  }
}

async function handleExcelChange(file) {
  excelFile.value = file.raw
  excelInspecting.value = true
  excelResult.value = null
  try {
    const fd = new FormData()
    fd.append('file', file.raw)
    const res = await request.post('/work-order-imports/excel/inspect', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000
    })
    excelHeaders.value = res.headers
    excelPreview.value = res.preview
    excelFields.value = res.fields
    excelRowCount.value = res.row_count
    Object.keys(excelMapping).forEach((k) => delete excelMapping[k])
    Object.assign(excelMapping, res.mapping)
    if (!mappedCount.value) ElMessage.warning('未能自动识别表头，请手动选择对应列')
  } catch (e) {
    resetExcel()
  } finally {
    excelInspecting.value = false
  }
}

function resetExcel() {
  excelFile.value = null
  excelHeaders.value = []
  excelPreview.value = []
  excelFields.value = []
  excelRowCount.value = 0
  Object.keys(excelMapping).forEach((k) => delete excelMapping[k])
}

async function handleExcelUpload() {
  if (!excelFile.value) return
  const mapping = {}
  Object.entries(excelMapping).forEach(([k, v]) => { if (v) mapping[k] = v })
  excelUploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', excelFile.value)
    fd.append('mapping', JSON.stringify(mapping))
    const res = await request.post('/work-order-imports/upload-excel', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000
    })
    excelResult.value = res
    ElMessage.success(`导入完成：${res.pending} 行待确认${res.failed ? `，${res.failed} 行失败` : ''}`)
    resetExcel()
    loadItems()
  } catch (e) {
    // 拦截器已提示
  } finally {
    excelUploading.value = false
  }
}

// ---- 图片 OCR 导入 ----
const imageList = ref([])
const imageUploading = ref(false)

function handleImageChange(file) {
  imageList.value = [...imageList.value, file]
}
function handleImageRemove(file) {
  imageList.value = imageList.value.filter((f) => f.uid !== file.uid)
}

async function handleImageUpload() {
  if (!imageList.value.length) return
  const fd = new FormData()
  for (const f of imageList.value) fd.append('files', f.raw)
  imageUploading.value = true
  try {
    const res = await request.post('/work-order-imports/upload-images', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 600000
    })
    lastBatch.value = {
      batch_no: res.batch_no,
      status: res.failed ? 'PARTIAL' : 'DONE',
      results: res.results.map((r) => ({
        file_name: r.file_name,
        status: r.status,
        message: r.message,
        elapsed: ''
      })),
      total_pending: res.pending,
      failed: res.failed
    }
    ElMessage.success(`识别完成：${res.pending} 张待确认${res.failed ? `，${res.failed} 张失败` : ''}`)
    imageList.value = []
    loadItems()
  } catch (e) {
    // 拦截器已提示
  } finally {
    imageUploading.value = false
  }
}

function handleFileChange(file) {
  if (file.raw && file.raw.type !== 'application/pdf' && !file.raw.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.error(`「${file.name}」不是 PDF 文件`)
    fileList.value = fileList.value.filter((f) => f.uid !== file.uid)
  }
}
function handleFileRemove(file) {
  fileList.value = fileList.value.filter((f) => f.uid !== file.uid)
}

async function handleUpload() {
  if (!fileList.value.length) return
  const fd = new FormData()
  for (const f of fileList.value) fd.append('files', f.raw)
  uploading.value = true
  try {
    // 解析+LLM 抽取较耗时，放宽超时
    const res = await request.post('/work-order-imports/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 600000
    })
    lastBatch.value = res
    ElMessage.success(`导入完成：${res.total_pending} 份待确认${res.failed ? `，${res.failed} 份失败` : ''}`)
    fileList.value = []
    loadItems()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '导入失败')
  } finally {
    uploading.value = false
  }
}

async function loadItems() {
  loading.value = true
  try {
    const res = await request.get('/work-order-imports/items', {
      params: { status: activeTab.value, page: page.value, page_size: pageSize }
    })
    items.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function openEdit(row) {
  editWarnings.value = row.validate_warnings || []
  const d = row.extracted_data || {}
  Object.keys(form).forEach((k) => delete form[k])
  Object.assign(form, {
    ...d,
    used_parts_text: d.used_parts ? JSON.stringify(d.used_parts, null, 0) : ''
  })
  editRowId = row.id
  editVisible.value = true
}
let editRowId = null

async function saveEdit() {
  saving.value = true
  try {
    const data = { ...form }
    delete data.used_parts_text
    if (form.used_parts_text && form.used_parts_text.trim()) {
      try {
        data.used_parts = JSON.parse(form.used_parts_text)
      } catch (e) {
        ElMessage.error('备件 JSON 格式不正确')
        saving.value = false
        return
      }
    }
    await request.put(`/work-order-imports/items/${editRowId}`, { extracted_data: data })
    ElMessage.success('已保存')
    editVisible.value = false
    loadItems()
  } finally {
    saving.value = false
  }
}

async function confirmItem(row) {
  try {
    await ElMessageBox.confirm(
      `确认将「${row.file_name}」写入工单并收录知识库吗？入库后工单为已归档状态。`,
      '确认入库',
      { confirmButtonText: '确认入库', cancelButtonText: '取消', type: 'warning' }
    )
  } catch (e) {
    return
  }
  confirmingId.value = row.id
  try {
    const res = await request.post(`/work-order-imports/items/${row.id}/confirm`)
    ElMessage.success(res.message)
    loadItems()
  } finally {
    confirmingId.value = null
  }
}

async function rejectItem(row) {
  try {
    await ElMessageBox.confirm(`确定拒绝「${row.file_name}」吗？`, '拒绝记录', { type: 'warning' })
  } catch (e) {
    return
  }
  await request.post(`/work-order-imports/items/${row.id}/reject`)
  ElMessage.success('已拒绝')
  loadItems()
}

function showError(row) {
  ElMessageBox.alert(row.error_message || '未知错误', '解析失败原因')
}

function goWorkOrder(id) {
  if (id) router.push(`/work-orders/${id}`)
}

// 各状态数量
async function loadCounts() {
  try {
    const res = await request.get('/work-order-imports/items', { params: { status: 'PENDING', page: 1, page_size: 1 } })
    countMap.PENDING = res.total
  } catch (e) { /* 忽略 */ }
}

onMounted(() => {
  loadItems()
  loadCounts()
})
</script>

<style scoped>
.import-page { padding: 20px; }
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px; font-size: 20px; color: #1D2129; }
.sub-title { color: #86909C; font-size: 13px; }
.upload-card { margin-bottom: 16px; }
.upload-actions { margin-top: 12px; display: flex; gap: 8px; }
.excel-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.file-name { color: #4E5969; font-size: 13px; }
.mapping-block { margin-top: 16px; }
.mapping-title { font-size: 14px; font-weight: 500; color: #1D2129; margin-bottom: 8px; }
.mapping-tip { font-size: 12px; color: #86909C; font-weight: 400; margin-left: 8px; }
.mapping-table { margin-bottom: 16px; }
.preview-title { font-size: 14px; font-weight: 500; color: #1D2129; margin: 4px 0 8px; }
.result-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.list-card { margin-bottom: 16px; }
.cell-main { color: #1D2129; }
.cell-sub { color: #86909C; font-size: 12px; }
.warn-box { background: #FFF7E6; border: 1px solid #FFD666; color: #D46B08; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px; display: flex; align-items: center; gap: 6px; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
.thumb { width: 40px; height: 40px; object-fit: cover; border-radius: 4px; border: 1px solid #E5E6EB; cursor: zoom-in; }
.preview-wrap { display: flex; justify-content: center; max-height: 70vh; overflow: auto; }
.preview-img { max-width: 100%; max-height: 68vh; object-fit: contain; border-radius: 4px; }
</style>
