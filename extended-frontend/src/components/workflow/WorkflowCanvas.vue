<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useWorkflowStore } from '../../stores/workflowStore'

const workflowStore = useWorkflowStore()

const canvasAreaRef = ref(null)
const canvasInnerRef = ref(null)

const DROP_MIME = 'application/x-workflow-node'

/** 是否允许从组件库拖入（放宽以兼容各浏览器 MIME 列表） */
function canAcceptToolboxDrag(e) {
  const types = [...(e.dataTransfer?.types || [])]
  return types.some(
    t =>
      t === DROP_MIME ||
      t === 'text/plain' ||
      t === 'Text'
  )
}

function parseDroppedToolboxItem(e) {
  let raw = ''
  try {
    raw = e.dataTransfer.getData(DROP_MIME)
  } catch (_) {
    /* ignore */
  }
  if (!raw) {
    try {
      raw = e.dataTransfer.getData('text/plain')
    } catch (_) {
      /* ignore */
    }
  }
  if (!raw || raw[0] !== '{') return null
  try {
    const o = JSON.parse(raw)
    if (o && typeof o.schemaKey === 'string' && o.title) return o
  } catch (_) {
    /* ignore */
  }
  return null
}

const dropZoneActive = ref(false)

function onCanvasDragEnter(e) {
  if (!canAcceptToolboxDrag(e)) return
  e.preventDefault()
  dropZoneActive.value = true
}

function onCanvasDragOver(e) {
  if (!canAcceptToolboxDrag(e)) return
  e.preventDefault()
  try {
    e.dataTransfer.dropEffect = 'copy'
  } catch (_) {
    /* ignore */
  }
}

function onCanvasDragLeave(e) {
  const el = canvasAreaRef.value
  if (el && e.relatedTarget && el.contains(e.relatedTarget)) return
  dropZoneActive.value = false
}

function onCanvasDrop(e) {
  dropZoneActive.value = false
  const item = parseDroppedToolboxItem(e)
  if (!item) return
  e.preventDefault()
  e.stopPropagation()
  const { x, y } = pointerToInnerLocal(e)
  const NODE_W = 200
  const NODE_H = 88
  workflowStore.addNodeAt(item, x - NODE_W / 2, y - NODE_H / 2)
}

// Transform-based pan + zoom state
const pan = ref({ x: 0, y: 0 })
const zoom = ref(1)
const MIN_ZOOM = 0.3
const MAX_ZOOM = 2.5

const isPanning = ref(false)
const panStart = ref({ mouseX: 0, mouseY: 0, panX: 0, panY: 0 })

const canvasStyle = computed(() => ({
  transform: `translate(${pan.value.x}px, ${pan.value.y}px) scale(${zoom.value})`,
  transformOrigin: '0 0',
}))

const zoomPercentLabel = computed(() => `${Math.round(zoom.value * 100)}%`)

/** 屏幕坐标 → canvas-inner 逻辑坐标（与 node.x / node.y 一致） */
function screenToInnerLocal(screenX, screenY) {
  const area = canvasAreaRef.value
  if (!area) return { x: 30, y: 160 }
  const rect = area.getBoundingClientRect()
  const z = zoom.value || 1
  return {
    x: (screenX - rect.left - pan.value.x) / z,
    y: (screenY - rect.top - pan.value.y) / z,
  }
}

/** 将指针位置转为 canvas-inner 内坐标（与 node.x / node.y 一致） */
function pointerToInnerLocal(e) {
  return screenToInnerLocal(e.clientX, e.clientY)
}

function onCanvasWheel(event) {
  if (!event.ctrlKey && !event.metaKey) return
  event.preventDefault()

  const area = canvasAreaRef.value
  if (!area) return

  const rect = area.getBoundingClientRect()
  const mouseX = event.clientX - rect.left
  const mouseY = event.clientY - rect.top
  const z = zoom.value || 1

  const before = {
    x: (mouseX - pan.value.x) / z,
    y: (mouseY - pan.value.y) / z,
  }

  const factor = event.deltaY < 0 ? 1.1 : 1 / 1.1
  const nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z * factor))
  if (nextZoom === z) return

  zoom.value = nextZoom
  pan.value = {
    x: mouseX - before.x * nextZoom,
    y: mouseY - before.y * nextZoom,
  }
  nextTick(refreshPortLayout)
}

/** 节点占位尺寸（与 main.css .workflow-node 一致） */
const NODE_LAYOUT = { w: 240, h: 88 }
const VIEW_FIT_PADDING = 32

function getWorkflowBounds() {
  const nodes = workflowStore.canvasNodes
  if (!nodes.length) return null

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  for (const n of nodes) {
    minX = Math.min(minX, n.x)
    minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x + NODE_LAYOUT.w)
    maxY = Math.max(maxY, n.y + NODE_LAYOUT.h)
  }

  return {
    minX,
    minY,
    maxX,
    maxY,
    width: maxX - minX,
    height: maxY - minY,
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
  }
}

/** 计算使工作流尽量居中的平移（zoom=1） */
function computeCenteredPan(z = 1) {
  const area = canvasAreaRef.value
  const bounds = getWorkflowBounds()
  if (!area || !bounds) return { x: 0, y: 0 }

  const rect = area.getBoundingClientRect()
  const topBar = area.querySelector('.canvas-top-bar')
  const topInset = topBar ? topBar.offsetHeight + 20 : 108
  const pad = VIEW_FIT_PADDING

  const viewW = Math.max(120, rect.width - pad * 2)
  const viewH = Math.max(120, rect.height - topInset - pad)

  const targetX = pad + viewW / 2
  const targetY = topInset + viewH / 2

  return {
    x: targetX - bounds.cx * z,
    y: targetY - bounds.cy * z,
  }
}

function resetCanvasView() {
  zoom.value = 1
  pan.value = computeCenteredPan(1)
  nextTick(refreshPortLayout)
}

// Node drag state
const isDraggingNode = ref(false)
const dragNodeId = ref(null)
const dragStart = ref({ mouseX: 0, mouseY: 0, nodeX: 0, nodeY: 0 })
/** 区分点击与拖拽，避免多选模式下拖移节点误触发选中 */
const nodeDragMoved = ref(false)
const DRAG_CLICK_THRESHOLD = 5

function handleNodeClick(event, nodeId) {
  event.stopPropagation()
  if (nodeDragMoved.value) {
    nodeDragMoved.value = false
    return
  }
  if (workflowStore.isBulkDeleteMode) {
    workflowStore.toggleBulkSelectNode(nodeId)
    return
  }
  workflowStore.selectNode(nodeId)
}

function handleNodeDelete(event, nodeId) {
  event.stopPropagation()
  workflowStore.deleteNode(nodeId)
}

// Canvas pan
function onCanvasMouseDown(event) {
  if (event.button !== 0) return
  if (event.target.closest('.workflow-node')) return
  isPanning.value = true
  panStart.value = {
    mouseX: event.clientX,
    mouseY: event.clientY,
    panX: pan.value.x,
    panY: pan.value.y
  }
  event.preventDefault()
}

function onCanvasMouseMove(event) {
  if (isPanning.value) {
    const dx = event.clientX - panStart.value.mouseX
    const dy = event.clientY - panStart.value.mouseY
    pan.value = {
      x: panStart.value.panX + dx,
      y: panStart.value.panY + dy
    }
  } else if (edgeDragFrom.value) {
    onEdgeDragMouseMove(event)
  } else if (isDraggingNode.value && dragNodeId.value) {
    const dx = event.clientX - dragStart.value.mouseX
    const dy = event.clientY - dragStart.value.mouseY
    if (Math.hypot(dx, dy) >= DRAG_CLICK_THRESHOLD) {
      nodeDragMoved.value = true
    }
    workflowStore.updateNodePosition(
      dragNodeId.value,
      dragStart.value.nodeX + dx / (zoom.value || 1),
      dragStart.value.nodeY + dy / (zoom.value || 1)
    )
  }
}

function onCanvasMouseUp() {
  if (edgeDragFrom.value) {
    cancelEdgeDrag()
  }
  // 仅「编辑顺序」模式根据位置重排执行列表；连线/多选模式只改坐标
  if (isDraggingNode.value && dragNodeId.value && workflowStore.isOrderEditMode) {
    workflowStore.reorderNodesByCanvasPosition()
  }
  isPanning.value = false
  isDraggingNode.value = false
  dragNodeId.value = null
}

function handleAlignCanvas() {
  workflowStore.alignCanvasNodes()
}

// Node drag（编辑连线 / 多选清除：仅移动坐标，不改变执行顺序）
function onNodeMouseDown(event, nodeId) {
  if (workflowStore.isExecuting) return
  if (event.target.closest('.node-port')) return
  if (event.target.closest('button')) return
  event.stopPropagation()
  const node = workflowStore.canvasNodes.find(n => n.id === nodeId)
  if (!node) return
  nodeDragMoved.value = false
  isDraggingNode.value = true
  dragNodeId.value = nodeId
  dragStart.value = {
    mouseX: event.clientX,
    mouseY: event.clientY,
    nodeX: node.x,
    nodeY: node.y
  }
}

function handleCanvasClick(event) {
  if (event.target.classList.contains('canvas-area') || event.target.classList.contains('canvas-inner')) {
    if (workflowStore.isBulkDeleteMode) return
    workflowStore.selectNode(null)
  }
}

function isBulkSelected(nodeId) {
  return workflowStore.bulkSelectedNodeIds.includes(nodeId)
}

/** 端口未测量完成时的回退尺寸（与画布布局常量接近） */
const NODE_CONN_FALLBACK = { w: 240, h: 88 }

/** 触发连线重算（节点移动/尺寸变化后刷新端口坐标） */
const layoutTick = ref(0)
function refreshPortLayout() {
  layoutTick.value++
}

function measureNodePortPoint(nodeId, side) {
  void layoutTick.value
  const inner = canvasInnerRef.value
  if (!inner || !nodeId) return null
  const nodeEl = inner.querySelector(`[data-node-id="${nodeId}"]`)
  if (!nodeEl) return null
  const portEl = nodeEl.querySelector(side === 'out' ? '.output-port' : '.input-port')
  if (!portEl) return null
  const portRect = portEl.getBoundingClientRect()
  return screenToInnerLocal(
    portRect.left + portRect.width / 2,
    portRect.top + portRect.height / 2
  )
}

/** 连线锚点与左右端口中心对齐 */
function nodeOutPoint(node) {
  return (
    measureNodePortPoint(node.id, 'out') ?? {
      x: node.x + NODE_CONN_FALLBACK.w,
      y: node.y + NODE_CONN_FALLBACK.h / 2,
    }
  )
}

function nodeInPoint(node) {
  return (
    measureNodePortPoint(node.id, 'in') ?? {
      x: node.x,
      y: node.y + NODE_CONN_FALLBACK.h / 2,
    }
  )
}

let portLayoutObserver = null

watch(() => zoom.value, () => nextTick(refreshPortLayout))

onMounted(() => {
  nextTick(refreshPortLayout)
  if (canvasInnerRef.value && typeof ResizeObserver !== 'undefined') {
    portLayoutObserver = new ResizeObserver(() => refreshPortLayout())
    portLayoutObserver.observe(canvasInnerRef.value)
  }
  window.addEventListener('resize', refreshPortLayout)
})

onUnmounted(() => {
  portLayoutObserver?.disconnect()
  window.removeEventListener('resize', refreshPortLayout)
})

watch(() => workflowStore.canvasNodes, () => nextTick(refreshPortLayout), { deep: true })
watch(() => workflowStore.workflowEdges, () => nextTick(refreshPortLayout), { deep: true })
watch(
  () => [workflowStore.hasCustomEdges, workflowStore.isEdgeEditMode, workflowStore.isOrderEditMode],
  () => nextTick(refreshPortLayout)
)

/**
 * 连接路径：原先用 Q 且控制点在水平线上会退化成直线；
 * - 有明显纵向偏移时用正交「折线」；
 * - 其余用三次贝塞尔近似水平出站/到站，弧线更自然；
 * - 大行距时仍可走平滑弧线。
 */
function buildConnectionPath(p1, p2) {
  const x1 = p1.x
  const y1 = p1.y
  const x2 = p2.x
  const y2 = p2.y
  const dx = x2 - x1
  const dy = y2 - y1
  const adx = Math.abs(dx)
  const ady = Math.abs(dy)

  if (adx < 1 && ady < 1) {
    return `M ${x1} ${y1}`
  }

  // 近似同一行：画直线即可
  if (ady < 5) {
    return `M ${x1} ${y1} L ${x2} ${y2}`
  }

  // 纵向错位明显时用正交布线（可读「折弯」）
  const preferOrthogonal = ady >= 14 && ady >= adx * 0.22
  if (preferOrthogonal) {
    const midX = x1 + dx * 0.5
    return `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`
  }

  // 顺滑弧线：两端沿水平方向伸出控制柄
  const tension = Math.min(160, Math.max(42, adx * 0.42))
  const sign = dx >= 0 ? 1 : -1
  const c1x = x1 + sign * tension
  const c2x = x2 - sign * tension
  return `M ${x1} ${y1} C ${c1x} ${y1} ${c2x} ${y2} ${x2} ${y2}`
}

const connPaths = computed(() => {
  void layoutTick.value
  const nodes = workflowStore.canvasNodes
  if (nodes.length < 2 && !workflowStore.hasCustomEdges) return []

  const nodeMap = {}
  nodes.forEach(n => { nodeMap[n.id] = n })

  const edges = workflowStore.hasCustomEdges
    ? workflowStore.workflowEdges
    : nodes.slice(0, -1).map((fromNode, i) => ({
        id: `linear-${fromNode.id}-${nodes[i + 1].id}`,
        from: fromNode.id,
        to: nodes[i + 1].id,
        label: '',
      }))

  return edges
    .map(e => {
      const fromNode = nodeMap[e.from]
      const toNode = nodeMap[e.to]
      if (!fromNode || !toNode) return null
      const pOut = nodeOutPoint(fromNode)
      const pIn = nodeInPoint(toNode)
      return {
        d: buildConnectionPath(pOut, pIn),
        key: e.id || `conn-${e.from}-${e.to}`,
        edgeId: e.id,
        fromId: e.from,
        toId: e.to,
        label: e.label || '',
        mid: {
          x: (pOut.x + pIn.x) / 2,
          y: (pOut.y + pIn.y) / 2,
        },
      }
    })
    .filter(Boolean)
})

// ==================== 连线编辑 ====================
const edgeDragFrom = ref(null)
const edgeDragPointer = ref(null)

function getNodeById(nodeId) {
  return workflowStore.canvasNodes.find(n => n.id === nodeId)
}

function onOutputPortMouseDown(event, nodeId) {
  if (!workflowStore.isEdgeEditMode || workflowStore.isExecuting) return
  event.stopPropagation()
  event.preventDefault()
  edgeDragFrom.value = nodeId
  const node = getNodeById(nodeId)
  edgeDragPointer.value = node ? nodeOutPoint(node) : pointerToInnerLocal(event)
}

function onInputPortMouseUp(event, nodeId) {
  if (!workflowStore.isEdgeEditMode || !edgeDragFrom.value) return
  event.stopPropagation()
  finishEdgeConnection(nodeId)
}

function onInputPortMouseEnter(event, nodeId) {
  if (!workflowStore.isEdgeEditMode || !edgeDragFrom.value) return
  if (edgeDragFrom.value === nodeId) return
  event.stopPropagation()
  finishEdgeConnection(nodeId)
}

function finishEdgeConnection(toId) {
  const fromId = edgeDragFrom.value
  edgeDragFrom.value = null
  edgeDragPointer.value = null
  if (!fromId || fromId === toId) return

  const fromNode = getNodeById(fromId)
  let label = ''
  if (fromNode?.schemaKey === 'schema-condition') {
    const existing = workflowStore.workflowEdges.filter(e => e.from === fromId)
    const hasTrue = existing.some(e => e.label === 'true')
    const hasFalse = existing.some(e => e.label === 'false')
    if (!hasTrue) label = 'true'
    else if (!hasFalse) label = 'false'
    else {
      const picked = window.prompt('条件出口标签：输入 true 或 false', 'true')
      if (picked !== 'true' && picked !== 'false') return
      label = picked
    }
  }
  workflowStore.addWorkflowEdge(fromId, toId, label)
}

function cancelEdgeDrag() {
  edgeDragFrom.value = null
  edgeDragPointer.value = null
}

function onEdgeDragMouseMove(event) {
  if (!edgeDragFrom.value) return
  edgeDragPointer.value = pointerToInnerLocal(event)
}

function handleEdgePathClick(event, edgeId) {
  if (!workflowStore.isEdgeEditMode || !edgeId) return
  event.stopPropagation()
  if (window.confirm('删除这条连线？')) {
    workflowStore.removeWorkflowEdge(edgeId)
  }
}

const edgePreviewPath = computed(() => {
  if (!edgeDragFrom.value || !edgeDragPointer.value) return ''
  const fromNode = getNodeById(edgeDragFrom.value)
  if (!fromNode) return ''
  return buildConnectionPath(nodeOutPoint(fromNode), edgeDragPointer.value)
})

const nodeProgressById = computed(() => {
  const map = {}
  ;(workflowStore.nodeProgress || []).forEach(item => {
    if (item?.id) map[item.id] = item
  })
  return map
})

function getNodeRunState(nodeId) {
  return nodeProgressById.value[nodeId]?.status || 'idle'
}

// 当前选中节点在数组中的索引
const selectedIndex = computed(() => {
  if (!workflowStore.selectedNodeId) return -1
  return workflowStore.canvasNodes.findIndex(n => n.id === workflowStore.selectedNodeId)
})
</script>

<template>
  <div class="workflow-canvas">
    <!-- Canvas Area -->
    <div
      ref="canvasAreaRef"
      class="canvas-area"
      :class="{
        'is-panning': isPanning,
        'canvas-area--drop-target': dropZoneActive,
        'canvas-area--order-edit': workflowStore.isOrderEditMode,
        'canvas-area--bulk-delete': workflowStore.isBulkDeleteMode,
        'canvas-area--edge-edit': workflowStore.isEdgeEditMode,
      }"
      @click="handleCanvasClick"
      @mousedown="onCanvasMouseDown"
      @mousemove="onCanvasMouseMove"
      @mouseup="onCanvasMouseUp"
      @mouseleave="onCanvasMouseUp"
      @dragenter="onCanvasDragEnter"
      @dragover="onCanvasDragOver"
      @dragleave="onCanvasDragLeave"
      @drop="onCanvasDrop"
      @wheel="onCanvasWheel"
    >
      <!-- 顶部：左侧工具栏 + 右侧执行顺序（互不重叠） -->
      <div v-if="workflowStore.canvasNodes.length > 0" class="canvas-top-bar">
        <div class="canvas-toolbar-zone" @mousedown.stop @click.stop>
          <div class="canvas-action-bar">
            <button
              type="button"
              class="canvas-action-btn"
              :class="{ active: workflowStore.isEdgeEditMode }"
              :disabled="workflowStore.isExecuting || workflowStore.isOrderEditMode || workflowStore.isBulkDeleteMode || workflowStore.canvasNodes.length < 2"
              @click="workflowStore.toggleEdgeEditMode()"
            >
              {{ workflowStore.isEdgeEditMode ? '完成连线' : '编辑连线' }}
            </button>
            <button
              v-if="workflowStore.isEdgeEditMode && workflowStore.hasCustomEdges"
              type="button"
              class="canvas-action-btn canvas-action-btn--danger"
              :disabled="workflowStore.isExecuting"
              title="清除所有自定义连线，恢复按顺序链式连接"
              @click="workflowStore.clearWorkflowEdges()"
            >
              清除连线
            </button>
            <button
              type="button"
              class="canvas-action-btn"
              :class="{ active: workflowStore.isOrderEditMode }"
              :disabled="workflowStore.isExecuting || workflowStore.isBulkDeleteMode || workflowStore.isEdgeEditMode"
              @click="workflowStore.toggleOrderEditMode()"
            >
              {{ workflowStore.isOrderEditMode ? '完成编辑' : '编辑顺序' }}
            </button>
            <button
              type="button"
              class="canvas-action-btn"
              :disabled="workflowStore.isExecuting || workflowStore.canvasNodes.length < 2"
              title="按当前执行顺序整理为一行"
              @click="handleAlignCanvas"
            >
              自动对齐
            </button>
            <button
              type="button"
              class="canvas-action-btn"
              :class="{ 'canvas-action-btn--neutral': workflowStore.isBulkDeleteMode }"
              :disabled="workflowStore.isExecuting || workflowStore.isOrderEditMode || workflowStore.isEdgeEditMode"
              @click="workflowStore.toggleBulkDeleteMode()"
            >
              {{ workflowStore.isBulkDeleteMode ? '清除完毕' : '多选清除' }}
            </button>
            <button
              v-if="workflowStore.isBulkDeleteMode && workflowStore.canvasNodes.length > 0 && workflowStore.bulkSelectedNodeIds.length < workflowStore.canvasNodes.length"
              type="button"
              class="canvas-action-btn"
              :disabled="workflowStore.isExecuting"
              @click="workflowStore.selectAllBulkNodes()"
            >
              一键全选
            </button>
            <button
              v-if="workflowStore.isBulkDeleteMode && workflowStore.bulkSelectedNodeIds.length > 0"
              type="button"
              class="canvas-action-btn"
              :disabled="workflowStore.isExecuting"
              @click="workflowStore.clearBulkSelection()"
            >
              取消选中
            </button>
            <button
              v-if="workflowStore.isBulkDeleteMode && workflowStore.bulkSelectedNodeIds.length > 0"
              type="button"
              class="canvas-action-btn canvas-action-btn--danger"
              :disabled="workflowStore.isExecuting"
              @click="workflowStore.deleteBulkSelectedNodes()"
            >
              清除选中 ({{ workflowStore.bulkSelectedNodeIds.length }})
            </button>
            <p v-if="workflowStore.isEdgeEditMode" class="canvas-action-tip canvas-action-tip--edge">
              从出口拖向入口；可拖节点调位置（不改顺序）
            </p>
            <p v-if="workflowStore.isOrderEditMode" class="canvas-action-tip">
              拖拽后松手更新顺序
            </p>
            <p v-if="workflowStore.isBulkDeleteMode" class="canvas-action-tip canvas-action-tip--danger">
              点击多选、一键全选或取消选中；可拖节点调位置
            </p>
          </div>
        </div>
        <div class="canvas-step-zone">
          <div class="canvas-step-bar">
            <template v-for="(node, i) in workflowStore.canvasNodes" :key="'step-' + node.id">
              <div
                class="step-item"
                :class="{
                  ['type-' + node.type]: true,
                  'step-done': selectedIndex > -1 && i < selectedIndex,
                  'step-active': workflowStore.selectedNodeId === node.id,
                  ['run-' + getNodeRunState(node.id)]: true
                }"
              >
                <div class="step-num">{{ i + 1 }}</div>
                <div class="step-name">{{ node.title }}</div>
              </div>
              <div v-if="i < workflowStore.canvasNodes.length - 1" class="step-line" :key="'line-' + i"></div>
            </template>
          </div>
        </div>
      </div>

      <!-- Inner transformable container (nodes + connections move) -->
      <div ref="canvasInnerRef" class="canvas-inner" :style="canvasStyle">
        <!-- SVG Connections -->
        <svg class="connections-svg">
          <path
            v-for="cp in connPaths"
            :key="cp.key"
            :d="cp.d"
            class="conn-path"
            :class="{
              'conn-selected':
                workflowStore.selectedNodeId === cp.fromId ||
                workflowStore.selectedNodeId === cp.toId,
              'conn-custom': workflowStore.hasCustomEdges,
              'conn-edge-edit': workflowStore.isEdgeEditMode,
            }"
            @click="handleEdgePathClick($event, cp.edgeId)"
          />
          <path
            v-if="edgePreviewPath"
            :d="edgePreviewPath"
            class="conn-path conn-preview"
          />
          <text
            v-for="cp in connPaths.filter(c => c.label)"
            :key="'lbl-' + cp.key"
            :x="cp.mid.x"
            :y="cp.mid.y - 6"
            class="conn-label"
            text-anchor="middle"
          >{{ cp.label }}</text>
        </svg>

        <!-- Nodes -->
        <div
          v-for="(node, i) in workflowStore.canvasNodes"
          :key="node.id"
          :data-node-id="node.id"
          class="workflow-node"
          :class="{
            selected: workflowStore.selectedNodeId === node.id && !workflowStore.isBulkDeleteMode,
            'bulk-selected': workflowStore.isBulkDeleteMode && isBulkSelected(node.id),
            ['type-' + node.type]: true,
            ['run-' + getNodeRunState(node.id)]: true,
            'has-run-status': getNodeRunState(node.id) !== 'idle',
            'order-edit-mode': workflowStore.isOrderEditMode,
            'bulk-delete-mode': workflowStore.isBulkDeleteMode,
            'edge-edit-mode': workflowStore.isEdgeEditMode,
          }"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @click="handleNodeClick($event, node.id)"
          @mousedown="onNodeMouseDown($event, node.id)"
        >
          <div
            class="node-port input-port"
            @mouseup.stop="onInputPortMouseUp($event, node.id)"
            @mouseenter="onInputPortMouseEnter($event, node.id)"
          ></div>
          <div class="node-card-inner">
            <span class="node-step-tag">Step {{ i + 1 }}</span>
            <div class="node-header">
              <div class="node-icon" :class="node.type" aria-hidden="true" />
              <span class="node-title" :title="node.title">{{ node.title }}</span>
            </div>
            <div
              v-if="!workflowStore.isBulkDeleteMode && !workflowStore.isEdgeEditMode"
              class="node-toolbar"
            >
              <template v-if="workflowStore.canvasNodes.length > 1">
                <button
                  type="button"
                  class="node-seq-btn"
                  :disabled="i === 0"
                  title="前移（更早执行）"
                  @mousedown.stop
                  @click.stop="workflowStore.moveNodeEarlier(node.id)"
                >◀</button>
                <button
                  type="button"
                  class="node-seq-btn"
                  :disabled="i >= workflowStore.canvasNodes.length - 1"
                  title="后移（更晚执行）"
                  @mousedown.stop
                  @click.stop="workflowStore.moveNodeLater(node.id)"
                >▶</button>
              </template>
              <button
                type="button"
                class="node-delete-btn"
                title="删除节点"
                @mousedown.stop
                @click.stop="handleNodeDelete($event, node.id)"
              >×</button>
            </div>
            <div v-if="getNodeRunState(node.id) !== 'idle'" class="node-run-status">
              <span class="node-run-dot"></span>
              <span>{{ nodeProgressById[node.id]?.message || nodeProgressById[node.id]?.status }}</span>
            </div>
          </div>
          <div
            class="node-port output-port"
            @mousedown.stop="onOutputPortMouseDown($event, node.id)"
          ></div>
        </div>
      </div>

      <div class="canvas-zoom-hud" @mousedown.stop @click.stop @wheel.stop="onCanvasWheel">
        <span class="canvas-zoom-label" title="Ctrl + 滚轮缩放画布">Ctrl+滚轮缩放</span>
        <span class="canvas-zoom-value">{{ zoomPercentLabel }}</span>
        <button
          v-if="zoom !== 1 || pan.x !== 0 || pan.y !== 0"
          type="button"
          class="canvas-zoom-reset"
          title="重置缩放与平移"
          @click="resetCanvasView"
        >
          重置视图
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.canvas-action-bar {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
  padding: 6px;
  width: max-content;
  min-width: 92px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}

.canvas-action-btn {
  width: 100%;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 500;
  font-family: inherit;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.canvas-action-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-color-hover);
}

.canvas-action-btn.active {
  background: rgba(37, 99, 235, 0.12);
  border-color: rgba(37, 99, 235, 0.45);
  color: var(--accent-primary);
  font-weight: 600;
}

.canvas-action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.canvas-action-btn--danger {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.45);
  color: #dc2626;
  font-weight: 600;
}

.canvas-action-btn--danger:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.18);
  border-color: rgba(239, 68, 68, 0.65);
  color: #b91c1c;
}

.canvas-action-btn--neutral {
  background: #52525b;
  border-color: #3f3f46;
  color: #f4f4f5;
  font-weight: 600;
}

.canvas-action-btn--neutral:hover:not(:disabled) {
  background: #3f3f46;
  border-color: #27272a;
  color: #ffffff;
}

.canvas-action-tip {
  margin: 0;
  padding: 0 2px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--accent-primary);
  text-align: center;
}

.canvas-action-tip--danger {
  color: #dc2626;
}

.canvas-action-tip--edge {
  color: #059669;
}

.canvas-area--edge-edit {
  box-sizing: border-box;
  border: 3px dashed rgba(5, 150, 105, 0.65);
  box-shadow:
    inset 0 0 0 1px rgba(5, 150, 105, 0.25),
    inset 0 0 32px rgba(5, 150, 105, 0.06);
  background-color: rgba(5, 150, 105, 0.03);
}

.canvas-area--edge-edit .workflow-node.edge-edit-mode .node-port {
  opacity: 1;
  pointer-events: auto;
}

.workflow-node .node-port {
  opacity: 0;
  pointer-events: none;
}

.workflow-node.edge-edit-mode .node-port,
.workflow-node:hover .node-port {
  opacity: 1;
  pointer-events: auto;
}

.canvas-area--edge-edit .workflow-node.edge-edit-mode {
  cursor: grab;
}

.canvas-area--edge-edit .workflow-node.edge-edit-mode:active {
  cursor: grabbing;
}

.conn-path.conn-preview {
  stroke: rgba(5, 150, 105, 0.85);
  stroke-dasharray: 6 4;
  pointer-events: none;
}

.conn-path.conn-edge-edit {
  cursor: pointer;
  stroke-width: 2.5;
}

.conn-label {
  font-size: 11px;
  font-weight: 600;
  fill: #059669;
  pointer-events: none;
  user-select: none;
}

.canvas-area--order-edit {
  box-sizing: border-box;
  border: 3px dashed rgba(37, 99, 235, 0.65);
  box-shadow:
    inset 0 0 0 1px rgba(37, 99, 235, 0.25),
    inset 0 0 32px rgba(37, 99, 235, 0.08);
  background-color: rgba(37, 99, 235, 0.04);
}

.canvas-area--order-edit .workflow-node.order-edit-mode {
  cursor: grab;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.28), var(--shadow-md);
}

.canvas-area--order-edit .workflow-node.order-edit-mode:active {
  cursor: grabbing;
}

.canvas-area--bulk-delete {
  box-sizing: border-box;
  border: 3px dashed rgba(239, 68, 68, 0.65);
  box-shadow:
    inset 0 0 0 1px rgba(239, 68, 68, 0.25),
    inset 0 0 32px rgba(239, 68, 68, 0.06);
  background-color: rgba(239, 68, 68, 0.03);
}

.canvas-area--bulk-delete .workflow-node.bulk-delete-mode {
  cursor: grab;
}

.canvas-area--bulk-delete .workflow-node.bulk-delete-mode:active {
  cursor: grabbing;
}

.canvas-zoom-hud {
  position: absolute;
  right: 14px;
  bottom: 14px;
  z-index: 12;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  pointer-events: auto;
}

.canvas-zoom-label {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

.canvas-zoom-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 2.5em;
  text-align: center;
}

.canvas-zoom-reset {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: var(--accent-primary);
  background: rgba(37, 99, 235, 0.08);
  border: 1px solid rgba(37, 99, 235, 0.25);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.canvas-zoom-reset:hover {
  background: rgba(37, 99, 235, 0.14);
}
</style>
