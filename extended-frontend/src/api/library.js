import client from './client'

export default {
  // ==================== 空间管理 ====================

  /** 获取所有文档空间 */
  getSpaces() {
    return client.get('/library/spaces')
  },

  /** 创建文档空间 */
  createSpace(data) {
    return client.post('/library/spaces', data)
  },

  /** 更新文档空间 */
  updateSpace(spaceId, data) {
    return client.put(`/library/spaces/${spaceId}`, data)
  },

  /** 删除文档空间 */
  deleteSpace(spaceId) {
    return client.delete(`/library/spaces/${spaceId}`)
  },

  // ==================== 文档管理 ====================

  /** 获取空间下的所有文档 */
  getDocs(spaceId) {
    return client.get(`/library/spaces/${spaceId}/docs`)
  },

  /** 上传文档到指定空间 */
  uploadDoc(spaceId, file) {
    const formData = new FormData()
    formData.append('file', file)
    return client.post(`/library/spaces/${spaceId}/docs`, formData)
  },

  /** 重命名文档 */
  renameDoc(docId, fileName) {
    return client.put(`/library/docs/${docId}`, { file_name: fileName })
  },

  /** 删除单个文档 */
  deleteDoc(docId) {
    return client.delete(`/library/docs/${docId}`)
  },

  /** 批量删除文档 */
  deleteDocsBatch(docIds) {
    return client.post('/library/docs/delete-batch', { doc_ids: docIds })
  },

  /** 下载文档 */
  downloadDoc(docId, fileName) {
    const token = localStorage.getItem('auth_token') || ''
    const url = `${import.meta.env.VITE_API_BASE_URL || ''}/api/library/docs/${docId}/download`
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    a.headers = { Authorization: token }
    a.click()
  },
}
