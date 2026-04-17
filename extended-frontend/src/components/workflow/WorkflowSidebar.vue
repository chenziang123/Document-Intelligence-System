<script setup>
import { useWorkflowStore } from '../../stores/workflowStore'

const workflowStore = useWorkflowStore()

function handleWorkflowClick(workflowId) {
  workflowStore.selectWorkflow(workflowId)
}

function handleNewWorkflow() {
  workflowStore.createNewWorkflow()
}

function handleSearch(e) {
  workflowStore.setSearchQuery(e.target.value)
}
</script>

<template>
  <aside class="workflow-sidebar">
    <!-- Header -->
    <div class="workflow-sidebar-header">
      <button class="new-workflow-btn" @click="handleNewWorkflow">
        <span>+</span>
        <span>新建工作流</span>
      </button>
    </div>

    <!-- Search -->
    <div class="workflow-search">
      <input
        type="text"
        placeholder="搜索工作流..."
        :value="workflowStore.searchQuery"
        @input="handleSearch"
      />
    </div>

    <!-- Workflow List -->
    <div class="workflow-list">
      <!-- My Workflows -->
      <div class="workflow-group">
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

      <!-- Templates -->
      <div class="workflow-group">
        <div class="workflow-group-title">预设模板</div>
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
    </div>
  </aside>
</template>
