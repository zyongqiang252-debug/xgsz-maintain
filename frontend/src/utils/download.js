import request from '../api'

/**
 * 带鉴权下载文件（Excel 等）
 * @param {string} url 相对路径，如 '/export/work-orders.xlsx'
 * @param {object} params 查询参数
 * @param {string} fallbackName 兜底文件名
 */
export async function downloadFile(url, params = {}, fallbackName = 'export.xlsx') {
  const res = await request.get(url, { params, responseType: 'blob', timeout: 60000 })
  const blob = new Blob([res], {
    type: res?.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  // 从 content-disposition 里取中文名（filename*=UTF-8''xxx）
  let name = fallbackName
  const cd = res?.headers?.['content-disposition'] || ''
  const m = /filename\*=UTF-8''([^;]+)/i.exec(cd)
  if (m) {
    try { name = decodeURIComponent(m[1]) } catch { /* 忽略 */ }
  }
  const a = document.createElement('a')
  const href = URL.createObjectURL(blob)
  a.href = href
  a.download = name
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(href), 2000)
  return name
}
