<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { Plus, GitBranch, Trash2, ChevronDown, CheckSquare, Square, Search } from 'lucide-vue-next'
import { useWorkflowStore } from '../../stores/workflowStore'

const workflowStore = useWorkflowStore()

const toolboxSearch = ref('')
const activeSection = ref('workflow') // 'workflow' | 'toolbox'
const isLoading = ref(false)

const CUSTOM_GROUP_KEY = 'dis_wf_group_custom_expanded'
const TEMPLATE_GROUP_KEY = 'dis_wf_group_template_expanded'

function readGroupExpanded(key, defaultValue = true) {
  try {
    const raw = sessionStorage.getItem(key)
    if (raw === '0') return false
    if (raw === '1') return true
  } catch {
    /* ignore */
  }
  return defaultValue
}

function persistGroupExpanded(key, value) {
  try {
    sessionStorage.setItem(key, value ? '1' : '0')
  } catch {
    /* ignore */
  }
}

const customWorkflowsExpanded = ref(readGroupExpanded(CUSTOM_GROUP_KEY, true))
const templateWorkflowsExpanded = ref(readGroupExpanded(TEMPLATE_GROUP_KEY, true))

function toggleCustomWorkflowsExpanded() {
  customWorkflowsExpanded.value = !customWorkflowsExpanded.value
  persistGroupExpanded(CUSTOM_GROUP_KEY, customWorkflowsExpanded.value)
}

function toggleTemplateWorkflowsExpanded() {
  templateWorkflowsExpanded.value = !templateWorkflowsExpanded.value
  persistGroupExpanded(TEMPLATE_GROUP_KEY, templateWorkflowsExpanded.value)
}

onMounted(async () => {
  isLoading.value = true
  try {
    await workflowStore.ensureWorkflowsLoaded()
    if (!workflowStore.currentWorkflowId) {
      await workflowStore.ensureInitialWorkflowSelection()
    }
  } finally {
    isLoading.value = false
  }
})

function handleSearch(e) {
  workflowStore.setSearchQuery(e.target.value)
}

function clearWorkflowSearch() {
  workflowStore.clearSearchQuery()
}

watch(
  () => workflowStore.searchQuery,
  (q) => {
    if (q.trim()) {
      customWorkflowsExpanded.value = true
      templateWorkflowsExpanded.value = true
    }
  }
)

function handleAddNode(item) {
  workflowStore.addNode(item)
}

const deleteError = ref('')
const isWorkflowListMultiSelect = ref(false)
const selectedWorkflowIds = ref([])
const isBulkDeleting = ref(false)

const customWorkflowIds = computed(() => workflowStore.filteredCustomWorkflows.map(w => w.id))

const hasAnyWorkflows = computed(
  () =>
    workflowStore.customWorkflows.length > 0 ||
    workflowStore.templateWorkflows.length > 0
)

const hasFilteredWorkflowResults = computed(
  () =>
    workflowStore.filteredCustomWorkflows.length > 0 ||
    workflowStore.filteredTemplateWorkflows.length > 0
)

function handleWorkflowClick(workflowId) {
  workflowStore.selectWorkflow(workflowId)
}

function handleNewWorkflow() {
  workflowStore.createNewWorkflow()
}

const isAllCustomSelected = computed(() => {
  const ids = customWorkflowIds.value
  return ids.length > 0 && ids.every(id => selectedWorkflowIds.value.includes(id))
})

watch(customWorkflowIds, (ids) => {
  const allowed = new Set(ids)
  selectedWorkflowIds.value = selectedWorkflowIds.value.filter(id => allowed.has(id))
  if (!ids.length) {
    isWorkflowListMultiSelect.value = false
  }
})

function toggleWorkflowListMultiSelect() {
  if (workflowStore.isExecuting) return
  isWorkflowListMultiSelect.value = !isWorkflowListMultiSelect.value
  if (!isWorkflowListMultiSelect.value) {
    selectedWorkflowIds.value = []
  }
}

function isWorkflowSelected(id) {
  return selectedWorkflowIds.value.includes(id)
}

function toggleWorkflowSelection(id) {
  if (selectedWorkflowIds.value.includes(id)) {
    selectedWorkflowIds.value = selectedWorkflowIds.value.filter(x => x !== id)
  } else {
    selectedWorkflowIds.value = [...selectedWorkflowIds.value, id]
  }
}

function selectAllCustomWorkflows() {
  selectedWorkflowIds.value = customWorkflowIds.value.slice()
}

function clearWorkflowSelection() {
  selectedWorkflowIds.value = []
}

function handleWorkflowItemClick(wf) {
  if (workflowStore.isExecuting) return
  if (isWorkflowListMultiSelect.value) {
    toggleWorkflowSelection(wf.id)
    return
  }
  handleWorkflowClick(wf.id)
}

async function handleBulkDeleteWorkflows() {
  if (workflowStore.isExecuting || isBulkDeleting.value) return
  const ids = selectedWorkflowIds.value.slice()
  if (!ids.length) return
  deleteError.value = ''
  const ok = window.confirm(`确定删除选中的 ${ids.length} 个工作流？此操作不可恢复。`)
  if (!ok) return
  isBulkDeleting.value = true
  try {
    const result = await workflowStore.deleteWorkflows(ids)
    selectedWorkflowIds.value = []
    isWorkflowListMultiSelect.value = false
    if (result.failed > 0) {
      deleteError.value = `已删除 ${result.deleted} 个，${result.failed} 个删除失败`
    }
  } catch (e) {
    deleteError.value = e?.message || '批量删除失败，请重试'
  } finally {
    isBulkDeleting.value = false
  }
}

async function handleDeleteWorkflow(event, wf) {
  event.stopPropagation()
  if (workflowStore.isExecuting) return
  deleteError.value = ''
  const ok = window.confirm(`确定删除工作流「${wf.name}」？此操作不可恢复。`)
  if (!ok) return
  try {
    await workflowStore.deleteWorkflow(wf.id)
    deleteError.value = ''
  } catch (e) {
    deleteError.value = e?.message || '删除失败，请重试'
  }
}

/** 组件库搜索过滤（拖拽仍作用于当前列表项） */
const filteredToolboxSections = computed(() => {
  const q = toolboxSearch.value.trim().toLowerCase()
  if (!q) return workflowStore.toolboxItems
  return workflowStore.toolboxItems
    .map(section => ({
      ...section,
      items: section.items.filter(
        i =>
          i.name.toLowerCase().includes(q) ||
          (i.title && i.title.toLowerCase().includes(q)) ||
          (i.body && i.body.toLowerCase().includes(q))
      )
    }))
    .filter(section => section.items.length > 0)
})

function onToolboxDragStart(e, item) {
  const payload = JSON.stringify({
    schemaKey: item.schemaKey,
    type: item.type,
    icon: item.icon,
    title: item.title,
    body: item.body,
    name: item.name
  })
  try {
    e.dataTransfer.setData('application/x-workflow-node', payload)
  } catch (_) {
    /* 部分环境仅支持 text/plain */
  }
  e.dataTransfer.setData('text/plain', payload)
  e.dataTransfer.effectAllowed = 'copy'
}
</script>

<template>
  <aside class="workflow-sidebar">

    <!-- Loading Indicator -->
    <div v-if="isLoading" class="sidebar-loading">
      <div class="loading-dots">
        <span></span><span></span><span></span>
      </div>
    </div>

    <template v-else>
      <!-- Section Switcher -->
      <div class="sidebar-switcher">
        <button
          class="switcher-btn"
          :class="{ active: activeSection === 'workflow' }"
          @click="activeSection = 'workflow'"
        >
          工作流
        </button>
        <button
          class="switcher-btn"
          :class="{ active: activeSection === 'toolbox' }"
          @click="activeSection = 'toolbox'"
        >
          组件库
        </button>
      </div>

      <!-- ===================== 工作流面板 ===================== -->
      <template v-if="activeSection === 'workflow'">
        <!-- New Workflow -->
        <div class="sidebar-section">
          <button class="new-workflow-btn" @click="handleNewWorkflow">
            <Plus :size="18" :stroke-width="2" aria-hidden="true" />
            <span>新建工作流</span>
          </button>
        </div>

        <!-- Search -->
        <div class="sidebar-section sidebar-search">
          <div class="workflow-search-box">
            <Search class="workflow-search-icon" :size="15" :stroke-width="2" aria-hidden="true" />
            <input
              type="text"
              placeholder="搜索工作流名称、节点..."
              :value="workflowStore.searchQuery"
              @input="handleSearch"
            />
            <button
              v-if="workflowStore.searchQuery"
              type="button"
              class="workflow-search-clear"
              title="清除搜索"
              @click="clearWorkflowSearch"
            >
              ×
            </button>
          </div>
        </div>

        <!-- Workflow List -->
        <div class="sidebar-scroll sidebar-scroll--workflow-groups">
          <p v-if="deleteError" class="workflow-delete-error">{{ deleteError }}</p>
          <!-- Custom Workflows -->
          <div
            class="workflow-group workflow-group--collapsible"
            v-if="workflowStore.filteredCustomWorkflows.length > 0"
          >
            <button
              type="button"
              class="workflow-group-header"
              :aria-expanded="customWorkflowsExpanded"
              @click="toggleCustomWorkflowsExpanded"
            >
              <span class="workflow-group-header-text">
                <span class="workflow-group-title">我的工作流</span>
                <span class="workflow-group-count">
                  {{
                    workflowStore.hasActiveWorkflowSearch
                      ? `${workflowStore.filteredCustomWorkflows.length}/${workflowStore.customWorkflows.length}`
                      : workflowStore.customWorkflows.length
                  }}
                </span>
              </span>
              <ChevronDown
                class="workflow-group-chevron"
                :class="{ 'is-collapsed': !customWorkflowsExpanded }"
                :size="16"
                :stroke-width="2.2"
                aria-hidden="true"
              />
            </button>
            <div
              v-show="customWorkflowsExpanded"
              class="workflow-group-body workflow-group-body--scroll"
            >
              <div
                v-if="workflowStore.filteredCustomWorkflows.length > 0"
                class="workflow-list-toolbar"
              >
                <button
                  type="button"
                  class="workflow-list-toolbar-btn"
                  :class="{ active: isWorkflowListMultiSelect }"
                  :disabled="workflowStore.isExecuting"
                  @click="toggleWorkflowListMultiSelect"
                >
                  {{ isWorkflowListMultiSelect ? '完成多选' : '多选' }}
                </button>
                <template v-if="isWorkflowListMultiSelect">
                  <button
                    v-if="!isAllCustomSelected"
                    type="button"
                    class="workflow-list-toolbar-btn"
                    :disabled="workflowStore.isExecuting"
                    @click="selectAllCustomWorkflows"
                  >
                    全选
                  </button>
                  <button
                    v-if="selectedWorkflowIds.length > 0"
                    type="button"
                    class="workflow-list-toolbar-btn"
                    :disabled="workflowStore.isExecuting"
                    @click="clearWorkflowSelection"
                  >
                    取消选中
                  </button>
                  <button
                    v-if="selectedWorkflowIds.length > 0"
                    type="button"
                    class="workflow-list-toolbar-btn danger"
                    :disabled="workflowStore.isExecuting || isBulkDeleting"
                    @click="handleBulkDeleteWorkflows"
                  >
                    删除选中 ({{ selectedWorkflowIds.length }})
                  </button>
                </template>
              </div>
              <div
                v-for="wf in workflowStore.filteredCustomWorkflows"
                :key="wf.id"
                class="workflow-item"
                :class="{
                  active: !isWorkflowListMultiSelect && workflowStore.currentWorkflowId === wf.id,
                  'is-multi-selected': isWorkflowListMultiSelect && isWorkflowSelected(wf.id),
                }"
                @click="handleWorkflowItemClick(wf)"
              >
                <button
                  v-if="isWorkflowListMultiSelect"
                  type="button"
                  class="workflow-select-btn"
                  :aria-pressed="isWorkflowSelected(wf.id)"
                  :disabled="workflowStore.isExecuting"
                  @click.stop="toggleWorkflowSelection(wf.id)"
                >
                  <CheckSquare v-if="isWorkflowSelected(wf.id)" :size="16" :stroke-width="2" aria-hidden="true" />
                  <Square v-else :size="16" :stroke-width="2" aria-hidden="true" />
                </button>
                <span
                  v-else
                  class="workflow-marker"
                  :class="wf.type === 'template' ? 'is-template' : 'is-custom'"
                  aria-hidden="true"
                />
                <div class="workflow-info">
                  <span class="workflow-name">{{ wf.name }}</span>
                  <span class="workflow-time">{{ wf.time }}</span>
                </div>
                <button
                  v-if="!isWorkflowListMultiSelect"
                  type="button"
                  class="workflow-delete-btn"
                  title="删除工作流"
                  :disabled="workflowStore.isExecuting"
                  @click="handleDeleteWorkflow($event, wf)"
                >
                  <Trash2 :size="15" :stroke-width="2" aria-hidden="true" />
                </button>
              </div>
            </div>
          </div>

          <div
            v-if="workflowStore.filteredCustomWorkflows.length > 0 && workflowStore.filteredTemplateWorkflows.length > 0"
            class="workflow-groups-divider"
            role="separator"
            aria-hidden="true"
          />

          <!-- System Templates -->
          <div
            class="workflow-group workflow-group--collapsible"
            v-if="workflowStore.filteredTemplateWorkflows.length > 0"
          >
            <button
              type="button"
              class="workflow-group-header"
              :aria-expanded="templateWorkflowsExpanded"
              @click="toggleTemplateWorkflowsExpanded"
            >
              <span class="workflow-group-header-text">
                <span class="workflow-group-title">系统预设模板</span>
                <span class="workflow-group-count">
                  {{
                    workflowStore.hasActiveWorkflowSearch
                      ? `${workflowStore.filteredTemplateWorkflows.length}/${workflowStore.templateWorkflows.length}`
                      : workflowStore.templateWorkflows.length
                  }}
                </span>
              </span>
              <ChevronDown
                class="workflow-group-chevron"
                :class="{ 'is-collapsed': !templateWorkflowsExpanded }"
                :size="16"
                :stroke-width="2.2"
                aria-hidden="true"
              />
            </button>
            <div
              v-show="templateWorkflowsExpanded"
              class="workflow-group-body workflow-group-body--scroll workflow-group-body--templates"
            >
              <div
                v-for="wf in workflowStore.filteredTemplateWorkflows"
                :key="wf.id"
                class="workflow-item"
                :class="{ active: workflowStore.currentWorkflowId === wf.id }"
                @click="handleWorkflowClick(wf.id)"
              >
                <span class="workflow-marker" :class="wf.type === 'template' ? 'is-template' : 'is-custom'" aria-hidden="true" />
                <div class="workflow-info">
                  <span class="workflow-name">{{ wf.name }}</span>
                  <span class="workflow-time">{{ wf.time }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Search Empty -->
          <div
            v-if="workflowStore.hasActiveWorkflowSearch && !hasFilteredWorkflowResults"
            class="workflow-empty workflow-empty--search"
          >
            <div class="workflow-empty-icon" aria-hidden="true">
              <Search :size="22" :stroke-width="1.75" />
            </div>
            <div class="workflow-empty-text">未找到匹配的工作流</div>
            <div class="workflow-empty-hint">可搜索名称、节点标题或模板说明</div>
            <button class="workflow-empty-btn" type="button" @click="clearWorkflowSearch">清除搜索</button>
          </div>

          <!-- Empty State -->
          <div v-else-if="!hasAnyWorkflows" class="workflow-empty">
            <div class="workflow-empty-icon" aria-hidden="true">
              <GitBranch :size="26" :stroke-width="1.75" />
            </div>
            <div class="workflow-empty-text">暂无工作流</div>
            <button class="workflow-empty-btn" @click="handleNewWorkflow">创建第一个工作流</button>
          </div>
        </div>
      </template>

      <!-- ===================== 组件库面板 ===================== -->
      <template v-else>
        <!-- Search -->
        <div class="sidebar-section sidebar-search">
          <div class="workflow-search-box">
            <Search class="workflow-search-icon" :size="15" :stroke-width="2" aria-hidden="true" />
            <input
              type="text"
              v-model="toolboxSearch"
              placeholder="搜索组件..."
            />
            <button
              v-if="toolboxSearch"
              type="button"
              class="workflow-search-clear"
              title="清除搜索"
              @click="toolboxSearch = ''"
            >
              ×
            </button>
          </div>
        </div>

        <!-- Toolbox：左侧可拖入画布，右侧 + 仍一键添加 -->
        <div class="sidebar-scroll">
          <div
            v-for="section in filteredToolboxSections"
            :key="section.section"
            class="toolbox-section"
          >
            <div class="toolbox-section-title">{{ section.section }}</div>
            <div
              v-for="item in section.items"
              :key="section.section + '|' + item.schemaKey + '|' + item.name"
              class="toolbox-item"
            >
              <div
                class="toolbox-item-main"
                draggable="true"
                title="按住拖到画布"
                @dragstart="onToolboxDragStart($event, item)"
              >
                <div class="toolbox-item-icon" :class="item.type" aria-hidden="true" />
                <span class="toolbox-item-name">{{ item.name }}</span>
              </div>
              <button
                type="button"
                class="toolbox-item-add"
                draggable="false"
                title="添加到画布末尾"
                @click.stop="handleAddNode(item)"
              >
                <Plus :size="16" :stroke-width="2" aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      </template>
    </template>
  </aside>
</template>

<style scoped>
.sidebar-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
}

.loading-dots {
  display: flex;
  gap: 6px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background: var(--accent-primary);
  border-radius: 0;
  animation: pulse-dot 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

.workflow-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  gap: 8px;
}

.workflow-empty-icon {
  width: 48px;
  height: 48px;
  border-radius: 0;
  background: rgba(37, 99, 235, 0.06);
  border: 2px dashed rgba(37, 99, 235, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-primary);
}

.workflow-empty-text {
  font-size: 14px;
  color: var(--text-muted);
}

.workflow-empty-btn {
  margin-top: 8px;
  padding: 8px 16px;
  background: rgba(37, 99, 235, 0.1);
  border: 1px solid rgba(37, 99, 235, 0.25);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--accent-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.workflow-empty-btn:hover {
  background: rgba(37, 99, 235, 0.16);
  border-color: var(--accent-primary);
}

.workflow-search-box {
  position: relative;
  display: flex;
  align-items: center;
}

.workflow-search-icon {
  position: absolute;
  left: 11px;
  color: var(--text-muted);
  pointer-events: none;
  flex-shrink: 0;
}

.workflow-search-box input {
  width: 100%;
  padding: 9px 32px 9px 34px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.2s;
}

.workflow-search-box input:focus {
  border-color: var(--primary);
}

.workflow-search-clear {
  position: absolute;
  right: 6px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.workflow-search-clear:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.workflow-empty--search {
  padding-top: 28px;
}

.workflow-empty-hint {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  line-height: 1.45;
}

.workflow-delete-error {
  margin: 0 16px 8px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.4;
  color: #dc2626;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.25);
}

.workflow-delete-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}

.workflow-item:hover .workflow-delete-btn,
.workflow-item.active .workflow-delete-btn {
  opacity: 1;
}

.workflow-delete-btn:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.12);
  color: #dc2626;
}

.workflow-delete-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.workflow-list-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 8px;
  border-bottom: 1px solid var(--border-color);
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--bg-secondary);
}

.workflow-list-toolbar-btn {
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.workflow-list-toolbar-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.workflow-list-toolbar-btn.active {
  color: var(--accent-primary);
  border-color: rgba(37, 99, 235, 0.35);
  background: rgba(37, 99, 235, 0.08);
}

.workflow-list-toolbar-btn.danger {
  color: #dc2626;
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(239, 68, 68, 0.06);
}

.workflow-list-toolbar-btn.danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.12);
}

.workflow-list-toolbar-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.workflow-item.is-multi-selected {
  background: rgba(37, 99, 235, 0.08);
}

.workflow-select-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--accent-primary);
  cursor: pointer;
}

.workflow-select-btn:hover:not(:disabled) {
  background: rgba(37, 99, 235, 0.1);
}

.workflow-select-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbox-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: grab;
}

.toolbox-item-main:active {
  cursor: grabbing;
}
</style>
