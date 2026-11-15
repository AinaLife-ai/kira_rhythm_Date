import { get, post, put, patch, upload, socket, ready } from './api.js'
import { state, loadBootstrap, loadPlan, saveConfig, notify, fmt } from './store.js'
import { UiIcon, TodayView, CalendarView, ChangesView, TemplatesView, SettingsView, ItemEditor, DayStateEditor, DayTypeEditor } from './views.js'
import { planTemplates, themeTemplates } from './templates.js'

const clone = (value) => JSON.parse(JSON.stringify(value))
const assetBase = window.PluginPageContext?.assetBase || '/static/plugin/kira_rhythm_Date/assets'
const dateShift = (date, days) => {
  const value = new Date(`${date}T12:00:00Z`)
  value.setUTCDate(value.getUTCDate() + days)
  return value.toISOString().slice(0, 10)
}

const app = Vue.createApp({
  components: { UiIcon, TodayView, CalendarView, ChangesView, TemplatesView, SettingsView, ItemEditor, DayStateEditor, DayTypeEditor },
  data() {
    return {
      state,
      fmt,
      planTemplates,
      themeTemplates,
      assetBase,
      booted: false,
      bootTimer: null,
      navItems: [
        { id: 'today', label: '此刻', icon: 'home' },
        { id: 'calendar', label: '日历', icon: 'calendar' },
        { id: 'changes', label: '变化', icon: 'changes' },
        { id: 'templates', label: '模板', icon: 'templates' },
        { id: 'settings', label: '设置', icon: 'settings' },
      ],
      diffs: [],
      diffPlanId: '',
      recentPlans: [],
      monthPlans: [],
      monthCalendar: {},
      calendarRefreshedYears: {},
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
      clockNow: Date.now() / 1000,
      clockTimer: null,
      avatarNonce: 0,
      settingsBaseRevision: 0,
      refreshEpoch: 0,
      viewEpoch: 0,
      monthEpoch: 0,
      diffEpoch: 0,
    }
  },
  computed: {
    timezoneOptions() {
      const options = [
        ['system', '跟随宿主系统'], ['Asia/Shanghai', '中国标准时间 · 上海'], ['Asia/Hong_Kong', '香港时间'],
        ['Asia/Taipei', '台北时间'], ['Asia/Tokyo', '日本标准时间 · 东京'], ['Asia/Seoul', '韩国标准时间 · 首尔'],
        ['Asia/Singapore', '新加坡时间'], ['Asia/Bangkok', '曼谷时间'], ['Asia/Kolkata', '印度标准时间'],
        ['Europe/London', '伦敦时间'], ['Europe/Paris', '巴黎时间'], ['Europe/Berlin', '柏林时间'],
        ['America/New_York', '纽约时间'], ['America/Chicago', '芝加哥时间'], ['America/Los_Angeles', '洛杉矶时间'],
        ['Australia/Sydney', '悉尼时间'], ['Pacific/Auckland', '奥克兰时间'], ['UTC', '协调世界时 UTC'],
      ]
      const current = this.draft?.timezone
      if (current && !options.some(([id]) => id === current)) options.push([current, `当前自定义 · ${current}`])
      return options
    },
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
    avatarUrl() {
      const url = this.data.avatar?.url || ''
      if (!url.startsWith('/') || !this.avatarNonce) return url
      return `${url}${url.includes('?') ? '&' : '?'}entry=${this.avatarNonce}`
    },
    weatherInfo() {
      const weather = this.data.weather || {}
      return weather.real || weather.virtual || null
    },
    weatherText() {
      if (!this.weatherInfo) return this.data.weather?.mode === 'off' ? '天气未启用' : '等待天气配置'
      if (this.weatherInfo.status === 'location_required') return '尚未设置地点'
      if (this.weatherInfo.status === 'pending') return '正在后台更新天气'
      if (this.weatherInfo.status === 'unavailable') return '天气暂时不可用'
      return this.weatherInfo.condition || '天气未知'
    },
    weatherDetail() {
      if (!this.weatherInfo) return '可在设置中开启真实或虚拟天气'
      const info = this.weatherInfo
      const temperature = info.temperature != null ? `${info.temperature}°C` : ''
      return `${info.location || ''} ${temperature} ${info.status === 'stale' ? '· 缓存' : ''}`.trim()
    },
    weatherKind() {
      const text = this.weatherText
      if (/雪/.test(text)) return 'snow'
      if (/雨|雷/.test(text)) return 'rain'
      if (/云|阴|雾/.test(text)) return 'cloud'
      if (/晴/.test(text)) return 'sun'
      return this.isNight ? 'moon' : 'sun'
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
    selectedCalendar() {
      return this.monthCalendar[state.selectedDate] ||
        (state.selectedDate === this.data.date ? this.data.calendar_today : null)
    },
    todayCalendar() { return this.data.calendar_today || null },
    todayHoliday() {
      const day = this.data.calendar_today
      return day?.holiday ? `${day.holiday.name}${day.holiday.is_off_day ? '' : ' · 调班'}` : ''
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
        const calendar = this.monthCalendar[iso]
        cells.push({ key: iso, date: iso, day: date.getUTCDate(), current: date.getUTCMonth() === month - 1, plan, count,
          calendar, lunar: calendar?.display || '', holiday: calendar?.holiday,
          color: this.data.day_types?.find((entry) => entry.id === plan?.day_type_id)?.config?.color })
      }
      return cells
    },
  },
  methods: {
    assetUrl(path) { return window.__KRD_INLINE_ASSETS__?.[path] || `${assetBase}/${path}` },
    async setView(view) {
      state.view = view
      const epoch = ++this.viewEpoch
      try {
        if (view === 'changes') await Promise.all([this.loadRecentPlans(), this.loadRuns(), this.loadDiff()])
        if (view === 'settings') this.prepareSettings()
        if (view === 'calendar') await this.loadMonth()
        if (view === 'templates') await this.loadCustomTemplates()
      } catch (error) {
        if (epoch === this.viewEpoch) notify(error.message, 'error')
      }
    },
    async refresh({ persona = state.selectedPersona, reset = false, entry = true } = {}) {
      const epoch = ++this.refreshEpoch
      const data = await loadBootstrap(persona, { reset })
      if (!data || epoch !== this.refreshEpoch || !data.ready) return
      this.applyAppearance()
      this.clockNow = Date.now() / 1000
      if (reset) {
        this.monthAnchor = state.selectedDate.slice(0, 7)
        this.diffPlanId = state.selectedPlan?.id || ''
        this.prepareSettings()
        state.editor = null
        state.dayStateEditor = false
        state.dayTypeEditor = null
      }
      const jobs = []
      if (state.view === 'today') jobs.push(this.loadDiff())
      if (state.view === 'calendar') jobs.push(this.loadMonth())
      if (state.view === 'changes') jobs.push(this.loadRecentPlans(), this.loadRuns(), this.loadDiff())
      if (state.view === 'templates') jobs.push(this.loadCustomTemplates())
      await Promise.all(jobs)
      if (entry) {
        this.avatarNonce = Date.now()
        // Deliberately after first paint: remote refresh must not hold bootstrap.
        this.refreshAvatar(data.persona_id).catch(() => {})
        this.loadWeather(data.persona_id).catch(() => {})
      }
    },
    async selectPersona() {
      try {
        await this.refresh({ persona: state.selectedPersona, reset: true, entry: true })
      } catch (error) { notify(error.message, 'error') }
    },
    async selectDate(date) {
      try {
        state.selectedDate = date
        this.monthAnchor = date.slice(0, 7)
        await loadPlan(date)
        this.diffPlanId = state.selectedPlan?.id || ''
        await this.loadDiff()
      } catch (error) { notify(error.message, 'error') }
    },
    async shiftMonth(delta) {
      const [year, month] = this.monthAnchor.split('-').map(Number)
      const date = new Date(Date.UTC(year, month - 1 + delta, 1, 12))
      this.monthAnchor = date.toISOString().slice(0, 10)
      await this.loadMonth()
    },
    async loadMonth() {
      if (!this.monthAnchor) return
      const epoch = ++this.monthEpoch
      const anchor = this.monthAnchor
      const persona = state.selectedPersona
      const [year, month] = anchor.split('-').map(Number)
      const start = `${anchor}-01`
      const end = new Date(Date.UTC(year, month, 0, 12)).toISOString().slice(0, 10)
      const [plans, calendar] = await Promise.all([
        get(`/plans?start=${start}&end=${end}&persona=${encodeURIComponent(persona)}`),
        get(`/calendar?start=${start}&end=${end}`),
      ])
      if (epoch === this.monthEpoch && persona === state.selectedPersona && anchor === this.monthAnchor) {
        this.monthPlans = plans
        this.monthCalendar = Object.fromEntries(calendar.days.map((day) => [day.date, day]))
      }
      if (!this.calendarRefreshedYears[year]) {
        this.calendarRefreshedYears[year] = true
        post('/calendar/refresh', { year }).then(async () => {
          const fresh = await get(`/calendar?start=${start}&end=${end}`)
          if (anchor === this.monthAnchor && persona === state.selectedPersona) {
            this.monthCalendar = Object.fromEntries(fresh.days.map((day) => [day.date, day]))
          }
        }).catch(() => { this.calendarRefreshedYears[year] = false })
      }
    },
    async loadRecentPlans() {
      const persona = state.selectedPersona
      const start = dateShift(state.selectedDate, -14)
      const end = dateShift(state.selectedDate, 14)
      const plans = await get(`/plans?start=${start}&end=${end}&persona=${encodeURIComponent(persona)}`)
      if (persona === state.selectedPersona) this.recentPlans = plans
    },
    async loadRuns() {
      const persona = state.selectedPersona
      const runs = await get(`/runs?limit=60&persona=${encodeURIComponent(persona)}`)
      if (persona === state.selectedPersona) state.runs = runs
    },
    async loadDiff() {
      const id = this.diffPlanId || state.selectedPlan?.id || this.data.plan?.id
      const epoch = ++this.diffEpoch
      if (!id) { this.diffs = []; return }
      const persona = state.selectedPersona
      this.diffPlanId = id
      const diffs = await get(`/plans/${encodeURIComponent(id)}/diff?limit=20&persona=${encodeURIComponent(persona)}`)
      if (epoch === this.diffEpoch && persona === state.selectedPersona) this.diffs = diffs
    },
    async refreshAvatar(persona) {
      const avatar = await get(`/avatar?refresh=1&persona=${encodeURIComponent(persona)}&entry=${Date.now()}`)
      if (persona === state.selectedPersona) this.data.avatar = avatar
    },
    async loadWeather(persona) {
      const weather = await get(`/weather/current?persona=${encodeURIComponent(persona)}`)
      if (persona === state.selectedPersona) this.data.weather = weather
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
        this.diffPlanId = result.plan.id
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
        const result = await post(`/items/${item.id}/skip?persona=${encodeURIComponent(state.selectedPersona)}`, { reason: 'WebUI 手动跳过' })
        state.selectedPlan = result.plan
        if (state.selectedDate === this.data.date) this.data.plan = result.plan
        await Promise.all([this.loadMonth(), this.loadDiff()])
      } catch (error) { notify(error.message, 'error') }
    },
    async saveDayState(form) {
      try {
        const allowed = ['current_appearance', 'current_mood', 'current_location', 'current_activity', 'current_note']
        const payload = Object.fromEntries(allowed.map((key) => [key, form[key] || '']))
        this.data.day_state = await post(`/day-state/${this.data.date}?persona=${encodeURIComponent(state.selectedPersona)}`, payload)
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
        this.diffPlanId = result.plan.id
        if (state.selectedDate === this.data.date) this.data.plan = result.plan
        await this.refresh({ entry: false })
        notify(`已应用「${template.name}」`)
        this.setView(state.selectedDate === this.data.date ? 'today' : 'calendar')
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
      const themeId = appearance.theme || 'lacrimosa_dusk'
      const theme = themeTemplates.find((entry) => entry.id === themeId) || themeTemplates[0]
      document.documentElement.dataset.themeName = theme.id
      document.documentElement.dataset.theme = theme.mode || 'dark'
      const root = document.documentElement.style
      const customBackground = this.data.background?.url
      if (customBackground || theme.art) {
        root.setProperty('--theme-art', `url("${customBackground || this.assetUrl(`themes/${theme.art}.webp`)}")`)
        root.setProperty('--pixel-sprite', `url("${this.assetUrl(`pixels/${theme.art}.png`)}")`)
      } else {
        root.removeProperty('--theme-art')
        root.removeProperty('--pixel-sprite')
      }
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
    async uploadBackground(event) {
      const file = event.target.files[0]
      if (!file) return
      try {
        const asset = await upload(`/assets?persona=${encodeURIComponent(state.selectedPersona)}`, file)
        this.data.background = asset
        await saveConfig({ appearance: { background_asset_id: asset.id } })
        this.applyAppearance()
        notify('全屏生活背景已更新')
      } catch (error) { notify(error.message, 'error') } finally { event.target.value = '' }
    },
    async clearBackground() {
      try {
        this.data.background = null
        await saveConfig({ appearance: { background_asset_id: '' } })
        this.applyAppearance()
        notify('已恢复主题插画背景')
      } catch (error) { notify(error.message, 'error') }
    },
    resetPrompt(kind) {
      const defaults = this.data.prompt_defaults || {}
      if (kind === 'planning') this.draft.planning_prompt = defaults.planning_prompt
      if (kind === 'execution') this.draft.execution_prompt = defaults.execution_prompt
      if (kind === 'review') this.draft.planning_review.prompt = defaults.planning_review_prompt
      notify('已恢复默认提示词，保存后生效')
    },
    resetAllPrompts() {
      this.resetPrompt('planning')
      this.resetPrompt('execution')
      this.resetPrompt('review')
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
      this.settingsBaseRevision = this.data.config_revision || 0
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
      try {
        const payload = clone(this.draft)
        delete payload.schema_version
        delete payload.per_persona
        await saveConfig(payload, this.settingsBaseRevision)
        this.prepareSettings()
      } catch (_) { /* already notified */ }
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
    this.bootTimer = setTimeout(() => { this.booted = true }, 1250)
    try {
      await ready()
      await this.refresh({ reset: true, entry: true })
      this.disconnect = socket(() => {
        clearTimeout(this.liveTimer)
        this.liveTimer = setTimeout(() => {
          this.refresh({ reset: false, entry: false }).catch((error) => notify(error.message, 'error'))
        }, 400)
      })
      this.clockTimer = setInterval(() => { this.clockNow = Date.now() / 1000 }, 1000)
      this.stopTheme = window.PluginPageContext?.onThemeChange?.((dark) => {
        if (document.documentElement.dataset.themeName === 'kira_mist') {
          document.documentElement.dataset.theme = dark ? 'dark' : 'light'
        }
      })
    } catch (error) {
      state.loading = false
      notify(error.message, 'error')
    }
  },
  beforeUnmount() {
    this.disconnect?.()
    this.stopTheme?.()
    clearTimeout(this.liveTimer)
    clearTimeout(this.bootTimer)
    clearInterval(this.clockTimer)
  },
})

// Keep the delete helper out of the component's public API surface.
import { del as requestDelete } from './api.js'

app.component('UiIcon', UiIcon)
const mounted = app.mount('#app')
if (location.search.includes('debug')) window.__krdApp = mounted
