import { get, post, put, patch, upload, socket, ready } from './api.js'
import { state, loadBootstrap, loadPlan, saveConfig, notify, fmt } from './store.js'
import { TodayView, CalendarView, ChangesView, TemplatesView, SettingsView, ItemEditor, DayStateEditor, DayTypeEditor } from './views.js'
import { planTemplates, themeTemplates } from './templates.js'

const clone = (value) => JSON.parse(JSON.stringify(value))
const dateShift = (date, days) => {
  const value = new Date(`${date}T12:00:00`)
  value.setDate(value.getDate() + days)
  return value.toISOString().slice(0, 10)
}

const app = Vue.createApp({
  components: { TodayView, CalendarView, ChangesView, TemplatesView, SettingsView, ItemEditor, DayStateEditor, DayTypeEditor },
  data() {
    return {
      state,
      fmt,
      planTemplates,
      themeTemplates,
      diffs: [],
      diffPlanId: '',
      recentPlans: [],
      monthPlans: [],
      draft: null,
      allSessions: [],
      cityQuery: '',
      cityResults: [],
      weatherResult: '',
      diagnostics: null,
      liveTimer: null,
      monthAnchor: '',
      customTemplates: [],
      customAccent: '',
    }
  },
  computed: {
    currentView() {
      const name = { today: 'TodayView', calendar: 'CalendarView', changes: 'ChangesView', templates: 'TemplatesView', settings: 'SettingsView' }[state.view] || 'TodayView'
      return this.$options.components[name]
    },
    selectedDate: { get() { return state.selectedDate }, set(value) { state.selectedDate = value } },
    selectedPlan: { get() { return state.selectedPlan }, set(value) { state.selectedPlan = value } },
    settingsTab: { get() { return state.settingsTab }, set(value) { state.settingsTab = value } },
    dayStateEditor: { get() { return state.dayStateEditor }, set(value) { state.dayStateEditor = value } },
    dayTypeEditor: { get() { return state.dayTypeEditor }, set(value) { state.dayTypeEditor = value } },
    runs() { return state.runs },
    data() { return state.data || {} },
    saving() { return state.saving },
    dayTypeName() {
      const id = this.data.plan?.day_type_id
      return this.data.day_types?.find((entry) => entry.id === id)?.name || '自由日'
    },
    nextItem() {
      const items = (this.data.plan?.blocks || []).flatMap((block) => block.items || [])
      return items.filter((item) => item.state === 'scheduled').sort((a, b) => a.scheduled_at - b.scheduled_at)[0] || null
    },
    planStats() {
      const items = (this.data.plan?.blocks || []).flatMap((block) => block.items || [])
      return { total: items.length, done: items.filter((item) => ['triggered', 'triggered_silent'].includes(item.state)).length }
    },
    latestDiff() { return this.diffs },
    allPlanTemplates() { return [...this.planTemplates, ...this.customTemplates] },
    heroStyle() {
      const banner = this.data.banner?.url
      return banner ? { backgroundImage: `linear-gradient(90deg, var(--panel-solid) 0%, transparent 100%), url("${banner}")`, backgroundSize: 'cover', backgroundPosition: 'center' } : {}
    },
    weatherInfo() {
      const weather = this.data.weather || {}
      return weather.real || weather.virtual || null
    },
    weatherText() {
      if (!this.weatherInfo) return this.data.weather?.mode === 'off' ? '天气未启用' : '等待天气配置'
      if (this.weatherInfo.status === 'location_required') return '尚未设置地点'
      if (this.weatherInfo.status === 'unavailable') return '天气暂时不可用'
      return this.weatherInfo.condition || '天气未知'
    },
    weatherDetail() {
      if (!this.weatherInfo) return '可在设置中开启真实或虚拟天气'
      const info = this.weatherInfo
      const temperature = info.temperature != null ? `${info.temperature}°C` : ''
      return `${info.location || ''} ${temperature} ${info.status === 'stale' ? '· 缓存' : ''}`.trim()
    },
    weatherIcon() {
      const text = this.weatherText
      if (/雪/.test(text)) return '❄'
      if (/雨|雷/.test(text)) return '☂'
      if (/云|阴|雾/.test(text)) return '☁'
      if (/晴/.test(text)) return '☀'
      return '✦'
    },
    isNight() { return new Date().getHours() >= 19 || new Date().getHours() < 6 },
    currentLocation() {
      const locations = this.draft?.weather?.locations || {}
      return locations[state.selectedPersona] || locations.default || null
    },
    monthTitle() {
      if (!this.monthAnchor) return ''
      const [year, month] = this.monthAnchor.split('-')
      return `${year} 年 ${Number(month)} 月`
    },
    monthCells() {
      if (!this.monthAnchor) return []
      const [year, month] = this.monthAnchor.split('-').map(Number)
      const first = new Date(Date.UTC(year, month - 1, 1, 12))
      const startOffset = (first.getUTCDay() + 6) % 7
      const cells = []
      for (let index = 0; index < 42; index++) {
        const date = new Date(first)
        date.setUTCDate(first.getUTCDate() + index - startOffset)
        const iso = date.toISOString().slice(0, 10)
        const plan = this.monthPlans.find((entry) => entry.date === iso)
        const count = plan ? plan.blocks.reduce((sum, block) => sum + block.items.length, 0) : 0
        cells.push({ key: iso, date: iso, day: date.getUTCDate(), current: date.getUTCMonth() === month - 1, plan, count,
          color: this.data.day_types?.find((entry) => entry.id === plan?.day_type_id)?.config?.color })
      }
      return cells
    },
  },
  methods: {
    setView(view) {
      state.view = view
      if (view === 'changes') this.loadDiff()
      if (view === 'settings') this.prepareSettings()
      if (view === 'calendar') this.loadMonth()
    },
    async refresh() {
      await loadBootstrap(state.selectedPersona)
      this.applyAppearance()
      this.monthAnchor = state.selectedDate
      await Promise.all([this.loadRecentPlans(), this.loadRuns(), this.loadMonth(), this.loadDiff(), this.loadCustomTemplates()])
      this.prepareSettings()
    },
    async selectPersona() {
      await loadBootstrap(state.selectedPersona)
      await this.refresh()
    },
    async selectDate(date) {
      state.selectedDate = date
      this.monthAnchor = date
      await loadPlan(date)
      this.diffPlanId = state.selectedPlan?.id || ''
      await this.loadDiff()
    },
    async shiftMonth(delta) {
      const [year, month] = this.monthAnchor.split('-').map(Number)
      const date = new Date(Date.UTC(year, month - 1 + delta, 1, 12))
      this.monthAnchor = date.toISOString().slice(0, 10)
      await this.loadMonth()
    },
    async loadMonth() {
      if (!this.monthAnchor) return
      const [year, month] = this.monthAnchor.split('-').map(Number)
      const start = `${this.monthAnchor}-01`
      const end = new Date(Date.UTC(year, month, 0, 12)).toISOString().slice(0, 10)
      this.monthPlans = await get(`/plans?start=${start}&end=${end}&persona=${encodeURIComponent(state.selectedPersona)}`)
    },
    async loadRecentPlans() {
      const start = dateShift(state.selectedDate, -14)
      const end = dateShift(state.selectedDate, 14)
      this.recentPlans = await get(`/plans?start=${start}&end=${end}&persona=${encodeURIComponent(state.selectedPersona)}`)
    },
    async loadRuns() { state.runs = await get(`/runs?limit=60&persona=${encodeURIComponent(state.selectedPersona)}`) },
    async loadDiff() {
      const id = this.diffPlanId || state.selectedPlan?.id || this.data.plan?.id
      if (!id) { this.diffs = []; return }
      this.diffPlanId = id
      this.diffs = await get(`/plans/${id}/diff?limit=20`)
    },
    diffSummary(diff) {
      return (diff || []).slice(0, 3).map((entry) => `${entry.op === 'added' ? '新增' : entry.op === 'removed' ? '移除' : '调整'}「${entry.title}」`).join('；') || '保持原计划'
    },
    shortValue(value) {
      if (value == null || value === '') return '空'
      const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
      return text.length > 42 ? `${text.slice(0, 42)}…` : text
    },
    async runPlanning() {
      try {
        const date = state.selectedDate === this.data.date ? dateShift(this.data.date, 1) : state.selectedDate
        await post(`/planning/run?persona=${encodeURIComponent(state.selectedPersona)}`, { date, reason: 'WebUI 手动给予一次规划机会' })
        notify('已把规划机会交给 bot')
      } catch (error) { notify(error.message, 'error') }
    },
    newItem() {
      state.editor = { item: null, block: null }
    },
    openItem(payload) {
      state.editor = { item: payload.item, block: payload.block }
    },
    newPlanForDate() { state.editor = { item: null, block: null } },
    closeEditor() { state.editor = null },
    async saveItem(form) {
      try {
        const plan = state.selectedPlan ? clone(state.selectedPlan) : {
          date: state.selectedDate, title: '这一天', overview: '', planned_appearance: '', planned_mood: '', blocks: [], expected_revision: 0,
        }
        const sourceBlock = state.editor?.block
        let block = sourceBlock ? plan.blocks.find((entry) => entry.id === sourceBlock.id) : plan.blocks[0]
        if (!block) {
          block = { id: '', title: '生活片段', items: [] }
          plan.blocks.push(block)
        }
        const existingIndex = block.items.findIndex((item) => item.id === form.id)
        if (existingIndex >= 0) block.items[existingIndex] = form
        else block.items.push(form)
        plan.expected_revision = plan.revision || 0
        const result = await post(`/plans?persona=${encodeURIComponent(state.selectedPersona)}`, plan)
        state.selectedPlan = result.plan
        if (state.selectedDate === this.data.date) this.data.plan = result.plan
        state.editor = null
        notify('计划已保存')
        await Promise.all([this.loadMonth(), this.loadRecentPlans(), this.loadDiff()])
      } catch (error) { notify(error.message, 'error') }
    },
    async runItem(item) {
      try { await post(`/items/${item.id}/run?persona=${encodeURIComponent(state.selectedPersona)}`) ; notify('已交给框架触发') }
      catch (error) { notify(error.message, 'error') }
    },
    async skipItem(item) {
      try {
        await post(`/items/${item.id}/skip?persona=${encodeURIComponent(state.selectedPersona)}`, { reason: 'WebUI 手动跳过' })
        await loadPlan(state.selectedDate)
        await this.refresh()
      } catch (error) { notify(error.message, 'error') }
    },
    async saveDayState(form) {
      try {
        this.data.day_state = await post(`/day-state/${this.data.date}?persona=${encodeURIComponent(state.selectedPersona)}`, form)
        state.dayStateEditor = false
        notify('此刻状态已更新')
      } catch (error) { notify(error.message, 'error') }
    },
    newDayType() { state.dayTypeEditor = { entry: null } },
    editDayType(entry) { state.dayTypeEditor = { entry } },
    toggleDayTypeWeekday(form, index) {
      const values = form.rules.weekdays
      values.includes(index) ? values.splice(values.indexOf(index), 1) : values.push(index)
    },
    async saveDayType(form) {
      try {
        const payload = clone(form)
        delete payload._dates
        payload.rules.dates = form._dates.split(',').map((value) => value.trim()).filter(Boolean)
        const overrides = payload.config?.overrides || {}
        for (const key of Object.keys(overrides)) {
          if (overrides[key] === '' || overrides[key] == null) delete overrides[key]
        }
        await post(`/day-types?persona=${encodeURIComponent(state.selectedPersona)}`, payload)
        state.dayTypeEditor = null
        this.data.day_types = await get(`/day-types?persona=${encodeURIComponent(state.selectedPersona)}`)
        notify('日型已保存')
      } catch (error) { notify(error.message, 'error') }
    },
    async deleteDayType(entry) {
      if (!confirm(`删除日型「${entry.name}」？`)) return
      try {
        await requestDelete(`/day-types/${encodeURIComponent(entry.id)}?persona=${encodeURIComponent(state.selectedPersona)}`)
        this.data.day_types = await get(`/day-types?persona=${encodeURIComponent(state.selectedPersona)}`)
      } catch (error) { notify(error.message, 'error') }
    },
    async applyTemplate(template) {
      try {
        const payload = clone(template.plan)
        payload.date = state.selectedDate
        payload.expected_revision = state.selectedPlan?.revision || 0
        const result = await post(`/plans?persona=${encodeURIComponent(state.selectedPersona)}`, payload)
        state.selectedPlan = result.plan
        if (state.selectedDate === this.data.date) this.data.plan = result.plan
        await this.refresh()
        notify(`已应用「${template.name}」`)
        this.setView('today')
      } catch (error) { notify(error.message, 'error') }
    },
    previewTemplate(template) {
      const count = template.plan.blocks.reduce((sum, block) => sum + block.items.length, 0)
      notify(`${template.name}：${template.plan.blocks.length} 组、${count} 项；${template.plan.overview}`)
    },
    async loadCustomTemplates() {
      this.customTemplates = await get(`/templates?persona=${encodeURIComponent(state.selectedPersona)}`)
    },
    async saveCurrentTemplate() {
      if (!state.selectedPlan) return notify('请先选择或创建一个计划', 'error')
      const name = prompt('模板名称', state.selectedPlan.title || '我的生活模板')
      if (!name) return
      const plan = clone(state.selectedPlan)
      for (const key of ['id', 'revision', 'expected_revision', 'state', 'created_at', 'updated_at', 'created_by', 'persona_id']) delete plan[key]
      for (const block of plan.blocks || []) {
        delete block.id
        delete block.meta
        for (const item of block.items || []) {
          for (const key of ['id', 'series_id', 'scheduled_at', 'state', 'revision', 'reason', 'created_at', 'updated_at', 'plan_id', 'block_id']) delete item[key]
        }
      }
      try {
        await post(`/templates?persona=${encodeURIComponent(state.selectedPersona)}`, { name, plan })
        await this.loadCustomTemplates()
        notify('已保存为我的模板')
      } catch (error) { notify(error.message, 'error') }
    },
    async deleteTemplate(template) {
      if (!confirm(`删除模板「${template.name}」？`)) return
      try {
        await requestDelete(`/templates/${encodeURIComponent(template.id)}?persona=${encodeURIComponent(state.selectedPersona)}`)
        await this.loadCustomTemplates()
      } catch (error) { notify(error.message, 'error') }
    },
    applyAppearance() {
      const appearance = this.data.config?.appearance || {}
      document.documentElement.dataset.themeName = appearance.theme || 'kira_mist'
      this.customAccent = appearance.custom_accent || ''
      if (appearance.custom_accent) {
        document.documentElement.style.setProperty('--accent', appearance.custom_accent)
        document.documentElement.style.setProperty('--accent-strong', appearance.custom_accent)
      } else {
        document.documentElement.style.removeProperty('--accent')
        document.documentElement.style.removeProperty('--accent-strong')
      }
    },
    async applyCustomAccent() {
      try { await saveConfig({ appearance: { custom_accent: this.customAccent } }); this.applyAppearance() }
      catch (_) { /* already notified */ }
    },
    async uploadBanner(event) {
      const file = event.target.files[0]
      if (!file) return
      try {
        const asset = await upload(`/assets?persona=${encodeURIComponent(state.selectedPersona)}`, file)
        await saveConfig({ appearance: { banner_asset_id: asset.id } })
        this.data.banner = asset
        notify('生活横幅已更新')
      } catch (error) { notify(error.message, 'error') } finally { event.target.value = '' }
    },
    async setTheme(theme) {
      try {
        await saveConfig({ appearance: { theme: theme.id } })
        this.data.config.appearance.theme = theme.id
        this.applyAppearance()
      } catch (_) { /* notification is handled by saveConfig */ }
    },
    async uploadAvatar(event) {
      const file = event.target.files[0]
      if (!file) return
      try {
        const asset = await upload(`/assets?persona=${encodeURIComponent(state.selectedPersona)}`, file)
        await saveConfig({ appearance: { avatar_asset_id: asset.id } })
        this.data.avatar = { source: 'upload', ...asset }
        notify('头像已更新')
      } catch (error) { notify(error.message, 'error') } finally { event.target.value = '' }
    },
    prepareSettings() {
      this.draft = clone(this.data.config || {})
      this.allSessions = this.data.sessions || []
      this.diagnostics = null
    },
    toggleAccess(sid) {
      const values = this.draft.session_access.sessions
      values.includes(sid) ? values.splice(values.indexOf(sid), 1) : values.push(sid)
    },
    togglePool(kind, sid) {
      const values = this.draft[`${kind}_pool`].sessions
      const index = values.findIndex((value) => (value.sid || value) === sid)
      index >= 0 ? values.splice(index, 1) : values.push(sid)
    },
    addWindow(kind) {
      const entry = { start: '23:00', end: '07:00' }
      if (kind === 'required_coverage_windows') Object.assign(entry, { min_items: 1, max_items: 12, category: '' })
      this.draft[kind].push(entry)
    },
    async saveSettings() {
      try { await saveConfig(this.draft); this.prepareSettings() } catch (_) { /* already notified */ }
    },
    async geocode() {
      if (!this.cityQuery.trim()) return
      try { this.cityResults = await post('/weather/geocode', { name: this.cityQuery }) }
      catch (error) { notify(error.message, 'error') }
    },
    chooseCity(city) {
      this.draft.weather.locations[state.selectedPersona] = city
      this.cityResults = []
      this.cityQuery = city.name
    },
    async weatherPreview() {
      try {
        this.weatherResult = JSON.stringify(await post('/weather/preview', {
          mode: this.draft.weather.mode,
          provider: this.draft.weather.provider,
          location: this.currentLocation,
          virtual: this.draft.weather.virtual,
        }), null, 2)
      } catch (error) { notify(error.message, 'error') }
    },
    async exportData() {
      try {
        const data = await get(`/export?persona=${encodeURIComponent(state.selectedPersona)}`)
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `KRD-${state.selectedPersona}-${state.selectedDate}.json`
        link.click()
        URL.revokeObjectURL(link.href)
      } catch (error) { notify(error.message, 'error') }
    },
    async importData(event) {
      const file = event.target.files[0]
      if (!file) return
      try {
        const data = JSON.parse(await file.text())
        const preview = await post(`/import/preview?persona=${encodeURIComponent(state.selectedPersona)}`, data)
        if (!confirm(`将导入 ${preview.plans} 个计划；运行不会重放。继续？`)) return
        const result = await post(`/import/commit?persona=${encodeURIComponent(state.selectedPersona)}`, data)
        notify(`导入完成：${result.imported_plans} 个新计划`)
        await this.refresh()
      } catch (error) { notify(error.message, 'error') } finally { event.target.value = '' }
    },
    async loadDiagnostics() { this.diagnostics = await get('/diagnostics') },
  },
  async mounted() {
    await ready()
    await this.refresh()
    this.disconnect = socket((message) => {
      clearTimeout(this.liveTimer)
      this.liveTimer = setTimeout(() => this.refresh(), 700)
    })
    window.PluginPageContext?.onThemeChange?.((dark) => {
      document.documentElement.dataset.theme = dark ? 'dark' : 'light'
    })
  },
  beforeUnmount() { this.disconnect?.() },
})

// Keep the delete helper out of the component's public API surface.
import { del as requestDelete } from './api.js'

const mounted = app.mount('#app')
if (location.search.includes('debug')) window.__krdApp = mounted
