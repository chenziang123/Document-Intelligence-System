<script setup>
import { ref } from 'vue'
import { useWorkflowStore } from '../../stores/workflowStore'

const emit = defineEmits(['openBatchModal'])

const workflowStore = useWorkflowStore()

const inputLibraries = ['论文翻译', '合同审查', '年报分析', '数据提取']
const outputLibraries = ['英文版论文', '审查结果', '分析结果', '新建文档库...']
const languages = ['英文', '中文', '日文', '韩文']

function openBatchModal() {
  emit('openBatchModal')
}
</script>

<template>
  <div class="workflow-config-panel">
    <div class="config-title">⚙️ 工作流配置</div>

    <!-- Basic Settings -->
    <div class="config-section">
      <div class="config-section-title">基础设置</div>
      <div class="config-field">
        <label class="config-label">工作流名称</label>
        <input
          type="text"
          class="config-input"
          :value="workflowStore.workflowName"
          @input="$emit('update:workflowName', $event.target.value)"
        />
      </div>
      <div class="config-field">
        <label class="config-label">输入文档库</label>
        <select class="config-select" v-model="workflowStore.inputLibrary">
          <option v-for="lib in inputLibraries" :key="lib" :value="lib">{{ lib }}</option>
        </select>
      </div>
      <div class="config-field">
        <label class="config-label">输出文档库</label>
        <select class="config-select" v-model="workflowStore.outputLibrary">
          <option v-for="lib in outputLibraries" :key="lib" :value="lib">{{ lib }}</option>
        </select>
      </div>
    </div>

    <!-- Processing Settings -->
    <div class="config-section">
      <div class="config-section-title">处理设置</div>
      <div class="config-field">
        <label class="config-label">翻译目标语言</label>
        <select class="config-select" v-model="workflowStore.targetLanguage">
          <option v-for="lang in languages" :key="lang" :value="lang">{{ lang }}</option>
        </select>
      </div>
    </div>

    <!-- Selected Documents -->
    <div class="config-section">
      <div class="config-section-title">
        待处理文档 <span id="docCount">({{ workflowStore.selectedDocs.length }})</span>
      </div>
      <div class="selected-docs-list">
        <div
          v-for="doc in workflowStore.selectedDocs"
          :key="doc.id"
          class="selected-doc-item"
        >
          <span class="selected-doc-icon">📕</span>
          <span class="selected-doc-name">{{ doc.name }}</span>
          <span class="selected-doc-size">{{ doc.size }}</span>
        </div>
      </div>
    </div>

    <!-- Action Button -->
    <button class="config-btn" @click="openBatchModal">
      <span>▶</span>
      <span>开始批量处理</span>
    </button>
  </div>
</template>
