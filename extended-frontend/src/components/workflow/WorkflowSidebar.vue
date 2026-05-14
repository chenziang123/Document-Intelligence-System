<script setup>
import { ref, onMounted, computed } from 'vue'
import { useWorkflowStore } from '../../stores/workflowStore'

const workflowStore = useWorkflowStore()

const toolboxSearch = ref('')
const activeSection = ref('workflow') // 'workflow' | 'toolbox'
const isLoading = ref(false)

onMounted(async () => {
  isLoading.value = true
  try {
    await Promise.all([
      workflowStore.loadWorkflows(),
      workflowStore.loadTemplates()
    ])
    // 加载后如果没有选中任何工作流，自动加载翻译模板
    if (!workflowStore.currentWorkflowId) {
      workflowStore.loadTranslationTemplate()
    }
  } finally {
    isLoading.value = false
  }
})

function handleWorkflowClick(workflowId) {
  workflowStore.selectWorkflow(workflowId)
}

function handleNewWorkflow() {
  workflowStore.createNewWorkflow()
}

function handleSearch(e) {
  workflowStore.setSearchQuery(e.target.value)
}

function handleAddNode(item) {
  workflowStore.addNode(item)
}

function handleLoadTranslationTemplate() {
  workflowStore.loadTranslationTemplate()
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
          <span>📋</span> 工作流
        </button>
        <button
          class="switcher-btn"
          :class="{ active: activeSection === 'toolbox' }"
          @click="activeSection = 'toolbox'"
        >
          <span>🧩</span> 组件库
        </button>
      </div>

      <!-- ===================== 工作流面板 ===================== -->
      <template v-if="activeSection === 'workflow'">
        <!-- New Workflow -->
        <div class="sidebar-section">
          <button class="new-workflow-btn" @click="handleNewWorkflow">
            <span>+</span>
            <span>新建工作流</span>
          </button>
        </div>

        <!-- Quick Template: Translation Flow -->
        <div class="sidebar-section">
          <div class="template-quick-card" @click="handleLoadTranslationTemplate">
            <div class="template-quick-icon">🌍</div>
            <div class="template-quick-info">
              <div class="template-quick-name">文档翻译流</div>
              <div class="template-quick-desc">PDF → AI翻译 → 输出</div>
            </div>
            <div class="template-quick-badge">预设</div>
          </div>
        </div>

        <!-- Search -->
        <div class="sidebar-section sidebar-search">
          <input
            type="text"
            placeholder="搜索工作流..."
            :value="workflowStore.searchQuery"
            @input="handleSearch"
          />
        </div>

        <!-- Workflow List -->
        <div class="sidebar-scroll">
          <!-- Custom Workflows -->
          <div class="workflow-group" v-if="workflowStore.customWorkflows.length > 0">
            <div class="workflow-group-title">我的工作流</div>
            <div
              v-for="wf in workflowStore.customWorkflows"
              :key="wf.id"
              class="workflow-item"
              :class="{ active: workflowStore.currentWorkflowId === wf.id }"
              @click="handleWorkflowClick(wf.id)"
            >
              <span class="workflow-icon">{{ wf.icon }}</span>
              <div class="workflow-info">
                <span class="workflow-name">{{ wf.name }}</span>
                <span class="workflow-time">{{ wf.time }}</span>
              </div>
            </div>
          </div>

          <!-- System Templates -->
          <div class="workflow-group" v-if="workflowStore.templateWorkflows.length > 0">
            <div class="workflow-group-title">系统预设模板</div>
            <div
              v-for="wf in workflowStore.templateWorkflows"
              :key="wf.id"
              class="workflow-item"
              :class="{ active: workflowStore.currentWorkflowId === wf.id }"
              @click="handleWorkflowClick(wf.id)"
            >
              <span class="workflow-icon">{{ wf.icon }}</span>
              <div class="workflow-info">
                <span class="workflow-name">{{ wf.name }}</span>
                <span class="workflow-time">{{ wf.time }}</span>
              </div>
            </div>
          </div>

          <!-- Empty State -->
          <div v-if="workflowStore.customWorkflows.length === 0 && workflowStore.templateWorkflows.length === 0" class="workflow-empty">
            <div class="workflow-empty-icon">📋</div>
            <div class="workflow-empty-text">暂无工作流</div>
            <button class="workflow-empty-btn" @click="handleNewWorkflow">创建第一个工作流</button>
          </div>
        </div>
      </template>

      <!-- ===================== 组件库面板 ===================== -->
      <template v-else>
        <!-- Search -->
        <div class="sidebar-section sidebar-search">
          <input
            type="text"
            v-model="toolboxSearch"
            placeholder="搜索组件..."
          />
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
                <div class="toolbox-item-icon">{{ item.icon }}</div>
                <span class="toolbox-item-name">{{ item.name }}</span>
              </div>
              <button
                type="button"
                class="toolbox-item-add"
                draggable="false"
                title="添加到画布末尾"
                @click.stop="handleAddNode(item)"
              >+</button>
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
  background: var(--accent-purple);
  border-radius: 50%;
  animation: pulse-dot 1.4s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse-dot {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

.template-quick-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(168, 85, 247, 0.1));
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}

.template-quick-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(168, 85, 247, 0.05));
  opacity: 0;
  transition: opacity 0.2s;
}

.template-quick-card:hover {
  border-color: rgba(99, 102, 241, 0.5);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.2);
}

.template-quick-card:hover::before {
  opacity: 1;
}

.template-quick-icon {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, var(--accent-primary), var(--accent-purple));
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.template-quick-info {
  flex: 1;
  min-width: 0;
}

.template-quick-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.template-quick-desc {
  font-size: 12px;
  color: var(--text-muted);
}

.template-quick-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-primary);
  background: rgba(99, 102, 241, 0.15);
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
}

.workflow-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  gap: 8px;
}

.workflow-empty-icon {
  font-size: 40px;
  opacity: 0.3;
}

.workflow-empty-text {
  font-size: 14px;
  color: var(--text-muted);
}

.workflow-empty-btn {
  margin-top: 8px;
  padding: 8px 16px;
  background: rgba(99, 102, 241, 0.15);
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--accent-primary);
  cursor: pointer;
  transition: all 0.2s;
}

.workflow-empty-btn:hover {
  background: rgba(99, 102, 241, 0.25);
  border-color: var(--accent-primary);
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
