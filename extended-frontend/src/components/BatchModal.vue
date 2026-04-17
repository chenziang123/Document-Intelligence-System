<script setup>
import { ref, computed } from 'vue'
import { useWorkflowStore } from '../stores/workflowStore'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const workflowStore = useWorkflowStore()

const isProcessing = ref(false)
const progress = ref(0)
const progressList = ref([])

const canStart = computed(() => !isProcessing.value && progress.value === 0)

function closeModal() {
  if (!isProcessing.value) {
    emit('close')
  }
}

async function startProcess() {
  if (!canStart.value) return

  isProcessing.value = true
  progress.value = 0
  progressList.value = []

  const docs = workflowStore.selectedDocs

  for (let i = 0; i < docs.length; i++) {
    const doc = docs[i]
    progressList.value.push({ name: doc.name, status: 'processing', icon: '⏳' })

    // Simulate processing
    await new Promise(resolve => setTimeout(resolve, 800))

    progressList.value[i] = { name: doc.name, status: 'completed', icon: '✅' }
    progress.value = Math.round(((i + 1) / docs.length) * 100)
  }

  isProcessing.value = false
}

function getProgressText() {
  if (isProcessing.value) return '处理中...'
  if (progress.value === 100) return '处理完成！'
  return '准备就绪'
}
</script>

<template>
  <div class="modal-overlay" :class="{ active: visible }" @click.self="closeModal">
    <div class="modal">
      <!-- Header -->
      <div class="modal-header">
        <h2 class="modal-title">🔄 批量处理</h2>
        <button class="modal-close" @click="closeModal">×</button>
      </div>

      <!-- Body -->
      <div class="modal-body">
        <p class="modal-text">
          确定要使用 <strong>{{ workflowStore.workflowName }}</strong> 处理选中的文档吗？
        </p>

        <!-- Document List -->
        <div class="modal-docs">
          <div
            v-for="doc in workflowStore.selectedDocs"
            :key="doc.id"
            class="modal-doc"
          >
            <span>📕</span>
            <span style="flex:1;">{{ doc.name }}</span>
            <span style="color: var(--text-muted); font-size: 12px;">{{ doc.size }}</span>
          </div>
          <div class="modal-doc" style="color: var(--text-muted);">
            <span>...</span>
            <span style="flex:1;">还有 {{ Math.max(0, 10 - workflowStore.selectedDocs.length) }} 个文档</span>
          </div>
        </div>

        <!-- Progress -->
        <div class="batch-progress" v-if="isProcessing || progress > 0">
          <div class="progress-header">
            <span>{{ getProgressText() }}</span>
            <span>{{ progress }}%</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: progress + '%' }"></div>
          </div>
          <div class="progress-list">
            <div
              v-for="(item, index) in progressList"
              :key="index"
              class="progress-item"
              :class="item.status"
            >
              <span>{{ item.icon }}</span>
              <span>{{ item.name }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <button class="modal-btn cancel" @click="closeModal">取消</button>
        <button
          class="modal-btn primary"
          @click="startProcess"
          :disabled="!canStart"
        >
          {{ isProcessing ? '处理中...' : '开始处理' }}
        </button>
      </div>
    </div>
  </div>
</template>
