<script setup>
import { computed, ref, watch, nextTick } from 'vue'
import { FolderOpen, Info, CircleCheck, AlertTriangle, CircleAlert } from 'lucide-vue-next'
import { useWorkflowStore } from '../stores/workflowStore'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const workflowStore = useWorkflowStore()

const logScrollRef = ref(null)

const totalDocs = computed(
  () => workflowStore.selectedDocs.length + workflowStore.localFiles.length
)

const canStart = computed(() => {
  const hasFiles = totalDocs.value > 0
  const hasNodes = workflowStore.canvasNodes.length > 0
  return (
    hasFiles &&
    hasNodes &&
    !!workflowStore.currentWorkflowId &&
    !workflowStore.isExecuting
  )
})

const displayDocs = computed(() => [
  ...workflowStore.selectedDocs.map(d => ({ name: d.name, size: d.size })),
  ...workflowStore.localFiles.map(f => ({ name: f.name, size: _formatSize(f.size) }))
])

function _formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function closeModal() {
  if (!workflowStore.isExecuting) {
    emit('close')
  }
}

async function startProcess() {
  if (!canStart.value) return
  try {
    await workflowStore.saveCurrentWorkflow()
  } catch (_) {
    /* save 失败仍尝试执行 */
  }
  await workflowStore.executeWorkflow()
}

const showProgressPanel = computed(
  () =>
    workflowStore.isExecuting ||
    workflowStore.executionProgress > 0 ||
    workflowStore.executionStatus === 'completed' ||
    workflowStore.executionStatus === 'failed'
)

const statusLabel = computed(() => {
  if (workflowStore.isExecuting || workflowStore.executionStatus === 'running') return '处理中'
  if (workflowStore.executionStatus === 'completed') return '已完成'
  if (workflowStore.executionStatus === 'failed') return '已失败'
  if (workflowStore.executionProgress >= 100) return '已完成'
  return '准备就绪'
})

const fileProgressLine = computed(() => {
  const total = workflowStore.executionTotalFiles
  const idx = workflowStore.executionCurrentFileIndex
  const name = (workflowStore.executionCurrentFileName || '').trim()
  if (!total && !name) return ''
  if (total > 0 && idx > 0) {
    const namePart = name ? ` · ${name}` : ''
    return `第 ${idx} / ${total} 个文件${namePart}`
  }
  if (name) return name
  return ''
})

const recentLogs = computed(() => {
  const logs = workflowStore.executionLogs || []
  return logs.slice(-80)
})

function logIconComponent(type) {
  const t = String(type || 'info').toLowerCase()
  if (t === 'done') return CircleCheck
  if (t === 'warn') return AlertTriangle
  if (t === 'error') return CircleAlert
  return Info
}

watch(
  () => workflowStore.executionLogs.length,
  async () => {
    await nextTick()
    const el = logScrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  }
)

watch(
  () => workflowStore.executionProgress,
  async () => {
    await nextTick()
    const el = logScrollRef.value
    if (el) el.scrollTop = el.scrollHeight
  }
)
</script>

<template>
  <div class="modal-overlay" :class="{ active: visible }" @click.self="closeModal">
    <div class="modal">
      <div class="modal-header">
        <h2 class="modal-title">批量处理</h2>
        <button class="modal-close" type="button" :disabled="workflowStore.isExecuting" @click="closeModal">×</button>
      </div>

      <div class="modal-body">
        <p class="modal-text">
          将使用当前工作流与画布上的节点配置，对下列文档依次执行（与右侧「运行工作流」相同）。下方会显示总体进度、当前文件与节点状态，以及后端返回的运行日志。
        </p>

        <p v-if="!workflowStore.currentWorkflowId" class="modal-warn">
          当前没有工作流 ID，请先创建或选择一个工作流。
        </p>
        <p v-else-if="workflowStore.canvasNodes.length === 0" class="modal-warn">
          画布上还没有节点，无法执行。
        </p>

        <div v-if="displayDocs.length > 0" class="modal-docs">
          <div v-for="(doc, i) in displayDocs" :key="i" class="modal-doc">
            <span class="doc-name">{{ doc.name }}</span>
            <span class="doc-size">{{ doc.size }}</span>
          </div>
        </div>

        <div v-else class="modal-docs-empty">
          <div class="empty-icon" aria-hidden="true">
            <FolderOpen :size="28" :stroke-width="1.75" />
          </div>
          <div class="empty-text">暂未选择文档</div>
          <div class="empty-hint">请先在配置面板中选择文档库文件或上传本地文件</div>
        </div>

        <div v-if="showProgressPanel" class="batch-progress">
          <div class="progress-header">
            <span class="progress-status" :class="'exec-' + (workflowStore.executionStatus || 'idle')">{{ statusLabel }}</span>
            <span class="progress-pct">{{ Math.min(100, Math.max(0, workflowStore.executionProgress)) }}%</span>
          </div>
          <p v-if="fileProgressLine" class="progress-file">{{ fileProgressLine }}</p>
          <p v-if="workflowStore.currentNodeName" class="progress-node">当前节点：{{ workflowStore.currentNodeName }}</p>

          <div class="progress-bar" role="progressbar" :aria-valuenow="workflowStore.executionProgress" aria-valuemin="0" aria-valuemax="100">
            <div
              class="progress-fill"
              :class="'fill-' + (workflowStore.executionStatus || 'idle')"
              :style="{ width: Math.min(100, Math.max(0, workflowStore.executionProgress)) + '%' }"
            ></div>
          </div>

          <div v-if="workflowStore.nodeProgress.length > 0" class="node-progress-strip" aria-label="节点状态">
            <div
              v-for="np in workflowStore.nodeProgress"
              :key="np.id || np.title"
              class="node-chip"
              :class="[
                'np-' + (np.status || 'pending'),
                np.type ? 'np-type-' + np.type : '',
              ]"
              :title="(np.title || '') + (np.message ? ' — ' + np.message : '')"
            >
              <span class="node-chip-idx">{{ np.index != null ? np.index : '' }}</span>
              <span class="node-chip-title">{{ np.title || '节点' }}</span>
            </div>
          </div>

          <div class="progress-logs-wrap">
            <div class="progress-logs-head">运行日志</div>
            <div ref="logScrollRef" class="progress-logs">
              <p v-if="recentLogs.length === 0" class="logs-placeholder">
                {{ workflowStore.isExecuting ? '等待后端返回日志…' : '暂无日志' }}
              </p>
              <div
                v-for="(log, index) in recentLogs"
                :key="index"
                class="log-row"
                :class="'log-' + (log.type || 'info')"
              >
                <span class="log-ico" aria-hidden="true">
                  <component :is="logIconComponent(log.type)" :size="14" :stroke-width="2" />
                </span>
                <span class="log-msg">{{ log.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="modal-btn cancel" type="button" :disabled="workflowStore.isExecuting" @click="closeModal">
          {{
            (workflowStore.executionStatus === 'completed' || workflowStore.executionStatus === 'failed') &&
            !workflowStore.isExecuting
              ? '关闭'
              : '取消'
          }}
        </button>
        <button class="modal-btn primary" type="button" :disabled="!canStart" @click="startProcess">
          {{ workflowStore.isExecuting ? '处理中…' : `开始处理 (${totalDocs} 个文档)` }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-text {
  margin-bottom: 12px;
  line-height: 1.6;
}

.modal-warn {
  font-size: 13px;
  color: var(--accent-warning);
  margin-bottom: 12px;
}

.doc-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-size {
  color: var(--text-muted);
  font-size: 12px;
  flex-shrink: 0;
}

.modal-docs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px dashed var(--border-color);
}

.empty-icon {
  width: 44px;
  height: 44px;
  border-radius: 0;
  border: 2px dashed rgba(37, 99, 235, 0.22);
  background: rgba(37, 99, 235, 0.04);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-primary);
}

.empty-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
}

.empty-hint {
  font-size: 13px;
  color: var(--text-muted);
}

.batch-progress {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border-color);
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.progress-status {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
}

.progress-status.exec-running {
  color: var(--accent-primary);
}

.progress-status.exec-completed {
  color: var(--accent-success);
}

.progress-status.exec-failed {
  color: var(--accent-danger);
}

.progress-pct {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.progress-file {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0 0 4px;
  word-break: break-all;
}

.progress-node {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0 0 10px;
}

.progress-bar {
  height: 10px;
  background: var(--bg-tertiary);
  border: var(--border-thick) solid var(--border-color);
  border-radius: 0;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent-primary);
  transition: width 0.35s ease;
}

.progress-fill.fill-failed {
  background: var(--accent-danger);
}

.progress-fill.fill-completed {
  background: var(--accent-success);
}

.node-progress-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
}

.node-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 140px;
  padding: 3px 8px;
  font-size: 11px;
  border: 1px solid var(--chip-accent, var(--border-color));
  background: var(--chip-accent-bg, var(--bg-secondary));
  color: var(--chip-accent, var(--text-secondary));
}

.node-chip.np-type-input {
  --chip-accent: #eab308;
  --chip-accent-bg: rgba(234, 179, 8, 0.12);
}

.node-chip.np-type-ai {
  --chip-accent: #2563eb;
  --chip-accent-bg: rgba(37, 99, 235, 0.1);
}

.node-chip.np-type-output {
  --chip-accent: #1e40af;
  --chip-accent-bg: rgba(30, 64, 175, 0.1);
}

.node-chip.np-type-control {
  --chip-accent: #7c3aed;
  --chip-accent-bg: rgba(124, 58, 237, 0.1);
}

.node-chip.np-running {
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--chip-accent, var(--accent-cyan)) 35%, transparent);
}

.node-chip.np-failed,
.node-chip.np-error {
  --chip-accent: var(--accent-danger);
  --chip-accent-bg: rgba(239, 68, 68, 0.08);
  border-color: var(--accent-danger);
  color: var(--accent-danger);
}

.node-chip-idx {
  opacity: 0.75;
  font-weight: 700;
}

.node-chip-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-logs-wrap {
  margin-top: 14px;
}

.progress-logs-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.progress-logs {
  max-height: 220px;
  overflow-y: auto;
  padding: 10px 10px 8px;
  background: var(--bg-primary);
  border: var(--border-thick) solid var(--border-color);
  border-radius: 0;
  font-size: 12px;
  line-height: 1.45;
}

.logs-placeholder {
  margin: 0;
  color: var(--text-muted);
  font-style: italic;
}

.log-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
  padding-left: 2px;
  border-left: 3px solid transparent;
}

.log-row:last-child {
  margin-bottom: 0;
}

.log-ico {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--text-muted);
}

.log-row.log-info {
  border-left-color: var(--accent-primary);
}

.log-row.log-info .log-ico {
  color: var(--accent-primary);
}

.log-row.log-done {
  border-left-color: var(--accent-success);
}

.log-row.log-done .log-ico {
  color: var(--accent-success);
}

.log-row.log-warn {
  border-left-color: var(--accent-warning);
}

.log-row.log-warn .log-ico {
  color: var(--accent-warning);
}

.log-row.log-error {
  border-left-color: var(--accent-danger);
}

.log-row.log-error .log-ico {
  color: var(--accent-danger);
}

.log-msg {
  flex: 1;
  min-width: 0;
  word-break: break-word;
  color: var(--text-primary);
}
</style>
