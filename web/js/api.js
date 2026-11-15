let bridgeReady = null

export function ready() {
  if (!bridgeReady) {
    bridgeReady = window.PluginPageContext?.ready?.() || Promise.resolve(null)
  }
  return bridgeReady
}

function errorFrom(status, body) {
  const detail = body?.detail || body?.error || body
  const message = detail?.message || detail?.error?.message || (typeof detail === 'string' ? detail : `HTTP ${status}`)
  const error = new Error(message)
  error.code = detail?.code || detail?.error?.code || status
  error.details = detail?.details || detail
  return error
}

export async function request(path, options = {}) {
  await ready()
  const { timeout = 20000, ...fetchOptions } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  const method = String(fetchOptions.method || 'GET').toUpperCase()
  try {
    const response = await fetch(`/api/plugin/kira_rhythm_Date/v1${path}`, {
      credentials: 'same-origin',
      cache: method === 'GET' ? 'no-store' : 'default',
      ...fetchOptions,
      headers: fetchOptions.body && !(fetchOptions.body instanceof FormData)
        ? { 'Content-Type': 'application/json', ...(fetchOptions.headers || {}) } : fetchOptions.headers,
      signal: controller.signal,
    })
    const type = response.headers.get('content-type') || ''
    const body = type.includes('json') ? await response.json() : await response.text()
    if (!response.ok) throw errorFrom(response.status, body)
    return body
  } catch (error) {
    if (error?.name === 'AbortError') {
      const timeoutError = new Error('请求超时，请检查服务状态后重试')
      timeoutError.code = 'request_timeout'
      throw timeoutError
    }
    throw error
  } finally {
    clearTimeout(timer)
  }
}

export const get = (path) => request(path)
export const post = (path, body = {}) => request(path, { method: 'POST', body: JSON.stringify(body) })
export const put = (path, body = {}) => request(path, { method: 'PUT', body: JSON.stringify(body) })
export const patch = (path, body = {}) => request(path, { method: 'PATCH', body: JSON.stringify(body) })
export const del = (path) => request(path, { method: 'DELETE' })
export const upload = (path, file) => {
  const data = new FormData()
  data.append('file', file)
  return request(path, { method: 'POST', body: data })
}

export function socket(handlers) {
  let ws
  let closed = false
  let retry
  const connect = async () => {
    await ready()
    const url = window.PluginPageContext?.buildWsUrl?.('/v1/events')
    if (!url) return
    ws = new WebSocket(url)
    ws.onmessage = (event) => {
      try { handlers(JSON.parse(event.data)) } catch (_) { /* ignore malformed frame */ }
    }
    ws.onclose = () => {
      if (!closed) retry = setTimeout(connect, 5000)
    }
    ws.onerror = () => ws.close()
  }
  connect()
  return () => {
    closed = true
    clearTimeout(retry)
    ws?.close()
  }
}
