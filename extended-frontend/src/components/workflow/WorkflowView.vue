<script setup>
defineOptions({ name: 'WorkflowView' })

import { ref, onDeactivated, watch } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import { useWorkflowStore } from '../../stores/workflowStore'
import WorkflowSidebar from './WorkflowSidebar.vue'
import WorkflowCanvas from './WorkflowCanvas.vue'
import WorkflowConfig from './WorkflowConfig.vue'

const workflowStore = useWorkflowStore()

const emit = defineEmits(['openBatchModal'])

const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
/** 进入画布编辑模式前右侧栏收起状态，退出时恢复 */
const rightCollapsedBeforeCanvasMode = ref(null)

watch(
  () => workflowStore.isOrderEditMode || workflowStore.isBulkDeleteMode || workflowStore.isEdgeEditMode,
  (inMode) => {
    if (inMode) {
      if (rightCollapsedBeforeCanvasMode.value === null) {
        rightCollapsedBeforeCanvasMode.value = rightCollapsed.value
      }
      rightCollapsed.value = true
      return
    }
    if (rightCollapsedBeforeCanvasMode.value !== null) {
      rightCollapsed.value = rightCollapsedBeforeCanvasMode.value
      rightCollapsedBeforeCanvasMode.value = null
    }
  },
)

function openBatchModal() {
  emit('openBatchModal')
}

onDeactivated(() => {
  workflowStore.syncCanvasToWorkflowCache()
})
</script>

<template>
  <div class="workflow-view" :class="{ 'left-collapsed': leftCollapsed, 'right-collapsed': rightCollapsed }">
    <!-- Left Sidebar -->
    <div class="sidebar-wrapper left-sidebar" :class="{ collapsed: leftCollapsed }">
      <WorkflowSidebar v-show="!leftCollapsed" />
      <button
        v-if="!leftCollapsed"
        type="button"
        class="panel-sidebar-toggle panel-sidebar-toggle--collapse-left"
        title="收起左侧栏"
        @click="leftCollapsed = true"
      >
        <ChevronLeft :size="18" :stroke-width="2.2" aria-hidden="true" />
      </button>
    </div>

    <!-- Canvas -->
    <WorkflowCanvas @open-batch-modal="openBatchModal" />

    <!-- 左侧栏收起后的展开按钮 -->
    <button
      v-if="leftCollapsed"
      type="button"
      class="panel-sidebar-toggle panel-sidebar-toggle--expand-left"
      title="展开左侧栏"
      @click="leftCollapsed = false"
    >
      <ChevronRight :size="18" :stroke-width="2.2" aria-hidden="true" />
    </button>

    <!-- Right Sidebar -->
    <div class="sidebar-wrapper right-sidebar" :class="{ collapsed: rightCollapsed }">
      <WorkflowConfig v-show="!rightCollapsed" @open-batch-modal="openBatchModal" />
      <button
        v-if="!rightCollapsed"
        type="button"
        class="panel-sidebar-toggle panel-sidebar-toggle--collapse-right"
        title="收起右侧栏"
        @click="rightCollapsed = true"
      >
        <ChevronRight :size="18" :stroke-width="2.2" aria-hidden="true" />
      </button>
    </div>

    <!-- 右侧栏收起后的展开按钮 -->
    <button
      v-if="rightCollapsed && !workflowStore.isOrderEditMode && !workflowStore.isBulkDeleteMode && !workflowStore.isEdgeEditMode"
      type="button"
      class="panel-sidebar-toggle panel-sidebar-toggle--expand-right"
      title="展开右侧栏"
      @click="rightCollapsed = false"
    >
      <ChevronLeft :size="18" :stroke-width="2.2" aria-hidden="true" />
    </button>
  </div>
</template>
