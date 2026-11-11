<template>
  <div class="page">
    <!-- 查看模式 -->
    <template v-if="isViewMode && form.work_order_no">
      <!-- SLA / 成本 / 评价 概览条（查看态也给） -->
      <div class="sla-bar">
        <el-tag :type="slaTagType" size="small" effect="light">{{ slaText }}</el-tag>
        <span class="sla-item" v-if="form.response_due_at">响应截止 {{ fmt(form.response_due_at) }}</span>
        <span class="sla-item" v-if="form.resolve_due_at">修复截止 {{ fmt(form.resolve_due_at) }}</span>
        <el-tooltip placement="bottom" effect="dark" raw-content>
          <template #content>
            响应/修复截止 = 创建时间 + 优先级时限<br />
            紧急 2/8h、高 4/24h、中 8/48h、低 24/72h<br />
            客户合同时限优先；挂起时长在恢复时自动顺延截止时间
          </template>
          <el-icon class="sla-help"><QuestionFilled /></el-icon>
        </el-tooltip>
        <template v-if="canSeeCost && hasCost">
          <el-divider direction="vertical" />
          <span class="sla-item">人工 <b>{{ money(form.labor_cost) }}</b></span>
          <span class="sla-item">备件 <b>{{ money(form.parts_cost) }}</b></span>
          <span class="sla-item">合计 <b class="sla-total">{{ money(form.total_cost) }}</b></span>
        </template>
        <template v-if="form.satisfaction_score">
          <el-divider direction="vertical" />
          <span class="sla-item">满意度 <b>{{ form.satisfaction_score }} 分</b>
            <span v-if="form.satisfaction_comment" class="sla-comment">「{{ form.satisfaction_comment }}」</span>
          </span>
        </template>
      </div>
      <el-card shadow="never" class="detail-card">
        <div class="detail-header">
          <div class="head-left">
            <h3>{{ form.work_order_no }}</h3>
            <el-tag :type="statusTagType" size="small" effect="light" class="status-pill">{{ statusGroupLabel }}</el-tag>
            <el-tag v-if="form.is_on_hold" type="warning" effect="light" size="small">挂起 · {{ holdLabel }}</el-tag>
            <el-tag v-if="form.transfer_from_name" type="warning" effect="plain" size="small">转派自 {{ form.transfer_from_name }}</el-tag>
          </div>
          <div class="head-right">
            <div class="wo-actions">
              <el-button
                v-if="['SUBMITTED', 'ASSIGNED', 'ACCEPTED', 'ARRIVED', 'INSPECTING'].includes(form.status) && canDispatch"
                type="primary" plain size="small" @click="openDispatch"
              >{{ form.status === 'SUBMITTED' ? '派工' : '改派' }}</el-button>
              <el-button
                v-if="form.status === 'SUBMITTED' && canClaim"
                type="primary" size="small" :loading="claiming" @click="claimTask"
              >领取任务</el-button>
              <el-button
                v-if="['ASSIGNED', 'ACCEPTED', 'ARRIVED', 'INSPECTING'].includes(form.status) && isMyTask && !canDispatch"
                plain size="small" @click="openDispatch"
              >转派</el-button>
              <el-button
                v-if="form.status === 'ASSIGNED' && isMyTask && !canDispatch"
                type="primary" size="small" :loading="accepting" @click="acceptAssignment"
              >接受</el-button>
              <el-button
                v-if="form.status === 'ASSIGNED' && isMyTask && !canDispatch"
                type="danger" plain size="small" @click="rejectAssignment"
              >拒收</el-button>
              <el-button
                v-if="['ACCEPTED', 'ARRIVED', 'INSPECTING'].includes(form.status) && (isMyTask || canDispatch)"
                type="primary" size="small" :loading="starting" @click="startProcessing"
              >{{ startActionLabel }}</el-button>
              <el-button
                v-if="['ARCHIVING', 'COMPLETED'].includes(form.status) && (isMyTask || isAdminUser)"
                type="primary" size="small" :loading="archiving" @click="openArchiveDialog"
              >归档</el-button>
              <el-button
                v-if="canHold"
                size="small" :type="form.is_on_hold ? 'success' : 'warning'" plain
                :loading="holdSaving" @click="onHoldAction"
              >{{ form.is_on_hold ? '恢复处理' : '挂起' }}</el-button>
              <el-button v-if="canRma" plain size="small" @click="openRma">RMA</el-button>
              <el-button
                v-if="canCompleteRepair"
                type="primary" size="small" @click="goEdit"
              >填写结果并完成</el-button>
              <el-button
                v-if="canEditWorkOrder && form.status !== 'IN_PROGRESS'"
                plain size="small" @click="goEdit"
              >编辑</el-button>
              <span class="wo-actions-sep"></span>
              <el-button plain size="small" :loading="printing" @click="printPdf">打印 / PDF</el-button>
            </div>
          </div>
        </div>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="故障描述" :span="2">{{ form.fault_description || '-' }}</el-descriptions-item>
          <el-descriptions-item v-if="displayFaultCodes" label="故障码">{{ displayFaultCodes }}</el-descriptions-item>
          <el-descriptions-item v-if="form.customer_name" label="客户">
            {{ form.customer_name }}<span v-if="form.customer_company">（{{ form.customer_company }}）</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.customer_site_name || form.customer_address" label="机房 / 地址">
            {{ form.customer_site_name || '—' }}
            <span v-if="form.customer_address" class="hint"> · {{ form.customer_address }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.customer_phone" label="客户电话">{{ form.customer_phone }}</el-descriptions-item>
          <el-descriptions-item v-if="form.customer_contact_name" label="报修联系人">
            {{ form.customer_contact_name }}
            <span v-if="form.customer_contact_phone"> · {{ form.customer_contact_phone }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.device_error_code" label="Xid/错误码">{{ form.device_error_code }}</el-descriptions-item>
          <template v-if="form.device_id">
            <el-descriptions-item label="服务器">
              <div style="display:flex;align-items:center;gap:8px">
                <span>{{ deviceName }}</span>
                <el-tag :type="devStatusTagType(selectedDevice?.run_status)" size="small" effect="dark" round>
                  {{ devStatusLabel(selectedDevice?.run_status) }}
                </el-tag>
                <el-tag v-if="selectedDevice?.fault_tags && selectedDevice.fault_tags.length" size="small" type="danger" effect="light">
                  {{ selectedDevice.fault_tags.length }} 项故障标签
                </el-tag>
              </div>
            </el-descriptions-item>
          </template>
          <el-descriptions-item v-if="form.device_type" label="服务器类型">{{ form.device_type }}</el-descriptions-item>
          <el-descriptions-item v-if="form.location" label="机房位置">{{ form.location }}</el-descriptions-item>
          <el-descriptions-item v-if="form.fault_object" label="涉及对象">{{ form.fault_object }}</el-descriptions-item>
          <el-descriptions-item v-if="form.fault_category" label="故障类别">{{ form.fault_category }}</el-descriptions-item>
          <el-descriptions-item v-if="form.fault_phenomenon_type" label="故障现象分类">{{ form.fault_phenomenon_type }}</el-descriptions-item>
          <el-descriptions-item v-if="form.gpu_index" label="故障 GPU">{{ form.gpu_index }}</el-descriptions-item>
          <el-descriptions-item v-if="form.fault_device_sn" label="故障件 SN">{{ form.fault_device_sn }}</el-descriptions-item>
          <el-descriptions-item label="服务方式">
            {{ { REMOTE: '远程处理', SITE: '现场处理', RMA: '返厂维修', VENDOR: '第三方现场' }[form.service_mode] || '待确认' }}
            <el-tag v-if="form.need_rma" size="small" type="warning" style="margin-left:6px">需返厂</el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.customer_id" label="客户验收">
            <el-tag v-if="form.customer_accept_status === 'ACCEPTED'" size="small" type="success">已确认解决</el-tag>
            <el-tag v-else-if="form.customer_accept_status === 'REJECTED'" size="small" type="danger">客户反馈未解决</el-tag>
            <el-tag v-else size="small" type="warning">待客户确认</el-tag>
            <span v-if="form.customer_accept_at" class="hint" style="margin-left:6px">
              {{ dayjs(form.customer_accept_at).format('MM-DD HH:mm') }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.is_on_hold || form.hold_total_minutes" label="挂起">
            <el-tag v-if="form.is_on_hold" size="small" type="warning">挂起中 · {{ holdLabel }}</el-tag>
            <span v-else class="hint">累计 {{ form.hold_total_minutes || 0 }} 分钟</span>
            <span v-if="form.hold_remark" class="hint" style="margin-left:6px">{{ form.hold_remark }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.rma_vendor || form.rma_no" label="RMA">
            {{ form.rma_vendor || '-' }} / {{ form.rma_no || '-' }} / {{ rmaStatusLabel(form.rma_status) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="form.reporter_name || form.created_by_name || form.customer_id" label="报修人">
            <template v-if="form.reporter_name || form.created_by_name">
            {{ form.reporter_name || form.created_by_name }}
            <span v-if="!form.reporter_name && form.created_by_department" class="hint"> · {{ form.created_by_department }}</span>
            </template>
            <span v-else>{{ form.customer_contact_name || form.customer_name }}<span class="hint"> · 客户</span></span>
            <el-tag v-if="form.reporter_name && form.created_by_name && form.reporter_name !== form.created_by_name"
                    size="small" type="info" effect="plain" style="margin-left:6px">
              代报：{{ form.created_by_name }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="claimTime" label="领取时间">{{ fmt(claimTime) }}</el-descriptions-item>
          <el-descriptions-item v-if="technicianName && technicianName !== '-'" label="技术员">{{ technicianName }}</el-descriptions-item>
          <el-descriptions-item v-if="form.fault_phenomenon" label="故障现象" :span="2">
            <pre class="detail-pre">{{ form.fault_phenomenon }}</pre>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.root_cause_type" label="根本原因分类">{{ form.root_cause_type }}</el-descriptions-item>
          <el-descriptions-item v-if="form.repair_result" label="维修结果">
            <el-tag :type="repairResultTagType" size="small">{{ repairResultLabel }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.root_cause" label="原因分析" :span="2">
            <pre class="detail-pre">{{ form.root_cause }}</pre>
          </el-descriptions-item>
          <el-descriptions-item v-if="form.solution_steps" label="处理步骤" :span="2">
            <pre class="detail-pre">{{ form.solution_steps }}</pre>
          </el-descriptions-item>
          <template v-if="form.repair_result === 'TEMPORARY_FIX'">
            <el-descriptions-item label="后续计划" :span="2">
              <pre class="detail-pre">{{ form.follow_up_plan || '-' }}</pre>
            </el-descriptions-item>
          </template>
          <el-descriptions-item v-if="form.work_hours != null" label="工时（小时）">{{ form.work_hours.toFixed(1) }}</el-descriptions-item>
          <el-descriptions-item v-if="form.collaborators && form.collaborators.length" label="协作人" :span="2">
            {{ form.collaborators.map(c => c.name).join('、') }}
          </el-descriptions-item>
        </el-descriptions>

        <!-- 处理进度：左列时间轴 + 状态胶囊，当前节点单独标记 -->
        <div v-if="progressRows.length" class="wo-block">
          <div class="wo-block-title">
            处理进度
            <span class="wo-block-count">{{ progressRows.length }}</span>
          </div>
          <div class="wo-timeline">
            <!-- 记录多时默认只显示最近 8 条，避免把下面的附件区挤到很远 -->
            <div v-if="progressRows.length > TL_MAX" class="wo-tl-fold">
              <el-button link type="primary" size="small" @click="tlExpanded = !tlExpanded">
                {{ tlExpanded ? '收起，只看最近 ' + TL_MAX + ' 条' : '更早的 ' + (progressRows.length - TL_MAX) + ' 条已折叠，展开' }}
              </el-button>
            </div>
            <template v-for="lg in tlRows" :key="lg.id">
              <div v-if="lg._date" class="wo-tl-date"><span>{{ lg._date }}</span></div>
              <div class="wo-tl-item" :class="{ 'is-last': lg._isLast }">
                <div class="wo-tl-time" :title="fmtFull(lg.created_at)">{{ lg._time }}</div>
                <div class="wo-tl-axis">
                  <span
                    class="wo-tl-dot"
                    :class="['tl-' + tlTone(lg.to_status), { 'is-now': lg._isLast, 'is-same': lg._noChange }]"
                  ></span>
                </div>
                <div class="wo-tl-body">
                  <div class="wo-tl-line">
                    <span
                      class="wo-tl-pill"
                      :class="['tl-pill-' + tlTone(lg.to_status), { 'is-same': lg._noChange }]"
                    >
                      {{ statusMap[lg.to_status] || lg.to_status }}
                    </span>
                    <span v-if="lg._isLast" class="wo-tl-now">当前</span>
                    <span class="wo-tl-who">
                      <span class="wo-tl-actor">{{ lg.operator_name || '系统' }}</span>
                      <span class="wo-tl-sep">·</span>
                      <span>{{ sourceLabel(lg.source) }}</span>
                    </span>
                    <span v-if="lg._delta" class="wo-tl-delta" title="距上一步">{{ lg._delta }}</span>
                  </div>
                  <div v-if="lg.remark" class="wo-tl-remark">{{ lg.remark }}</div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- 现场照片 / 附件：汇总报修附件、处理附件、各节点上传的附件（始终可见，无附件给空态） -->
        <div class="wo-block">
          <div class="wo-block-title">
            现场照片 / 附件
            <span v-if="allAttachments.length" class="wo-block-count">{{ allAttachments.length }}</span>
            <el-button
              v-if="canEditWorkOrder" link type="primary" class="wo-block-action"
              @click="openUploadDialog"
            >上传附件</el-button>
          </div>
          <div v-if="!allAttachments.length" class="wo-attach-empty">
            暂无附件。点右上角「上传附件」直接传照片/视频（单文件 ≤ 50MB），也可以点「编辑」在表单里批量补。
          </div>
          <div v-else class="wo-attach-grid">
            <div v-for="(f, i) in allAttachments" :key="i" class="wo-attach-item">
              <img
                v-if="isImageFile(f)" :src="f.url" class="wo-attach-thumb wo-attach-clickable"
                title="点击查看大图" @click="openPreview(f.url)"
              />
              <video v-else :src="f.url" class="wo-attach-thumb" controls preload="metadata" />
              <div class="wo-attach-meta">
                <span class="wo-attach-name" :title="f.name">{{ f.name }}</span>
                <span v-if="f.stage" class="wo-attach-stage">{{ f.stage }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 领用备件（有才显示） -->
        <div v-if="usedParts.length" class="wo-block">
          <div class="wo-block-title">领用备件</div>
          <div class="wo-parts">
            <div v-for="(p, i) in usedParts" :key="i" class="wo-part-item">
              <span class="wo-part-name">{{ p.name }}</span>
              <span v-if="p.code" class="wo-part-code">{{ p.code }}</span>
              <span class="wo-part-count">× {{ p.count }}</span>
              <span v-if="canSeeCost && p.unit_price != null" class="wo-part-price">单价 {{ money(p.unit_price) }}</span>
            </div>
          </div>
        </div>

        <!-- 关键时间：创建 / 派单 / 领取 / 开始 / 完成（截止时间见顶部 SLA 条，不重复） -->
        <el-descriptions :column="timeColCount" border size="small" class="time-desc">
          <el-descriptions-item label="创建时间">{{ fmtFull(form.created_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="form.dispatched_at" label="派单时间">{{ fmtFull(form.dispatched_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="claimTime || form.status === 'ASSIGNED'" label="领取/接单">
            {{ claimTime ? fmtFull(claimTime) : '待接受' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="form.start_time" label="开始维修">{{ fmtFull(form.start_time) }}</el-descriptions-item>
          <el-descriptions-item v-if="form.resolved_at" label="完成时间">{{ fmtFull(form.resolved_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="form.hold_total_minutes" label="挂起累计">
            {{ form.hold_total_minutes }} 分钟
          </el-descriptions-item>
        </el-descriptions>
        <div class="detail-footer">
          <el-button plain @click="goBackToList">{{ backLabel }}</el-button>
        </div>
      </el-card>

      <!-- 修改记录（已归档工单的管理员修改审计） -->
      <el-card v-if="editLogs.length" shadow="never" class="section-card edit-log-card">
        <div class="edit-log-title">修改记录</div>
        <div v-for="log in editLogs" :key="log.id" class="edit-log-item">
          <div class="edit-log-head">
            <span class="edit-log-editor">{{ log.editor_name || '管理员' }}</span>
            <span class="edit-log-time">{{ fmt(log.created_at) }}</span>
          </div>
          <div v-for="(val, key) in log.changes" :key="key" class="edit-log-change">
            <span class="edit-log-key">{{ key }}</span>
            <span class="edit-log-before">{{ auditText(val.before) }}</span>
            <span class="edit-log-arrow">→</span>
            <span class="edit-log-after">{{ auditText(val.after) }}</span>
          </div>
        </div>
      </el-card>
    </template>

    <!-- 派工 -->
    <el-dialog v-model="dispatchDlg.visible" :title="dispatchTitle" width="460px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="维修员" required>
          <el-select v-model="dispatchDlg.technicianId" filterable placeholder="选择维修员" style="width:100%">
            <el-option v-for="t in dispatchDlg.technicians" :key="t.id"
                       :label="`${t.real_name}（在办 ${t.current_workload_count} · 近7天完成 ${t.recent7d_completed}）`"
                       :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="协作人">
          <el-select v-model="dispatchDlg.collaboratorIds" multiple filterable placeholder="可选，多人一起处理时选择" style="width:100%">
            <el-option v-for="t in dispatchDlg.technicians" :key="t.id"
                       :label="t.real_name" :value="t.id"
                       :disabled="t.id === dispatchDlg.technicianId" />
          </el-select>
        </el-form-item>
        <el-form-item :label="dispatchNeedsReason ? '改派原因' : '备注'" :required="dispatchNeedsReason">
          <el-input v-model="dispatchDlg.remark" type="textarea" :rows="2" maxlength="100"
                    :placeholder="dispatchNeedsReason ? '必填，例如：维修员不熟悉该设备/临时请假' : '选填'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dispatchDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="dispatchDlg.saving" @click="submitDispatch">{{ dispatchTitle === '转派工单' ? '确认转派' : (form.status === 'SUBMITTED' ? '确认派工' : '确认改派') }}</el-button>
      </template>
    </el-dialog>

    <!-- 报修人评价 -->
    <el-dialog v-model="feedbackVisible" title="报修人回访评价" width="460px" append-to-body>
      <el-form label-width="70px">
        <el-form-item label="满意度">
          <el-rate v-model="feedbackScore" :max="5" show-score score-template="{value} 分" />
        </el-form-item>
        <el-form-item label="意见">
          <el-input v-model="feedbackComment" type="textarea" :rows="3" maxlength="200" show-word-limit
                    placeholder="选填，例如：响应快 / 备件等太久" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="feedbackVisible = false">取消</el-button>
        <el-button type="primary" :loading="feedbackSaving" @click="submitFeedback">提交评价</el-button>
      </template>
    </el-dialog>

    <!-- 附件原图预览 -->
    <el-dialog v-model="previewVisible" title="附件查看" width="900px" append-to-body destroy-on-close>
      <div class="preview-wrap">
        <img v-if="previewUrl" :src="previewUrl" class="preview-img" />
      </div>
      <template #footer>
        <el-button v-if="previewUrl" type="primary" plain @click="openInNewTab(previewUrl)">新窗口打开</el-button>
        <el-button @click="previewVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 查看页直接上传附件：独立小弹窗，不必进整页编辑态（原「去上传」只是跳编辑页，等于没做的事） -->
    <el-dialog v-model="uploadDialog.visible" title="上传现场附件" width="560px" append-to-body destroy-on-close>
      <div class="up-dialog">
        <el-upload
          drag
          multiple
          :show-file-list="false"
          :http-request="uploadOne"
          :before-upload="beforeUpload"
          accept=".jpg,.jpeg,.png,.gif,.mp4,.mov,.avi,.webm"
        >
          <el-icon class="up-icon"><UploadFilled /></el-icon>
          <div class="up-text">把照片拖到这里，或<em>点击选择</em></div>
          <div class="up-sub">JPG / PNG / GIF / MP4，单文件 ≤ 50MB，可多选</div>
        </el-upload>
        <div class="up-note">
          选完即上传并挂到本工单，<b>不需要再点保存</b>。
          <span v-if="uploadDialog.count" class="up-done">本次已上传 {{ uploadDialog.count }} 个</span>
          <span v-if="uploadDialog.busy" class="up-busy">上传中 {{ uploadDialog.busy }} 个…</span>
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="uploadDialog.visible = false">完成</el-button>
      </template>
    </el-dialog>

    <!-- 编辑模式 -->
    <template v-if="!isViewMode">
      <div class="work-order-form-head">
        <div class="head-left">
          <h3 class="work-order-form-title">{{ isNew ? '新增工单' : (form.work_order_no || '编辑工单') }}</h3>
          <el-tag v-if="!isNew" :type="statusTagType" size="small">{{ statusGroupLabel }}</el-tag>
          <el-tag v-if="form.is_on_hold" type="warning" effect="dark" size="small">挂起 · {{ holdLabel }}</el-tag>
          <span v-if="form.customer_id" class="head-meta">
            {{ form.customer_company || form.customer_name }}
            <span v-if="form.customer_site_name"> · {{ form.customer_site_name }}</span>
          </span>
          <span v-if="form.technician_name || form.technician?.real_name" class="head-meta">
            负责人：{{ form.technician_name || form.technician?.real_name }}
          </span>
        </div>
        <div class="work-order-form-actions">
          <div class="wo-actions">
            <el-button
              v-if="['SUBMITTED','ASSIGNED','ACCEPTED','ARRIVED','INSPECTING'].includes(form.status) && canDispatch"
              type="primary" plain size="small" @click="openDispatch"
            >{{ form.status === 'SUBMITTED' ? '派工' : '改派' }}</el-button>
            <el-button v-if="form.status === 'SUBMITTED' && canClaim" type="primary" size="small"
                       :loading="claiming" @click="claimTask">领取任务</el-button>
            <el-button v-if="['ASSIGNED','ACCEPTED','ARRIVED','INSPECTING'].includes(form.status) && isMyTask && !canDispatch"
                       plain size="small" @click="openDispatch">转派</el-button>
            <template v-if="form.status === 'ASSIGNED' && isMyTask && !canDispatch">
              <el-button type="primary" size="small" :loading="accepting" @click="acceptAssignment">接受</el-button>
              <el-button type="danger" plain size="small" @click="rejectAssignment">拒收</el-button>
            </template>
            <el-button v-if="['ACCEPTED','ARRIVED','INSPECTING'].includes(form.status) && (isMyTask || canDispatch)"
                       type="primary" size="small" :loading="starting" @click="startProcessing">
              {{ startActionLabel }}
            </el-button>
            <el-button v-if="canHold" size="small" :type="form.is_on_hold ? 'success' : 'warning'" plain
                       :loading="holdSaving" @click="onHoldAction">{{ form.is_on_hold ? '恢复处理' : '挂起' }}</el-button>
            <el-button v-if="canRma" size="small" plain @click="openRma">RMA</el-button>
            <el-button v-if="isNew" plain size="small" @click="viewDrafts">历史草稿</el-button>
            <span class="wo-actions-sep"></span>
            <el-button plain size="small" @click="goBackToList">{{ backLabel }}</el-button>
          </div>
        </div>
      </div>

      <el-alert
        v-if="!isNew && form.status === 'ARCHIVED'"
        type="warning" :closable="false" show-icon
        title="该工单已归档，保存的修改会写入「修改记录」留痕"
        style="margin-bottom:12px"
      />

      <!-- SLA / 成本 / 评价 概览条 -->
      <div v-if="!isNew" class="sla-bar">
        <el-tag :type="slaTagType" size="small" effect="light">{{ slaText }}</el-tag>
        <span class="sla-item" v-if="form.response_due_at">响应截止 {{ fmt(form.response_due_at) }}</span>
        <span class="sla-item" v-if="form.resolve_due_at">修复截止 {{ fmt(form.resolve_due_at) }}</span>
        <template v-if="canSeeCost && hasCost">
          <el-divider direction="vertical" />
          <span class="sla-item">人工 <b>{{ money(form.labor_cost) }}</b></span>
          <span class="sla-item">备件 <b>{{ money(form.parts_cost) }}</b></span>
          <span class="sla-item">合计 <b class="sla-total">{{ money(form.total_cost) }}</b></span>
        </template>
        <template v-if="form.satisfaction_score">
          <el-divider direction="vertical" />
          <span class="sla-item">满意度 <b>{{ form.satisfaction_score }} 分</b>
            <span v-if="form.satisfaction_comment" class="sla-comment">「{{ form.satisfaction_comment }}」</span>
          </span>
        </template>
      </div>
      <div class="form-body">
        <!-- 录入模式切换：仅新建时显示 -->
        <div v-if="isNew" class="mode-switch-bar">
          <span class="mode-switch-label">录入方式</span>
          <div class="mode-switch">
            <span class="mode-tab" :class="{ active: entryMode === 'standard' }" @click="switchEntryMode('standard')">标准录入</span>
            <span class="mode-tab" :class="{ active: entryMode === 'error_code' }" @click="switchEntryMode('error_code')">日志录入</span>
          </div>
        </div>

        <!-- 日志录入模式：粘贴日志原文 → 抠码 + 手册情形勾选 + 工单案例预填 -->
        <template v-if="entryMode === 'error_code'">
          <el-card shadow="never" class="section-card error-code-card">
            <template #header>
              <div class="card-header-row">
                <span class="section-title">日志原文检索预填</span>
                <span class="mode-tip">粘贴 dmesg / nvidia-smi / BMC 日志原文，自动提取 Xid 等错误码并匹配历史处置方案，一键预填</span>
              </div>
            </template>
            <div class="ec-search">
              <el-input
                v-model="ecQuery"
                type="textarea"
                :rows="6"
                placeholder="粘贴设备屏幕/日志原文，如：2026-08-14 10:32:15 SV0436 X AXIS: EXCESS CURRENT IN SERVO 启动瞬间电流突增报警，电机无法转动"
                style="flex:1"
              />
              <el-button type="primary" :loading="ecSearching" @click="ecSearch">解析匹配</el-button>
            </div>
            <div v-if="ecError" class="ec-error">{{ ecError }}</div>
            <template v-if="ecResults">
              <div class="ec-results">
                <!-- 抠码结果：可增删 tag，最终写入 device_error_code -->
                <div class="ec-codes-row">
                  <span class="ec-codes-label">识别报警码</span>
                  <el-tag
                    v-for="c in extractedCodes"
                    :key="c"
                    closable
                    size="small"
                    class="ec-code-tag"
                    @close="removeExtractedCode(c)"
                  >{{ c }}</el-tag>
                  <el-input
                    v-model="manualCodeInput"
                    size="small"
                    class="ec-code-input"
                    placeholder="手动补码后回车"
                    @keydown.enter="addManualCode"
                  />
                  <span v-if="!extractedCodes.length" class="ec-code-empty">未识别到报警码可手动补充</span>
                </div>
                <div v-if="!ecResults.manual_items.length && !ecResults.case_items.length" class="ec-empty">
                  未检索到相关手册或工单案例
                </div>
                <div v-if="ecResults.manual_items.length" class="ec-group">
                  <div class="ec-group-title">服务器手册 / 厂商文档（权威标准处理）</div>
                  <div v-for="m in ecResults.manual_items" :key="m.manual_code_id" class="ec-item manual">
                    <div class="ec-item-header">
                      <span class="ec-code">{{ m.error_code }}</span>
                      <span class="ec-title">{{ m.title }}</span>
                      <el-tag v-if="m.severity" :type="sevTagType(m.severity)" size="small">{{ sevLabel(m.severity) }}（{{ m.effect || '-' }}）</el-tag>
                      <el-tag v-if="m.manual_name" size="small" type="info">{{ m.manual_name }}</el-tag>
                      <el-tag v-if="m.chapter" size="small" effect="plain">{{ m.chapter }}</el-tag>
                      <el-tag v-if="m.page" size="small" effect="plain">P{{ m.page }}</el-tag>
                    </div>
                    <div v-if="m.message_text" class="ec-msg">{{ m.message_text }}</div>
                    <div v-if="m.description" class="ec-desc">{{ m.description }}</div>
                    <div v-if="m.related_codes?.length" class="ec-block">
                      <span class="ec-block-label">伴随报警</span>
                      <el-tag v-for="rc in m.related_codes" :key="rc" size="small" effect="plain" style="margin-right:4px">{{ rc }}</el-tag>
                    </div>
                    <div v-if="m.conditions?.length" class="ec-cond-list">
                      <div class="ec-cond-head">勾选命中的情形（已按日志信号匹配度排序，可多选）</div>
                      <el-checkbox-group v-model="m._selected" class="ec-cond-group">
                        <el-checkbox v-for="(c, i) in m.conditions" :key="i" :value="i" class="ec-cond">
                          <span class="ec-cond-signal">{{ c.signal }}</span>
                          <span class="ec-cond-cause">{{ c.cause }}</span>
                        </el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <div v-if="!m.conditions?.length && (m.causes || m.solutions)" class="ec-block">
                      <span class="ec-block-label">可能原因</span>{{ m.causes }}
                      <div v-if="m.solutions"><span class="ec-block-label">标准处理</span>{{ m.solutions }}</div>
                    </div>
                    <div class="ec-item-footer">
                      <el-button size="small" type="primary" @click="applyManualItem(m)">选用选中情形</el-button>
                    </div>
                  </div>
                </div>
                <div v-if="ecResults.case_items.length" class="ec-group">
                  <div class="ec-group-title">历史工单案例（真实处理记录）</div>
                  <div v-for="c in ecResults.case_items" :key="c.knowledge_id" class="ec-item case">
                    <div class="ec-item-header">
                      <span class="ec-title">{{ c.title }}</span>
                      <el-tag v-if="c.device_type" size="small" type="info">{{ c.device_type }}</el-tag>
                      <el-tag v-if="c.fault_code" size="small" type="warning">{{ c.fault_code }}</el-tag>
                    </div>
                    <div v-if="c.content" class="ec-desc">{{ c.content }}</div>
                    <div class="ec-item-footer">
                      <el-button size="small" type="primary" plain @click="applyCaseItem(c)">引用此案例</el-button>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </el-card>
        </template>

        <template v-if="analysisResult">
          <el-card shadow="never" class="section-card analysis-card">
            <template #header>
              <div class="card-header-row">
                <span class="section-title">AI 校验结果</span>
                <el-button size="small" text type="primary" @click="analysisResult = null">收起</el-button>
              </div>
            </template>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="完整度">
                <el-progress :percentage="Math.round((analysisResult.completeness_score || 0) * 100)" :stroke-width="16" :status="analysisResult.completeness_score >= 0.8 ? 'success' : 'warning'" style="width:180px" />
              </el-descriptions-item>
              <el-descriptions-item label="置信度">
                <span :style="{ fontWeight:600, color: analysisResult.confidence >= 0.8 ? '#52c41a' : '#faad14' }">
                  {{ Math.round((analysisResult.confidence || 0) * 100) }}%
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="服务器类型">{{ analysisResult.device_type || '-' }}</el-descriptions-item>
              <el-descriptions-item label="故障分类">{{ analysisResult.fault_category || '-' }}</el-descriptions-item>
              <el-descriptions-item label="标准化故障码">{{ analysisResult.standardized_fault_code || '-' }}</el-descriptions-item>
              <el-descriptions-item label="缺失字段">
                <div v-if="(analysisResult.missing_fields || []).length" class="missing-fields">
                  <template v-for="f in analysisResult.missing_fields" :key="f">
                  <el-tag type="danger" size="small" style="margin-right:4px">{{ fieldLabelMap[f] || f }}</el-tag>
                </template>
                </div>
                <span v-if="!(analysisResult.missing_fields || []).length" style="color:#52c41a">无</span>
              </el-descriptions-item>
              <el-descriptions-item label="校验说明" :span="2">{{ analysisResult.validation_notes || '-' }}</el-descriptions-item>
              <template v-if="analysisResult.standardized_fault_code">
                <el-descriptions-item label="推荐操作" :span="2">
                  <el-button size="small" type="primary" @click="applyAIFields">一键填充 AI 推荐字段</el-button>
                </el-descriptions-item>
              </template>
            </el-descriptions>
          </el-card>
        </template>

        <template v-if="deviceMaintenance">
          <el-alert
            :title="`设备「${deviceMaintenance.device_name}」近 6 个月维修 ${deviceMaintenance.recent_count} 次`"
            type="info"
            :closable="false"
            show-icon
            style="margin-bottom:16px"
          >
            <template #default>
              <span v-if="deviceMaintenance.last_fault">
                最近故障：{{ deviceMaintenance.last_fault }}
                <span v-if="deviceMaintenance.last_date">（{{ dayjs(deviceMaintenance.last_date).format('MM-DD HH:mm') }}）</span>
              </span>
            </template>
          </el-alert>
        </template>

        <el-alert
          v-if="isNew || form.status === 'DRAFT'"
          title="只填故障描述即可提交；知道是哪台服务器就选，集群/网络问题可不选服务器，填「涉及对象」即可"
          type="info" :closable="false" show-icon style="margin-bottom:12px"
        />
        <el-card shadow="never" class="form-card">
          <el-form :model="form" label-width="118px" label-position="left" class="form-grid">
            <div class="form-section">
              <div class="section-header">基本信息</div>
              <el-form-item label="关联服务器">
                <el-select
                  v-model="form.device_id"
                  clearable
                  filterable
                  remote
                  :remote-method="searchDevices"
                  placeholder="选填：知道是哪台就搜；集群/网络问题可留空"
                  style="width:100%"
                  @change="onDeviceChange"
                >
                  <el-option v-for="d in deviceFiltered" :key="d.id" :label="`${d.device_name} (${d.device_code})`" :value="d.id">
                    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%">
                      <div style="display:flex;flex-direction:column;gap:2px;min-width:0">
                        <span style="font-weight:600;color:#1D2129">{{ d.device_name }}</span>
                        <span style="font-size:11px;color:#86909C">{{ d.device_code }} · {{ d.location || '未设置位置' }}</span>
                      </div>
                      <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
                        <el-tag v-if="d.fault_tags && d.fault_tags.length" size="small" type="danger" effect="light">
                          {{ d.fault_tags.length }} 故障
                        </el-tag>
                        <el-tag :type="devStatusTagType(d.run_status)" size="small" effect="dark" round>
                          {{ devStatusLabel(d.run_status) }}
                        </el-tag>
                      </div>
                    </div>
                  </el-option>
                </el-select>
                <div class="device-picker-hint">
                  共 <b>{{ deviceTotal }}</b> 台设备
                  <el-link type="primary" :underline="false" @click="$router.push('/devices')">查看设备台账</el-link>
                </div>
              </el-form-item>
              <el-form-item label="涉及对象">
                <el-input v-model="form.fault_object" maxlength="200" placeholder="选填：集群 A / 核心交换机 / IB 交换机 / 光模块链路 / 其他" />
              </el-form-item>
              <el-form-item v-if="form.device_id" label="服务器类型">
                <el-input v-model="form.device_type" disabled placeholder="选择服务器后自动填充" />
              </el-form-item>
              <el-form-item v-if="form.device_id" label="机房位置">
                <el-input v-model="form.location" disabled placeholder="选择服务器后自动填充" />
              </el-form-item>
            </div>

            <div class="form-section">
              <div class="section-header">
                故障信息
                <el-button size="small" type="primary" plain style="float:right" @click="askAI('fault')">AI 分析故障</el-button>
              </div>
              <el-form-item v-if="isNew || form.status === 'DRAFT'" label="影响程度">
                <el-radio-group v-model="form.priority">
                  <el-radio-button v-for="o in IMPACT_OPTIONS" :key="o.value" :value="o.value">
                    {{ o.label }}
                  </el-radio-button>
                </el-radio-group>
                <div class="cascader-hint">选填，默认「一般」；影响告警级别和 SLA 响应/修复时限</div>
              </el-form-item>
              <el-form-item label="故障现象">
                <el-select
                  v-model="form.fault_phenomenon_type" clearable filterable allow-create
                  placeholder="选填：选一个常见现象，也可不填" style="width:100%"
                  @change="onFaultPhenomenonSelect"
                >
                  <el-option v-for="p in FAULT_PHENOMENA" :key="p.value" :label="p.label" :value="p.value" />
                </el-select>
              </el-form-item>
              <el-form-item label="故障描述" required>
                <el-input v-model="form.fault_description" type="textarea" :rows="4" :placeholder="faultDescPlaceholder" />
                <div class="cascader-hint">写清楚现象即可，系统会自动识别是 GPU、集群、网络、存储还是供电问题；不用先选分类</div>
              </el-form-item>
              <el-form-item v-if="isNew" label="工单类型">
                <el-select v-model="form.order_type" style="width:100%">
                  <el-option label="报修工单" value="REPAIR" />
                  <el-option label="保养工单" value="MAINTENANCE" />
                  <el-option label="点检工单" value="INSPECTION" />
                  <el-option label="交付 / 验收单" value="DELIVERY" />
                </el-select>
              </el-form-item>
              <el-form-item v-if="!isNew" label="服务方式">
                <el-radio-group v-model="form.service_mode">
                  <el-radio label="REMOTE">远程处理</el-radio>
                  <el-radio label="SITE">现场处理</el-radio>
                  <el-radio label="RMA">返厂维修</el-radio>
                </el-radio-group>
                <span v-if="!form.service_mode" class="hint" style="margin-left:8px">待确认（技术员接单时选择）</span>
              </el-form-item>
              <template v-if="form.order_type === 'DELIVERY'">
                <el-form-item label="项目名称">
                  <el-input v-model="form.project_name" maxlength="100" placeholder="例如：XX 智算中心一期" />
                </el-form-item>
                <el-row :gutter="12">
                  <el-col :span="12"><el-form-item label="交付批次"><el-input v-model="form.delivery_batch" maxlength="50" /></el-form-item></el-col>
                  <el-col :span="12"><el-form-item label="机柜 / U 位"><el-input v-model="form.rack_location" maxlength="100" /></el-form-item></el-col>
                </el-row>
                <el-form-item label="加电时间">
                  <el-date-picker v-model="form.power_on_at" type="datetime" style="width:100%" />
                </el-form-item>
              </template>
              <el-form-item v-if="form.service_mode === 'RMA' || form.need_rma" label="需要返厂">
                <el-switch v-model="form.need_rma" />
                <span class="hint" style="margin-left:8px">勾选后会标记为需 RMA 的工单</span>
              </el-form-item>
            </div>

            <div v-if="showRepairFields" class="form-section">
              <div class="section-header">
                诊断与维修
              </div>
              <el-form-item label="处理步骤" required>
                  <div class="solution-area">
                    <el-input v-model="form.solution_steps" type="textarea" :rows="4" placeholder="1. 隔离节点并停机&#10;2. 更换故障 GPU / 清理散热风道&#10;3. 压测 30 分钟确认无 Xid" />
                    <el-button size="small" type="primary" plain style="margin-top:8px" @click="openKnowledgeRef">
                      从知识库引用
                    </el-button>
                  </div>
                </el-form-item>
                <el-form-item label="维修时间" required>
                  <el-date-picker
                    v-model="timeRange"
                    type="datetimerange"
                    start-placeholder="开始"
                    end-placeholder="结束"
                    style="width:100%"
                    :disabled-date="disabledDate"
                    @change="calcWorkHours"
                  />
                </el-form-item>
                <el-form-item label="工时（小时）">
                  <el-input :model-value="form.work_hours != null ? form.work_hours.toFixed(1) : ''" disabled placeholder="自动计算">
                    <template #append>小时</template>
                  </el-input>
                </el-form-item>
                <el-form-item label="维修结果" required>
                  <el-radio-group v-model="form.repair_result" @change="onRepairResultChange">
                    <el-radio value="PERMANENT_FIX">彻底修复</el-radio>
                    <el-radio value="TEMPORARY_FIX">临时措施</el-radio>
                    <el-radio value="UNABLE_FIX">未能修复</el-radio>
                  </el-radio-group>
                </el-form-item>
                <el-row :gutter="12">
                  <el-col v-if="isGpuDevice" :span="12">
                    <el-form-item v-if="isGpuFault" label="故障 GPU">
                      <el-select v-model="form.gpu_index" clearable filterable allow-create placeholder="选填：如 GPU3 / 0-7 / 整机" style="width:100%">
                        <el-option v-for="i in 8" :key="i" :label="`GPU${i - 1}`" :value="`GPU${i - 1}`" />
                        <el-option label="整机 / 非单卡故障" value="整机" />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="isGpuDevice ? 12 : 24">
                    <el-form-item label="故障件 SN">
                      <el-input v-model="form.fault_device_sn" placeholder="选填：故障部件 SN（内存 / 电源 / 硬盘 / 板卡等）" />
                    </el-form-item>
                  </el-col>
                </el-row>
                <template v-if="form.repair_result === 'TEMPORARY_FIX'">
                  <el-form-item label="后续计划" required>
                    <el-input v-model="form.follow_up_plan" type="textarea" :rows="2" placeholder="请填写后续处理计划，如：已订购配件，预计 3 天后到货更换" />
                  </el-form-item>
                </template>
                <template v-if="form.repair_result === 'UNABLE_FIX'">
                  <el-form-item label="未修复原因" required>
                    <el-input v-model="form.follow_up_plan" type="textarea" :rows="2" placeholder="请说明未能修复的原因" />
                  </el-form-item>
                </template>
              <!-- 故障码：日志录入模式下复用顶部解析出的识别报警码，与日志区联动；标准录入使用故障码下拉 -->
              <el-form-item v-if="entryMode === 'error_code'" label="报警码（可选）">
                <div class="ec-codes-row">
                  <span class="ec-codes-label">识别报警码</span>
                  <el-tag
                    v-for="c in extractedCodes"
                    :key="c"
                    closable
                    size="small"
                    class="ec-code-tag"
                    @close="removeExtractedCode(c)"
                  >{{ c }}</el-tag>
                  <el-input
                    v-model="manualCodeInput"
                    size="small"
                    class="ec-code-input"
                    placeholder="手动补码后回车"
                    @keydown.enter="addManualCode"
                  />
                  <span v-if="!extractedCodes.length" class="ec-code-empty">未识别到报警码可手动补充</span>
                </div>
                <div class="cascader-hint">日志解析后自动填入报警码，可手动增删；识别不到可留空，不影响提交</div>
              </el-form-item>
              <el-form-item v-else label="故障码（可选）">
                <div class="fault-code-row">
                  <el-select
                    v-model="form.fault_code"
                    multiple
                    filterable
                    allow-create
                    default-first-option
                    placeholder="输入故障码，如 100001"
                    style="flex:1"
                    :reserve-keyword="false"
                    :filter-method="filterFaultCodes"
                  >
                    <el-option
                      v-for="opt in faultCodeFiltered"
                      :key="opt.code"
                      :label="opt.code"
                      :value="opt.code"
                    >
                      <span class="fc-option">
                        <span class="fc-code">{{ opt.code }}</span>
                        <span class="fc-desc">{{ opt.desc }}</span>
                      </span>
                    </el-option>
                  </el-select>
                  <el-button size="small" type="primary" plain @click="faultCodeDialog.visible = true">
                    + 新增
                  </el-button>
                </div>
                <div class="cascader-hint">有就选，没有可留空；不确定故障码不用勉强编一个，故障描述写清楚即可</div>
              </el-form-item>
            </div>

            <!-- 报修人提交的照片/语音：只读展示，不混进维修人员的现场附件 -->
            <div v-if="reporterMedia.length" class="form-section">
              <div class="section-header">报修人提交的照片 / 语音（只读）</div>
              <div class="wo-attach-grid">
                <div v-for="(f, i) in reporterMedia" :key="'rm-' + i" class="wo-attach-item">
                  <img v-if="isImageFile(f)" :src="f.url" class="wo-attach-thumb wo-attach-clickable"
                       @click="openPreview(f.url)" />
                  <video v-else :src="f.url" class="wo-attach-thumb" controls preload="metadata" />
                  <div class="wo-attach-meta"><span class="wo-attach-name">{{ f.name || '报修附件' }}</span></div>
                </div>
              </div>
            </div>

            <!-- 随单/历史附件（没有维修人标记的旧数据）：只读，避免被当成维修人员现场照片 -->
            <div v-if="legacyAttachments.length" class="form-section">
              <div class="section-header">随单附件（报修/历史提交，只读）</div>
              <div class="wo-attach-grid">
                <div v-for="(f, i) in legacyAttachments" :key="'lg-' + i" class="wo-attach-item">
                  <img v-if="isImageFile(f)" :src="f.url" class="wo-attach-thumb wo-attach-clickable"
                       @click="openPreview(f.url)" />
                  <video v-else :src="f.url" class="wo-attach-thumb" controls preload="metadata" />
                  <div class="wo-attach-meta"><span class="wo-attach-name">{{ f.name }}</span></div>
                </div>
              </div>
            </div>

            <!-- 现场附件：独立成节、始终可见。只放维修人员本次拍的照片/视频 -->
            <div id="wo-upload-section" class="form-section attach-section">
              <div class="section-header">
                现场附件（维修人员填写）
                <span v-if="attachments.length" class="attach-count">{{ attachments.length }}</span>
                <span v-if="attachDirty" class="attach-dirty">未保存</span>
              </div>
              <el-form-item label="照片 / 视频">
                <div class="attach-upload-wrap">
                  <el-upload
                    :http-request="uploadFile"
                    :file-list="uploadFileList"
                    list-type="picture-card"
                    :on-remove="removeAttachment"
                    :before-upload="beforeUpload"
                    accept=".jpg,.jpeg,.png,.gif,.mp4,.mov,.avi,.webm"
                    multiple
                  >
                    <el-icon><Plus /></el-icon>
                  </el-upload>
                  <div class="upload-hint">
                    点方块选图，支持 JPG/PNG/GIF/MP4，单文件 ≤ 50MB，可多选。
                    <template v-if="isNew">保存工单时一并写入。</template>
                    <template v-else>上传只是把文件传上去，还要点「保存附件到工单」才会挂到本工单。</template>
                  </div>
                  <el-button
                    v-if="attachDirty && !isNew" type="primary" size="small" plain
                    :loading="saving" class="attach-save-btn" @click="handleSaveDraft"
                  >保存附件到工单</el-button>
                </div>
              </el-form-item>
            </div>

            <!-- 补充信息（可选）：次要字段折叠，关键路径 = 设备 + 日志粘贴 + 处理结果 -->
            <div class="form-section">
              <el-collapse v-model="supplementOpen" class="supplement-collapse">
                <el-collapse-item :name="'supplement'">
                  <template #title>
                    <span class="supplement-title">
                      补充信息（可选）
                      <el-badge v-if="supplementFilledCount" :value="supplementFilledCount" type="info" class="supplement-badge" />
                    </span>
                  </template>
                  <div class="supplement-body">
                    <el-form-item label="根本原因">
                      <el-cascader
                        v-model="rootCauseCascader"
                        :options="rootCauseOptions"
                        :props="{ value: 'value', label: 'label', children: 'children', checkStrictly: false }"
                        placeholder="选择原因大类 → 具体原因（也可跳过，直接在下方手动输入）"
                        style="width:100%"
                        clearable
                        filterable
                        @change="onRootCauseChange"
                      />
                      <div class="cascader-hint">如原因类型不在列表中，可直接在下方文本框自由描述</div>
                    </el-form-item>
                    <el-form-item :label="rootCauseCascader.length ? '补充说明' : '根本原因描述'">
                      <el-input
                        v-model="form.root_cause"
                        type="textarea"
                        :rows="3"
                        :placeholder="rootCauseCascader.length ? '选填：根本原因的补充说明' : '请描述根本原因，如：GPU 卡故障触发 Xid 79；散热风道堵塞导致降频'"
                      />
                    </el-form-item>
                    <div class="supplement-sub">
                      <div class="section-header">备件记录</div>
                      <div class="parts-list">
                        <div v-if="!usedParts.length" class="parts-empty">备件由「备件出库 / 领用发料」自动写入，这里只做展示</div>
                        <div v-for="(part, idx) in usedParts" :key="idx" class="part-row part-row-readonly">
                          <span class="part-name">{{ part.name || part.code }}</span>
                          <span class="part-code">{{ part.code }}</span>
                          <span class="part-qty">× {{ part.count ?? part.qty ?? 1 }}</span>
                          <span v-if="part.unit_price" class="part-price">¥{{ part.unit_price }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>
          </el-form>
        </el-card>

        <div class="form-footer">
          <el-button plain @click="$router.back()">取消</el-button>
          <el-button type="primary" plain :loading="saving" @click="handleSaveDraft">
            {{ saving ? '保存中...' : (isNew ? '保存草稿' : '保存修改') }}
          </el-button>
          <template v-if="!['ARCHIVING', 'COMPLETED'].includes(form.status)">
            <el-button plain :loading="analyzing" @click="handleAnalyze">
              {{ analyzing ? 'AI 校验中...' : 'AI 校验' }}
            </el-button>
            <el-button v-if="isNew || form.status === 'DRAFT'" type="primary" :loading="submitting" @click="handleSubmitReport">
              {{ submitting ? '提交中...' : '提交报修' }}
            </el-button>
            <el-button v-else-if="form.status === 'IN_PROGRESS' && (isMyTask || canDispatch)" type="primary" :loading="submitting" @click="handleSubmit" :disabled="!canSubmit">
              {{ submitting ? '提交中...' : '提交完成' }}
            </el-button>
          </template>
        </div>
        <p v-if="!isNew && ['ARCHIVING', 'COMPLETED'].includes(form.status) && form.customer_id && form.customer_accept_status !== 'ACCEPTED'" class="submit-hint warn">
          客户尚未在门户确认解决，客户确认后才能完成归档
        </p>
        <p v-else-if="!isNew && ['ARCHIVING', 'COMPLETED'].includes(form.status)" class="submit-hint">
          保存修改后返回详情，在右上角点「归档」：先校验完成度，通过后在弹窗里确认归档
        </p>
        <p v-else-if="['SUBMITTED','ASSIGNED','ACCEPTED','ARRIVED','INSPECTING'].includes(form.status) && !isNew" class="submit-hint">
          当前工单等待推进：主管先「派工」，维修员点右上角「开始处理」即可进入处理中（接单/到场/检查自动记录），完成后点「提交完成」
        </p>
        <p v-else-if="!canSubmit && !isNew" class="submit-hint">
          {{ entryMode === 'error_code'
              ? '请先通过「错误码检索」选用方案（或填写故障描述），再提交'
              : '请先点击「AI 校验」完成分析后再提交' }}
        </p>
      </div>
    </template>

    <!-- AI 问答弹窗 -->
    <el-dialog v-model="aiDialog.visible" title="AI 助手" width="960px" :close-on-click-modal="false" class="ai-dialog">
      <div class="ai-dialog-body">
        <div class="ai-dialog-msgs" ref="aiMsgRef">
          <div v-for="(m, i) in aiDialog.messages" :key="i" class="ai-msg-row" :class="m.role">
            <div class="ai-msg-bubble">{{ m.content }}</div>
          </div>
          <div v-if="aiDialog.loading" class="ai-msg-row assistant">
            <div class="ai-msg-bubble thinking">AI 思考中...</div>
          </div>
        </div>
        <div class="ai-dialog-input">
          <el-input v-model="aiDialog.input" type="textarea" :rows="2" placeholder="输入你的维修问题..." @keydown.enter.prevent="sendAIMessage" />
          <el-button type="primary" @click="sendAIMessage" :loading="aiDialog.loading" style="margin-top:8px">发送</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 知识库引用弹窗 -->
    <el-dialog v-model="knowledgeDialog.visible" title="从知识库引用处理步骤" width="750px" :close-on-click-modal="false">
      <div class="knowledge-dialog">
        <div class="kd-search">
          <el-input v-model="knowledgeDialog.keyword" placeholder="输入故障现象或 GPU/服务器关键词检索" clearable @keydown.enter="searchSolutions" style="flex:1">
            <template #append>
              <el-button type="primary" @click="searchSolutions" :loading="knowledgeDialog.searching">搜索</el-button>
            </template>
          </el-input>
        </div>
        <div class="kd-results" v-loading="knowledgeDialog.searching">
          <div v-if="knowledgeDialog.results.length === 0 && !knowledgeDialog.searching" class="kd-empty">
            请输入关键词搜索知识库中的处理步骤
          </div>
          <div v-for="item in knowledgeDialog.results" :key="item.knowledge_id" class="kd-item" @click="applySolution(item)">
            <div class="kd-item-header">
              <span class="kd-title">{{ item.title }}</span>
              <el-tag size="small" type="info">{{ item.device_type || '通用' }}</el-tag>
              <template v-if="item.fault_code">
                <el-tag size="small" type="warning">{{ item.fault_code }}</el-tag>
              </template>
            </div>
            <pre class="kd-steps">{{ item.solution_steps }}</pre>
            <div class="kd-item-footer">
              <span class="kd-count">共 {{ item.solution_count }} 个步骤</span>
              <el-button size="small" type="primary">引用此方案</el-button>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 新增故障码弹窗 -->
    <el-dialog v-model="faultCodeDialog.visible" title="新增故障码" width="500px" :close-on-click-modal="false">
      <div class="fc-dialog">
        <el-form label-width="80px">
          <el-form-item label="设备类型">
            <el-input :model-value="form.device_type || '（未选择）'" disabled />
            <div class="cascader-hint">系统根据设备类型自动分配编码前缀</div>
          </el-form-item>
          <el-form-item label="故障描述" required>
            <el-input
              v-model="faultCodeDialog.description"
              type="textarea"
              :rows="4"
              placeholder="请填写故障描述，如：注塑机料筒温度偏高报警"
            />
          </el-form-item>
        </el-form>
        <div v-if="faultCodeDialog.result" class="fc-dialog-result">
          <div v-if="faultCodeDialog.result.is_new">
            <el-alert
              title="新增成功"
              type="success"
              :description="`故障码 ${faultCodeDialog.result.fault_code} 已自动生成并收录`"
              show-icon
              :closable="false"
            />
          </div>
          <div v-if="!faultCodeDialog.result.is_new">
            <el-alert
              title="检测到重复"
              type="warning"
              :description="faultCodeDialog.result.duplicate_hint"
              show-icon
              :closable="false"
            />
          </div>
        </div>
        <div class="fc-dialog-footer">
          <el-button @click="faultCodeDialogClose">取消</el-button>
          <div v-if="!faultCodeDialog.result" style="display:inline">
            <el-button type="primary" :loading="faultCodeDialog.creating" @click="handleCreateFaultCode">
              {{ faultCodeDialog.creating ? '生成中...' : '自动生成故障码' }}
            </el-button>
          </div>
          <div v-if="faultCodeDialog.result" style="display:inline">
            <el-button type="primary" @click="confirmFaultCodeResult">
              确认使用
            </el-button>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 挂起 -->
    <el-dialog v-model="holdDlg.visible" title="挂起工单" width="440px">
      <el-form label-width="90px">
        <el-form-item label="挂起原因" required>
          <el-select v-model="holdDlg.reason" style="width:100%">
            <el-option label="等厂商返修 / RMA" value="VENDOR" />
            <el-option label="等备件到货" value="SPARE" />
            <el-option label="等客户回复 / 配合" value="CUSTOMER" />
            <el-option label="等 IDC / 机房配合" value="IDC" />
            <el-option label="其他" value="OTHER" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="holdDlg.remark" type="textarea" :rows="3" maxlength="300"
                    placeholder="例如：已寄回 NVIDIA，等待返修或换件" />
        </el-form-item>
        <el-alert title="挂起期间暂停修复 SLA，恢复后继续计时" type="info" :closable="false" show-icon />
      </el-form>
      <template #footer>
        <el-button @click="holdDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="holdSaving" @click="submitHold">确认挂起</el-button>
      </template>
    </el-dialog>

    <!-- RMA -->
    <el-dialog v-model="rmaDlg.visible" title="RMA / 厂商返修" width="560px">
      <el-form label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="厂商"><el-input v-model="rmaDlg.vendor" maxlength="100" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="RMA / 案例号"><el-input v-model="rmaDlg.rma_no" maxlength="80" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="当前状态">
          <el-select v-model="rmaDlg.status" style="width:100%">
            <el-option v-for="o in RMA_STATUS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="寄出时间"><el-date-picker v-model="rmaDlg.shipped_at" type="datetime" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="厂商收到"><el-date-picker v-model="rmaDlg.vendor_received_at" type="datetime" style="width:100%" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="返回时间"><el-date-picker v-model="rmaDlg.returned_at" type="datetime" style="width:100%" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="换件 SN"><el-input v-model="rmaDlg.replacement_sn" maxlength="100" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="备注"><el-input v-model="rmaDlg.remark" type="textarea" :rows="2" maxlength="300" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="rmaDlg.visible = false">取消</el-button>
        <el-button type="primary" :loading="rmaDlg.saving" @click="saveRma">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="submitChoice.visible" title="提交报修" width="480px" append-to-body :close-on-click-modal="false">
      <div class="submit-choice-title">这张工单提交后由谁处理？</div>
      <div class="submit-choice-desc">
        选择「我自己处理」会直接接单，进入「我的工单」；选择「放入工单池」则不占负责人，等待主管派工或其他技术员领取。
      </div>
      <template #footer>
        <el-button plain @click="submitChoice.visible = false">取消</el-button>
        <el-button plain type="primary" :loading="submitting" @click="doSubmitReport(true)">放入工单池</el-button>
        <el-button type="primary" :loading="submitting" @click="doSubmitReport(false)">我自己处理</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="archiveDialog.visible" title="工单归档" width="560px" append-to-body>
      <template v-if="archiveDialog.result">
        <el-result
          :icon="archiveDialog.result.passed ? 'success' : 'warning'"
          :title="archiveDialog.result.passed ? '归档校验通过' : '归档完成度不足'"
        >
          <template #sub-title>
            <div>当前完成度：{{ Math.round((archiveDialog.result.completeness || 0) * 100) }}%</div>
            <div v-if="archiveDialog.result.missing_fields && archiveDialog.result.missing_fields.length" style="margin-top:6px">
              缺失项：{{ archiveDialog.result.missing_fields.map(f => fieldLabelMap[f] || f).join('、') }}
            </div>
          </template>
        </el-result>
        <el-alert
          v-if="form.customer_id && form.customer_accept_status !== 'ACCEPTED'"
          type="warning" :closable="false" show-icon
          title="客户尚未在门户确认解决，客户确认后才能完成归档"
        />
      </template>
      <template #footer>
        <el-button plain @click="archiveDialog.visible = false">取消</el-button>
        <el-button
          v-if="archiveDialog.result && !archiveDialog.result.passed && canEditWorkOrder"
          plain type="primary" @click="goEditFromArchive"
        >去补充</el-button>
        <el-button type="primary" :loading="archiving" :disabled="!canArchiveComplete" @click="handleArchiveComplete">
          {{ archiving ? '归档中...' : '确认归档' }}
        </el-button>
      </template>
    </el-dialog>

    <ServiceModeDialog
      v-model="serviceDialog.visible"
      :title="serviceDialog.action === 'claim' ? '领取任务' : '确认接单'"
      :confirm-text="serviceDialog.action === 'claim' ? '确认领取' : '确认接单'"
      :work-order-no="form.work_order_no || ''"
      :loading="serviceDialog.loading"
      @confirm="onServiceConfirm"
    />
  </div>
</template>

<script setup>
import { downloadFile } from '../utils/download'
import { ref, computed, reactive, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, QuestionFilled, UploadFilled } from '@element-plus/icons-vue'
import request from '../api'
import dayjs from 'dayjs'
import ServiceModeDialog from '../components/ServiceModeDialog.vue'
import { IMPACT_OPTIONS } from '../config/impact'
import { FAULT_PHENOMENA } from '../config/faultPhenomena'

const route = useRoute()
const router = useRouter()
const isNew = computed(() => !route.params.id || route.path.endsWith('/new'))

// ===== SLA / 成本 / 回访 =====
const feedbackVisible = ref(false)
const feedbackScore = ref(5)
const feedbackComment = ref('')
const feedbackSaving = ref(false)

const fmt = (t) => (t ? dayjs(t).format('MM-DD HH:mm') : '-')
const fmtFull = (t) => (t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '—')
const money = (v) => (v || v === 0 ? `${Number(v).toFixed(0)} 元` : '—')


const slaText = computed(() => {
  if (isNew.value) return '未建单'
  const st = form.sla_status
  const s = form.status
  if (['COMPLETED', 'ARCHIVED'].includes(s)) return st === 'OVERDUE' ? '超时完成' : '按时完成'
  if (st === 'OVERDUE') return '已超时'
  if (st === 'AT_RISK') return '即将超时'
  return '正常'
})
const slaTagType = computed(() => {
  const st = form.sla_status
  if (st === 'OVERDUE') return 'danger'
  if (st === 'AT_RISK') return 'warning'
  if (['COMPLETED', 'ARCHIVED'].includes(form.status)) return st === 'OVERDUE' ? 'danger' : 'success'
  return 'success'
})

const currentUserId = (() => { try { return JSON.parse(localStorage.getItem('current_user') || '{}').id } catch { return null } })()
const currentUserRole = (() => { try { return JSON.parse(localStorage.getItem('current_user') || '{}').role || '' } catch { return '' } })()
// 返回列表时回到进入详情前所在的工单 tab（工单池进来的回工单池，我的工单进来的回我的工单）
const backLabel = computed(() => route.query.from === 'customers' ? '返回客户' : '返回列表')
const goBackToList = () => {
  if (route.query.from === 'customers') {
    const cid = route.query.customer_id
    // 从客户详情的「工单记录」点进来：关掉详情回到那个客户的工单页，不落到客户列表/工单中心
    router.push(cid ? `/customers/${cid}` : '/customers')
    return
  }
  const supervise = ['ADMIN', 'SUPERVISOR'].includes(currentUserRole)
  const valid = supervise ? ['list', 'progress', 'import'] : ['mine', 'pool', 'import']
  const fallback = supervise ? 'list' : 'mine'
  let tab = ''
  try { tab = sessionStorage.getItem('wo_last_tab') || '' } catch { /* ignore */ }
  router.push(`/orders?tab=${valid.includes(tab) ? tab : fallback}`)
}
// 成本只对管理员/主管展示，且没有实际成本时不占位置（避免“人工 0 / 备件 0 / 合计 0”的噪声）
const canSeeCost = computed(() => ['ADMIN', 'SUPERVISOR'].includes(currentUserRole))
const hasCost = computed(() => {
  return Number(form.labor_cost || 0) > 0
    || Number(form.parts_cost || 0) > 0
    || Number(form.total_cost || 0) > 0
})
const canDispatch = computed(() => {
  try {
    const u = JSON.parse(localStorage.getItem('current_user') || '{}')
    return ['ADMIN', 'SUPERVISOR'].includes(u.role)
  } catch { return false }
})
const isAdminUser = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('current_user') || '{}').role === 'ADMIN'
  } catch { return false }
})

const canClaim = computed(() => {
  try {
    const u = JSON.parse(localStorage.getItem('current_user') || '{}')
    return u.role === 'TECHNICIAN'
  } catch { return false }
})
const isMyTask = computed(() => {
  try {
    const u = JSON.parse(localStorage.getItem('current_user') || '{}')
    return !!u.id && (form.technician_id === u.id || form.assignee_id === u.id)
  } catch { return false }
})
// 改派后新负责人尚未接单：旧接单时间不再展示，改为「待接受」
const claimTime = computed(() => {
  if (!form.first_response_at) return ''
  if (form.status === 'ASSIGNED' && form.dispatched_at
      && new Date(form.dispatched_at) > new Date(form.first_response_at)) return ''
  return form.first_response_at
})

const claiming = ref(false)
const accepting = ref(false)
const serviceDialog = reactive({ visible: false, action: '', loading: false })
// 服务方式由技术员在接单/领取时确认，创建阶段不再出现
const claimTask = () => {
  serviceDialog.action = 'claim'
  serviceDialog.visible = true
}
const acceptAssignment = () => {
  serviceDialog.action = 'accept'
  serviceDialog.visible = true
}
const onServiceConfirm = async ({ service_mode, remark }) => {
  serviceDialog.loading = true
  try {
    const ok = serviceDialog.action === 'claim'
      ? await doClaim(service_mode, remark)
      : await doAccept(service_mode, remark)
    if (ok) serviceDialog.visible = false
  } finally {
    serviceDialog.loading = false
  }
}
const doClaim = async (service_mode, remark) => {
  claiming.value = true
  try {
    const u = JSON.parse(localStorage.getItem('current_user') || '{}')
    await request.post(`/work-orders/${form.id}/transition`, {
      to_status: 'ASSIGNED', technician_id: u.id, service_mode, source: 'TECH_CLAIM',
    })
    let autoAccepted = true
    try {
      await request.post(`/work-orders/${form.id}/transition`, {
        to_status: 'ACCEPTED', service_mode, remark, source: 'TECH_ACCEPT',
      })
    } catch {
      autoAccepted = false
    }
    ElMessage.success(autoAccepted ? '领取成功，已自动接单（处理中）' : '已领取，请点「接受」完成接单')
    const res = await request.get(`/work-orders/${form.id}`)
    Object.assign(form, res)
    return autoAccepted
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '领取失败')
    return false
  } finally {
    claiming.value = false
  }
}
const doAccept = async (service_mode, remark) => {
  accepting.value = true
  try {
    await request.post(`/work-orders/${form.id}/transition`, {
      to_status: 'ACCEPTED', service_mode, remark, source: 'TECH_ACCEPT',
    })
    ElMessage.success('已接单')
    const res = await request.get(`/work-orders/${form.id}`)
    Object.assign(form, res)
    return true
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '接单失败')
    return false
  } finally {
    accepting.value = false
  }
}

// 拒收：ASSIGNED → SUBMITTED（退回待派工池，必须填原因）
const rejectAssignment = async () => {
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt(
      '工单将退回「待派工」池，由主管重新派工', '拒收工单',
      {
        confirmButtonText: '确认拒收', cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '必填，例如：不熟悉该设备 / 手头工单已满 / 不在现场',
        inputValidator: (v) => (v && v.trim().length >= 2) || '请填写至少 2 个字的拒收原因',
      },
    )
    reason = value.trim()
  } catch { return }
  try {
    await request.post(`/work-orders/${form.id}/transition`, {
      to_status: 'SUBMITTED', remark: reason, source: 'TECH_REJECT',
    })
    ElMessage.success('已拒收，工单已回到待派工池')
    const res = await request.get(`/work-orders/${form.id}`)
    Object.assign(form, res)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '拒收失败')
  }
}

const dispatchTitle = computed(() => (!canDispatch.value && form.status === 'ASSIGNED') ? '转派工单' : (form.status === 'SUBMITTED' ? '工单派工' : '工单改派'))
const startActionLabel = computed(() => '开始处理')
const dispatchNeedsReason = computed(() => ['ACCEPTED', 'ARRIVED', 'INSPECTING'].includes(form.status))
const dispatchDlg = reactive({ visible: false, technicianId: null, collaboratorIds: [], remark: '', technicians: [], saving: false })
const openDispatch = async () => {
  Object.assign(dispatchDlg, {
    visible: true, technicianId: null,
    collaboratorIds: (form.collaborators || []).map((c) => c.id),
    remark: '', saving: false,
  })
  try {
    const res = await request.get('/dispatch/technicians')
    const all = Array.isArray(res) ? res : (res.items || [])
    dispatchDlg.technicians = canDispatch.value ? all : all.filter((t) => t.id !== currentUserId)
  } catch { dispatchDlg.technicians = [] }
}
const submitDispatch = async () => {
  if (!dispatchDlg.technicianId) return ElMessage.warning('请选择维修员')
  if (dispatchNeedsReason.value && !String(dispatchDlg.remark || '').trim()) {
    return ElMessage.warning('接单后改派必须填写原因')
  }
  const reassignStatuses = ['ASSIGNED', 'ACCEPTED', 'ARRIVED', 'INSPECTING']
  const toStatus = reassignStatuses.includes(form.status) ? form.status : 'ASSIGNED'
  dispatchDlg.saving = true
  try {
    await request.post(`/work-orders/${form.id}/transition`, {
      to_status: toStatus,
      technician_id: dispatchDlg.technicianId,
      collaborator_ids: dispatchDlg.collaboratorIds,
      source: 'SUPERVISOR_DISPATCH',
      remark: dispatchDlg.remark || null,
    })
    ElMessage.success(!canDispatch.value ? '转派成功' : (form.status === 'SUBMITTED' ? '派工成功' : '改派成功'))
    dispatchDlg.visible = false
    const res = await request.get(`/work-orders/${form.id}`)
    Object.assign(form, res)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '派工失败')
  } finally {
    dispatchDlg.saving = false
  }
}

const openFeedback = () => {
  feedbackScore.value = form.satisfaction_score || 5
  feedbackComment.value = form.satisfaction_comment || ''
  feedbackVisible.value = true
}

const submitFeedback = async () => {
  const id = route.params.id || form.id
  if (!id) return
  feedbackSaving.value = true
  try {
    const res = await request.post(`/work-orders/${id}/feedback`,
      { score: feedbackScore.value, comment: feedbackComment.value || null })
    form.satisfaction_score = res.score
    form.satisfaction_comment = res.comment
    feedbackVisible.value = false
    ElMessage.success('评价已提交，谢谢反馈')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    feedbackSaving.value = false
  }
}
const isViewMode = computed(() => !isNew.value && !route.query.edit)

// 查看历史草稿：前往维修报表并预选「草稿」筛选（联动 WorkOrders.vue 的 workorders_filter 恢复逻辑）
const viewDrafts = () => {
  sessionStorage.setItem('workorders_filter', JSON.stringify({ status: 'DRAFT' }))
  router.push('/orders?tab=list')
}

const DEFAULT_DEVICE_TYPES = [
  { label: 'GPU服务器整机', value: 'GPU服务器整机' },
  { label: 'GPU模组/板卡', value: 'GPU模组/板卡' },
  { label: '计算节点', value: '计算节点' },
  { label: '存储节点', value: '存储节点' },
  { label: 'IB/网络交换机', value: 'IB/网络交换机' },
  { label: '管理节点', value: '管理节点' },
]

const flattenTree = (nodes, result = []) => {
  for (const node of nodes) {
    result.push({ label: node.name, value: node.name })
    if (node.children && node.children.length > 0) flattenTree(node.children, result)
  }
  return result
}

const editLogs = ref([])

const loadEditLogs = async () => {
  if (!route.params.id) return
  try {
    const res = await request.get(`/work-orders/${route.params.id}/edit-logs`)
    editLogs.value = res.items || []
  } catch { editLogs.value = [] }
}

const auditText = (v) => {
  if (v === null || v === undefined || v === '') return '空'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

const form = reactive({
  work_order_no: '',
  id: null,
  device_id: null,
  fault_object: '',
  device_type: '',
  location: '',
  technician_id: null,
  technician_name: '',
  created_by_name: '',
  created_by_department: '',
  reporter_name: '',
  priority: 'MEDIUM',
  fault_description: '',
  fault_category: '',
  fault_phenomenon_type: '',
  fault_phenomenon: '',
  // GPU 维修专有字段
  gpu_index: '',
  fault_device_sn: '',
  order_type: 'REPAIR',
  service_mode: null,
  need_rma: false,
  fault_code: [],
  device_error_code: '',
  log_text: '',
  root_cause_category: '',
  root_cause_type: '',
  root_cause: '',
  solution_steps: '',
  solution_ref_knowledge_id: null,
  repair_result: '',
  follow_up_plan: '',
  work_hours: null,
  status: 'DRAFT',
  tags: [],
  fault_tags: [],
})

const faultPhenomenonCascader = ref([])
const faultPhenomenaOptions = ref([])
const rootCauseCascader = ref([])
const rootCauseOptions = ref([])
const attachments = ref([])
const legacyAttachments = ref([])   // 随单/历史附件（只读）
const reporterMedia = ref([])        // 报修人提交的照片/语音（只读）
const previewVisible = ref(false)
const previewUrl = ref('')

function openPreview(url) {
  previewUrl.value = url
  previewVisible.value = true
}
function openInNewTab(url) {
  window.open(url, '_blank')
}
const uploadFileList = ref([])
const attachDirty = ref(false)   // 有未落库的附件变更
const devices = ref([])
const deviceTotal = ref(0)
const deviceFiltered = ref([])
const users = ref([])
const timeRange = ref(null)
const usedParts = ref([])
const analyzing = ref(false)
const submitting = ref(false)
const saving = ref(false)
const analysisResult = ref(null)
const entryMode = ref('standard')          // standard 标准录入 | error_code 日志录入
const ecQuery = ref('')                    // 日志原文输入
const ecSearching = ref(false)
const ecResults = ref(null)                // { manual_items, case_items, error_codes }
const ecError = ref('')
const extractedCodes = ref([])             // 抠出的报警码 tag 组（写入 device_error_code）
const manualCodeInput = ref('')            // 手动补码输入
const supplementOpen = ref([])             // 补充信息折叠区展开状态
// 根本原因是否已填
const hasRootCause = () => !!(rootCauseCascader.value.length || (form.root_cause && form.root_cause.trim()))
// 补充信息是否启用：折叠区被展开过，视为需要填写补充信息
const supplementActive = () => supplementOpen.value.includes('supplement')
// 提交允许条件：故障描述不为空即可提交（标准/日志录入均如此）
const canSubmit = computed(() => {
  return !!(form.fault_description)
})

// 只有维修中/待归档阶段才展示“诊断与维修”必填项；新建/草稿阶段只收报修信息
const showRepairFields = computed(() =>
  ['IN_PROGRESS', 'ARCHIVING', 'COMPLETED', 'ARCHIVED'].includes(form.status))
// 只有系统识别为 GPU/显卡，或已有 GPU 序号时，维修阶段才显示 GPU 专项字段
const isGpuFault = computed(() => {
  const c = String(form.fault_category || '').toUpperCase()
  return c.includes('GPU') || c.includes('显卡') || !!form.gpu_index
})
// 报修阶段只收描述；GPU/SN 等维修信息在进入维修中后展示
const faultDescPlaceholder = '描述现象即可，例如：GPU3 掉卡 / 集群训练任务卡住 / 核心交换机端口 down / 硬盘掉盘 / 电源告警'

// 故障 GPU 只在故障本身涉及 GPU 时才出现（不能只看设备类型：GPU 服务器也会报网络/供电/存储故障）
const isGpuDevice = computed(() => {
  const desc = `${form.fault_description || ''} ${form.fault_phenomenon || ''} ${form.fault_object || ''}`
  return /GPU|Xid|显存|掉卡|CUDA|NVLink|显卡|加速卡/i.test(desc)
})

const sevTagType = (s) => ({ EX: 'danger', OH: 'warning', INFO: 'info' }[s] || 'info')
const sevLabel = (s) => ({ EX: 'EX 急停', OH: 'OH 停机', INFO: 'INFO 提示' }[s] || s)

// 补充信息已填项数（折叠区标题徽标）
const supplementFilledCount = computed(() => {
  let n = 0
  if (rootCauseCascader.value.length || form.root_cause) n++
  // 附件已独立成节，不再计入「补充信息」徽标
  if (usedParts.value.length) n++
  return n
})

const isFormDirty = () => {
  return !!(form.device_id || form.device_error_code || form.fault_description ||
    form.fault_phenomenon || form.fault_code.length || form.root_cause ||
    form.solution_steps || form.repair_result || form.follow_up_plan ||
    usedParts.value.length || attachments.value.length || timeRange.value)
}

// 清空工单表单（保留工单编号/状态/技术员等系统字段）
const resetFormFields = () => {
  form.device_id = null
  form.fault_object = ''
  form.device_type = ''
  form.location = ''
  form.priority = 'MEDIUM'
  form.fault_description = ''
  form.fault_category = ''
  form.fault_phenomenon_type = ''
  form.fault_phenomenon = ''
  form.fault_code = []
  form.device_error_code = ''
  form.log_text = ''
  form.root_cause_category = ''
  form.root_cause_type = ''
  form.root_cause = ''
  form.solution_steps = ''
  form.solution_ref_knowledge_id = null
  form.repair_result = ''
  form.follow_up_plan = ''
  form.work_hours = null
  form.tags = []
  form.fault_tags = []
  faultPhenomenonCascader.value = []
  rootCauseCascader.value = []
  timeRange.value = null
  usedParts.value = []
  attachments.value = []
  uploadFileList.value = []
  deviceMaintenance.value = null
  analysisResult.value = null
  archiveCheckResult.value = null
}

const switchEntryMode = (mode) => {
  if (entryMode.value === mode) return
  const confirmSwitch = () => {
    resetFormFields()
    // 日志解析结果暂存：不清空 ecResults/ecQuery/extractedCodes，切换回来仍可见
    entryMode.value = mode
  }
  if (isFormDirty()) {
    ElMessageBox.confirm('切换录入模式将清空当前已填写的内容（日志解析结果会保留），是否继续？', '切换确认', {
      confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning',
    }).then(confirmSwitch).catch(() => {})
  } else {
    confirmSwitch()
  }
}

// 清洗日志：去掉时间戳/日期等无关信息，保留故障/报警描述供自动回填基本信息
const cleanLogText = (text) => (text || '')
  .replace(/\d{4}[-/.].\d{1,2}[-/.].\d{1,2}[ T]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?/g, ' ')
  .replace(/\d{4}[-/.].\d{1,2}[-/.].\d{1,2}/g, ' ')
  .replace(/\b\d{1,2}:\d{2}(:\d{2})?(\.\d+)?\b/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()

// 日志原文检索：抠码 + 手册情形匹配 + 工单案例
const ecSearch = async () => {
  const q = ecQuery.value.trim()
  if (!q) {
    ElMessage.warning('请粘贴服务器日志原文')
    return
  }
  ecSearching.value = true
  ecError.value = ''
  try {
    const lookupData = await request.post('/search/manual-lookup', { query: q, top_k: 5 }, { timeout: 60000 });
    // 情形勾选初始化：命中情形（signal 带 [命中] 标记）默认勾选
    (lookupData.manual_items || []).forEach(m => {
      m._selected = (m.conditions || [])
        .map((c, i) => (c.signal || '').includes('[命中]') ? i : -1)
        .filter(i => i >= 0)
    })
    ecResults.value = lookupData
    // 自动回填基本信息：
    //  1) 故障描述：优先取手册命中的故障名称（更精炼），否则用清洗无关时间戳/日期后的日志原文
    //  2) 设备类型：优先取手册/案例命中的 device_type
    //  3) 报警码：回填到 extractedCodes / device_error_code
    if (!form.fault_description) {
      const manualTitle = lookupData.manual_items?.[0]?.title?.trim()
      const cleaned = cleanLogText(q)
      form.fault_description = (manualTitle || cleaned || '')
    }
    const devType = (lookupData.manual_items?.[0]?.device_type) || (lookupData.case_items?.[0]?.device_type)
    if (devType && !form.device_id) form.device_type = devType
    if (lookupData.error_codes?.length) {
      extractedCodes.value = lookupData.error_codes
      form.device_error_code = lookupData.error_codes.join(',')
      // 同步到 fault_code，避免提交时故障码为空仍需手动重新输入
      const inCodes = Array.isArray(form.fault_code) ? form.fault_code : []
      for (const c of lookupData.error_codes) {
        if (!inCodes.includes(c)) inCodes.push(c)
      }
      form.fault_code = inCodes
    }
  } catch (e) {
    ecError.value = '检索失败：' + ((e.response?.data?.detail) || (e && e.stack) || e.message || '请稍后重试')
  } finally {
    ecSearching.value = false
  }
}

const syncExtractedCodes = () => {
  const codes = extractedCodes.value
  form.device_error_code = codes.join(',')
  // 同步到 fault_code，保证日志录入自动填入后提交无缺失
  const inCodes = (Array.isArray(form.fault_code) ? form.fault_code : []).filter(c => codes.includes(c))
  for (const c of codes) { if (!inCodes.includes(c)) inCodes.push(c) }
  form.fault_code = inCodes
}
// 监听 extractedCodes 变化，自动同步到 form.device_error_code（确保故障码联动）
watch(extractedCodes, () => { syncExtractedCodes() }, { deep: true })
const removeExtractedCode = (c) => { extractedCodes.value = extractedCodes.value.filter(x => x !== c); syncExtractedCodes() }
const addManualCode = () => {
  const c = (manualCodeInput.value || '').trim().toUpperCase()
  if (!c) return
  if (!extractedCodes.value.includes(c)) {
    extractedCodes.value.push(c)
    syncExtractedCodes()
  }
  manualCodeInput.value = ''
}

// 错误码去重累计（逗号分隔）
const addDeviceErrorCode = (code) => {
  const c = (code || '').trim().toUpperCase()
  if (!c) return
  const existing = (form.device_error_code || '').split(',').map(x => x.trim().toUpperCase()).filter(Boolean)
  if (!existing.includes(c)) existing.push(c)
  form.device_error_code = existing.join(',')
}

// 选用手册条目：勾选的情形 → 预填工单（日志原文落库留痕）
const applyManualItem = (m) => {
  addDeviceErrorCode(m.error_code)
  if (m.device_type && !form.device_type) form.device_type = m.device_type
  form.log_text = ecQuery.value.trim()
  const selected = (m._selected || []).map(i => (m.conditions || [])[i]).filter(Boolean)
  if (selected.length) {
    form.fault_description = `${m.title}：${selected[0].cause || m.description || ''}`
    if (m.message_text && !form.fault_phenomenon) form.fault_phenomenon = `日志原文：${m.message_text}`
    form.solution_steps = selected.map(c => c.steps).filter(Boolean).join('\n')
  } else {
    form.fault_description = m.title || m.description || form.fault_description
    if (m.description && !form.fault_phenomenon) form.fault_phenomenon = m.description
    if (m.solutions) form.solution_steps = m.solutions
  }
  ElMessage.success(`已选用手册方案：${m.error_code} ${m.title}`)
}

// 引用工单案例：预填故障描述与故障码，处理步骤供参考
const applyCaseItem = (c) => {
  form.fault_description = c.title || form.fault_description
  if (c.device_type && !form.device_type) form.device_type = c.device_type
  if (c.fault_code && !form.fault_code.includes(c.fault_code)) form.fault_code.push(c.fault_code)
  ElMessage.success(`已引用案例：${c.title}`)
}
const archiving = ref(false)
const archiveCheckResult = ref(null)
const archiveDialog = reactive({ visible: false, result: null })
const canArchiveComplete = computed(() => !!archiveCheckResult.value?.passed && (!form.customer_id || form.customer_accept_status === 'ACCEPTED'))
const deviceMaintenance = ref(null)
const deviceTypeOptions = ref([...DEFAULT_DEVICE_TYPES])
const deviceTypeFiltered = ref([...DEFAULT_DEVICE_TYPES])
const faultCodeOptions = ref([])
const faultCodeFiltered = ref([])
const aiDialog = reactive({ visible: false, input: '', messages: [], loading: false })
const aiMsgRef = ref(null)
const knowledgeDialog = reactive({ visible: false, keyword: '', results: [], searching: false })
const faultCodeDialog = reactive({ visible: false, description: '', creating: false, result: null })

const selectedDevice = computed(() => {
  // form 是 reactive 对象（无 .value），直接用 form.device_id
  if (!form.device_id) return null
  const d = devices.value.find(d => d.id === form.device_id)
  if (d) return d
  // 备选：deviceFiltered（远程检索可能引入 devices.value 之外的新数据）
  return deviceFiltered.value.find(d => d.id === form.device_id) || null
})
const deviceName = computed(() => {
  if (!form.device_id) return '-'
  if (selectedDevice.value) return selectedDevice.value.device_name
  // 兜底：设备不在本地列表时，用后端详情接口返回的设备名称
  return form.device_name || form.device_code || '-'
})
const devStatusLabel = (s) => ({ ONLINE: '正常', OFFLINE: '离线', ALARM: '告警', FAULT: '故障', UNKNOWN: '未知' }[s] || '未知')
const devStatusTagType = (s) => ({ ONLINE: 'success', OFFLINE: 'info', ALARM: 'warning', FAULT: 'danger' }[s] || 'info')

const displayFaultCodes = computed(() => {
  const c = form.fault_code
  if (!c) return ''
  if (Array.isArray(c)) return c.join(', ')
  return c
})

const technicianName = computed(() => {
  // 优先用后端返回的 technician_name（确保个人中心改名字后工单同步）
  if (form.technician_name) return form.technician_name
  if (!form.technician_id) return '-'
  const u = users.value.find(u => u.id === form.technician_id)
  return u ? u.real_name : '-'
})

const currentUserName = computed(() => {
  try {
    const raw = localStorage.getItem('current_user')
    if (raw) {
      const u = JSON.parse(raw)
      return u.name || u.real_name || ''
    }
  } catch {}
  return ''
})

// 新建时显示当前登录用户；查看/编辑时显示工单维修员（=创建者）
const technicianDisplay = computed(() => {
  if (isNew.value) return currentUserName.value
  return form.technician_id ? technicianName.value : '-'
})

const statusMap = {
  DRAFT: '草稿', SUBMITTED: '待派工', ASSIGNED: '已派单', ACCEPTED: '已接单',
  ARRIVED: '已到达', INSPECTING: '检查中', IN_PROGRESS: '维修中',
  ARCHIVING: '待归档', ARCHIVED: '已归档', COMPLETED: '已完成', REJECTED: '已退回'
}
const GROUP_LABEL = {
  DRAFT: '草稿', SUBMITTED: '待派工',
  ASSIGNED: '处理中', ACCEPTED: '处理中', ARRIVED: '处理中', INSPECTING: '处理中', IN_PROGRESS: '处理中',
  ARCHIVING: '待归档', COMPLETED: '待归档', ARCHIVED: '已归档', REJECTED: '已退回',
}
const statusGroupLabel = computed(() => GROUP_LABEL[form.status] || form.status || '')

const statusLabel = computed(() => statusMap[form.status] || form.status || '-')
const statusTagType = computed(() => {
  const map = {
    DRAFT: 'info', SUBMITTED: 'info', ASSIGNED: 'primary', ACCEPTED: 'primary',
    ARRIVED: 'primary', INSPECTING: 'warning', IN_PROGRESS: 'warning',
    ARCHIVING: 'warning', ARCHIVED: 'success', COMPLETED: 'success', REJECTED: 'danger'
  }
  return map[form.status] || 'info'
})

const repairResultLabel = computed(() => {
  const map = { PERMANENT_FIX: '彻底修复', TEMPORARY_FIX: '临时措施', UNABLE_FIX: '未能修复' }
  return map[form.repair_result] || form.repair_result || ''
})
const repairResultTagType = computed(() => {
  const map = { PERMANENT_FIX: 'success', TEMPORARY_FIX: 'warning', UNABLE_FIX: 'danger' }
  return map[form.repair_result] || 'info'
})

// 时间块列数跟随实际有值的时间点，避免草稿态只有一个格子却占半行空白
const timeColCount = computed(() => {
  let n = 1 // 创建时间始终有
  if (form.dispatched_at) n += 1
  if (claimTime.value || form.status === 'ASSIGNED') n += 1
  if (form.start_time) n += 1
  if (form.resolved_at) n += 1
  if (form.hold_total_minutes) n += 1
  return Math.min(Math.max(n, 1), 3)
})

// ===== 处理进度时间线 =====
// 后端 GET /work-orders/{id} 已返回 progress_logs，按时间正序展示
// 注意：一次「开始处理」会连写多条日志，created_at 可能落在同一毫秒，
// 用日期排序会乱序，这里以自增 id 为准（id 与写入顺序一致）
const progressLogs = computed(() => {
  const rows = Array.isArray(form.progress_logs) ? form.progress_logs : []
  return [...rows].sort((a, b) => {
    const ia = Number(a.id) || 0
    const ib = Number(b.id) || 0
    if (ia && ib && ia !== ib) return ia - ib
    return new Date(a.created_at || 0) - new Date(b.created_at || 0)
  })
})

const SOURCE_LABEL = {
  WEB: '网页端', DINGTALK: '钉钉', MOBILE: '移动端',
  CUSTOMER: '客户门户', IMPORT: '历史导入', SYSTEM: '系统',
  TECH_CLAIM: '技术员抢单', TECH_ACCEPT: '技术员接单', TECH_REJECT: '技术员拒收',
  TECH_START: '技术员开始处理', TECH_COMPLETE: '技术员提交完成',
  SUPERVISOR_DISPATCH: '主管派工', AUTO_DISPATCH: '自动派工',
}
const sourceLabel = (s) => SOURCE_LABEL[s] || s || '网页端'

// 时间线圆点配色：与状态标签同一套语义
const tlTone = (st) => {
  const map = {
    DRAFT: 'info', SUBMITTED: 'info',
    ASSIGNED: 'primary', ACCEPTED: 'primary', ARRIVED: 'primary',
    INSPECTING: 'warning', IN_PROGRESS: 'warning', ARCHIVING: 'warning',
    ARCHIVED: 'success', COMPLETED: 'success', REJECTED: 'danger',
  }
  return map[st] || 'info'
}

// 时间线渲染行：把完整时间拆成「左列 HH:mm + 跨天日期分隔」，
// 同一天不再每行重复日期，横向空间留给状态和操作人
const pad2 = (n) => String(n).padStart(2, '0')
const dayKeyOf = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
const dayLabelOf = (d) => {
  const wd = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()]
  const today = new Date()
  const yest = new Date(today.getTime() - 86400000)
  if (dayKeyOf(d) === dayKeyOf(today)) return `今天 · ${wd}`
  if (dayKeyOf(d) === dayKeyOf(yest)) return `昨天 · ${wd}`
  return `${dayKeyOf(d)} · ${wd}`
}
// 相邻两步的间隔：看时间都花在哪一步（卡住的环节一眼可见）
const fmtDelta = (ms) => {
  if (ms == null || ms < 0) return ''
  // 不足 1 分钟不显示：一次操作连写的几条日志本来就同时发生，标出来只是噪声
  if (ms < 60000) return ''
  const m = Math.round(ms / 60000)
  if (m < 60) return `${m} 分`
  const h = Math.floor(m / 60)
  const r = m % 60
  return r ? `${h} 时 ${r} 分` : `${h} 时`
}
const progressRows = computed(() => {
  const list = progressLogs.value
  let lastKey = ''
  let prevDate = null
  return list.map((lg, i) => {
    const d = lg.created_at ? new Date(lg.created_at) : null
    const ok = d && !isNaN(d)
    const key = ok ? dayKeyOf(d) : ''
    const showDate = !!key && key !== lastKey
    if (key) lastKey = key
    const row = {
      ...lg,
      _time: ok ? `${pad2(d.getHours())}:${pad2(d.getMinutes())}` : '--:--',
      _date: showDate ? dayLabelOf(d) : '',
      _delta: ok && prevDate ? fmtDelta(d - prevDate) : '',
      _isLast: i === list.length - 1,
      // from == to：不是状态变化，只是挂起 / 备注 / 改派一类的过程记录
      _noChange: !!lg.from_status && lg.from_status === lg.to_status,
    }
    if (ok) prevDate = d
    return row
  })
})

// 折叠：超过 TL_MAX 条时只显示最近的，避免时间线过长把附件区挤到屏幕外
const TL_MAX = 8
const tlExpanded = ref(false)
const tlRows = computed(() => {
  const all = progressRows.value
  if (tlExpanded.value || all.length <= TL_MAX) return all
  const tail = all.slice(-TL_MAX)
  // 截断后第一行可能丢了所属日期分隔，补一个
  if (tail.length && !tail[0]._date) {
    const d = tail[0].created_at ? new Date(tail[0].created_at) : null
    if (d && !isNaN(d)) {
      tail[0] = { ...tail[0], _date: dayLabelOf(d) }
    }
  }
  return tail
})

// ===== 现场照片 / 附件汇总 =====
// 三个来源：工单 fault_media（移动端上报）、工单 attachments（处理附件）、进度日志 attachments（各节点上传）
const _IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp|heic)$/i
const isImageFile = (f) => {
  if (!f) return false
  if (f.type === 'image') return true
  if (f.type === 'video') return false
  return _IMAGE_EXT.test(f.url || '')
}

const allAttachments = computed(() => {
  const out = []
  const seen = new Set()
  const push = (raw, stage) => {
    const f = typeof raw === 'string' ? { url: raw } : (raw || {})
    const url = f.url || f.path || f.src
    if (!url || seen.has(url)) return
    seen.add(url)
    const image = isImageFile({ url, type: f.type })
    out.push({
      url,
      name: f.name || (image ? '现场照片' : '现场视频'),
      type: f.type,
      stage,
    })
  }
  if (Array.isArray(form.fault_media)) form.fault_media.forEach((x) => push(x, '报修'))
  if (Array.isArray(form.attachments)) form.attachments.forEach((x) => push(x, '维修'))
  progressLogs.value.forEach((lg) => {
    if (Array.isArray(lg.attachments)) {
      lg.attachments.forEach((x) => push(x, statusMap[lg.to_status] || lg.to_status))
    }
  })
  return out
})

const loadDeviceTypes = async () => {
  try {
    const res = await request.get('/categories/', { params: { category_type: 'DEVICE_TYPE', page_size: 1000 } })
    const items = flattenTree(res.items || [])
    if (items.length > 0) {
      deviceTypeOptions.value = items
      deviceTypeFiltered.value = items
    }
  } catch { /* ignore */ }
}

const fetchFaultCodes = async () => {
  try {
    const res = await request.get('/fault-codes/', { params: { page_size: 200 } })
    faultCodeOptions.value = (res.items || []).map(item => ({
      code: item.fault_code,
      desc: item.fault_description,
    }))
    faultCodeFiltered.value = faultCodeOptions.value
  } catch { /* ignore */ }
}

// 故障码下拉联合搜索：输入可同时匹配「故障码」或「描述」
const filterFaultCodes = (query) => {
  if (!query) {
    faultCodeFiltered.value = faultCodeOptions.value
    return
  }
  const q = query.trim().toLowerCase()
  faultCodeFiltered.value = faultCodeOptions.value.filter(o =>
    (o.code || '').toLowerCase().includes(q) || (o.desc || '').toLowerCase().includes(q)
  )
}

const fetchFaultPhenomena = async (deviceType) => {
  try {
    const params = {}
    if (deviceType) params.device_type = deviceType
    const res = await request.get('/categories/data/fault-phenomena', { params })
    faultPhenomenaOptions.value = res.data || []
  } catch { faultPhenomenaOptions.value = [] }
}

const fetchRootCauses = async () => {
  try {
    const res = await request.get('/categories/data/root-causes')
    rootCauseOptions.value = res.data || []
  } catch { rootCauseOptions.value = [] }
}

const onFaultPhenomenonSelect = (val) => {
  if (!val) {
    form.fault_phenomenon = ''
    return
  }
  const hit = FAULT_PHENOMENA.find((p) => p.value === val)
  form.fault_phenomenon = hit ? hit.label : String(val)
}

const onDeviceChange = async (deviceId) => {
  if (!deviceId) {
    form.device_type = ''
    form.location = ''
    deviceMaintenance.value = null
    fetchFaultPhenomena()
    return
  }
  const d = devices.value.find(d => d.id === deviceId)
  if (d) {
    form.device_type = d.device_type || ''
    form.location = d.location || ''
    fetchFaultPhenomena(d.device_type)
  }
  try {
    const res = await request.get(`/devices/${deviceId}/maintenance-summary`)
    deviceMaintenance.value = res
  } catch { deviceMaintenance.value = null }
}

const onFaultPhenomenonChange = (val) => {
  if (val && val.length >= 2) {
    form.fault_category = val[0]
    form.fault_phenomenon_type = val.join(' > ')
  } else if (val && val.length === 1) {
    form.fault_category = val[0]
    form.fault_phenomenon_type = val[0]
  } else {
    form.fault_category = ''
    form.fault_phenomenon_type = ''
  }
}

const onRootCauseChange = (val) => {
  if (val && val.length >= 2) {
    form.root_cause_category = val[0]
    form.root_cause_type = val.join(' > ')
  } else if (val && val.length === 1) {
    form.root_cause_category = val[0]
    form.root_cause_type = val[0]
  } else {
    form.root_cause_category = ''
    form.root_cause_type = ''
  }
}

const onRepairResultChange = (val) => {
  if (val !== 'TEMPORARY_FIX' && val !== 'UNABLE_FIX') {
    form.follow_up_plan = ''
  }
}

const calcWorkHours = () => {
  if (timeRange.value && timeRange.value.length === 2 && timeRange.value[0] && timeRange.value[1]) {
    const diff = timeRange.value[1].getTime() - timeRange.value[0].getTime()
    form.work_hours = Math.round((diff / (1000 * 60 * 60)) * 10) / 10
  } else {
    form.work_hours = null
  }
}

const uploadFile = async (option) => {
  const formData = new FormData()
  formData.append('file', option.file)
  try {
    const res = await request.post('/upload/work-order-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    attachments.value.push({ url: res.url, name: res.name, type: res.type, source: 'REPAIR' })
    attachDirty.value = true
    option.onSuccess(res)
  } catch (e) {
    option.onError(e)
    ElMessage.error('文件上传失败')
  }
}

const beforeUpload = (file) => {
  const maxSize = 50 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.warning('文件大小不能超过 50MB')
    return false
  }
  return true
}

const removeAttachment = (uploadFile) => {
  const idx = attachments.value.findIndex(f => f.name === uploadFile.name)
  if (idx >= 0) { attachments.value.splice(idx, 1); attachDirty.value = true }
}

const openKnowledgeRef = () => {
  knowledgeDialog.keyword = [form.fault_description, form.fault_phenomenon_type, form.device_type]
    .filter(Boolean).join(' ')
  knowledgeDialog.results = []
  knowledgeDialog.visible = true
  if (knowledgeDialog.keyword) searchSolutions()
}

const searchSolutions = async () => {
  if (!knowledgeDialog.keyword.trim()) return
  knowledgeDialog.searching = true
  try {
    const params = { keyword: knowledgeDialog.keyword.trim(), top_k: 10 }
    if (form.device_type) params.device_type = form.device_type
    const res = await request.get('/knowledge/solutions', { params })
    knowledgeDialog.results = res.results || []
  } catch {
    ElMessage.error('搜索失败')
    knowledgeDialog.results = []
  } finally {
    knowledgeDialog.searching = false
  }
}

const applySolution = (item) => {
  form.solution_steps = item.solution_steps || ''
  form.solution_ref_knowledge_id = item.knowledge_id
  knowledgeDialog.visible = false
  ElMessage.success(`已引用知识库方案: ${item.title}`)
}

const applyAIFields = () => {
  if (!analysisResult.value) return
  const a = analysisResult.value
  if (a.standardized_fault_code && (!form.fault_code || (Array.isArray(form.fault_code) && form.fault_code.length === 0))) {
    form.fault_code = [a.standardized_fault_code]
  }
  if (a.device_type && !form.device_type) form.device_type = a.device_type
  if (a.standardized_fault_phenomenon && !form.fault_phenomenon_type) {
    form.fault_phenomenon_type = a.standardized_fault_phenomenon
  }
  if (a.standardized_solution_steps && !form.solution_steps) {
    form.solution_steps = a.standardized_solution_steps
  }
  ElMessage.success('AI 推荐字段已填充')
}

const searchDevices = (query) => {
  if (!query) { deviceFiltered.value = devices.value; return }
  const q = query.toLowerCase()
  deviceFiltered.value = devices.value.filter(d =>
    (d.device_name && d.device_name.toLowerCase().includes(q)) ||
    (d.device_code && d.device_code.toLowerCase().includes(q))
  )
}

const disabledDate = (time) => time.getTime() > Date.now()

const saveForm = async () => {
  try {
    const validFields = [
      'device_id','device_type','fault_object','fault_code','fault_description','fault_phenomenon',
      'fault_category','fault_phenomenon_type','priority',
      'order_type','service_mode','need_rma','gpu_index','fault_device_sn',
      'root_cause','root_cause_category','root_cause_type',
      'solution_steps','solution_ref_knowledge_id',
      'repair_result','follow_up_plan','work_hours',
      'assignee_id',
      'location','status','tags','attachments',
      'device_error_code','log_text',
    ]
    const data = { fault_description: form.fault_description || '' }
    for (const k of validFields) {
      let val = form[k]
      if (val === undefined || val === null) continue
      if (k === 'fault_code') {
        if (Array.isArray(val) && val.length > 0) {
          data[k] = val.join(',')
        }
        continue
      }
      if (val !== '') data[k] = val
    }
    if (timeRange.value) {
      data.start_time = timeRange.value[0]?.toISOString()
      data.end_time = timeRange.value[1]?.toISOString()
    }
    // 附件：有变更时按当前列表整体覆盖（可清空为空数组），无变更且非空时也带上
    if (attachDirty.value || attachments.value.length) data.attachments = [...legacyAttachments.value, ...attachments.value]

    if (isNew.value) {
      const res = await request.post('/work-orders/', data)
      form.id = res.id
      attachDirty.value = false
      router.replace(`/work-orders/${res.id}?edit=1`)
      return res
    } else {
      const res = await request.put(`/work-orders/${route.params.id}`, data)
      attachDirty.value = false
      return res
    }
  } catch (e) {
    ElMessage.error('保存失败')
    throw e
  }
}

// 归档：先校验，再在弹窗里确认；按钮只保留详情页右上角一个
const openArchiveDialog = async () => {
  archiving.value = true
  try {
    const id = route.params.id || form.id
    const res = await request.post(`/work-orders/${id}/archive-check`)
    archiveCheckResult.value = res
    archiveDialog.result = res
    archiveDialog.visible = true
    if (res.passed) {
      ElMessage.success(`归档校验通过（完成度 ${Math.round(res.completeness * 100)}%）`)
    } else {
      ElMessage.warning(`归档完成度不足（${Math.round(res.completeness * 100)}%），缺失：${(res.missing_fields || []).join('、')}`)
    }
  } catch { /* 错误提示由请求拦截器统一处理 */ }
  finally { archiving.value = false }
}

const goEditFromArchive = () => {
  archiveDialog.visible = false
  if (canEditWorkOrder.value) goEdit()
}

const handleArchiveComplete = async () => {
  if (!canArchiveComplete.value) return
  archiving.value = true
  try {
    const id = route.params.id || form.id
    await request.post(`/work-orders/${id}/archive-complete`, null, { timeout: 120000 })
    archiveDialog.visible = false
    ElMessage.success('工单归档完成，知识已收录')
    goBackToList()
  } catch { /* 错误提示由请求拦截器统一处理 */ }
  finally { archiving.value = false }
}

// AI 校验返回的英文字段名 -> 中文展示
const fieldLabelMap = {
  fault_description: '故障描述',
  fault_code: '故障码',
  fault_phenomenon: '故障现象',
  root_cause: '根本原因',
  solution_steps: '处理步骤',
  repair_result: '维修结果',
  device_id: '关联服务器',
  work_hours: '工时',
}

const handleAnalyze = async () => {
  if (!form.fault_description) {
    ElMessage.warning('请填写故障描述')
    return
  }
  analyzing.value = true
  try {
    try { await saveForm() } catch { analyzing.value = false; return }
    const targetId = route.params.id || form.id
    if (!targetId) {
      ElMessage.warning('请先保存工单基本信息')
      analyzing.value = false
      return
    }
    const res = await request.post(`/work-orders/${targetId}/analyze`, null, { timeout: 60000 })
    analysisResult.value = res
    ElMessage.success('AI 校验完成')
  } catch { ElMessage.error('AI 校验失败') }
  finally { analyzing.value = false }
}

const scrollToFirstError = () => {
  nextTick(() => {
    const el = document.querySelector('.el-form-item.is-error')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
}

const handleSubmit = async () => {
  if (!canSubmit.value) return
  // 补充信息选填：根因未填时仅文字提醒，不阻塞提交
  if (supplementActive() && !hasRootCause()) {
    ElMessage.info('提醒：补充信息中根本原因尚未填写，建议补充后再提交')
  }
  try {
    await ElMessageBox.confirm(
      '确认提交该工单？提交后系统将自动提取知识并上传到公司知识库。',
      '提交确认',
      { confirmButtonText: '确认提交', cancelButtonText: '取消', type: 'warning', customClass: 'submit-confirm-dialog' }
    )
  } catch { return }
  submitting.value = true
  try {
    // 提交完成时：没填结束时间就取当前时间，并自动算工时
    if (!form.end_time) {
      const start = form.start_time || form.first_response_at || form.created_at
      if (start) {
        timeRange.value = [dayjs(start).toDate(), new Date()]
        calcWorkHours()
      }
    }
    const id = route.params.id || form.id
    await saveForm()
    const res = await request.post(`/work-orders/${id}/complete`, null, { timeout: 120000 })
    ElMessage.success(res.message || '工单已提交完成，进入待归档；AI 分析与知识收录在后台进行')
    // 提交完成就离开当前页：从客户页进来的回客户，其余回工单列表
    goBackToList()
  } catch (e) {
    const msg = (e && e.response && e.response.data && (e.response.data.detail || e.response.data.message))
      || (e && e.message) || '未知错误'
    ElMessage.error('提交失败：' + msg)
    scrollToFirstError()
  }
  finally { submitting.value = false }
}

const handleSaveDraft = async () => {
  saving.value = true
  try {
    await saveForm()
    if (form.status === 'ARCHIVED') {
      ElMessage.success('修改已保存，已写入修改记录')
      loadEditLogs()
    } else {
      ElMessage.success('草稿已保存')
    }
  } catch { scrollToFirstError() }
  finally { saving.value = false }
}

// 提交报修：保存后把 DRAFT → SUBMITTED（不再依赖后端"保存即改状态"的隐式行为）
const submitChoice = reactive({ visible: false })
const isSelfCreatedTech = computed(() =>
  currentUserRole === 'TECHNICIAN' && (isNew.value || Number(form.created_by) === currentUserId))

const handleSubmitReport = () => {
  if (isSelfCreatedTech.value) {
    submitChoice.visible = true
    return
  }
  doSubmitReport(false)
}

const doSubmitReport = async (toPool) => {
  submitChoice.visible = false
  submitting.value = true
  try {
    const res = await saveForm()
    const id = (res && res.id) || route.params.id || form.id
    const tr = await request.post(`/work-orders/${id}/transition`, {
      to_status: 'SUBMITTED',
      remark: toPool ? '提交报修并放入工单池' : '提交报修',
      to_pool: toPool || undefined,
      source: 'WEB',
    })
    if (tr && tr.status === 'ACCEPTED') {
      ElMessage.success('已提交并自动接单，可在「我的工单」直接开始处理')
      router.push('/orders?tab=mine')
      return
    }
    if (toPool) {
      ElMessage.success('已提交报修并放入工单池，等待接单/派工')
      router.push('/orders?tab=pool')
      return
    }
    ElMessage.success('已提交报修，等待主管派工')
    form.status = 'SUBMITTED'
    router.push(['ADMIN', 'SUPERVISOR'].includes(currentUserRole) ? '/orders?tab=list' : '/orders?tab=mine')
  } catch (e) {
    const msg = (e && e.response && e.response.data && (e.response.data.detail || e.response.data.message))
      || (e && e.message) || '未知错误'
    ElMessage.error('提交报修失败：' + msg)
    scrollToFirstError()
  } finally { submitting.value = false }
}

const handleCreateFaultCode = async () => {
  if (!faultCodeDialog.description.trim()) {
    ElMessage.warning('请填写故障描述')
    return
  }
  faultCodeDialog.creating = true
  try {
    const res = await request.post('/fault-codes/create', {
      fault_description: faultCodeDialog.description.trim(),
      device_type: form.device_type || undefined,
    })
    faultCodeDialog.result = res
    fetchFaultCodes()
    if (res.is_new) {
      ElMessage.success(`新故障码 ${res.fault_code} 已自动生成`)
    } else {
      ElMessage.info(res.duplicate_hint)
    }
  } catch (e) {
    ElMessage.error('新增故障码失败')
  } finally {
    faultCodeDialog.creating = false
  }
}

const confirmFaultCodeResult = () => {
  if (faultCodeDialog.result && faultCodeDialog.result.fault_code) {
    const code = faultCodeDialog.result.fault_code
    if (!form.fault_code.includes(code)) {
      form.fault_code.push(code)
    }
  }
  faultCodeDialogClose()
}

const faultCodeDialogClose = () => {
  faultCodeDialog.visible = false
  setTimeout(() => {
    faultCodeDialog.description = ''
    faultCodeDialog.result = null
  }, 200)
}

// 保留 AI 弹窗内最近 3 次分析的对话历史（每次分析 = 1 条 user + 1 条 assistant）
const trimAiHistory = () => {
  const userIdx = []
  aiDialog.messages.forEach((m, i) => { if (m.role === 'user') userIdx.push(i) })
  if (userIdx.length > 3) {
    const keepFrom = userIdx[userIdx.length - 3]
    aiDialog.messages.splice(0, keepFrom)
  }
}

const askAI = async (type) => {
  if (form.fault_description) {
    try { await saveForm() } catch { /* ignore */ }
  }

  let context = `我正在填写维修工单，请帮我分析：\n`
  if (form.device_id) {
    const d = devices.value.find(d => d.id === form.device_id)
    context += `设备：${d?.device_name || '未知'}\n`
  }
  if (form.device_type) context += `设备类型：${form.device_type}\n`
  if (form.location) context += `位置：${form.location}\n`
  context += `故障描述：${form.fault_description || '（未填写）'}\n`
  if (form.fault_phenomenon_type) context += `故障现象分类：${form.fault_phenomenon_type}\n`
  if (form.fault_phenomenon) context += `故障现象补充：${form.fault_phenomenon}\n`

  if (type === 'diagnosis') {
    if (form.root_cause_type) context += `根本原因分类：${form.root_cause_type}\n`
    if (form.root_cause) context += `根本原因说明：${form.root_cause}\n`
    if (form.solution_steps) context += `处理步骤：${form.solution_steps}\n`
    if (form.fault_code && (Array.isArray(form.fault_code) ? form.fault_code.length : form.fault_code)) {
      const codes = Array.isArray(form.fault_code) ? form.fault_code.join(', ') : form.fault_code
      context += `故障码：${codes}\n`
    }
    context += `\n请根据以上信息分析可能的根本原因，并推荐处理方案。`
  } else {
    context += `\n请帮我分析故障分类、可能原因，并给出诊断建议（包括可能的故障码）。`
  }

  // 标准录入 & 日志录入统一：把已填好的故障信息预填到输入框，弹窗打开但不自动发送，
  // 等待用户修改后点击「发送」；历史保留最近 3 次已发送的分析
  aiDialog.input = context
  aiDialog.visible = true
}

const sendAIMessage = async () => {
  const text = aiDialog.input.trim()
  const lastMsg = aiDialog.messages[aiDialog.messages.length - 1]
  const autoSend = !text && lastMsg && lastMsg.role === 'user'
  if (text) {
    aiDialog.messages.push({ role: 'user', content: text })
    aiDialog.input = ''
  } else if (!autoSend) {
    return
  }
  trimAiHistory()

  const question = aiDialog.messages[aiDialog.messages.length - 1].content
  const aiMsg = { role: 'assistant', content: '' }
  aiDialog.messages.push(aiMsg)
  aiDialog.loading = true

  try {
    const response = await fetch('/api/v1/search/answer/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': localStorage.getItem('auth_token') ? `Bearer ${localStorage.getItem('auth_token')}` : ''
      },
      body: JSON.stringify({ question, top_k: 5, device_type: form.device_type || null }),
    });

    if (!response.ok) {
      aiMsg.content = '请求失败，请稍后重试。'
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const data = JSON.parse(line.slice(6))
          if (data.type === 'answer' && data.content) {
            aiMsg.content += data.content
          }
        } catch { /* skip */ }
      }
      await nextTick()
      if (aiMsgRef.value) aiMsgRef.value.scrollTop = aiMsgRef.value.scrollHeight
    }

    if (!aiMsg.content) aiMsg.content = '抱歉，无法生成回答。'
  } catch (e) {
    console.error('AI 发送失败:', e)
    aiMsg.content = '请求失败，请稍后重试。'
  } finally {
    aiDialog.loading = false
    await nextTick()
    if (aiMsgRef.value) aiMsgRef.value.scrollTop = aiMsgRef.value.scrollHeight
  }
}


const printing = ref(false)
const printPdf = async () => {
  if (!form.id) return
  printing.value = true
  try {
    await downloadFile(`/work-orders/${form.id}/pdf`, {},
                       `工单-${form.work_order_no || form.id}.pdf`)
  } catch (e) {
    ElMessage.error('PDF 生成失败')
  } finally {
    printing.value = false
  }
}


const starting = ref(false)
const HOLD_LABELS = { VENDOR: '等厂商', SPARE: '等备件', CUSTOMER: '等客户', IDC: '等 IDC', OTHER: '其他' }
const holdLabel = computed(() => HOLD_LABELS[form.hold_reason] || '其他')
const canHold = computed(() => ['ACCEPTED', 'ARRIVED', 'INSPECTING', 'IN_PROGRESS'].includes(form.status)
  && (isMyTask.value || canDispatch.value))

// 编辑权限：技术员只能编辑自己创建的工单；管理员/主管可编辑所有工单。
// 被指派的技术员虽然不能改基本信息，但维修中仍可通过「填写结果并完成」进入完成表单。
const isCreator = computed(() =>
  !!currentUserId && Number(form.created_by) === Number(currentUserId))
const canEditWorkOrder = computed(() => {
  const finished = ['ARCHIVED', 'REJECTED', 'COMPLETED'].includes(form.status)
  if (finished) return canDispatch.value
  return canDispatch.value || isCreator.value
})
const canCompleteRepair = computed(() =>
  form.status === 'IN_PROGRESS' && (isMyTask.value || canDispatch.value || isCreator.value))
// 查看页「上传附件」弹窗：每选一张就 上传文件 → 挂工单，两步都在服务端完成，
// 不经过 saveForm，所以不会因为别的必填项没填而传不上去
const uploadDialog = reactive({ visible: false, count: 0, busy: 0 })
const openUploadDialog = () => {
  uploadDialog.count = 0
  uploadDialog.busy = 0
  uploadDialog.visible = true
}
const uploadOne = async (option) => {
  uploadDialog.busy++
  try {
    const fd = new FormData()
    fd.append('file', option.file)
    const up = await request.post('/upload/work-order-image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const res = await request.post(`/work-orders/${form.id}/attachments`, {
      url: up.url, name: up.name, type: up.type,
    })
    form.attachments = res.attachments || []
    uploadDialog.count++
    ElMessage.success(`${up.name} 已上传`)
    option.onSuccess(up)
  } catch (e) {
    option.onError(e)
    ElMessage.error('上传失败，请重试')
  } finally {
    uploadDialog.busy--
  }
}

const goEdit = () => router.push(`/work-orders/${form.id}?edit=1`)

const canRma = computed(() => {
  if (!['ACCEPTED', 'ARRIVED', 'INSPECTING', 'IN_PROGRESS'].includes(form.status)) return false
  // 已标记需返厂 / 服务方式本身是返厂 → 显示
  if (form.need_rma || form.service_mode === 'RMA') return true
  // 远程处理默认不出现 RMA（远程不可能返厂；确需返厂先改服务方式）
  if (form.service_mode === 'REMOTE') return false
  return canDispatch.value
})
const holdDlg = reactive({ visible: false, reason: 'VENDOR', remark: '' })
const holdSaving = ref(false)
const RMA_STATUS_OPTIONS = [
  { value: 'PENDING', label: '待寄出' }, { value: 'SHIPPED', label: '已寄出' },
  { value: 'RECEIVED', label: '厂商已收' }, { value: 'REPAIRED', label: '已修复' },
  { value: 'RETURNED', label: '已返回' }, { value: 'CLOSED', label: '已关闭' },
]
const rmaDlg = reactive({
  visible: false, vendor: '', rma_no: '', status: 'PENDING', shipped_at: null,
  vendor_received_at: null, returned_at: null, replacement_sn: '', remark: '', saving: false,
})
const rmaStatusLabel = (s) => (RMA_STATUS_OPTIONS.find((x) => x.value === s)?.label || s || '-')
const rmaDateTime = (v) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : null)
const reloadForm = async () => {
  const res = await request.get(`/work-orders/${form.id}`)
  Object.assign(form, res)
}
const onHoldAction = async () => {
  if (form.is_on_hold) {
    holdSaving.value = true
    try {
      const res = await request.post(`/work-orders/${form.id}/resume`)
      ElMessage.success(`已恢复，本次挂起 ${res.hold_minutes} 分钟`)
      await reloadForm()
    } catch (e) { ElMessage.error(e?.response?.data?.detail || '恢复失败') }
    finally { holdSaving.value = false }
    return
  }
  Object.assign(holdDlg, { visible: true, reason: 'VENDOR', remark: '' })
}
const submitHold = async () => {
  holdSaving.value = true
  try {
    await request.post(`/work-orders/${form.id}/hold`, {
      reason: holdDlg.reason, remark: holdDlg.remark || null,
    })
    ElMessage.success('已挂起，SLA 暂停计时')
    holdDlg.visible = false
    await reloadForm()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '挂起失败') }
  finally { holdSaving.value = false }
}
const openRma = () => {
  Object.assign(rmaDlg, {
    visible: true, vendor: form.rma_vendor || '', rma_no: form.rma_no || '',
    status: form.rma_status || 'PENDING',
    shipped_at: form.rma_shipped_at || null,
    vendor_received_at: form.rma_vendor_received_at || null,
    returned_at: form.rma_returned_at || null,
    replacement_sn: form.rma_replacement_sn || '', remark: form.rma_remark || '', saving: false,
  })
}
const saveRma = async () => {
  rmaDlg.saving = true
  try {
    await request.put(`/work-orders/${form.id}/rma`, {
      vendor: rmaDlg.vendor || null, rma_no: rmaDlg.rma_no || null,
      status: rmaDlg.status || null,
      shipped_at: rmaDateTime(rmaDlg.shipped_at),
      vendor_received_at: rmaDateTime(rmaDlg.vendor_received_at),
      returned_at: rmaDateTime(rmaDlg.returned_at),
      replacement_sn: rmaDlg.replacement_sn || null, remark: rmaDlg.remark || null,
    })
    ElMessage.success('RMA 信息已保存')
    rmaDlg.visible = false
    await reloadForm()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '保存失败') }
  finally { rmaDlg.saving = false }
}

const startProcessing = async () => {
  if (!form.id) return
  starting.value = true
  try {
    await request.post(`/work-orders/${form.id}/start`)
    ElMessage.success('已开始处理')
    window.location.reload()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '操作失败')
  } finally {
    starting.value = false
  }
}

onMounted(async () => {
  fetchFaultCodes()
  fetchFaultPhenomena()
  fetchRootCauses()

  try {
    const [dRes, uRes] = await Promise.all([
      request.get('/devices/', { params: { page_size: 200 } }),
      request.get('/users/', { params: { page_size: 200 } }),
    ])
    devices.value = dRes.items || []
    deviceFiltered.value = dRes.items || []
    deviceTotal.value = dRes.total ?? (dRes.items || []).length
    users.value = uRes.items || []
    // 维修员由后端强制设为当前登录用户（号主），前端无需设置 technician_id
  } catch { /* ignore */ }

  loadDeviceTypes()

  if (route.params.id && !route.path.endsWith('/new')) {
    try {
      const res = await request.get(`/work-orders/${route.params.id}`)
      Object.assign(form, res)
      if (res.status === 'ARCHIVED') loadEditLogs()

      if (typeof res.fault_code === 'string' && res.fault_code) {
        form.fault_code = res.fault_code.split(',').map(c => c.trim()).filter(Boolean)
      } else if (!res.fault_code) {
        form.fault_code = []
      }

      // 编辑已有工单：确保当前设备出现在下拉选项里，避免显示空白
      if (!form.device_id && form.device_code) {
        const byCode = devices.value.find((x) => x.device_code === form.device_code)
        if (byCode) form.device_id = byCode.id
      }
      if (form.device_id) {
        let d = devices.value.find((x) => x.id === form.device_id)
        if (!d) {
          try {
            d = await request.get(`/devices/${form.device_id}`)
            devices.value.unshift(d)
          } catch { /* 设备可能已删除 */ }
        }
        if (d) {
          if (!deviceFiltered.value.some((x) => x.id === d.id)) deviceFiltered.value.unshift(d)
          if (!form.device_type) form.device_type = d.device_type
          if (!form.location) form.location = d.location
        }
      }

      if (res.start_time && res.end_time) {
        timeRange.value = [dayjs(res.start_time).toDate(), dayjs(res.end_time).toDate()]
        calcWorkHours()
      } else if (res.start_time) {
        timeRange.value = [dayjs(res.start_time).toDate(), null]
      }

      usedParts.value = Array.isArray(res.used_parts) ? res.used_parts : []

      if (res.attachments && Array.isArray(res.attachments)) {
        // 只有 source=REPAIR 的才是维修人员自己上传的；报修人/历史附件只读单列
        reporterMedia.value = (Array.isArray(res.fault_media) ? res.fault_media : []).map((x) => (
          typeof x === 'string' ? { url: x, name: '报修附件' } : x
        ))
        legacyAttachments.value = res.attachments.filter((f) => f.source !== 'REPAIR')
        attachments.value = res.attachments.filter((f) => f.source === 'REPAIR')
        uploadFileList.value = attachments.value.map((f, i) => ({ uid: i, name: f.name, url: f.url, status: 'success' }))
      }
      attachDirty.value = false

      if (res.fault_phenomenon_type) {
        faultPhenomenonCascader.value = res.fault_phenomenon_type.split(' > ')
        if (res.device_type) fetchFaultPhenomena(res.device_type)
      }
      if (res.root_cause_type) {
        rootCauseCascader.value = res.root_cause_type.split(' > ')
      }

      // 不自动回显历史 AI 校验结果：刚进入工单时不显示校验卡片，需手动点「AI 校验」重新分析
      analysisResult.value = null

      if (res.analysis_result?.device_type && !res.device_type) {
        form.device_type = res.analysis_result.device_type
      } else if (res.device_id && !res.device_type) {
        try {
          const dRes2 = await request.get(`/devices/${res.device_id}`)
          form.device_type = dRes2.device_type || ''
        } catch { /* ignore */ }
      }

      if (res.device_id) onDeviceChange(res.device_id)
    } catch (e) {
      const detail = e?.response?.data?.detail
      if (e?.response?.status === 404) {
        ElMessage.error(typeof detail === 'string' ? detail : '工单不存在或已被删除')
        router.replace('/orders?tab=list')
      } else {
        ElMessage.error(typeof detail === 'string' ? detail : '加载工单失败')
      }
    }
  }
})

// [debug] 通过 ?debug=日志原文 自动触发错误码检索（仅带 debug 参数时生效），用于运行时排障
{
  const __q = new URLSearchParams(location.search).get('debug')
  if (__q) {
    entryMode.value = 'error_code'
    ecQuery.value = __q
    ecSearch()
  }
}
</script>

<style scoped>
.sla-bar {
  display: flex; align-items: center; flex-wrap: wrap; gap: 12px;
  max-width: 860px; margin: 0 auto 12px; padding: 10px 14px;
  background: #F7F8FA; border: 1px solid #E5E6EB; border-radius: 8px;
  font-size: 13px; color: #4E5969;
}
.sla-item b { color: #1F2329; }
.sla-total { color: #0FC6C2; }
.sla-comment { color: #86909C; margin-left: 4px; }
.sla-rate-btn { margin-left: auto; border-radius: 8px; height: 30px; }
.form-body { max-width: 860px; margin: 0 auto; }
.form-card { padding: 16px; }
.form-section { margin-bottom: 24px; padding-bottom: 20px; border-bottom: 1px solid #E5E6EB; }
.form-section:last-of-type { border-bottom: none; }
.section-header { font-size: 15px; font-weight: 600; color: #1D2129; margin-bottom: 16px; }

/* 现场附件独立区：始终可见 */
.attach-section { border-radius: 8px; }
.attach-count {
  display: inline-block; min-width: 20px; padding: 0 6px; margin-left: 6px;
  font-size: 12px; font-weight: 500; line-height: 18px; text-align: center;
  color: #0FC6C2; background: #E8FFFE; border: 1px solid #B5F1EF; border-radius: 9px;
}
.attach-dirty {
  margin-left: 8px; padding: 0 6px; font-size: 12px; font-weight: 400;
  color: #FF7D00; background: #FFF7E8; border: 1px solid #FFE4BA; border-radius: 4px;
}
.attach-upload-wrap { display: flex; flex-direction: column; gap: 6px; }
.attach-save-btn { align-self: flex-start; margin-top: 4px; border-radius: 6px; }

/* 查看页「上传附件」弹窗 */
.up-dialog :deep(.el-upload-dragger) { padding: 26px 16px; border-radius: 8px; }
.up-icon { font-size: 34px; color: #0FC6C2; margin-bottom: 6px; }
.up-text { font-size: 14px; color: #4E5969; }
.up-text em { font-style: normal; color: #0FC6C2; font-weight: 600; }
.up-sub { font-size: 12px; color: #86909C; margin-top: 4px; }
.up-note { margin-top: 10px; font-size: 12px; color: #86909C; line-height: 1.6; }
.up-note b { color: #FF7D00; }
.up-done { margin-left: 8px; color: #00B42A; }
.up-busy { margin-left: 8px; color: #0FC6C2; }
.form-grid { max-width: 760px; }
/* 标签左对齐后，统一标签的字重和颜色，避免左侧一列发灰发虚 */
.form-grid :deep(.el-form-item__label) { color: #4E5969; font-weight: 500; }
.form-grid :deep(.el-form-item) { margin-bottom: 18px; }
.analysis-card { margin-bottom: 16px; border: 1px solid #FFD666; background: #FFFBE6; }
.analysis-card :deep(.el-card__header) { background: #FFF7D6; border-bottom: 1px solid #FFE58F; padding: 10px 16px; }
.card-header-row { display: flex; justify-content: space-between; align-items: center; }
.section-title { font-size: 14px; font-weight: 600; color: #D48806; }
.form-footer { display: flex; gap: 12px; justify-content: center; margin-top: 16px; padding: 12px 16px; position: sticky; bottom: 0; z-index: 20; background: rgba(255,255,255,.97); border-top: 1px solid #E5E6EB; box-shadow: 0 -4px 14px rgba(0,0,0,.06); }
.form-footer .el-button { margin-left: 0 !important; height: 34px; padding: 0 18px; border-radius: 8px; font-weight: 500; }
.submit-hint { font-size: 12px; color: #FF7D00; text-align: center; margin-top: 8px; }
.parts-list { display: flex; flex-direction: column; gap: 8px; }
.part-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.part-row-readonly { padding: 3px 0; font-size: 13px; color: #4E5969; }
.part-row-readonly .part-name { color: #1D2129; }
.part-row-readonly .part-code { color: #86909C; font-size: 12px; }
.part-row-readonly .part-price { color: #86909C; font-size: 12px; }
.parts-empty { font-size: 12px; color: #86909C; line-height: 1.6; }
.part-stock-tip { font-size: 12px; color: #86909C; white-space: nowrap; }
.part-stock-tip.stock-warning { color: #F53F3F; }
.stock-short { font-weight: 600; }
.qty-over-stock :deep(.el-input__inner) { border-color: #F53F3F !important; }
.qty-over-stock :deep(.el-input-number__decrease),
.qty-over-stock :deep(.el-input-number__increase) { border-color: #F53F3F !important; }
.spare-option { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.spare-code { color: #1D2129; font-weight: 600; min-width: 80px; }
.spare-name { color: #4E5969; flex: 1; }
.spare-spec { color: #86909C; font-size: 12px; }
.spare-option-info { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding-top: 2px; }
.spare-stock { color: #00B42A; }
.spare-stock.stock-low { color: #FF7D00; }
.spare-stock.stock-out { color: #F53F3F; }
.spare-location { color: #86909C; }
.solution-area { width: 100%; display: flex; flex-direction: column; }
.upload-hint { font-size: 12px; color: #86909C; margin-top: 4px; line-height: 1.6; max-width: 760px; }
.cascader-hint { font-size: 12px; color: #86909C; margin-top: 4px; line-height: 1.4; }
.fault-code-row { display: flex; gap: 8px; align-items: flex-start; width: 100%; }
.fc-option { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.fc-code { font-weight: 600; color: #E6A23C; min-width: 70px; text-align: left; }
.fc-desc { color: #4E5969; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; text-align: right; margin-left: 16px; }
.attach-gallery { display: flex; gap: 8px; flex-wrap: wrap; }
.attach-item { display: flex; flex-direction: column; align-items: center; gap: 4px; }
.attach-thumb { width: 80px; height: 80px; object-fit: cover; border-radius: 4px; border: 1px solid #E5E6EB; }
.attach-clickable { cursor: zoom-in; }
.preview-wrap { display: flex; justify-content: center; max-height: 70vh; overflow: auto; }
.preview-img { max-width: 100%; max-height: 68vh; object-fit: contain; border-radius: 4px; }
.attach-name { font-size: 11px; color: #86909C; max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-dialog-body { display: flex; flex-direction: column; gap: 12px; }
.ai-dialog-msgs { max-height: 560px; min-height: 320px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; padding: 8px; }
.ai-msg-row { max-width: 85%; }
.ai-msg-row.user { align-self: flex-end; }
.ai-msg-row.assistant { align-self: flex-start; }
.ai-msg-bubble { padding: 10px 14px; border-radius: 8px; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
.ai-msg-row.user .ai-msg-bubble { background: var(--color-primary); color: #fff; }
.ai-msg-row.assistant .ai-msg-bubble { background: #F2F3F5; color: #1D2129; }
.ai-msg-bubble.thinking { color: #C9CDD4; font-style: italic; }
.ai-dialog-input { border-top: 1px solid #E5E6EB; padding-top: 12px; }
.ai-dialog .ai-dialog-input .el-textarea__inner { min-height: 80px !important; font-size: 14px; }
.knowledge-dialog { display: flex; flex-direction: column; gap: 12px; }
.kd-search { display: flex; gap: 8px; }
.kd-results { max-height: 420px; overflow-y: auto; }
.kd-empty { text-align: center; color: #C9CDD4; padding: 40px 0; font-size: 14px; }
.kd-item { border: 1px solid #E5E6EB; border-radius: 6px; padding: 12px; margin-bottom: 8px; cursor: pointer; transition: border-color 0.2s; }
.kd-item:hover { border-color: var(--color-primary); }
.kd-item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.kd-title { font-weight: 600; font-size: 14px; color: #1D2129; flex: 1; }
.kd-steps { margin: 0 0 8px; padding: 8px; background: #F7F8FA; border-radius: 4px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; font-family: inherit; color: #4E5969; }
.kd-item-footer { display: flex; justify-content: space-between; align-items: center; }
.kd-count { font-size: 12px; color: #86909C; }
.detail-card { max-width: 900px; margin: 0 auto; padding: 16px; }
.detail-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.detail-header h3 { font-size: 18px; font-weight: 600; color: #1D2129; margin: 0; }
.detail-header .head-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-height: 32px; }
.detail-header .head-right { display: flex; align-items: center; }
.detail-pre { margin: 0; white-space: pre-wrap; font-family: inherit; font-size: 14px; line-height: 1.7; }
.wo-actions {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 4px; background: #F7F8FA; border: 1px solid #F2F3F5; border-radius: 10px;
}
.wo-actions .el-button {
  margin-left: 0 !important; height: 32px; padding: 0 14px;
  border-radius: 8px; font-weight: 500;
}
.wo-actions .el-button.is-plain { background: #fff; }
/* 悬停时保持浅色描边，不要被 Element 的“实心+白字”覆盖导致白底白字 */
.wo-actions .el-button.is-plain:hover {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-7);
  color: var(--el-color-primary);
}
.wo-actions .el-button--danger.is-plain:hover {
  background: var(--el-color-danger-light-9);
  border-color: var(--el-color-danger-light-7);
  color: var(--el-color-danger);
}
.wo-actions .el-button--warning.is-plain:hover {
  background: var(--el-color-warning-light-9);
  border-color: var(--el-color-warning-light-7);
  color: var(--el-color-warning);
}
.wo-actions .el-button--success.is-plain:hover {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-7);
  color: var(--el-color-success);
}
.wo-actions .el-button--primary.is-plain { color: var(--el-color-primary); }
.wo-actions-sep { width: 1px; height: 20px; background: #E5E6EB; margin: 0 2px; flex-shrink: 0; }
.status-pill { font-weight: 500; border-radius: 6px; }
.detail-footer { margin-top: 24px; display: flex; justify-content: center; }
.time-desc { margin-top: 16px; }
/* 时间块：标签列固定宽度，列数变化时不会出现超宽标签格 */
.time-desc :deep(.el-descriptions__label) { width: 92px; min-width: 92px; white-space: nowrap; }
.time-desc :deep(.el-descriptions__content) { white-space: nowrap; }
/* ===== 处理进度时间线 ===== */
.wo-block { margin-top: 18px; }
.wo-block-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; font-weight: 600; color: #1D2129;
  margin-bottom: 10px; padding-left: 8px; border-left: 3px solid #0FC6C2; line-height: 1;
}
.wo-block-count {
  font-size: 11px; font-weight: 500; color: #0FC6C2;
  background: rgba(15, 198, 194, 0.1); border-radius: 9px; padding: 1px 7px;
}
.wo-block-action { margin-left: auto; font-size: 12px; }
/* ===== 现场照片 / 附件 ===== */
.wo-attach-empty {
  font-size: 12px; color: #86909C; background: #FAFBFC;
  border: 1px dashed #E5E6EB; border-radius: 6px; padding: 14px; text-align: center;
}
.wo-attach-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.wo-attach-item { width: 96px; }
.wo-attach-thumb {
  width: 96px; height: 96px; object-fit: cover; border-radius: 6px;
  border: 1px solid #E5E6EB; background: #F7F8FA; display: block;
}
.wo-attach-clickable { cursor: zoom-in; }
.wo-attach-clickable:hover { border-color: #0FC6C2; }
.wo-attach-meta { display: flex; flex-direction: column; gap: 2px; margin-top: 4px; }
.wo-attach-name {
  font-size: 11px; color: #4E5969;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.wo-attach-stage { font-size: 10px; color: #86909C; }
.wo-timeline { margin-top: 2px; }
.wo-tl-fold { margin: -2px 0 8px 50px; }
.wo-tl-fold :deep(.el-button) { font-size: 12px; padding: 0; height: 20px; }
/* 日期分隔：同一天只在第一行出现一次 */
.wo-tl-date {
  display: flex; align-items: center; gap: 8px;
  margin: 2px 0 8px; font-size: 11px; color: #86909C;
}
.wo-tl-date span {
  padding: 1px 7px; line-height: 16px;
  background: #F7F8FA; border-radius: 9px; white-space: nowrap;
}
.wo-tl-date::after { content: ''; flex: 1; height: 1px; background: #F2F3F5; }
/* 每行：时间 44px | 轴 16px | 内容 */
.wo-tl-item {
  display: grid; grid-template-columns: 44px 16px minmax(0, 1fr);
  column-gap: 6px; padding-bottom: 14px;
}
.wo-tl-item.is-last { padding-bottom: 0; }
.wo-tl-time {
  font-size: 12px; line-height: 20px; text-align: right; color: #86909C;
  font-variant-numeric: tabular-nums;
}
.wo-tl-axis { position: relative; }
/* 竖线穿过圆点圆心，最后一行不画 */
.wo-tl-axis::before {
  content: ''; position: absolute; left: 50%; top: 10px; bottom: -10px;
  width: 1px; margin-left: -0.5px; background: #E5E6EB;
}
.wo-tl-item.is-last .wo-tl-axis::before { display: none; }
.wo-tl-dot {
  position: absolute; left: 50%; top: 6px; transform: translateX(-50%);
  width: 8px; height: 8px; border-radius: 50%; background: #C9CDD4;
}
.wo-tl-dot.is-now {
  width: 10px; height: 10px; top: 5px;
  box-shadow: 0 0 0 4px rgba(15, 198, 194, 0.16);
}
.wo-tl-dot.tl-primary { background: #165DFF; }
.wo-tl-dot.tl-warning { background: #FF7D00; }
.wo-tl-dot.tl-success { background: #00B42A; }
.wo-tl-dot.tl-danger { background: #F53F3F; }
.wo-tl-dot.tl-info { background: #86909C; }
/* 状态没变化的记录（挂起 / 改派 / 备注）：空心点 + 描边胶囊，避免和真正的流转混淆 */
.wo-tl-dot.is-same { background: #FFFFFF; box-shadow: inset 0 0 0 2px #C9CDD4; }
.wo-tl-pill.is-same {
  background: transparent; border: 1px solid #E5E6EB; color: #86909C; font-weight: 400;
}
.wo-tl-body { min-width: 0; }
.wo-tl-line { display: flex; align-items: center; gap: 8px; min-height: 20px; flex-wrap: wrap; }
.wo-tl-pill {
  font-size: 12px; font-weight: 500; line-height: 18px;
  padding: 0 8px; border-radius: 4px; white-space: nowrap;
}
.wo-tl-pill.tl-pill-info { color: #4E5969; background: #F2F3F5; }
.wo-tl-pill.tl-pill-primary { color: #165DFF; background: #E8F3FF; }
.wo-tl-pill.tl-pill-warning { color: #D25F00; background: #FFF7E8; }
.wo-tl-pill.tl-pill-success { color: #009A29; background: #E8FFEA; }
.wo-tl-pill.tl-pill-danger { color: #CB2634; background: #FFECE8; }
.wo-tl-now {
  font-size: 11px; line-height: 16px; padding: 0 5px; border-radius: 3px;
  color: #0FC6C2; background: #F0FBFB; border: 1px solid #B5F1EF;
}
.wo-tl-who { display: inline-flex; align-items: baseline; gap: 5px; font-size: 12px; color: #86909C; }
.wo-tl-actor { color: #4E5969; }
.wo-tl-sep { color: #C0C4CC; }
.wo-tl-delta {
  margin-left: auto; font-size: 11px; color: #86909C;
  background: #FAFBFC; border: 1px solid #F2F3F5; border-radius: 3px;
  padding: 0 6px; line-height: 16px; white-space: nowrap;
}
.wo-tl-remark {
  margin-top: 5px; font-size: 12px; color: #4E5969; line-height: 1.5;
  background: #F7F8FA; border-left: 2px solid #E5E6EB; border-radius: 0 4px 4px 0;
  padding: 4px 8px;
}
/* ===== 领用备件 ===== */
.wo-parts { display: flex; flex-wrap: wrap; gap: 8px; }
.wo-part-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; background: #F7F8FA; border: 1px solid #E5E6EB; border-radius: 6px;
  font-size: 12px; color: #4E5969;
}
.wo-part-name { color: #1D2129; font-weight: 500; }
.wo-part-code { color: #86909C; font-family: ui-monospace, Menlo, monospace; }
.wo-part-count { color: #0FC6C2; font-weight: 600; }
.wo-part-price { color: #86909C; }
.sla-help { color: #86909C; cursor: help; font-size: 14px; }
.time-tip { margin-top: 8px; font-size: 12px; color: #86909C; line-height: 1.6; }
.submit-choice-title { font-size: 15px; font-weight: 600; color: #1D2129; margin-bottom: 8px; }
.submit-choice-desc { font-size: 13px; color: #4E5969; line-height: 1.7; }
.device-picker-hint { margin-top: 4px; font-size: 12px; color: #86909C; display: flex; align-items: center; gap: 8px; }
.device-picker-hint b { color: #1D2129; }
.detail-footer .el-button { border-radius: 8px; height: 34px; padding: 0 18px; }
.edit-log-card { margin-top: 16px; }
.edit-log-title { font-size: 15px; font-weight: 600; color: #1D2129; margin-bottom: 12px; }
.edit-log-item { padding: 10px 0; border-bottom: 1px dashed #EDEFF3; }
.edit-log-item:last-child { border-bottom: none; }
.edit-log-head { display: flex; gap: 10px; align-items: center; margin-bottom: 6px; font-size: 13px; }
.edit-log-editor { font-weight: 600; color: #1D2129; }
.edit-log-time { color: #86909C; font-size: 12px; }
.edit-log-change { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; font-size: 12.5px; line-height: 1.7; }
.edit-log-key { color: #4E5969; background: #F2F3F5; border-radius: 3px; padding: 0 6px; }
.edit-log-before { color: #86909C; text-decoration: line-through; }
.edit-log-arrow { color: #C9CDD4; }
.edit-log-after { color: #0FC6C2; }
.fc-dialog-footer { display: flex; gap: 8px; justify-content: flex-end; }
.submit-confirm-dialog .el-message-box__btns .el-button:not(.el-button--primary) {
  background: var(--color-primary) !important;
  border-color: var(--color-primary) !important;
  color: #fff !important;
}
.submit-confirm-dialog .el-message-box__btns .el-button:not(.el-button--primary):hover {
  background: #0db3af !important;
  border-color: #0db3af !important;
  color: #fff !important;
}
.submit-confirm-dialog .el-message-box__btns .el-button--primary {
  background: #52c41a !important;
  border-color: var(--color-primary) !important;
}
.submit-confirm-dialog .el-message-box__btns .el-button--primary:hover {
  background: #49ad17 !important;
  border-color: #49ad17 !important;
}
/* 录入模式切换 */
.mode-switch-bar { display: flex; align-items: center; gap: 12px; max-width: 860px; margin: 0 auto 16px; }
.mode-switch-label { font-size: 13px; color: #86909C; }
.mode-switch {
  display: flex; gap: 4px; background: #F2F3F5; border-radius: 8px; padding: 3px;
}
.mode-tab {
  padding: 5px 14px; border-radius: 6px; font-size: 13px; cursor: pointer;
  color: #86909C; font-weight: 500; transition: all .2s; white-space: nowrap;
}
.mode-tab:hover { color: #4E5969; }
.mode-tab.active { background: #fff; color: #0FC6C2; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
/* 错误码检索预填 */
.error-code-card { margin-bottom: 16px; }
.error-code-card :deep(.el-card__header) { padding: 10px 16px; }
.mode-tip { font-size: 12px; color: #86909C; }
.ec-search { display: flex; gap: 8px; margin-bottom: 12px; align-items: flex-start; }
.ec-search .el-button { margin-top: 2px; }
.ec-error { color: #F53F3F; font-size: 13px; margin-bottom: 8px; }
.ec-results { max-height: 480px; overflow-y: auto; }
.ec-group { margin-bottom: 14px; }
.ec-group-title { font-size: 13px; font-weight: 600; color: #4E5969; margin-bottom: 8px; }
.ec-item { border: 1px solid #E5E6EB; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; }
.ec-item.manual { border-left: 3px solid #FF7D00; background: #FFFDF9; }
.ec-item.case { border-left: 3px solid var(--color-primary); }
.ec-item-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.ec-code { font-weight: 700; color: #E6A23C; font-size: 14px; }
.ec-title { font-weight: 600; font-size: 14px; color: #1D2129; }
.ec-desc { font-size: 13px; color: #4E5969; line-height: 1.6; margin-bottom: 6px; }
.ec-msg {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  color: #1D2129;
  background: #F7F8FA;
  border-left: 3px solid #C9CDD4;
  border-radius: 4px;
  padding: 6px 10px;
  margin-bottom: 6px;
  white-space: pre-wrap;
}
.ec-block { font-size: 13px; color: #4E5969; line-height: 1.7; margin-bottom: 4px; }
.ec-block-label { font-weight: 600; color: #1D2129; margin-right: 6px; }
.ec-item-footer { display: flex; justify-content: flex-end; margin-top: 6px; }
.ec-empty { text-align: center; color: #C9CDD4; padding: 30px 0; font-size: 14px; }
.ec-codes-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.ec-codes-label { font-size: 13px; font-weight: 600; color: #4E5969; }
.ec-code-tag { font-family: Consolas, Monaco, monospace; font-weight: 700; }
.ec-code-input { width: 170px; }
.ec-code-empty { font-size: 12px; color: #86909C; }
.ec-cond-list { margin: 6px 0; }
.ec-cond-head { font-size: 12px; color: #86909C; margin-bottom: 6px; }
.ec-cond-group { display: flex; flex-direction: column; gap: 4px; }
.ec-cond { height: auto; align-items: flex-start; white-space: normal; margin-right: 0; }
.ec-cond :deep(.el-checkbox__label) { white-space: normal; line-height: 1.5; }
.ec-cond-signal { font-weight: 600; color: #FF7D00; font-size: 13px; }
.ec-cond-cause { color: #4E5969; font-size: 12px; margin-left: 6px; }
/* 补充信息折叠区 */
.supplement-collapse { border: none; }
.supplement-collapse :deep(.el-collapse-item__header) { background: #F7F8FA; border-radius: 6px; padding: 0 14px; font-size: 14px; font-weight: 600; }
.supplement-collapse :deep(.el-collapse-item__content) { padding: 14px 4px 0; }
.supplement-badge { margin-left: 8px; }
.supplement-body { padding-left: 4px; }

.work-order-form-head { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:20px; flex-wrap:wrap; }
.work-order-form-title { font-size:20px; font-weight:600; color:var(--color-text-primary); margin:0; }
.head-left { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.head-meta { font-size:13px; color:#86909C; }
.work-order-form-actions { display:flex; gap:8px; flex-shrink:0; flex-wrap:wrap; }
.head-right { display:flex; align-items:center; gap:10px; }
</style>
