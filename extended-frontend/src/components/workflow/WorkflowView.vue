<script setup>
import { useWorkflowStore } from '../../stores/workflowStore'
import WorkflowSidebar from './WorkflowSidebar.vue'
import WorkflowCanvas from './WorkflowCanvas.vue'
import WorkflowConfig from './WorkflowConfig.vue'

const emit = defineEmits(['openBatchModal'])

const workflowStore = useWorkflowStore()

function openBatchModal() {
  emit('openBatchModal')
}
</script>

<template>
  <div class="workflow-view">
    <WorkflowSidebar />

    <!-- Toolbox + Canvas -->
    <div class="workflow-toolbox">
      <input
        type="text"
        class="toolbox-search"
        placeholder="搜索组件..."
      />

      <div
        v-for="section in workflowStore.toolboxItems"
        :key="section.section"
        class="toolbox-section"
      >
        <div class="toolbox-section-title">{{ section.section }}</div>
        <div
          v-for="item in section.items"
          :key="item.name"
          class="toolbox-item"
        >
          <div class="toolbox-item-icon">{{ item.icon }}</div>
          <span>{{ item.name }}</span>
        </div>
      </div>
    </div>

    <WorkflowCanvas @open-batch-modal="openBatchModal" />
    <WorkflowConfig @open-batch-modal="openBatchModal" />
  </div>
</template>
