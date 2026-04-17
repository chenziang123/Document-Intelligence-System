<script setup>
import { ref } from 'vue'
import { useWorkflowStore } from '../../stores/workflowStore'

const workflowStore = useWorkflowStore()

const currentTool = ref('select')
const canvasRef = ref(null)

const tools = [
  { id: 'select', icon: '◻', title: '选择' },
  { id: 'connect', icon: '⬡', title: '连接' },
  { id: 'undo', icon: '↩', title: '撤销' },
  { id: 'redo', icon: '↪', title: '重做' },
  { id: 'save', icon: '💾', title: '保存' }
]

function selectTool(toolId) {
  currentTool.value = toolId
}

function saveWorkflow() {
  console.log('Saving workflow...')
}

function runWorkflow() {
  console.log('Running workflow...')
}
</script>

<template>
  <div class="workflow-canvas">
    <!-- Toolbar -->
    <div class="canvas-toolbar">
      <button
        v-for="tool in tools"
        :key="tool.id"
        class="canvas-tool"
        :class="{
          active: currentTool === tool.id,
          run: tool.id === 'run'
        }"
        :title="tool.title"
        @click="tool.id === 'save' ? saveWorkflow() : tool.id === 'run' ? runWorkflow() : selectTool(tool.id)"
      >
        {{ tool.icon }}
      </button>
    </div>

    <!-- Canvas Area -->
    <div class="workflow-canvas-area" ref="canvasRef">
      <!-- Nodes -->
      <div
        v-for="node in workflowStore.canvasNodes"
        :key="node.id"
        class="workflow-node"
        :style="{ left: node.x + 'px', top: node.y + 'px' }"
      >
        <div class="node-header">
          <div class="node-icon" :class="node.type">{{ node.icon }}</div>
          <span class="node-title">{{ node.title }}</span>
        </div>
        <div class="node-body">{{ node.body }}</div>
        <div class="node-port input-port"></div>
        <div class="node-port output-port"></div>
      </div>

      <!-- Connection Lines -->
      <svg style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none;">
        <path
          d="M 260 210 Q 290 210 320 210"
          stroke="rgba(168, 85, 247, 0.5)"
          stroke-width="2"
          fill="none"
          stroke-dasharray="5,5"
        />
        <path
          d="M 520 210 Q 550 210 580 210"
          stroke="rgba(168, 85, 247, 0.5)"
          stroke-width="2"
          fill="none"
          stroke-dasharray="5,5"
        />
      </svg>
    </div>
  </div>
</template>
