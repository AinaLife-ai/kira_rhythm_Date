import { get, put } from './api.js'

export const state = Vue.reactive({
  loading: true,
  saving: false,
  view: 'today',
  data: null,
  selectedPersona: '',
  selectedDate: '',
  selectedPlan: null,
  runs: [],
  diagnostics: null,
  notices: [],
  editor: null,
  dayStateEditor: false,
  dayTypeEditor: null,
  settingsTab: 'general',
  theme: 'kira_mist',
  loadError: '',
})

export function notify(text, type = 'success') {
  const id = Date.now() + Math.random()
  state.notices.push({ id, text, type })
  setTimeout(() => {
    const index = state.notices.findIndex((item) => item.id === id)
    if (index >= 0) state.notices.splice(index, 1)
  }, 4200)
}

let bootstrapEpoch = 0
let planEpoch = 0

export async function loadBootstrap(persona = '', { reset = true } = {}) {
  const epoch = ++bootstrapEpoch
  const showLoading = reset || !state.data
  if (showLoading) state.loading = true
  try {
    const data = await get(`/bootstrap${persona ? `?persona=${encodeURIComponent(persona)}` : ''}`)
    if (epoch !== bootstrapEpoch) return null
    state.loadError = ''
    state.data = data
    state.selectedPersona = data.persona_id || persona
    if (reset || !state.selectedDate) {
      state.selectedDate = data.date || ''
      state.selectedPlan = data.plan
    } else if (state.selectedDate === data.date) {
      state.selectedPlan = data.plan
    }
    document.documentElement.dataset.themeName = data.config?.appearance?.theme || 'kira_mist'
    return data
  } catch (error) {
    if (epoch === bootstrapEpoch) state.loadError = error.message
    throw error
  } finally {
    if (epoch === bootstrapEpoch && showLoading) state.loading = false
  }
}

export async function loadPlan(date, persona = state.selectedPersona) {
  if (!date) return null
  const epoch = ++planEpoch
  const plans = await get(`/plans?start=${encodeURIComponent(date)}&end=${encodeURIComponent(date)}&persona=${encodeURIComponent(persona)}`)
  if (epoch !== planEpoch || persona !== state.selectedPersona) return null
  state.selectedPlan = plans[0] || null
  state.selectedDate = date
  return state.selectedPlan
}

export async function saveConfig(patch, expectedRevision = state.data.config_revision) {
  state.saving = true
  try {
    const result = await put(`/config?persona=${encodeURIComponent(state.selectedPersona)}`, {
      patch,
      expected_revision: expectedRevision,
    })
    state.data.config = result.config
    state.data.config_revision = result.revision
    notify('设置已热生效')
    return result
  } catch (error) {
    notify(error.message, 'error')
    throw error
  } finally {
    state.saving = false
  }
}

export const fmt = {
  time(value, withSeconds = false) {
    if (!value) return '—'
    const date = new Date(Number(value) * 1000)
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', ...(withSeconds ? { second: '2-digit' } : {}) })
  },
  date(value) {
    if (!value) return '—'
    const date = new Date(Number(value) * 1000)
    return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  },
  dateOnly(value) {
    if (!value) return '—'
    const parts = String(value).split('-')
    return `${parts[1]}/${parts[2]}`
  },
  state(value) {
    return ({
      scheduled: '待触发', queued: '已排队', running: '执行中', triggered: '已触发',
      triggered_silent: '安静经历', skipped_probability: '概率跳过', missed: '已错过',
      cancelled: '已取消', failed: '失败', interrupted: '已中断', delivery_unmet: '投递未达成',
    })[value] || value
  },
  interaction(value) {
    return ({ auto: '自由', must_message: '需发言', silent: '安静' })[value] || value
  },
  runStatus(value) {
    return ({ prepared: '已准备', queued: '已排队', running: '执行中', responded: '已回应', finalized: '已归档', skipped_probability: '概率跳过', failed: '失败', interrupted: '已中断' })[value] || value
  },
  countdown(value, serverTime) {
    if (!value) return ''
    const seconds = Math.max(0, Math.round(value - serverTime))
    if (seconds < 60) return `${seconds} 秒后`
    if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟后`
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分后`
    return `${Math.floor(seconds / 86400)} 天后`
  },
}
