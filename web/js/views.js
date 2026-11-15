import { fmt } from './store.js'
import { planTemplates, themeTemplates } from './templates.js'

const ICON_PATHS = {
  home: ['M3 11.5 12 4l9 7.5', 'M5.5 10.5V20h13v-9.5', 'M9.5 20v-6h5v6'],
  calendar: ['M5 5h14a1 1 0 0 1 1 1v13H4V6a1 1 0 0 1 1-1Z', 'M8 3v4M16 3v4M4 9h16', 'M8 13h2M14 13h2M8 17h2M14 17h2'],
  changes: ['M4 7h11l-3-3M20 17H9l3 3', 'M15 7l5 5-5 5'],
  templates: ['M4 5h7v7H4zM13 5h7v7h-7zM4 14h7v6H4zM13 14h7v6h-7z'],
  settings: ['M12 8.5a3.5 3.5 0 1 1 0 7 3.5 3.5 0 0 1 0-7Z', 'M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.7 5.7l1.5 1.5M16.8 16.8l1.5 1.5M18.3 5.7l-1.5 1.5M7.2 16.8l-1.5 1.5'],
  plus: ['M12 5v14M5 12h14'],
  refresh: ['M20 7v5h-5', 'M4 17v-5h5', 'M6.2 8a7 7 0 0 1 11.3-.8L20 12M4 12l2.5 4.8A7 7 0 0 0 18 16'],
  clock: ['M12 4a8 8 0 1 1 0 16 8 8 0 0 1 0-16Z', 'M12 8v4.5l3 2'],
  play: ['M8 5l11 7-11 7z'],
  skip: ['M6 5l9 7-9 7zM18 5v14'],
  edit: ['M4 20h4l11-11-4-4L4 16v4Z', 'M13 7l4 4'],
  close: ['M6 6l12 12M18 6 6 18'],
  left: ['M14.5 5 7.5 12l7 7'],
  right: ['M9.5 5l7 7-7 7'],
  sun: ['M12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10Z', 'M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4'],
  cloud: ['M7 18h10a4 4 0 0 0 .2-8A6 6 0 0 0 5.6 12 3 3 0 0 0 7 18Z'],
  rain: ['M7 15h10a4 4 0 0 0 0-8 6 6 0 0 0-11.2 2A3 3 0 0 0 7 15Z', 'M8 18l-1 2M12 18l-1 2M16 18l-1 2'],
  snow: ['M12 3v18M4.5 7l15 10M19.5 7l-15 10', 'M9.5 5 12 7l2.5-2M9.5 19l2.5-2 2.5 2'],
  moon: ['M19 15.5A8 8 0 0 1 8.5 5 8 8 0 1 0 19 15.5Z'],
  flower: ['M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z', 'M12 9C9 8 8 4 12 4s3 4 0 5ZM15 12c1-3 5-3 5 0s-4 3-5 0ZM12 15c3 1 4 5 0 5s-3-4 0-5ZM9 12c-1 3-5 3-5 0s4-3 5 0Z'],
  sparkle: ['M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z', 'M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z'],
  pin: ['M12 21s6-6.2 6-11a6 6 0 1 0-12 0c0 4.8 6 11 6 11Z', 'M12 8a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z'],
  stats: ['M5 19V9M12 19V5M19 19v-7'],
  check: ['M5 12.5 9.5 17 19 6.5'],
  alert: ['M12 3 2.8 20h18.4L12 3Z', 'M12 9v5M12 17v.2'],
  upload: ['M12 16V4M7 9l5-5 5 5', 'M4 16v4h16v-4'],
  download: ['M12 4v12M7 11l5 5 5-5', 'M4 16v4h16v-4'],
  trash: ['M5 7h14M9 7V4h6v3M8 7l1 13h6l1-13', 'M10 11v5M14 11v5'],
  chevron: ['M8 5l7 7-7 7'],
  heart: ['M12 20S4 15 4 9.5A4.5 4.5 0 0 1 12 6a4.5 4.5 0 0 1 8 3.5C20 15 12 20 12 20Z'],
}

export const UiIcon = {
  props: { name: { type: String, default: 'sparkle' }, size: { type: Number, default: 18 } },
  computed: {
    paths() { return ICON_PATHS[this.name] || ICON_PATHS.sparkle },
  },
  template: `<svg class="ui-icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path v-for="(d, index) in paths" :key="index" :d="d" /></svg>`,
}

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
        <span class="meta-icon"><ui-icon name="clock" :size="13" /> {{ scheduleText }}</span>
        <span v-if="item.execution_probability < 1">概率 {{ Math.round(item.execution_probability * 100) }}%</span>
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
    <span class="empty-orbit"><ui-icon name="sparkle" :size="27" /></span><h3>今天还没有安排</h3>
    <p>给生活留一点空白，或者让 bot 规划接下来的节奏。</p>
    <button class="primary" @click="$root.runPlanning()">现在规划</button>
  </div>`,
}

export const TodayView = {
  components: { Timeline },
  template: `
  <div class="nte-today">
    <section class="scene-hero">
      <div class="scene-noise"></div><div class="scene-scan"></div>
      <div class="scene-topline">
        <span class="live-tag"><i></i> LIVE PERSONA / 当前人格 <b>{{ $root.data.personas?.find(p => p.id === $root.data.persona_id)?.name || '在线' }}</b></span>
        <span class="scene-coord">35.68N / 139.76E</span>
      </div>
      <span class="scene-index">01</span>
      <div class="phone-lock-clock"><strong>{{ $root.localClock }}</strong><span>{{ $root.data.date }} · {{ $root.dayTypeName }}</span></div>
      <div class="scene-title">
        <span class="kicker">DAILY NARRATIVE // 今日叙事</span>
        <h1><small>{{ $root.dayTypeName }}</small>{{ $root.data.day_state.current_activity || $root.data.plan?.title || '生活正在展开' }}</h1>
        <p>{{ $root.data.day_state.current_note || $root.data.plan?.overview || '没有安排也很好，让今天自然发生。' }}</p>
      </div>
      <div class="scene-identity">
        <div class="avatar-wrap"><img v-if="$root.avatarUrl && !$root.avatarBroken" :src="$root.avatarUrl" alt="生活头像" @error="$root.avatarBroken = true"><span v-else class="avatar-placeholder" aria-label="未设置头像">?</span><span class="avatar-status"></span><i></i></div>
        <div><span class="identity-label">CURRENT PERSONA / 当前人格</span><strong>{{ $root.data.personas?.find(p => p.id === $root.data.persona_id)?.name || '生活人格' }}</strong><small>{{ $root.data.day_state.current_location || '常驻城市 · 生活区' }}</small></div>
      </div>
      <div class="scene-status">
        <div class="scene-weather">
          <ui-icon :name="$root.weatherKind" :size="28" /><div><span>{{ $root.phaseLabel }}</span><strong>{{ $root.weatherText }}</strong><small>{{ $root.weatherDetail }}</small></div>
        </div>
        <div class="scene-tags">
          <span v-if="$root.data.day_state.current_appearance">{{ $root.data.day_state.current_appearance }}</span>
          <span v-if="$root.data.day_state.current_mood">情绪 / {{ $root.data.day_state.current_mood }}</span>
          <span>{{ $root.data.date }}<template v-if="$root.todayHoliday"> · {{ $root.todayHoliday }}</template></span>
        </div>
        <button class="scene-action" @click="$root.dayStateEditor = true"><span>更新此刻状态</span><ui-icon name="edit" :size="15" /></button>
      </div>
      <div class="scene-cut" aria-hidden="true"></div>
    </section>

    <aside class="mission-dock">
      <div class="dock-top"><span>MISSION CONTROL <b>/ 今日任务</b></span><strong>{{ $root.planStats.done }}<small>/{{ $root.planStats.total }}</small></strong></div>
      <div class="mission-main" v-if="$root.nextItem">
        <div class="mission-kicker"><i></i> NEXT SIGNAL <span>下一事件</span></div>
        <div class="mission-clock"><strong>{{ $root.fmt.time($root.nextItem.scheduled_at) }}</strong><span>{{ $root.fmt.countdown($root.nextItem.scheduled_at, $root.clockNow) }}</span></div>
        <h2>{{ $root.nextItem.title }}</h2>
        <p>{{ $root.nextItem.intent || '按照自己的想法继续今天。' }}</p>
        <div class="mission-meta"><span>{{ $root.fmt.interaction($root.nextItem.interaction) }}</span><span v-if="$root.nextItem.execution_probability < 1">概率 {{ Math.round($root.nextItem.execution_probability * 100) }}%</span></div>
        <div class="mission-queue" v-if="$root.upcomingItems.length"><span class="queue-label">LATER / 随后</span><div v-for="item in $root.upcomingItems" :key="item.id"><b>{{ $root.fmt.time(item.scheduled_at) }}</b><span>{{ item.title }}</span></div></div>
        <div class="mission-telemetry">
          <span class="telemetry-label">SYSTEM TELEMETRY / 系统读数</span>
          <div class="telemetry-row"><span>日程密度</span><i><b :style="{width: Math.min(100, $root.planStats.total / Math.max(1, $root.data.config?.max_items || 12) * 100) + '%'}"></b></i><em>{{ Math.round(Math.min(1, $root.planStats.total / Math.max(1, $root.data.config?.max_items || 12)) * 100) }}%</em></div>
          <div class="telemetry-row"><span>完成进度</span><i><b :style="{width: ($root.planStats.total ? $root.planStats.done / $root.planStats.total * 100 : 0) + '%'}"></b></i><em>{{ $root.planStats.total ? Math.round($root.planStats.done / $root.planStats.total * 100) : 0 }}%</em></div>
          <div class="telemetry-row"><span>环境干扰</span><i><b :style="{width: ($root.weatherKind === 'rain' || $root.weatherKind === 'snow' ? 76 : $root.weatherKind === 'cloud' ? 38 : 18) + '%'}"></b></i><em>{{ $root.weatherKind === 'rain' || $root.weatherKind === 'snow' ? '偏高' : $root.weatherKind === 'cloud' ? '中' : '低' }}</em></div>
        </div>
        <button class="mission-run" @click="$root.runItem($root.nextItem)"><span>立即触发</span><ui-icon name="play" :size="14" /></button>
      </div>
      <div class="mission-main empty" v-else>
        <div class="mission-kicker"><i></i> SIGNAL EMPTY <span>暂无下一项</span></div>
        <h2>让 bot 写下一段生活</h2><p>今天可以留白，也可以现在给 bot 一次规划机会。</p>
        <button class="mission-run" @click="$root.runPlanning()"><span>开始规划</span><ui-icon name="sparkle" :size="14" /></button>
      </div>
      <div class="mission-stats">
        <div><strong>{{ String($root.planStats.done).padStart(2, '0') }}</strong><span>已触发</span></div>
        <div><strong>{{ String($root.planStats.total - $root.planStats.done).padStart(2, '0') }}</strong><span>待发生</span></div>
        <div><strong>{{ $root.data.plan?.revision || 0 }}</strong><span>计划版本</span></div>
      </div>
      <div class="dock-footer">
        <button @click="$root.newItem()"><ui-icon name="plus" :size="15" /> 添加小项</button>
        <button @click="$root.setView('calendar')"><ui-icon name="calendar" :size="15" /> 查看日历</button>
      </div>
      <div class="dock-barcode" aria-hidden="true"><i v-for="n in 18" :key="n" :style="{height: (4 + (n * 7) % 15) + 'px'}"></i></div>
    </aside>

    <section class="timeline-console">
      <div class="console-heading"><div><span class="kicker">SCHEDULE / 行为序列</span><h2>今天的生活轨迹</h2></div><span class="console-count">{{ $root.planStats.total }} ENTRIES</span></div>
      <timeline :plan="$root.data.plan" :server-time="$root.data.server_time" @edit="$root.openItem($event)" @run="$root.runItem($event)" @skip="$root.skipItem($event)" />
    </section>

    <aside class="life-signal">
      <section class="signal-card identity-card">
        <div class="signal-heading"><span>STATE / 当前切片</span><ui-icon name="heart" :size="14" /></div>
        <div class="state-list">
          <div><span>地点</span><strong>{{ $root.data.day_state.current_location || '未记录' }}</strong></div>
          <div><span>服装</span><strong>{{ $root.data.day_state.current_appearance || '未记录' }}</strong></div>
          <div><span>心情</span><strong>{{ $root.data.day_state.current_mood || '未记录' }}</strong></div>
          <div><span>活动</span><strong>{{ $root.data.day_state.current_activity || '自由活动' }}</strong></div>
        </div>
        <button class="signal-link" @click="$root.dayStateEditor = true">调整此刻状态 <ui-icon name="chevron" :size="13" /></button>
      </section>
      <section class="signal-card changes-preview" v-if="$root.latestDiff.length">
        <div class="signal-heading"><span>CHANGE LOG / 变化</span><button @click="$root.setView('changes')">全部</button></div>
        <div v-for="change in $root.latestDiff.slice(0, 3)" :key="change.revision" class="change-row">
          <span class="revision-badge">第{{ change.revision }}版</span>
          <div><strong>{{ change.actor === 'bot' ? 'bot' : '你' }} · {{ change.reason || '调整了计划' }}</strong><p>{{ $root.diffSummary(change.diff) }}</p></div>
        </div>
      </section>
      <section class="signal-card environment-card">
        <div class="signal-heading"><span>ENVIRONMENT / 环境信号</span><i class="pulse"></i></div>
        <div class="anomaly-readout"><strong>{{ $root.weatherText }}</strong><span>{{ $root.phaseLabel.split(' · ')[0] }}</span></div>
        <p>界面光效、城市场景与信号强度会随时间、天气和事件状态实时变化。</p>
      </section>
    </aside>
  </div>`,
}

export const CalendarView = {
  components: { Timeline },
  template: `
  <div class="calendar-layout">
    <section class="calendar-card glass">
      <div class="section-heading">
        <button class="icon-button" @click="$root.shiftMonth(-1)"><ui-icon name="left" :size="16" /></button>
        <h2>{{ $root.monthTitle }}</h2>
        <button class="icon-button" @click="$root.shiftMonth(1)"><ui-icon name="right" :size="16" /></button>
        <button class="soft-button today-button" @click="$root.selectDate($root.data.date)">回到今天</button>
      </div>
      <div class="weekday-row"><span v-for="day in ['一','二','三','四','五','六','日']">周{{ day }}</span></div>
      <div class="month-grid">
        <button v-for="cell in $root.monthCells" :key="cell.key" class="day-cell" :class="{'other-month': !cell.current, 'is-today': cell.date === $root.data.date, 'is-selected': cell.date === $root.selectedDate, 'has-plan': cell.plan, 'is-holiday': cell.holiday?.is_off_day, 'is-workday': cell.holiday && !cell.holiday.is_off_day}"
          @click="$root.selectDate(cell.date)">
          <span class="day-top"><span class="day-number">{{ cell.day }}</span><span v-if="cell.holiday" class="holiday-mark" :class="{work: !cell.holiday.is_off_day}">{{ cell.holiday.is_off_day ? '休' : '班' }}</span></span>
          <span class="lunar-label" :class="{festival: cell.lunar && cell.lunar !== '初一'}">{{ cell.lunar }}</span>
          <small v-if="cell.plan" class="plan-count">{{ cell.count }} 项</small>
        </button>
      </div>
      <div class="calendar-legend"><span><i class="legend-dot"></i> 有计划</span><span><i class="legend-ring"></i> 今天</span><button class="text-button" @click="$root.newPlanForDate()">为 {{ $root.selectedDate }} 安排 →</button></div>
    </section>
    <section class="day-detail glass">
      <div class="section-heading"><div><span class="eyebrow">{{ $root.selectedDate }}</span><h2>{{ $root.selectedPlan?.title || '未安排的一天' }}</h2></div>
        <button class="soft-button" @click="$root.newItem()"><ui-icon name="plus" :size="15" /> 小项</button></div>
      <div v-if="$root.selectedCalendar" class="calendar-facts"><strong>{{ $root.selectedCalendar.lunar?.text }}</strong><span v-if="$root.selectedCalendar.solar_term">{{ $root.selectedCalendar.solar_term }}</span><span v-if="$root.selectedCalendar.holiday">{{ $root.selectedCalendar.holiday.name }} · {{ $root.selectedCalendar.holiday.is_off_day ? '放假' : '调班' }}</span><span v-for="name in $root.selectedCalendar.solar_festivals" :key="name">{{ name }}</span><span v-for="name in $root.selectedCalendar.lunar_festivals" :key="name">{{ name }}</span><small>{{ $root.selectedCalendar.data_status === 'fresh' ? '法定假期已在线更新' : '法定假期本地回退' }}</small></div>
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
        <div class="diff-revision"><span>第{{ change.revision }}版</span><small>{{ change.actor === 'bot' ? 'bot' : '你' }}</small></div>
        <div class="diff-body"><h3>{{ change.reason || '调整生活安排' }}</h3><time>{{ $root.fmt.date(change.created_at) }}</time>
          <div v-for="entry in change.diff" class="diff-entry" :class="'op-' + entry.op">
            <strong>{{ entry.op === 'added' ? '+' : entry.op === 'removed' ? '-' : '~' }} {{ entry.title }}</strong>
            <span v-for="(value, field) in entry.changes">{{ $root.fmt.field(field) }}：{{ $root.fmt.humanValue(field, value.from) }} → {{ $root.fmt.humanValue(field, value.to) }}</span>
          </div>
        </div>
      </article>
    </section>
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">运行记录</span><h2>触发不是盲目发送</h2></div><button class="soft-button" @click="$root.loadRuns">刷新</button></div>
      <div class="run-table"><div class="run-row run-head"><span>小项</span><span>状态</span><span>概率</span><span>时间</span></div>
        <div v-for="run in $root.runs" class="run-row"><span>{{ $root.itemTitle(run.item_id) }}</span><span>{{ $root.fmt.runStatus(run.status) }}</span><span>{{ run.probability == null ? '—' : Math.round(run.probability * 100) + '%' }}</span><span>{{ $root.fmt.date(run.claimed_at) }}</span></div>
      </div>
    </section>
  </div>`,
}

export const TemplatesView = {
  template: `
  <div class="view-stack">
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">生活模板</span><h2>从一种节奏开始，再变成自己的</h2></div><button class="soft-button" @click="$root.saveCurrentTemplate"><ui-icon name="plus" :size="14" /> 保存当前为模板</button></div>
      <div class="template-grid">
        <article v-for="template in $root.allPlanTemplates" :key="template.id" class="template-card" :class="'tone-' + (template.tone || 'violet')">
          <span class="template-icon"><ui-icon :name="template.icon" :size="21" /></span><h3>{{ template.name }}</h3><p>{{ template.description }}</p>
          <div class="template-actions"><button class="soft-button" @click="$root.applyTemplate(template)">应用到 {{ $root.selectedDate }}</button><button class="text-button" @click="$root.previewTemplate(template)">预览结构</button><button v-if="template.custom" class="text-button muted" @click="$root.deleteTemplate(template)">删除我的模板</button></div>
        </article>
      </div>
    </section>
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">日型</span><h2>每一天都可以有自己的名字</h2></div><button class="soft-button" @click="$root.newDayType"><ui-icon name="plus" :size="14" /> 自定义日型</button></div>
      <div class="day-type-grid"><article v-for="entry in $root.data.day_types" class="day-type-card" :style="{'--day-color': entry.config.color || 'var(--accent)'}">
        <span class="day-type-color"></span><h3>{{ entry.name }}</h3><small>{{ entry.builtin ? '内置日型' : '自定义日型' }}</small>
        <button class="text-button" @click="$root.editDayType(entry)">编辑</button><button v-if="!entry.builtin" class="text-button muted" @click="$root.deleteDayType(entry)">删除</button>
      </article></div>
    </section>
    <section class="section-card glass">
      <div class="section-heading"><div><span class="eyebrow">外观与头像</span><h2>让界面也拥有生活感</h2></div></div>
      <div class="theme-grid"><button v-for="theme in $root.themeTemplates" class="theme-card" :class="{active: ($root.data.config.appearance.theme === 'random' ? theme.random : $root.data.config.appearance.theme === theme.id)}" @click="$root.setTheme(theme)">
        <span class="theme-preview" :data-theme-name="theme.id" :style="$root.themePreviewStyle(theme)"><i></i><i></i><i></i></span><strong>{{ theme.name }}</strong><small>{{ theme.description }}</small>
      </button></div>
      <div class="avatar-editor"><img v-if="$root.avatarUrl && !$root.avatarBroken" :src="$root.avatarUrl" alt="当前头像" @error="$root.avatarBroken = true"><span v-else class="avatar-placeholder" aria-label="未设置头像">?</span><div><h3>生活头像</h3><p>默认自动获取适配器头像，也可以为此人格上传专属图片。</p><label class="soft-button upload-button">上传头像<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="$root.uploadAvatar"></label></div></div>
      <div class="avatar-editor"><div><h3>全屏生活背景</h3><p>上传后会覆盖主题插画，手机和桌面均以全屏裁切适配；随时可恢复主题背景。</p><div class="data-actions"><label class="soft-button upload-button">上传背景<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="$root.uploadBackground"></label><button class="soft-button" @click="$root.clearBackground">恢复主题背景</button></div></div></div>
      <div class="avatar-editor"><div><h3>生活横幅与强调色</h3><p>图片只保存在本机；颜色会立即应用到当前人格的界面。</p><div class="data-actions"><label class="soft-button upload-button">上传横幅<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="$root.uploadBanner"></label><input type="color" v-model="$root.customAccent" style="width: 100px" @change="$root.applyCustomAccent"></div></div></div>
    </section>
  </div>`,
}

export const SettingsView = {
  template: `
  <div class="settings-layout glass" v-if="$root.draft">
    <aside class="settings-tabs"><button v-for="tab in [['general','规划与数量'],['time','时间与夜间'],['sessions','会话权限'],['weather','天气与地点'],['data','数据与诊断']]" :class="{active: $root.settingsTab === tab[0]}" @click="$root.settingsTab = tab[0]">{{ tab[1] }}</button></aside>
    <div class="settings-content">
      <section v-if="$root.settingsTab === 'general'" class="settings-section">
        <span class="eyebrow">规划与数量</span><h2>自主，但有清晰边界</h2>
        <p class="field-hint">这些规则决定 bot 能安排多少生活，以及日程在多大范围内变化。初次使用建议保持默认，先观察一两天再调整。</p>
        <div class="form-grid">
          <label><span>每日最少安排</span><small>太少会显得空，推荐 2 到 4 项。</small><input type="number" min="0" max="500" v-model.number="$root.draft.min_items"></label>
          <label><span>每日最多安排</span><small>避免日程过密，推荐 8 到 12 项。</small><input type="number" min="1" max="500" v-model.number="$root.draft.max_items"></label>
          <label><span>定时规划</span><input type="time" v-model="$root.draft.planning_time"></label>
          <label><span>允许提前规划几天</span><small>默认 14 天已经足够，无需频繁修改。</small><input type="number" min="1" max="366" v-model.number="$root.draft.max_horizon_days"></label>
          <label><span>新日程默认执行概率</span><small>1 表示一定执行；0.8 表示偶尔会自然错过。</small><input type="number" min="0" max="1" step="0.05" v-model.number="$root.draft.default_probability"></label>
          <label><span>bot 可设置的最低概率</span><small>防止 bot 把所有安排设得太随意，推荐 0.2。</small><input type="number" min="0" max="1" step="0.05" v-model.number="$root.draft.min_probability"></label>
          <label><span>历史天数</span><input type="number" min="0" max="30" v-model.number="$root.draft.history_days"></label>
          <label><span>每组保留的最近变更记录</span><small>只影响发送给 bot 的变化上下文，推荐 2。</small><input type="number" min="1" max="20" v-model.number="$root.draft.diff_revisions"></label>
        </div>
        <div class="switch-grid"><label class="switch-row"><span>自动规划</span><input type="checkbox" v-model="$root.draft.auto_plan"></label>
          <label class="switch-row"><span>全项触发后再给规划机会</span><input type="checkbox" v-model="$root.draft.plan_on_all_triggered"></label>
          <label class="switch-row"><span>精确时间</span><input type="checkbox" v-model="$root.draft.allow_exact"></label>
          <label class="switch-row"><span>随机时间窗</span><input type="checkbox" v-model="$root.draft.allow_window"></label>
          <label class="switch-row"><span>概率触发</span><input type="checkbox" v-model="$root.draft.allow_probability"></label>
          <label class="switch-row"><span>普通聊天附带当前生活状态</span><input type="checkbox" v-model="$root.draft.inject_day_state"></label>
        </div>
        <label class="full-field"><span>历史模式</span><select v-model="$root.draft.history_mode"><option value="notice">系统短标记（推荐）</option><option value="full">额外保留提示词模板</option><option value="none">完全不写入聊天历史</option></select></label>
        <label class="full-field"><span>全部小项结束后的规划会话</span><select v-model="$root.draft.all_triggered_target_mode"><option value="planning_pool">规划起始池（默认）</option><option value="last_session">最后一个实际完成的会话</option></select><small class="field-hint">推荐保持规划池。只有希望 bot 在刚完成对话的地方继续规划时，才选择“最后实际完成的会话”。</small></label>
        <label class="full-field"><span class="prompt-title">完整规划提示词<button class="text-button" @click="$root.resetPrompt('planning')">恢复默认</button></span><textarea rows="7" v-model="$root.draft.planning_prompt"></textarea></label>
        <label class="full-field"><span class="prompt-title">小项执行提示词<button class="text-button" @click="$root.resetPrompt('execution')">恢复默认</button></span><textarea rows="6" v-model="$root.draft.execution_prompt"></textarea></label>
      </section>
      <section v-if="$root.settingsTab === 'time'" class="settings-section">
        <span class="eyebrow">时间与夜间</span><h2>执行、打扰与覆盖，分别决定</h2>
        <p class="field-hint">跨午夜时段可直接填写，例如 23:00 至 07:00。三类时段含义不同，请按说明设置。</p>
        <div v-for="group in [['blocked_execution_windows','禁止执行时段','任何日程都不会在此唤醒'],['quiet_delivery_windows','安静投递时段','允许做梦与思考，但不发可见消息'],['required_coverage_windows','必需覆盖时段','设置时段内的最小/最大项数']]" class="window-group">
          <div class="section-heading"><div><h3>{{ group[1] }}</h3><p>{{ group[2] }}</p></div><button class="soft-button" @click="$root.addWindow(group[0])"><ui-icon name="plus" :size="14" /> 添加</button></div>
          <div v-for="(window, index) in $root.draft[group[0]]" class="window-row">
            <input type="time" v-model="window.start"><span>至</span><input type="time" v-model="window.end">
            <template v-if="group[0] === 'required_coverage_windows'"><input type="number" min="0" max="100" v-model.number="window.min_items" title="最小项数"><input type="number" min="0" max="100" v-model.number="window.max_items" title="最大项数"><input placeholder="分类（可选）" v-model="window.category"></template>
            <button class="icon-button danger" @click="$root.draft[group[0]].splice(index, 1)"><ui-icon name="close" :size="14" /></button>
          </div>
        </div>
        <div class="form-grid"><label><span>迟到多久仍可触发（秒）</span><small>推荐 600 秒；设备短暂休眠后仍有机会补触发。</small><input type="number" min="0" v-model.number="$root.draft.recovery_grace_seconds"></label><label><span>生活时区</span><small>决定所有日程使用的当地时钟，推荐跟随系统。</small><select v-model="$root.draft.timezone"><option v-for="zone in $root.timezoneOptions" :key="zone[0]" :value="zone[0]">{{ zone[1] }}</option></select></label></div>
        <div class="review-setting">
          <label class="switch-row"><span>计划中途检查提醒</span><input type="checkbox" v-model="$root.draft.planning_review.enabled"></label>
          <p class="field-hint">默认关闭。开启后向距离下一小项最近的会话提供完整计划与调整引导，不强制修改。</p>
          <div class="form-grid"><label><span>检查间隔（分钟）</span><input type="number" min="60" max="10080" v-model.number="$root.draft.planning_review.interval_minutes"></label><label><span>触发前最小余量（分钟）</span><input type="number" min="5" max="240" v-model.number="$root.draft.planning_review.min_lead_minutes"></label></div>
          <label class="full-field"><span class="prompt-title">检查提示词<button class="text-button" @click="$root.resetPrompt('review')">恢复默认</button></span><textarea rows="5" v-model="$root.draft.planning_review.prompt"></textarea></label>
        </div>
      </section>
      <section v-if="$root.settingsTab === 'sessions'" class="settings-section">
        <span class="eyebrow">会话权限</span><h2>允许生活在哪些地方发生</h2>
        <p class="field-hint">先决定 bot 可以在哪些聊天里生活，再分别选择“规划开始时”和“执行日程时”优先使用的会话。</p>
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
        <p class="field-hint">只想快速体验可选择虚拟气候；需要真实天气时再填写地点。没有注册密钥就优先使用无需账号的服务。</p>
        <div class="form-grid"><label><span>模式</span><select v-model="$root.draft.weather.mode"><option value="off">关闭</option><option value="real">真实天气</option><option value="virtual">虚拟气候</option><option value="hybrid">真实 + 虚拟</option></select></label>
          <label><span>天气服务</span><select v-model="$root.draft.weather.provider"><option value="open_meteo">Open-Meteo · 无需账号</option><option value="met_norway">MET Norway · 无需账号</option><option value="nws">US NWS · 美国</option><option value="bright_sky">Bright Sky · DWD</option><option value="weatherapi">WeatherAPI · 注册</option><option value="visualcrossing">Visual Crossing · 注册</option><option value="qweather">和风天气 · 注册</option><option value="weatherbit">Weatherbit · 注册</option><option value="openweather">OpenWeather · 注册</option></select></label></div>
        <div class="location-editor"><input v-model="$root.cityQuery" placeholder="搜索城市，例如 上海" @keyup.enter="$root.geocode"><button class="soft-button" @click="$root.geocode">查找地点</button></div>
        <div v-if="$root.cityResults.length" class="city-results"><button v-for="city in $root.cityResults" @click="$root.chooseCity(city)"><strong>{{ city.name }}</strong> {{ city.admin1 }} {{ city.country }}<small>{{ city.latitude }}, {{ city.longitude }}</small></button></div>
        <div v-if="$root.currentLocation" class="current-location">当前地点：<strong>{{ $root.currentLocation.name }}</strong><span>{{ $root.currentLocation.latitude }}, {{ $root.currentLocation.longitude }}</span><button class="text-button" @click="$root.weatherPreview">预览天气</button></div>
        <div class="form-grid"><label><span>虚拟地点</span><input v-model="$root.draft.weather.virtual.location"></label><label><span>虚拟气候</span><select v-model="$root.draft.weather.virtual.climate"><option value="temperate">温带四季</option><option value="island">海岛</option><option value="rainforest">雨林</option><option value="snow">雪原</option><option value="desert">沙漠</option><option value="floating_city">幻想浮空城</option></select></label></div>
        <label class="full-field"><span>虚拟随机种子</span><input v-model="$root.draft.weather.virtual.seed"></label>
        <pre v-if="$root.weatherResult" class="weather-preview">{{ $root.weatherResult }}</pre>
      </section>
      <section v-if="$root.settingsTab === 'data'" class="settings-section">
        <span class="eyebrow">数据与诊断</span><h2>可备份、可恢复、可解释</h2>
        <p class="field-hint">导出包含当前人格的计划、状态、体验和模板，不包含任何天气密钥。导入前会先预览并确认。</p>
        <div class="data-actions"><button class="soft-button" @click="$root.exportData">导出当前人格数据</button><label class="soft-button upload-button">导入备份<input type="file" accept="application/json" @change="$root.importData"></label><button class="soft-button" @click="$root.loadDiagnostics">刷新诊断</button></div>
        <pre v-if="$root.diagnostics" class="diagnostics">{{ JSON.stringify($root.diagnostics, null, 2) }}</pre>
      </section>
      <div class="settings-save"><button class="soft-button" @click="$root.resetAllPrompts()">全部提示词恢复默认</button><button class="primary" :disabled="$root.saving" @click="$root.saveSettings">{{ $root.saving ? '正在生效…' : '保存并热生效' }}</button><span>保存后立即生效；正在执行的日程仍使用启动时规则，新规则用于之后的日程。</span></div>
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
    <div class="modal-heading"><div><span class="eyebrow">生活小项</span><h2>{{ editor.item ? '调整安排' : '添加安排' }}</h2></div><button class="icon-button" @click="$root.closeEditor"><ui-icon name="close" :size="16" /></button></div>
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
    <div class="modal-heading"><div><span class="eyebrow">当日状态</span><h2>此刻的我</h2></div><button class="icon-button" @click="$root.dayStateEditor = false"><ui-icon name="close" :size="16" /></button></div>
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
    <div class="modal-heading"><div><span class="eyebrow">日型</span><h2>{{ entry ? '编辑日型' : '创建日型' }}</h2></div><button class="icon-button" @click="$root.dayTypeEditor = null"><ui-icon name="close" :size="16" /></button></div>
    <label class="full-field"><span>名称</span><input v-model="form.name" placeholder="考试周 / 旅行日 / 雨天宅家"></label>
    <label class="full-field"><span>日型标识（创建后不可修改）</span><input v-model="form.id" :disabled="!!entry" placeholder="exam_week"></label>
    <label class="full-field"><span>主题色</span><input type="color" v-model="form.config.color"></label>
    <label class="full-field"><span>此日型规划提示词（留空继承全局）</span><textarea rows="3" v-model="form.config.overrides.planning_prompt"></textarea></label>
    <div class="form-grid" style="margin-top: 17px">
      <label><span>每日最少安排</span><small>太少会显得空，推荐 2 到 4 项。</small><input type="number" min="0" max="500" v-model.number="form.config.overrides.min_items"></label>
      <label><span>每日最多安排</span><small>避免日程过密，推荐 8 到 12 项。</small><input type="number" min="1" max="500" v-model.number="form.config.overrides.max_items"></label>
    </div>
    <label class="full-field"><span>此日型执行会话策略</span><select v-model="form.config.overrides.execution_pool.strategy"><option value="pure_random">完全随机</option><option value="no_immediate_repeat">避免连续重复</option><option value="shuffle_bag">一轮内不重复</option><option value="round_robin">顺序轮换</option></select></label>
    <div class="weekday-picker"><span>周重复</span><label v-for="(name, index) in ['一','二','三','四','五','六','日']"><input type="checkbox" :checked="form.rules.weekdays.includes(index)" @change="$root.toggleDayTypeWeekday(form, index)">周{{ name }}</label></div>
    <label class="full-field"><span>指定日期（逗号分隔）</span><textarea rows="2" v-model="form._dates" placeholder="2026-11-20, 2026-12-01"></textarea></label>
    <label class="full-field"><span>规则优先级（数字越小越优先）</span><input type="number" v-model.number="form.rules.priority"></label>
    <div class="modal-actions"><button class="soft-button" @click="$root.dayTypeEditor = null">取消</button><button class="primary" @click="$root.saveDayType(form)">保存日型</button></div>
  </div></div>`,
}
