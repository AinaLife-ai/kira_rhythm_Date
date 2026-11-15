import { fmt } from './store.js'
import { planTemplates, themeTemplates } from './templates.js'

export const ItemCard = {
  props: ['item', 'serverTime'],
  emits: ['edit', 'run', 'skip'],
  computed: {
    itemStateClass() { return `state-${this.item.state}` },
    scheduleText() {
      const schedule = this.item.schedule || {}
      if (schedule.type === 'window') return `${schedule.start}–${schedule.end} · ${fmt.time(this.item.scheduled_at)}`
      return fmt.time(this.item.scheduled_at)
    },
  },
  template: `
  <article class="item-card" :class="itemStateClass">
    <div class="item-rail"><span class="item-dot"></span><span class="item-line"></span></div>
    <div class="item-main">
      <div class="item-top">
        <div>
          <h4>{{ item.title }}</h4>
          <p v-if="item.intent" class="item-intent">{{ item.intent }}</p>
        </div>
        <span class="state-pill">{{ $root.fmt.state(item.state) }}</span>
      </div>
      <div class="item-meta">
        <span>◷ {{ scheduleText }}</span>
        <span v-if="item.execution_probability < 1">🎲 {{ Math.round(item.execution_probability * 100) }}%</span>
        <span>{{ $root.fmt.interaction(item.interaction) }}</span>
        <span v-if="item.category" class="tag">{{ item.category }}</span>
      </div>
      <div class="item-actions">
        <button v-if="item.state === 'scheduled'" class="text-button" @click="$emit('edit', item)">调整</button>
        <button v-if="item.state === 'scheduled'" class="text-button" @click="$emit('run', item)">立即触发</button>
        <button v-if="item.state === 'scheduled'" class="text-button muted" @click="$emit('skip', item)">跳过</button>
      </div>
    </div>
  </article>`,
}

export const Timeline = {
  components: { ItemCard },
  props: ['plan', 'serverTime'],
  emits: ['edit', 'run', 'skip'],
  template: `
  <div class="timeline" v-if="plan && plan.blocks?.length">
    <section v-for="block in plan.blocks" :key="block.id" class="timeline-block" v-show="!block.meta?.archived">
      <div class="block-heading">
        <span class="block-swatch" :style="{background: block.color || 'var(--accent)'}"></span>
        <h3>{{ block.title }}</h3><span>{{ block.items.length }} 项</span>
      </div>
      <item-card v-for="item in block.items" :key="item.id" :item="item" :server-time="serverTime"
        @edit="$emit('edit', {item, block})" @run="$emit('run', $event)" @skip="$emit('skip', $event)" />
    </section>
  </div>
  <div v-else class="empty-state">
    <span class="empty-orbit">✦</span><h3>今天还没有安排</h3>
    <p>给生活留一点空白，或者让 bot 规划接下来的节奏。</p>
    <button class="primary" @click="$root.runPlanning()">现在规划</button>
  </div>`,
}

export const TodayView = {
  components: { Timeline },
  template: `
  <div class="view-stack today-view">
    <section class="hero-card glass" :style="$root.heroStyle">
      <div class="hero-aurora"></div>
      <div class="hero-person">
        <div class="avatar-wrap"><img :src="$root.avatarUrl" alt="生活头像"><span class="avatar-status"></span></div>
        <div class="hero-copy">
          <span class="eyebrow">{{ $root.dayTypeName }} · {{ $root.data.date }}</span>
          <h1>{{ $root.data.day_state.current_activity || $root.data.plan?.title || '此刻，生活正在展开' }}</h1>
          <p>{{ $root.data.day_state.current_note || $root.data.plan?.overview || '没有安排也很好，给自己一点自由。' }}</p>
          <div class="state-chips">
            <span v-if="$root.data.day_state.current_appearance">👕 {{ $root.data.day_state.current_appearance }}</span>
            <span v-if="$root.data.day_state.current_mood">☁ {{ $root.data.day_state.current_mood }}</span>
          </div>
        </div>
      </div>
      <div class="hero-side">
        <div class="weather-orb" :class="{'is-night': $root.isNight}">
          <span class="weather-icon">{{ $root.weatherIcon }}</span>
          <strong>{{ $root.weatherText }}</strong>
          <small>{{ $root.weatherDetail }}</small>
        </div>
        <button class="soft-button" @click="$root.dayStateEditor = true">更新此刻状态</button>
      </div>
    </section>

    <section class="quick-grid">
      <div class="next-card glass" v-if="$root.nextItem">
        <span class="eyebrow">下一件生活小事</span>
        <h2>{{ $root.nextItem.title }}</h2>
        <p>{{ $root.nextItem.intent || '按照自己的想法继续今天。' }}</p>
        <div class="next-time"><strong>{{ $root.fmt.countdown($root.nextItem.scheduled_at, $root.clockNow) }}</strong><span>{{ $root.fmt.time($root.nextItem.scheduled_at) }}</span></div>
      </div>
      <div class="next-card glass empty-next" v-else>
        <span class="eyebrow">接下来</span><h2>给生活一个新想法</h2>
        <p>定时规划仍会到来，也可以现在让 bot 重新审视。</p>
        <button class="soft-button" @click="$root.runPlanning()">现在规划</button>
      </div>
      <div class="mini-stats glass">
        <div><strong>{{ $root.planStats.total }}</strong><span>今日小项</span></div>
        <div><strong>{{ $root.planStats.done }}</strong><span>已经触发</span></div>
        <div><strong>r{{ $root.data.plan?.revision || 0 }}</strong><span>计划版本</span></div>
      </div>
    </section>

    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">今日时间轴</span><h2>生活的节奏</h2></div>
        <button class="soft-button" @click="$root.newItem()">＋ 添加小项</button>
      </div>
      <timeline :plan="$root.data.plan" :server-time="$root.data.server_time"
        @edit="$root.openItem($event)" @run="$root.runItem($event)" @skip="$root.skipItem($event)" />
    </section>

    <section class="section-card glass changes-preview" v-if="$root.latestDiff.length">
      <div class="section-heading"><div><span class="eyebrow">最近变化</span><h2>计划也在生长</h2></div>
        <button class="text-button" @click="$root.setView('changes')">全部变化 →</button>
      </div>
      <div v-for="change in $root.latestDiff.slice(0, 3)" :key="change.revision" class="change-row">
        <span class="revision-badge">r{{ change.revision }}</span>
        <div><strong>{{ change.actor === 'bot' ? 'bot' : change.actor }} · {{ change.reason || '调整了计划' }}</strong>
        <p>{{ $root.diffSummary(change.diff) }}</p></div>
      </div>
    </section>
  </div>`,
}

export const CalendarView = {
  components: { Timeline },
  template: `
  <div class="calendar-layout">
    <section class="calendar-card glass">
      <div class="section-heading">
        <button class="icon-button" @click="$root.shiftMonth(-1)">‹</button>
        <h2>{{ $root.monthTitle }}</h2>
        <button class="icon-button" @click="$root.shiftMonth(1)">›</button>
        <button class="soft-button today-button" @click="$root.selectDate($root.data.date)">回到今天</button>
      </div>
      <div class="weekday-row"><span v-for="day in ['一','二','三','四','五','六','日']">周{{ day }}</span></div>
      <div class="month-grid">
        <button v-for="cell in $root.monthCells" :key="cell.key" class="day-cell" :class="{'other-month': !cell.current, 'is-today': cell.date === $root.data.date, 'is-selected': cell.date === $root.selectedDate, 'has-plan': cell.plan}"
          @click="$root.selectDate(cell.date)">
          <span class="day-number">{{ cell.day }}</span>
          <span v-if="cell.plan" class="day-type-dot" :style="{background: cell.color || 'var(--accent)'}"></span>
          <small v-if="cell.plan">{{ cell.count }} 项</small><small v-else>·</small>
        </button>
      </div>
      <div class="calendar-legend"><span><i class="legend-dot"></i> 有计划</span><span><i class="legend-ring"></i> 今天</span><button class="text-button" @click="$root.newPlanForDate()">为 {{ $root.selectedDate }} 安排 →</button></div>
    </section>
    <section class="day-detail glass">
      <div class="section-heading"><div><span class="eyebrow">{{ $root.selectedDate }}</span><h2>{{ $root.selectedPlan?.title || '未安排的一天' }}</h2></div>
        <button class="soft-button" @click="$root.newItem()">＋ 小项</button></div>
      <p v-if="$root.selectedPlan" class="plan-overview">{{ $root.selectedPlan.overview }}</p>
      <timeline :plan="$root.selectedPlan" :server-time="$root.data.server_time"
        @edit="$root.openItem($event)" @run="$root.runItem($event)" @skip="$root.skipItem($event)" />
    </section>
  </div>`,
}

export const ChangesView = {
  template: `
  <div class="view-stack">
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">生活变化审计</span><h2>每一次调整都有来处</h2></div>
        <select v-model="$root.diffPlanId" @change="$root.loadDiff"><option v-for="plan in $root.recentPlans" :value="plan.id">{{ plan.date }} · {{ plan.title }}</option></select>
      </div>
      <div v-if="!$root.diffs.length" class="empty-inline">还没有变化记录，生活才刚刚开始。</div>
      <article v-for="change in $root.diffs" :key="change.revision" class="diff-card">
        <div class="diff-revision"><span>r{{ change.revision }}</span><small>{{ change.actor }}</small></div>
        <div class="diff-body"><h3>{{ change.reason || '调整生活安排' }}</h3><time>{{ $root.fmt.date(change.created_at) }}</time>
          <div v-for="entry in change.diff" class="diff-entry" :class="'op-' + entry.op">
            <strong>{{ entry.op === 'added' ? '＋' : entry.op === 'removed' ? '−' : '～' }} {{ entry.title }}</strong>
            <span v-for="(value, field) in entry.changes">{{ field }}: {{ $root.shortValue(value.from) }} → {{ $root.shortValue(value.to) }}</span>
          </div>
        </div>
      </article>
    </section>
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">运行记录</span><h2>触发不是盲目发送</h2></div><button class="soft-button" @click="$root.loadRuns">刷新</button></div>
      <div class="run-table"><div class="run-row run-head"><span>小项</span><span>状态</span><span>概率</span><span>时间</span></div>
        <div v-for="run in $root.runs" class="run-row"><span class="mono">{{ run.item_id.slice(0, 14) }}…</span><span>{{ run.status }}</span><span>{{ run.probability == null ? '—' : Math.round(run.probability * 100) + '%' }}</span><span>{{ $root.fmt.date(run.claimed_at) }}</span></div>
      </div>
    </section>
  </div>`,
}

export const TemplatesView = {
  template: `
  <div class="view-stack">
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">生活模板</span><h2>从一种节奏开始，再变成自己的</h2></div><button class="soft-button" @click="$root.saveCurrentTemplate">＋ 保存当前为模板</button></div>
      <div class="template-grid">
        <article v-for="template in $root.allPlanTemplates" :key="template.id" class="template-card" :class="'tone-' + (template.tone || 'violet')">
          <span class="template-icon">{{ template.icon }}</span><h3>{{ template.name }}</h3><p>{{ template.description }}</p>
          <div class="template-actions"><button class="soft-button" @click="$root.applyTemplate(template)">应用到 {{ $root.selectedDate }}</button><button class="text-button" @click="$root.previewTemplate(template)">预览结构</button><button v-if="template.custom" class="text-button muted" @click="$root.deleteTemplate(template)">删除我的模板</button></div>
        </article>
      </div>
    </section>
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">日型</span><h2>每一天都可以有自己的名字</h2></div><button class="soft-button" @click="$root.newDayType">＋ 自定义日型</button></div>
      <div class="day-type-grid"><article v-for="entry in $root.data.day_types" class="day-type-card" :style="{'--day-color': entry.config.color || 'var(--accent)'}">
        <span class="day-type-color"></span><h3>{{ entry.name }}</h3><small>{{ entry.builtin ? '内置日型' : entry.id }}</small>
        <button class="text-button" @click="$root.editDayType(entry)">编辑</button><button v-if="!entry.builtin" class="text-button muted" @click="$root.deleteDayType(entry)">删除</button>
      </article></div>
    </section>
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">外观与头像</span><h2>让界面也拥有生活感</h2></div></div>
      <div class="theme-grid"><button v-for="theme in $root.themeTemplates" class="theme-card" :class="{active: $root.data.config.appearance.theme === theme.id}" @click="$root.setTheme(theme)">
        <span class="theme-preview" :data-theme-name="theme.id"><i></i><i></i><i></i></span><strong>{{ theme.name }}</strong><small>{{ theme.description }}</small>
      </button></div>
      <div class="avatar-editor"><img :src="$root.avatarUrl" alt="当前头像"><div><h3>生活头像</h3><p>默认自动获取适配器头像，也可以为此人格上传专属图片。</p><label class="soft-button upload-button">上传头像<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="$root.uploadAvatar"></label></div></div>
      <div class="avatar-editor"><div><h3>生活横幅与强调色</h3><p>图片只保存在本机；颜色会立即应用到当前人格的界面。</p><div class="data-actions"><label class="soft-button upload-button">上传横幅<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="$root.uploadBanner"></label><input type="color" v-model="$root.customAccent" style="width: 100px" @change="$root.applyCustomAccent"></div></div></div>
    </section>
  </div>`,
}

export const SettingsView = {
  template: `
  <div class="settings-layout glass">
    <aside class="settings-tabs"><button v-for="tab in [['general','规划与数量'],['time','时间与夜间'],['sessions','会话权限'],['weather','天气与地点'],['data','数据与诊断']]" :class="{active: $root.settingsTab === tab[0]}" @click="$root.settingsTab = tab[0]">{{ tab[1] }}</button></aside>
    <div class="settings-content">
      <section v-if="$root.settingsTab === 'general'" class="settings-section">
        <span class="eyebrow">规划与数量</span><h2>自主，但有清晰边界</h2>
        <div class="form-grid">
          <label><span>每日最小项</span><input type="number" min="0" max="500" v-model.number="$root.draft.min_items"></label>
          <label><span>每日最大项</span><input type="number" min="1" max="500" v-model.number="$root.draft.max_items"></label>
          <label><span>定时规划</span><input type="time" v-model="$root.draft.planning_time"></label>
          <label><span>最远天数</span><input type="number" min="1" max="366" v-model.number="$root.draft.max_horizon_days"></label>
          <label><span>默认概率</span><input type="number" min="0" max="1" step="0.05" v-model.number="$root.draft.default_probability"></label>
          <label><span>bot 最低概率</span><input type="number" min="0" max="1" step="0.05" v-model.number="$root.draft.min_probability"></label>
          <label><span>历史天数</span><input type="number" min="0" max="30" v-model.number="$root.draft.history_days"></label>
          <label><span>组内 diff 次数</span><input type="number" min="1" max="20" v-model.number="$root.draft.diff_revisions"></label>
        </div>
        <div class="switch-grid"><label class="switch-row"><span>自动规划</span><input type="checkbox" v-model="$root.draft.auto_plan"></label>
          <label class="switch-row"><span>全项触发后再给规划机会</span><input type="checkbox" v-model="$root.draft.plan_on_all_triggered"></label>
          <label class="switch-row"><span>精确时间</span><input type="checkbox" v-model="$root.draft.allow_exact"></label>
          <label class="switch-row"><span>随机时间窗</span><input type="checkbox" v-model="$root.draft.allow_window"></label>
          <label class="switch-row"><span>概率触发</span><input type="checkbox" v-model="$root.draft.allow_probability"></label>
          <label class="switch-row"><span>普通会话注入 DayState</span><input type="checkbox" v-model="$root.draft.inject_day_state"></label>
        </div>
        <label class="full-field"><span>历史模式</span><select v-model="$root.draft.history_mode"><option value="notice">notice · 系统短标记</option><option value="full">full · 额外保留模板</option><option value="none">none · 全非持久（空 user 边界）</option></select></label>
        <label class="full-field"><span>完整规划提示词</span><textarea rows="7" v-model="$root.draft.planning_prompt"></textarea></label>
        <label class="full-field"><span>小项执行提示词</span><textarea rows="6" v-model="$root.draft.execution_prompt"></textarea></label>
      </section>
      <section v-if="$root.settingsTab === 'time'" class="settings-section">
        <span class="eyebrow">时间与夜间</span><h2>执行、打扰与覆盖，分别决定</h2>
        <div v-for="group in [['blocked_execution_windows','禁止执行时段','任何日程都不会在此唤醒'],['quiet_delivery_windows','安静投递时段','允许做梦与思考，但不发可见消息'],['required_coverage_windows','必需覆盖时段','设置时段内的最小/最大项数']]" class="window-group">
          <div class="section-heading"><div><h3>{{ group[1] }}</h3><p>{{ group[2] }}</p></div><button class="soft-button" @click="$root.addWindow(group[0])">＋ 添加</button></div>
          <div v-for="(window, index) in $root.draft[group[0]]" class="window-row">
            <input type="time" v-model="window.start"><span>至</span><input type="time" v-model="window.end">
            <template v-if="group[0] === 'required_coverage_windows'"><input type="number" min="0" max="100" v-model.number="window.min_items" title="最小项数"><input type="number" min="0" max="100" v-model.number="window.max_items" title="最大项数"><input placeholder="分类（可选）" v-model="window.category"></template>
            <button class="icon-button danger" @click="$root.draft[group[0]].splice(index, 1)">×</button>
          </div>
        </div>
        <div class="form-grid"><label><span>过期宽限（秒）</span><input type="number" min="0" v-model.number="$root.draft.recovery_grace_seconds"></label><label><span>时区（system 或 IANA）</span><input v-model="$root.draft.timezone" placeholder="Asia/Shanghai"></label></div>
      </section>
      <section v-if="$root.settingsTab === 'sessions'" class="settings-section">
        <span class="eyebrow">会话权限</span><h2>允许生活在哪些地方发生</h2>
        <label class="full-field"><span>名单模式</span><select v-model="$root.draft.session_access.mode"><option value="deny_list">黑名单：默认全部允许</option><option value="allow_list">白名单：仅列表允许</option></select></label>
        <div class="session-picker"><label v-for="session in $root.allSessions" :class="{selected: $root.draft.session_access.sessions.includes(session.sid)}"><input type="checkbox" :checked="$root.draft.session_access.sessions.includes(session.sid)" @change="$root.toggleAccess(session.sid)"><span>{{ session.title }}</span><small>{{ session.sid }}</small></label></div>
        <div v-for="kind in ['planning', 'execution']" class="pool-editor"><h3>{{ kind === 'planning' ? '规划起始会话池' : '小项执行会话池' }}</h3>
          <label class="full-field"><span>选择策略</span><select v-model="$root.draft[kind + '_pool'].strategy"><option value="pure_random">完全随机</option><option value="no_immediate_repeat">避免连续重复</option><option value="shuffle_bag">一轮内不重复</option><option value="round_robin">顺序轮换</option><option value="weighted_random">加权随机</option></select></label>
          <p class="field-hint">不勾选表示使用权限范围内的全部会话；勾选后只使用池内会话。</p>
          <div class="session-picker"><label v-for="session in $root.allSessions" :class="{selected: $root.draft[kind + '_pool'].sessions.some(v => (v.sid || v) === session.sid)}"><input type="checkbox" :checked="$root.draft[kind + '_pool'].sessions.some(v => (v.sid || v) === session.sid)" @change="$root.togglePool(kind, session.sid)"><span>{{ session.title }}</span><small>{{ session.sid }}</small></label></div>
        </div>
      </section>
      <section v-if="$root.settingsTab === 'weather'" class="settings-section">
        <span class="eyebrow">天气与地点</span><h2>真实或虚拟，都能参与生活</h2>
        <div class="form-grid"><label><span>模式</span><select v-model="$root.draft.weather.mode"><option value="off">关闭</option><option value="real">真实天气</option><option value="virtual">虚拟气候</option><option value="hybrid">真实 + 虚拟</option></select></label>
          <label><span>Provider</span><select v-model="$root.draft.weather.provider"><option value="open_meteo">Open-Meteo · 无需账号</option><option value="met_norway">MET Norway · 无需账号</option><option value="nws">US NWS · 美国</option><option value="bright_sky">Bright Sky · DWD</option><option value="weatherapi">WeatherAPI · 注册</option><option value="visualcrossing">Visual Crossing · 注册</option><option value="qweather">和风天气 · 注册</option><option value="weatherbit">Weatherbit · 注册</option><option value="openweather">OpenWeather · 注册</option></select></label></div>
        <div class="location-editor"><input v-model="$root.cityQuery" placeholder="搜索城市，例如 上海" @keyup.enter="$root.geocode"><button class="soft-button" @click="$root.geocode">查找地点</button></div>
        <div v-if="$root.cityResults.length" class="city-results"><button v-for="city in $root.cityResults" @click="$root.chooseCity(city)"><strong>{{ city.name }}</strong> {{ city.admin1 }} {{ city.country }}<small>{{ city.latitude }}, {{ city.longitude }}</small></button></div>
        <div v-if="$root.currentLocation" class="current-location">当前地点：<strong>{{ $root.currentLocation.name }}</strong><span>{{ $root.currentLocation.latitude }}, {{ $root.currentLocation.longitude }}</span><button class="text-button" @click="$root.weatherPreview">预览天气</button></div>
        <div class="form-grid"><label><span>虚拟地点</span><input v-model="$root.draft.weather.virtual.location"></label><label><span>虚拟气候</span><select v-model="$root.draft.weather.virtual.climate"><option value="temperate">温带四季</option><option value="island">海岛</option><option value="rainforest">雨林</option><option value="snow">雪原</option><option value="desert">沙漠</option><option value="floating_city">幻想浮空城</option></select></label></div>
        <label class="full-field"><span>虚拟随机种子</span><input v-model="$root.draft.weather.virtual.seed"></label>
        <pre v-if="$root.weatherResult" class="weather-preview">{{ $root.weatherResult }}</pre>
      </section>
      <section v-if="$root.settingsTab === 'data'" class="settings-section">
        <span class="eyebrow">数据与诊断</span><h2>可备份、可恢复、可解释</h2>
        <div class="data-actions"><button class="soft-button" @click="$root.exportData">导出当前人格数据</button><label class="soft-button upload-button">导入备份<input type="file" accept="application/json" @change="$root.importData"></label><button class="soft-button" @click="$root.loadDiagnostics">刷新诊断</button></div>
        <pre v-if="$root.diagnostics" class="diagnostics">{{ JSON.stringify($root.diagnostics, null, 2) }}</pre>
      </section>
      <div class="settings-save"><button class="primary" :disabled="$root.saving" @click="$root.saveSettings">{{ $root.saving ? '正在生效…' : '保存并热生效' }}</button><span>进行中的 Run 保留启动时规则，新规则用于后续认领。</span></div>
    </div>
  </div>`,
}

export const ItemEditor = {
  props: ['editor'],
  data() {
    const source = this.editor.item || { interaction: 'auto', execution_probability: 1, schedule: { type: 'exact', at: '09:00' }, target: '' }
    return { form: JSON.parse(JSON.stringify(source)) }
  },
  computed: {
    schedule() {
      if (!this.form.schedule) this.form.schedule = { type: 'exact', at: '09:00' }
      return this.form.schedule
    },
  },
  template: `
  <div class="modal-backdrop" @click.self="$root.closeEditor"><div class="modal-card large">
    <div class="modal-heading"><div><span class="eyebrow">生活小项</span><h2>{{ editor.item ? '调整安排' : '添加安排' }}</h2></div><button class="icon-button" @click="$root.closeEditor">×</button></div>
    <div class="form-grid">
      <label class="wide"><span>标题</span><input v-model="form.title" autofocus></label>
      <label class="wide"><span>为什么安排</span><textarea rows="2" v-model="form.intent"></textarea></label>
      <label class="wide"><span>执行指令</span><textarea rows="4" v-model="form.instruction"></textarea></label>
      <label><span>时间模式</span><select v-model="schedule.type"><option value="exact">精确时间</option><option value="window">随机时间窗</option></select></label>
      <label><span>互动方式</span><select v-model="form.interaction"><option value="auto">自由决定</option><option value="must_message">需要发言</option><option value="silent">安静经历</option></select></label>
      <label v-if="schedule.type === 'exact'"><span>执行时间</span><input type="time" v-model="schedule.at"></label>
      <template v-else><label><span>窗口开始</span><input type="time" v-model="schedule.start"></label><label><span>窗口结束</span><input type="time" v-model="schedule.end"></label>
        <label><span>出现次数</span><input type="number" min="1" max="100" v-model.number="schedule.occurrences"></label>
        <label><span>窗口子模式</span><select v-model="schedule.window_mode"><option value="single_random">随机一次</option><option value="interval_random">随机间隔</option></select></label></template>
      <label><span>执行概率</span><input type="number" min="0" max="1" step="0.05" v-model.number="form.execution_probability"></label>
      <label><span>分类</span><input v-model="form.category" placeholder="dream / reading…"></label>
      <label class="wide"><span>目标会话（留空使用执行池）</span><select v-model="form.target"><option value="">执行会话池自动选择</option><option v-for="session in $root.data.sessions" :value="session.sid">{{ session.title }} · {{ session.sid }}</option></select></label>
    </div>
    <div class="modal-actions"><button class="soft-button" @click="$root.closeEditor">取消</button><button class="primary" @click="$root.saveItem(form)">保存并校验</button></div>
  </div></div>`,
}

export const DayStateEditor = {
  data() { return { form: JSON.parse(JSON.stringify(this.$root.data.day_state)) } },
  template: `
  <div class="modal-backdrop" @click.self="$root.dayStateEditor = false"><div class="modal-card">
    <div class="modal-heading"><div><span class="eyebrow">DayState</span><h2>此刻的我</h2></div><button class="icon-button" @click="$root.dayStateEditor = false">×</button></div>
    <label class="full-field"><span>现在的服装</span><input v-model="form.current_appearance"></label>
    <label class="full-field"><span>现在的心情</span><input v-model="form.current_mood"></label>
    <label class="full-field"><span>现在的地点</span><input v-model="form.current_location"></label>
    <label class="full-field"><span>正在做什么</span><input v-model="form.current_activity"></label>
    <label class="full-field"><span>总体思路</span><textarea rows="4" v-model="form.current_note"></textarea></label>
    <div class="modal-actions"><button class="soft-button" @click="$root.dayStateEditor = false">取消</button><button class="primary" @click="$root.saveDayState(form)">更新此刻</button></div>
  </div></div>`,
}

export const DayTypeEditor = {
  props: ['entry'],
  data() {
    const value = this.entry || { id: '', name: '', builtin: false, rules: { weekdays: [], dates: [], priority: 100 }, config: { color: '#9b8cff' } }
    const copy = JSON.parse(JSON.stringify(value))
    copy._dates = (copy.rules.dates || []).join(', ')
    copy.config ||= { color: '#9b8cff' }
    copy.config.overrides ||= {}
    copy.config.overrides.execution_pool ||= { strategy: 'pure_random', sessions: [] }
    return { form: copy }
  },
  template: `
  <div class="modal-backdrop" @click.self="$root.dayTypeEditor = null"><div class="modal-card">
    <div class="modal-heading"><div><span class="eyebrow">日型</span><h2>{{ entry ? '编辑日型' : '创建日型' }}</h2></div><button class="icon-button" @click="$root.dayTypeEditor = null">×</button></div>
    <label class="full-field"><span>名称</span><input v-model="form.name" placeholder="考试周 / 旅行日 / 雨天宅家"></label>
    <label class="full-field"><span>内部 ID（创建后不可改）</span><input v-model="form.id" :disabled="!!entry" placeholder="exam_week"></label>
    <label class="full-field"><span>主题色</span><input type="color" v-model="form.config.color"></label>
    <label class="full-field"><span>此日型规划提示词（留空继承全局）</span><textarea rows="3" v-model="form.config.overrides.planning_prompt"></textarea></label>
    <div class="form-grid" style="margin-top: 17px">
      <label><span>每日最小项</span><input type="number" min="0" max="500" v-model.number="form.config.overrides.min_items"></label>
      <label><span>每日最大项</span><input type="number" min="1" max="500" v-model.number="form.config.overrides.max_items"></label>
    </div>
    <label class="full-field"><span>此日型执行会话策略</span><select v-model="form.config.overrides.execution_pool.strategy"><option value="pure_random">完全随机</option><option value="no_immediate_repeat">避免连续重复</option><option value="shuffle_bag">一轮内不重复</option><option value="round_robin">顺序轮换</option></select></label>
    <div class="weekday-picker"><span>周重复</span><label v-for="(name, index) in ['一','二','三','四','五','六','日']"><input type="checkbox" :checked="form.rules.weekdays.includes(index)" @change="$root.toggleDayTypeWeekday(form, index)">周{{ name }}</label></div>
    <label class="full-field"><span>指定日期（逗号分隔）</span><textarea rows="2" v-model="form._dates" placeholder="2026-11-20, 2026-12-01"></textarea></label>
    <label class="full-field"><span>规则优先级（数字越小越优先）</span><input type="number" v-model.number="form.rules.priority"></label>
    <div class="modal-actions"><button class="soft-button" @click="$root.dayTypeEditor = null">取消</button><button class="primary" @click="$root.saveDayType(form)">保存日型</button></div>
  </div></div>`,
}
