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
})

export function notify(text, type = 'success') {
  const id = Date.now() + Math.random()
  state.notices.push({ id, text, type })
  setTimeout(() => {
    const index = state.notices.findIndex((item) => item.id === id)
    if (index >= 0) state.notices.splice(index, 1)
  }, 4200)
}

export async function loadBootstrap(persona = '') {
  state.loading = true
  try {
    const data = await get(`/bootstrap${persona ? `?persona=${encodeURIComponent(persona)}` : ''}`)
    state.data = data
    state.selectedPersona = data.persona_id
    state.selectedDate = data.date
    state.selectedPlan = data.plan
    document.documentElement.dataset.themeName = data.config?.appearance?.theme || 'kira_mist'
    return data
  } finally {
    state.loading = false
  }
}

export async function loadPlan(date, persona = state.selectedPersona) {
  if (!date) return null
  const plans = await get(`/plans?start=${date}&end=${date}&persona=${encodeURIComponent(persona)}`)
  state.selectedPlan = plans[0] || null
  state.selectedDate = date
  return state.selectedPlan
}

export async function saveConfig(patch) {
  state.saving = true
  try {
    const result = await put(`/config?persona=${encodeURIComponent(state.selectedPersona)}`, {
      patch,
      expected_revision: state.data.config_revision,
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
  countdown(value, serverTime) {
    if (!value) return ''
    const seconds = Math.max(0, Math.round(value - serverTime))
    if (seconds < 60) return `${seconds} 秒后`
    if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟后`
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分后`
    return `${Math.floor(seconds / 86400)} 天后`
  },
}
