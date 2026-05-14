<script setup>
import { ref, computed } from 'vue'
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

/** 将指针位置转为 canvas-inner 内坐标（与 node.x / node.y 一致） */
function pointerToInnerLocal(e) {
  const inner = canvasInnerRef.value
  if (!inner) return { x: 30, y: 160 }
  const rect = inner.getBoundingClientRect()
  return {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  }
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

// Transform-based pan state
const pan = ref({ x: 0, y: 0 })
const isPanning = ref(false)
const panStart = ref({ mouseX: 0, mouseY: 0, panX: 0, panY: 0 })

// Canvas style computed from pan transform
const canvasStyle = computed(() => ({
  transform: `translate(${pan.value.x}px, ${pan.value.y}px)`
}))

// Node drag state
const isDraggingNode = ref(false)
const dragNodeId = ref(null)
const dragStart = ref({ mouseX: 0, mouseY: 0, nodeX: 0, nodeY: 0 })

function handleNodeClick(event, nodeId) {
  event.stopPropagation()
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
  } else if (isDraggingNode.value && dragNodeId.value) {
    const dx = event.clientX - dragStart.value.mouseX
    const dy = event.clientY - dragStart.value.mouseY
    workflowStore.updateNodePosition(dragNodeId.value, dragStart.value.nodeX + dx, dragStart.value.nodeY + dy)
  }
}

function onCanvasMouseUp() {
  isPanning.value = false
  isDraggingNode.value = false
  dragNodeId.value = null
}

// Node drag
function onNodeMouseDown(event, nodeId) {
  event.stopPropagation()
  event.preventDefault()
  const node = workflowStore.canvasNodes.find(n => n.id === nodeId)
  if (!node) return
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
    workflowStore.selectNode(null)
  }
}

/** 与节点占位一致：连线从右侧端口到下一节点左侧，纵坐标取卡片中线附近 */
const NODE_CONN_W = 220
function nodeOutPoint(n) {
  return { x: n.x + NODE_CONN_W, y: n.y + 76 }
}
function nodeInPoint(n) {
  return { x: n.x, y: n.y + 76 }
}

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
  const nodes = workflowStore.canvasNodes
  return nodes.slice(0, -1).map((fromNode, i) => {
    const toNode = nodes[i + 1]
    const pOut = nodeOutPoint(fromNode)
    const pIn = nodeInPoint(toNode)
    return {
      d: buildConnectionPath(pOut, pIn),
      key: `conn-${i}`,
      fromId: fromNode.id,
      toId: toNode.id
    }
  })
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
      :class="{ 'is-panning': isPanning, 'canvas-area--drop-target': dropZoneActive }"
      @click="handleCanvasClick"
      @mousedown="onCanvasMouseDown"
      @mousemove="onCanvasMouseMove"
      @mouseup="onCanvasMouseUp"
      @mouseleave="onCanvasMouseUp"
      @dragenter="onCanvasDragEnter"
      @dragover="onCanvasDragOver"
      @dragleave="onCanvasDragLeave"
      @drop="onCanvasDrop"
    >
      <!-- Step Indicator (outside transform, stays fixed at top) -->
      <div class="canvas-step-bar">
        <template v-for="(node, i) in workflowStore.canvasNodes" :key="'step-' + node.id">
          <div
            class="step-item"
            :class="{
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
                workflowStore.selectedNodeId === cp.toId
            }"
          />
        </svg>

        <!-- Nodes -->
        <div
          v-for="(node, i) in workflowStore.canvasNodes"
          :key="node.id"
          class="workflow-node"
          :class="{ selected: workflowStore.selectedNodeId === node.id, ['type-' + node.type]: true, ['run-' + getNodeRunState(node.id)]: true }"
          :style="{ left: node.x + 'px', top: node.y + 'px' }"
          @click="handleNodeClick($event, node.id)"
          @mousedown="onNodeMouseDown($event, node.id)"
        >
          <div class="node-selected-badge">当前选中</div>
          <div class="node-port input-port"></div>
          <div class="node-header">
            <div class="node-icon" :class="node.type + '-icon'">{{ node.icon }}</div>
            <span class="node-title">{{ node.title }}</span>
            <span class="node-step-tag">Step {{ i + 1 }}</span>
            <div
              v-if="workflowStore.canvasNodes.length > 1"
              class="node-seq-actions"
              @mousedown.stop
              @click.stop
            >
              <button
                type="button"
                class="node-seq-btn"
                :disabled="i === 0"
                title="前移（更早执行）"
                @click="workflowStore.moveNodeEarlier(node.id)"
              >◀</button>
              <button
                type="button"
                class="node-seq-btn"
                :disabled="i >= workflowStore.canvasNodes.length - 1"
                title="后移（更晚执行）"
                @click="workflowStore.moveNodeLater(node.id)"
              >▶</button>
            </div>
            <button
              class="node-delete-btn"
              title="删除节点"
              @click.stop="handleNodeDelete($event, node.id)"
            >×</button>
          </div>
          <div class="node-body">{{ node.body }}</div>
          <div v-if="getNodeRunState(node.id) !== 'idle'" class="node-run-status">
            <span class="node-run-dot"></span>
            <span>{{ nodeProgressById[node.id]?.message || nodeProgressById[node.id]?.status }}</span>
          </div>
          <div class="node-port output-port"></div>
        </div>
      </div>
    </div>
  </div>
</template>
