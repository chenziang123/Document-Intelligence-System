import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useLibraryStore = defineStore('library', () => {
  const currentSpaceId = ref('research')
  const searchQuery = ref('')

  const spaces = ref([
    { id: 'research', name: '论文研究', icon: '📚', count: 24 },
    { id: 'contract', name: '合同管理', icon: '⚖️', count: 18 },
    { id: 'report', name: '年报分析', icon: '📊', count: 12 },
    { id: 'translate', name: '论文翻译', icon: '🌍', count: 8 },
    { id: 'data', name: '数据提取', icon: '🎯', count: 15 }
  ])

  const allDocs = ref([
    { id: 1, name: '深度学习综述.pdf', size: '2.4 MB', time: '2小时前' },
    { id: 2, name: '注意力机制研究.pdf', size: '1.8 MB', time: '2小时前' },
    { id: 3, name: 'Transformer架构.pdf', size: '3.2 MB', time: '2小时前' },
    { id: 4, name: 'GAN生成对抗网络.pdf', size: '2.1 MB', time: '昨天' },
    { id: 5, name: 'BERT预训练模型.pdf', size: '1.5 MB', time: '昨天' },
    { id: 6, name: '卷积神经网络.pdf', size: '2.8 MB', time: '3天前' },
    { id: 7, name: '循环神经网络.pdf', size: '1.9 MB', time: '3天前' },
    { id: 8, name: '自编码器原理.pdf', size: '1.2 MB', time: '1周前' },
    { id: 9, name: '目标检测算法.pdf', size: '3.5 MB', time: '1周前' },
    { id: 10, name: '图像分割技术.pdf', size: '2.3 MB', time: '1周前' }
  ])

  const selectedDocIds = ref(new Set())

  const currentSpace = computed(() => spaces.value.find(s => s.id === currentSpaceId.value))

  const selectedCount = computed(() => selectedDocIds.value.size)

  function selectSpace(spaceId) {
    currentSpaceId.value = spaceId
  }

  function toggleDocSelect(docId) {
    if (selectedDocIds.value.has(docId)) {
      selectedDocIds.value.delete(docId)
    } else {
      selectedDocIds.value.add(docId)
    }
  }

  function isDocSelected(docId) {
    return selectedDocIds.value.has(docId)
  }

  function clearSelection() {
    selectedDocIds.value.clear()
  }

  function setSearchQuery(query) {
    searchQuery.value = query
  }

  return {
    currentSpaceId,
    searchQuery,
    spaces,
    allDocs,
    selectedDocIds,
    currentSpace,
    selectedCount,
    selectSpace,
    toggleDocSelect,
    isDocSelected,
    clearSelection,
    setSearchQuery
  }
})
