import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useWorkflowStore = defineStore('workflow', () => {
  const currentWorkflowId = ref('wf1')
  const searchQuery = ref('')
  const workflowName = ref('论文翻译工作流')
  const inputLibrary = ref('论文翻译')
  const outputLibrary = ref('英文版论文')
  const targetLanguage = ref('英文')

  const workflows = ref({
    'wf1': {
      id: 'wf1',
      name: '论文翻译工作流',
      icon: '🌍',
      time: '刚刚编辑',
      type: 'custom'
    },
    'wf2': {
      id: 'wf2',
      name: '合同审查工作流',
      icon: '⚖️',
      time: '昨天',
      type: 'custom'
    },
    'wf3': {
      id: 'wf3',
      name: '数据提取工作流',
      icon: '📊',
      time: '3天前',
      type: 'custom'
    },
    'tpl1': {
      id: 'tpl1',
      name: '文档分析模板',
      icon: '📄',
      time: '系统预设',
      type: 'template'
    },
    'tpl2': {
      id: 'tpl2',
      name: '批量摘要模板',
      icon: '📝',
      time: '系统预设',
      type: 'template'
    }
  })

  const selectedDocs = ref([
    { id: 1, name: '深度学习综述.pdf', size: '2.4MB' },
    { id: 2, name: '注意力机制研究.pdf', size: '1.8MB' },
    { id: 3, name: 'Transformer架构.pdf', size: '3.2MB' },
    { id: 4, name: 'GAN生成对抗网络.pdf', size: '2.1MB' }
  ])

  const toolboxItems = ref([
    { section: '输入', items: [
      { icon: '📄', name: '文档上传' },
      { icon: '📊', name: 'Excel导入' },
      { icon: '📁', name: '文档库输入' }
    ]},
    { section: '处理', items: [
      { icon: '📖', name: '文档解析' },
      { icon: '🎯', name: '实体提取' },
      { icon: '✂️', name: '数据清洗' }
    ]},
    { section: 'AI 能力', items: [
      { icon: '🤖', name: 'LLM 翻译' },
      { icon: '💬', name: '对话生成' },
      { icon: '📝', name: '内容总结' }
    ]},
    { section: '输出', items: [
      { icon: '💾', name: '保存文件' },
      { icon: '📁', name: '输出到文档库' },
      { icon: '📧', name: '发送邮件' }
    ]}
  ])

  const canvasNodes = ref([
    { id: 'n1', type: 'input', icon: '📄', title: '文档输入', body: '从文档库选择多个文档', x: 60, y: 180 },
    { id: 'n2', type: 'ai', icon: '🤖', title: 'LLM 翻译', body: '使用大模型进行文档翻译', x: 320, y: 180 },
    { id: 'n3', type: 'output', icon: '📁', title: '输出到文档库', body: '保存到指定文档库空间', x: 580, y: 180 }
  ])

  const currentWorkflow = computed(() => workflows.value[currentWorkflowId.value])

  const customWorkflows = computed(() =>
    Object.values(workflows.value).filter(w => w.type === 'custom')
  )

  const templateWorkflows = computed(() =>
    Object.values(workflows.value).filter(w => w.type === 'template')
  )

  function selectWorkflow(workflowId) {
    currentWorkflowId.value = workflowId
    const wf = workflows.value[workflowId]
    if (wf) {
      workflowName.value = wf.name
    }
  }

  function createNewWorkflow() {
    const id = 'wf' + Date.now()
    workflows.value[id] = {
      id,
      name: '新建工作流',
      icon: '🔧',
      time: '刚刚',
      type: 'custom'
    }
    currentWorkflowId.value = id
    workflowName.value = '新建工作流'
  }

  function setSearchQuery(query) {
    searchQuery.value = query
  }

  function updateWorkflowName(name) {
    workflowName.value = name
    const wf = workflows.value[currentWorkflowId.value]
    if (wf) {
      wf.name = name
    }
  }

  return {
    currentWorkflowId,
    searchQuery,
    workflowName,
    inputLibrary,
    outputLibrary,
    targetLanguage,
    workflows,
    selectedDocs,
    toolboxItems,
    canvasNodes,
    currentWorkflow,
    customWorkflows,
    templateWorkflows,
    selectWorkflow,
    createNewWorkflow,
    setSearchQuery,
    updateWorkflowName
  }
})
