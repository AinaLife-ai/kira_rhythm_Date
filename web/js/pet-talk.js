/* KRD pet chatter: deterministic data-in, persona-voiced, theme-tokenised lines. */

const WEATHER_TEXT = {
  rain: '雨', snow: '雪', storm: '雷雨', fog: '雾', cloud: '阴天', clear: '晴天', off: '',
}

const TERMINAL = new Set(['triggered', 'triggered_silent', 'skipped_probability', 'missed', 'cancelled', 'failed', 'interrupted'])

const DONE = new Set(['triggered', 'triggered_silent'])

const TONE = {
  left: 'count', total: 'count', done: 'count', index: 'index', title: 'title',
  detail: 'detail', session: 'session', time: 'time', weather: 'weather',
  activity: 'detail', name: 'name',
}

const VOICES = {
  tomato: {
    name: '番茄',
    progress: [
      '番茄数了数，今天 {{total}} 件事，已经做完 {{done}} 件，还剩 {{left}} 件。',
      '今天有 {{total}} 件，番茄做完 {{done}} 件啦……还剩 {{left}} 件。',
      '番茄记着呢：{{total}} 件里完成 {{done}} 件，{{left}} 件还在等。',
    ],
    next: [
      '{{index}}是 {{title}}，{{time}} 开始。番茄会在 {{session}} 等你。',
      '接下来是 {{index}}，{{title}}。{{time}}，在 {{session}}。',
      '{{title}}排在{{index}}，{{time}}。番茄没忘，在 {{session}}。',
    ],
    item: [
      '{{title}}呀，{{detail}}。番茄觉得慢慢来就好。',
      '{{index}}是 {{title}}，{{detail}}。不急。',
      '番茄看到 {{title}} 了，{{detail}}。',
    ],
    session: [
      '{{session}} 那边有 {{index}} {{title}}。番茄记住了。',
      '要去 {{session}} 呀。{{index}}是 {{title}}，番茄会跟着。',
      '{{index}} {{title}} 在 {{session}}。番茄先看一眼。',
    ],
    weather: [
      '外面{{weather}}，番茄会待在 {{session}}。还剩 {{left}} 件事。',
      '{{weather}}天呀。番茄数过了，还有 {{left}} 件事。',
      '听见{{weather}}了。{{index}} {{title}} 在 {{session}}，番茄会记得。',
    ],
    quiet: [
      '今天没有安排。番茄就晒晒太阳，也很好。',
      '没有要赶的时间。番茄在等下一件小事。',
      '今天留白。番茄把时间留给你。',
    ],
    done: [
      '今天的 {{total}} 件事都做完啦。番茄要奖励自己一颗番茄。',
      '全都完成了。{{done}} 件，一件不少。番茄可以发呆了。',
      '清单空了。番茄把最后一点力气也收好了。',
    ],
  },
  mint: {
    name: '薄荷',
    progress: [
      '喵！今天 {{total}} 件事，完成 {{done}} 件，还剩 {{left}} 件，尾巴都数累了。',
      '{{total}} 件里做完 {{done}} 件啦，{{left}} 件排在后面。薄荷陪你。',
      '还剩 {{left}} 件！薄荷把耳朵竖起来了。',
    ],
    next: [
      '{{index}}是 {{title}}！{{time}} 去 {{session}}，薄荷已经准备好啦。',
      '下一件 {{title}}，{{index}}，在 {{session}}。{{time}}，别跟丢哦。',
      '{{title}}在{{index}}，{{time}}。薄荷会先跑到 {{session}}。',
    ],
    item: [
      '{{title}}，{{detail}}。听起来不错，喵。',
      '{{index}}是 {{title}}，{{detail}}。薄荷的尾巴说可以。',
      '要做 {{title}} 呀，{{detail}}。薄荷陪你一起。',
    ],
    session: [
      '下一站 {{session}}！{{index}} {{title}}，薄荷闻到了。',
      '{{session}} 见，{{index}}是 {{title}}。',
      '{{index}} {{title}} 在 {{session}}。薄荷跑得快。',
    ],
    weather: [
      '{{weather}}天！还剩 {{left}} 件事，薄荷的耳朵已经听见了。',
      '外面{{weather}}，{{index}} {{title}} 在 {{session}}。薄荷会跳过去。',
      '{{weather}}，{{left}} 件小事。薄荷把尾巴收好。',
    ],
    quiet: [
      '今天没有安排，尾巴自己晃起来了。',
      '没有要赶的时间，薄荷在窗边看海。',
      '今天留白。薄荷把阳光分你一半。',
    ],
    done: [
      '全都做完啦！{{done}} 件，薄荷要转个圈。',
      '清单空了，尾巴也开心。',
      '{{total}} 件完成！薄荷今天超棒。',
    ],
  },
  garnet: {
    name: '石榴',
    progress: [
      '{{total}} 件，完成 {{done}} 件，还剩 {{left}} 件。别磨蹭。',
      '还剩 {{left}} 件。{{done}} 件已经做完，继续保持。',
      '进度：{{done}} / {{total}}。还有 {{left}} 件。',
    ],
    next: [
      '{{index}}：{{title}}。{{time}}，{{session}}。',
      '下一件 {{title}}。{{time}}，去 {{session}}。',
      '{{title}}，{{index}}。{{time}}。别迟到。',
    ],
    item: [
      '{{title}}。{{detail}}。就这些。',
      '{{index}}，{{title}}。{{detail}}。',
      '{{title}}，{{detail}}。先做完再说。',
    ],
    session: [
      '{{session}}。{{index}} {{title}}。别迟到。',
      '去 {{session}}。{{index}}是 {{title}}。',
      '{{session}} 那边，{{title}}。路线自己记。',
    ],
    weather: [
      '{{weather}}。还剩 {{left}} 件。路线自己定。',
      '外面{{weather}}。{{index}} {{title}}，{{session}}。',
      '{{weather}}天。{{left}} 件事，不用慌。',
    ],
    quiet: [
      '今天没事。别靠太近。',
      '清单是空的。可以安静一会儿。',
      '没有下一件。风有点大。',
    ],
    done: [
      '都做完了。{{done}} 件。可以安静了。',
      '清单空了。{{total}} 件，一件没漏。',
      '收工。今天到这里。',
    ],
  },
  xun: {
    name: '老板娘',
    progress: [
      '客人，今天 {{total}} 件事，做完 {{done}} 件，还剩 {{left}} 件。茶还热着。',
      '店里记着：{{total}} 件里完成 {{done}} 件，{{left}} 件慢慢来。',
      '还有 {{left}} 件。茶先喝着，不用急。',
    ],
    next: [
      '{{index}}是 {{title}}，{{time}}。在 {{session}}，慢慢来。',
      '接下来 {{title}}，{{index}}。{{time}}，{{session}} 见。',
      '{{title}}排在{{index}}，{{time}}。客人，别忘。',
    ],
    item: [
      '{{title}}，{{detail}}。不急，先把这杯茶喝完。',
      '{{index}}是 {{title}}，{{detail}}。',
      '要做 {{title}} 呀，{{detail}}。听着就暖。',
    ],
    session: [
      '{{session}} 的客人，{{index}} {{title}}，别忘了。',
      '{{session}} 那边有 {{title}}。茶留着。',
      '去 {{session}} 吧，{{index}}是 {{title}}。',
    ],
    weather: [
      '外面{{weather}}，店里还有 {{left}} 件事。进来坐坐。',
      '{{weather}}天，{{index}} {{title}} 在 {{session}}。茶刚泡好。',
      '{{weather}}。还有 {{left}} 件，慢慢来。',
    ],
    quiet: [
      '今天没有安排。店面照常，茶也热着。',
      '没有下一件。客人，坐一会儿吧。',
      '今天留白。灯笼还没点。',
    ],
    done: [
      '今天的 {{total}} 件都做完了。客人辛苦了。',
      '全都完成了。{{done}} 件，可以收摊了。',
      '清单空了。茶还热着。',
    ],
  },
  hathor: {
    name: '天使',
    progress: [
      '清单 {{total}} 项，完成 {{done}} 项，剩余 {{left}} 项。',
      '{{total}} 项里已完成 {{done}} 项，{{left}} 项待处理。',
      '进度确认：{{done}} / {{total}}，剩余 {{left}} 项。',
    ],
    next: [
      '{{index}}：{{title}}。{{time}}，目标 {{session}}。',
      '下一项 {{title}}，{{index}}。{{time}}，{{session}}。',
      '{{title}}，{{index}}。{{time}} 出发，目标 {{session}}。',
    ],
    item: [
      '{{title}}，{{detail}}。已记录。',
      '{{index}} {{title}}。{{detail}}。',
      '{{title}}。{{detail}}。路线确认。',
    ],
    session: [
      '{{session}}，{{index}} {{title}}。路线确认。',
      '目标 {{session}}。{{index}} {{title}}。',
      '{{index}} {{title}}，{{session}}。收到。',
    ],
    weather: [
      '{{weather}}，能见度变化。剩余 {{left}} 项，路线不变。',
      '{{weather}}。{{index}} {{title}}，目标 {{session}}。',
      '{{weather}}，{{left}} 项待处理。注意安全。',
    ],
    quiet: [
      '今日无任务。待命。',
      '清单为空。可以休息。',
      '没有下一项。路线待定。',
    ],
    done: [
      '清单完成。{{done}} 项，全部收尾。',
      '{{total}} 项全部完成。收工。',
      '任务结束。{{done}} 项，确认。',
    ],
  },
}

const TOPIC_WEIGHTS = {
  progress: 24, next: 28, item: 18, session: 14, weather: 10, quiet: 4, done: 2,
}

const trim = (value, size) => {
  const text = String(value == null ? '' : value).replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > size ? text.slice(0, size).replace(/[，。；、,.;\s]+$/, '') + '…' : text
}

const flattenItems = (plan) => (plan?.blocks || []).flatMap((block) => block.items || [])
const isDone = (item) => DONE.has(item?.state)
const isPending = (item) => item && !TERMINAL.has(item?.state || 'scheduled')
const itemOrder = (item) => Number.isFinite(Number(item?.position)) ? Number(item.position) : 0

const clockText = (item) => {
  if (!item) return '稍后'
  if (item.scheduled_at) {
    const date = new Date(Number(item.scheduled_at) * 1000)
    if (!Number.isNaN(date.getTime())) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  const raw = item.schedule?.at || item.schedule?.start || ''
  const match = String(raw).match(/(\d{1,2}):(\d{2})/)
  return match ? `${match[1].padStart(2, '0')}:${match[2]}` : '稍后'
}

const sessionText = (item, sessions) => {
  if (!item?.target) return '执行池自动选'
  const found = (sessions || []).find((session) => session?.sid === item.target)
  const title = trim(found?.title, 18)
  return title || String(item.target).trim()
}

const chooseOne = (list, rng) => list[Math.floor(rng() * list.length)] || list[0]

const pickTemplate = (voice, topic, rng, lastKey) => {
  const list = voice[topic] || voice.quiet
  let index = Math.floor(rng() * list.length)
  let key = `${topic}:${index}`
  if (lastKey === key && list.length > 1) {
    index = (index + 1 + Math.floor(rng() * (list.length - 1))) % list.length
    key = `${topic}:${index}`
  }
  return { text: list[index], key }
}

const render = (template, values) => {
  const parts = []
  let cursor = 0
  const re = /\{\{(\w+)\}\}/g
  let match
  while ((match = re.exec(template))) {
    if (match.index > cursor) parts.push({ text: template.slice(cursor, match.index), tone: 'plain' })
    const key = match[1]
    const value = values[key]
    if (value !== undefined && value !== null && String(value).trim()) {
      parts.push({ text: String(value), tone: TONE[key] || 'plain' })
    }
    cursor = match.index + match[0].length
  }
  if (cursor < template.length) parts.push({ text: template.slice(cursor), tone: 'plain' })
  return parts
}

/**
 * Build one in-character line about the current plan.
 * Session labels deliberately prefer the human title over the raw sid.
 */
export function buildPetChatter({
  variant = 'tomato', plan = null, nextItem = null, sessions = [], weather = 'off',
  phase = 'day', event = 'quiet', activity = '', now = Date.now() / 1000,
  rng = Math.random, lastKey = '', preferredTopic = '',
} = {}) {
  const voice = VOICES[variant] || VOICES.tomato
  const items = flattenItems(plan)
  const pending = items.filter(isPending).sort((a, b) => (Number(a.scheduled_at) || 0) - (Number(b.scheduled_at) || 0) || itemOrder(a) - itemOrder(b))
  const next = (nextItem && isPending(nextItem) ? nextItem : pending[0]) || null
  const chosen = next || pending[Math.floor(rng() * pending.length)] || items[items.length - 1] || null
  const index = chosen ? items.indexOf(chosen) + 1 : 0
  const done = items.filter(isDone).length
  const leftCount = pending.length
  const total = items.length
  const weatherText = WEATHER_TEXT[weather] || ''
  const values = {
    name: voice.name,
    total: String(total),
    done: String(done),
    left: String(leftCount),
    index: index ? `第 ${index} 件` : '稍后',
    title: trim(chosen?.title || activity || '下一件小事', 18),
    detail: trim(chosen?.intent || chosen?.instruction || chosen?.category || '没有额外说明', 22),
    session: sessionText(chosen, sessions),
    time: clockText(chosen),
    weather: weatherText,
    activity: trim(activity, 16),
  }

  let topics = []
  if (total === 0) topics = ['quiet']
  else if (leftCount === 0) topics = ['done', 'quiet']
  else topics = ['progress', 'next', 'item', 'session']
  if (weatherText) topics.push('weather', 'weather')
  const weighted = []
  for (const topic of topics) {
    const weight = TOPIC_WEIGHTS[topic] || 1
    for (let i = 0; i < weight; i += 1) weighted.push(topic)
  }
  const usablePreferred = preferredTopic === 'weather' && !weatherText ? '' : preferredTopic
  const topic = (usablePreferred && voice[usablePreferred]) ? usablePreferred : (chooseOne(weighted, rng) || 'quiet')
  const picked = pickTemplate(voice, topic, rng, lastKey)
  const parts = render(picked.text, values)
  return {
    key: `${variant}:${picked.key}`,
    topic,
    parts,
    text: parts.map((part) => part.text).join(''),
    index,
    title: values.title,
    session: values.session,
  }
}

export const PET_CHATTER_TOPICS = Object.keys(TOPIC_WEIGHTS)
