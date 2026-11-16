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
    name: '我',
    progress: [
      '我数了数，今天 {{total}} 件事，已经做完 {{done}} 件，还剩 {{left}} 件。',
      '今天有 {{total}} 件，我做完 {{done}} 件啦……还剩 {{left}} 件。',
      '我记着呢：{{total}} 件里完成 {{done}} 件，{{left}} 件还在等。',
    ],
    next: [
      '{{index}}是 {{title}}，{{time}} 开始。我会在 {{session}} 等你。',
      '接下来是 {{index}}，{{title}}。{{time}}，在 {{session}}。',
      '{{title}}排在{{index}}，{{time}}。我没忘，在 {{session}}。',
    ],
    item: [
      '{{title}}呀，{{detail}}。我觉得慢慢来就好。',
      '{{index}}是 {{title}}，{{detail}}。不急。',
      '我看到 {{title}} 了，{{detail}}。',
    ],
    session: [
      '{{session}} 那边有 {{index}} {{title}}。我记住了。',
      '要去 {{session}} 呀。{{index}}是 {{title}}，我会跟着。',
      '{{index}} {{title}} 在 {{session}}。我先看一眼。',
    ],
    weather: [
      '外面{{weather}}，我会待在 {{session}}。还剩 {{left}} 件事。',
      '{{weather}}天呀。我数过了，还有 {{left}} 件事。',
      '听见{{weather}}了。{{index}} {{title}} 在 {{session}}，我会记得。',
    ],
    quiet: [
      '今天没有安排。我就晒晒太阳，也很好。',
      '没有要赶的时间。我在等下一件小事。',
      '今天留白。我把时间留给你。',
    ],
    done: [
      '今天的 {{total}} 件事都做完啦。我要奖励自己一颗番茄。',
      '全都完成了。{{done}} 件，一件不少。我可以发呆了。',
      '清单空了。我把最后一点力气也收好了。',
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

const INTERACTIONS = {
  tomato: {
    talk: [
      '我在听。今天还剩 {{left}} 件，{{index}}是 {{title}}，{{time}} 去 {{session}}，{{detail}}',
      '要聊今天吗？我把 {{index}} {{title}} 记在 {{session}} 了，{{time}} 开始，{{detail}}',
      '现在是{{phase}}。{{total}} 件里做完 {{done}} 件，{{index}} {{title}} 还在等，{{time}} 在 {{session}}',
      '我没有走神。{{title}}在{{index}}，{{time}}，{{session}}；{{detail}}',
    ],
    pat: [
      '摸头可以……我在。{{index}} {{title}}，{{time}} 在 {{session}}，{{detail}}',
      '再摸一下也可以。我记得还剩 {{left}} 件，{{index}} {{title}} 在 {{session}}',
      '我被你摸醒了。{{title}} 在 {{index}}，{{time}}，别担心',
      '呼……{{phase}}里，我在{{activity}}，{{index}} {{title}} 在 {{session}}',
    ],
    talkQuiet: ['今天没有安排。我在这里，想聊什么都可以', '我把时间留给你了。没有要赶的事，慢慢说'],
    patQuiet: ['今天没有安排……我在，摸头也可以', '没有下一件了。我把一点安静分给你'],
    talkDone: ['今天的 {{total}} 件都做完了。我可以陪你聊一会儿', '清单空了。{{done}} 件一件不少，我在这里'],
    patDone: ['全都做完了……我把剩下的时间给你', '今天的 {{total}} 件收好了。我可以安心被你摸头'],
  },
  mint: {
    talk: [
      '喵，陪你聊一会儿。下一件是 {{index}} {{title}}，{{time}} 在 {{session}}，{{detail}}',
      '{{total}} 件里做完 {{done}} 件啦，还剩 {{left}} 件。{{index}} {{title}}，{{time}} 去 {{session}}',
      '薄荷在窗边听着。{{phase}}的{{activity}}，{{title}}排在{{index}}，{{session}}',
      '要聊天吗？{{index}} {{title}} 在 {{session}}，{{time}}；{{detail}}，薄荷陪你',
    ],
    pat: [
      '呼噜……薄荷在。还剩 {{left}} 件，{{index}} {{title}}，{{time}} 去 {{session}}',
      '摸头收到！薄荷把 {{index}} {{title}} 记好了，{{time}} 在 {{session}}',
      '再摸一下尾巴会翘起来。{{title}}在{{index}}，{{session}}，{{detail}}',
      '薄荷被你摸得暖乎乎的。{{phase}}的{{activity}}，{{index}} {{title}} 在 {{session}}',
    ],
    talkQuiet: ['今天没有安排，薄荷在窗边看海。想聊什么喵', '今天留白，薄荷把阳光分你一半'],
    patQuiet: ['没有安排也可以摸头，薄荷的耳朵在这里', '呼噜……今天没有下一件，陪你一会儿'],
    talkDone: ['全都做完啦。{{done}} 件，薄荷要转个圈再陪你', '清单空了，尾巴也开心。聊点别的吧'],
    patDone: ['全都做完了，薄荷把尾巴借你摸一下', '今天的 {{total}} 件收好，薄荷现在只负责陪你'],
  },
  garnet: {
    talk: [
      '说。还剩 {{left}} 件。{{index}}：{{title}}。{{time}}，{{session}}。{{detail}}',
      '{{total}} 件，已做 {{done}} 件。{{index}} {{title}}，{{time}}，{{session}}。别忘',
      '现在是{{phase}}。{{activity}}。{{index}} {{title}}，{{time}} 前到 {{session}}',
      '{{title}}在{{index}}。{{time}}，{{session}}。{{detail}}。别磨蹭',
    ],
    pat: [
      '手拿开……只准一下。{{index}} {{title}}，{{time}}，{{session}}。别忘了',
      '摸够了？{{left}} 件还在。{{index}} {{title}}，{{time}} 去 {{session}}',
      '{{title}} 在 {{index}}。{{time}}，{{session}}。别以为摸头就能混过去',
      '{{phase}}的{{activity}}。{{index}} {{title}}，{{session}}。就这些',
    ],
    talkQuiet: ['今天没事。别靠太近', '清单空的。你可以说，我在听'],
    patQuiet: ['只准一下。今天没有下一件', '手拿开……算了，今天可以多一下'],
    talkDone: ['都做完了。{{done}} 件。可以安静了', '{{total}} 件收工。现在没有要赶的'],
    patDone: ['做完了。手可以拿开了', '清单空了。摸头……下不为例'],
  },
  xun: {
    talk: [
      '客人想聊什么？店里还剩 {{left}} 件……{{index}} {{title}}，{{time}} 在 {{session}}',
      '茶还热着。{{total}} 件里做完 {{done}} 件，{{index}} {{title}} 在 {{session}}，{{detail}}',
      '现在是{{phase}}，{{activity}}。{{index}} {{title}}，{{time}}，去 {{session}} 慢慢来',
      '店里记着呢：{{index}} {{title}}，{{time}}，{{session}}。{{detail}}',
    ],
    pat: [
      '摸头可以，茶要凉了。客人，{{index}} {{title}}，{{time}} 在 {{session}}',
      '老板娘可不是随便摸的……下不为例。{{index}} {{title}}，{{time}}，{{session}}',
      '摸完记得洗手。{{title}}在{{index}}，{{time}}，{{session}}，{{detail}}',
      '客人，{{phase}}的{{activity}}，{{index}} {{title}} 在 {{session}}。慢慢来',
    ],
    talkQuiet: ['今天没有安排。店面照常，茶也热着', '客人，没有下一件了。坐一会儿，慢慢聊'],
    patQuiet: ['摸头可以，今天店里不忙', '没有安排也要喝茶。手暖了再走'],
    talkDone: ['今天的 {{total}} 件都做完了。客人辛苦了', '全都完成了。{{done}} 件，可以收摊聊会儿'],
    patDone: ['收摊了。摸头就摸头吧，客人', '清单空了，茶还热着。今天辛苦了'],
  },
  hathor: {
    talk: [
      '通讯已接通。清单剩余 {{left}} 项，{{index}} {{title}}，{{time}} 目标 {{session}}',
      '{{total}} 项，完成 {{done}} 项。{{index}} {{title}}，{{time}}，{{session}}。{{detail}}',
      '当前{{phase}}，{{activity}}。{{index}} {{title}}，{{time}}，路线 {{session}}',
      '记录：{{index}} {{title}}，{{time}}，{{session}}。{{detail}}',
    ],
    pat: [
      '接触确认。{{index}} {{title}}，{{time}}，{{session}}。剩余 {{left}} 项',
      '摸头请求已接收。{{index}} {{title}}，{{time}}，目标 {{session}}',
      '{{title}}在{{index}}。{{time}}，{{session}}。路线不变',
      '{{phase}}的{{activity}}。{{index}} {{title}}，{{time}}，{{session}}。待命',
    ],
    talkQuiet: ['今日无任务。待命，也可以陪你说一会儿', '清单为空。通讯保持，慢慢讲'],
    patQuiet: ['接触确认。今日无任务，可以摸', '没有下一项。待命中，手可以放着'],
    talkDone: ['清单完成。{{done}} 项，全部收尾', '{{total}} 项全部完成。现在可以聊别的'],
    patDone: ['接触确认。清单已清空', '任务结束。{{done}} 项，摸头许可'],
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

const pickTemplate = (voice, topic, rng, lastKey, avoidKeys = []) => {
  const list = voice[topic] || voice.quiet
  const blocked = new Set([lastKey, ...avoidKeys])
  const free = list.map((_, index) => index).filter((index) => !blocked.has(`${topic}:${index}`))
  const pool = free.length ? free : list.map((_, index) => index)
  const index = pool[Math.floor(rng() * pool.length)]
  return { text: list[index], key: `${topic}:${index}` }
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

const stripTrailingPeriod = (parts) => {
  let last = parts[parts.length - 1]
  while (last) {
    const cleaned = last.text.replace(/。\s*$/, '')
    if (cleaned) {
      last.text = cleaned
      break
    }
    parts.pop()
    last = parts[parts.length - 1]
  }
  return parts
}

/**
 * Build one in-character line about the current plan.
 * Session labels deliberately prefer the human title over the raw sid.
 */
export function buildPetChatter({
  variant = 'tomato', plan = null, nextItem = null, sessions = [], weather = 'off',
  phase = 'day', event = 'quiet', activity = '', now = Date.now() / 1000,
  rng = Math.random, lastKey = '', preferredTopic = '', avoidKeys = [],
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
  const picked = pickTemplate(voice, topic, rng, lastKey, avoidKeys)
  const parts = stripTrailingPeriod(render(picked.text, values))
  return {
    key: `${variant}:${picked.key}`,
    templateKey: picked.key,
    topic,
    parts,
    text: parts.map((part) => part.text).join(''),
    index,
    title: values.title,
    session: values.session,
  }
}

const EXTRA_VOICES = {
  tomato: {
    progress: ['我掰着手指数：{{total}} 件，完成 {{done}} 件，还剩 {{left}} 件', '{{left}} 件还没做完。我把它们排好了'],
    next: ['{{time}} 的 {{title}}，在 {{session}}。我已经记住了', '下一件不是番茄，是 {{title}}。{{index}}，{{time}}'],
    item: ['{{title}}，{{detail}}。我想配一颗小番茄', '{{detail}} 的 {{title}}，我会慢慢做'],
    session: ['{{session}} 里等着的，是 {{index}} {{title}}', '我会去 {{session}}，{{title}} 排在 {{index}}'],
    weather: ['{{weather}}的时候，我想喝番茄汤，还剩 {{left}} 件', '外面{{weather}}。{{session}} 的 {{title}}，我会记得'],
    quiet: ['今天没有安排。我在窗边晒一会儿', '清单是空的。我把番茄酱留到明天'],
    done: ['{{total}} 件全做完了。我奖励自己一颗番茄', '清单空了。我可以慢慢吃番茄了'],
  },
  mint: {
    progress: ['喵，{{left}} 件还没做，薄荷的尾巴数得过来', '{{done}} 件完成啦，剩下 {{left}} 件交给薄荷'],
    next: ['薄荷已经把 {{title}} 放进 {{session}} 的路线了', '{{index}} {{title}}，{{time}}，薄荷先跑一步'],
    item: ['{{title}} 呀，{{detail}}。薄荷陪你拆成小块', '{{detail}}，听起来像小鱼干……薄荷会认真'],
    session: ['要去 {{session}} 找 {{title}}，薄荷不会迷路', '{{session}} 的 {{index}} {{title}}，薄荷记得味道'],
    weather: ['{{weather}}天，薄荷的耳朵湿了一点，还剩 {{left}} 件', '天气变了也不怕，{{index}} {{title}} 在 {{session}}'],
    quiet: ['没有安排，薄荷在追自己的尾巴', '今天留白，薄荷把海风分你一半'],
    done: ['{{total}} 件完成，薄荷要打个滚', '清单空了，薄荷把尾巴绕成一个圈'],
  },
  garnet: {
    progress: ['{{total}} 件，完成 {{done}} 件，剩余 {{left}} 件。别让我重复', '{{left}} 件没清。{{done}} 件已结案'],
    next: ['{{index}} {{title}}。{{time}}，{{session}}。迟到不等人', '下一项 {{title}}。{{time}}，去 {{session}}'],
    item: ['{{title}}。{{detail}}。别拖', '{{index}} {{title}}，{{detail}}。做完再说话'],
    session: ['{{session}}。{{title}}。别走错', '{{index}} {{title}}，目标 {{session}}。收到'],
    weather: ['{{weather}}。{{left}} 件，自己安排', '{{weather}}天。{{session}} 的 {{title}}，别忘'],
    quiet: ['没有下一件。安静点', '今天清单为空。别来吵我'],
    done: ['{{total}} 件清完。收工', '{{done}} 件。可以安静了'],
  },
  xun: {
    progress: ['客人，今天 {{total}} 件，做完 {{done}} 件，还剩 {{left}} 件。先喝口茶', '店里记着 {{left}} 件，慢慢来，茶不会凉'],
    next: ['{{time}} 的 {{title}}，在 {{session}}。客人，别让茶等', '下一件 {{title}}，{{index}}。{{time}}，{{session}} 见'],
    item: ['{{title}}，{{detail}}。像一碗热汤，慢慢喝', '{{index}} {{title}}。{{detail}}，先做起来'],
    session: ['去 {{session}} 吧，{{index}} {{title}}，茶给你留着', '{{session}} 的 {{title}}，客人，慢慢走'],
    weather: ['外面{{weather}}，店里正好有热茶。还剩 {{left}} 件', '{{weather}}天，{{index}} {{title}} 在 {{session}}，进来坐坐'],
    quiet: ['今天不忙。客人，坐一会儿', '没有下一件，灯笼还没点，茶已经好了'],
    done: ['{{total}} 件都做完了。客人，收摊喝茶', '{{done}} 件完成。今天辛苦了'],
  },
  hathor: {
    progress: ['清单 {{total}} 项，完成 {{done}} 项，剩余 {{left}} 项。状态正常', '{{left}} 项待处理，{{done}} 项已归档'],
    next: ['{{index}} {{title}}，{{time}}。目标 {{session}}，路线已更新', '下一项 {{title}}。{{time}}，{{session}}，确认'],
    item: ['{{title}}，{{detail}}。记录完毕', '{{index}} {{title}}，{{detail}}。执行序列确认'],
    session: ['{{session}}，{{index}} {{title}}。联络点确认', '目标 {{session}}，{{title}}，{{time}}。保持频道'],
    weather: ['{{weather}}，环境变化。剩余 {{left}} 项，按计划', '{{weather}}。{{index}} {{title}}，{{session}}，注意'],
    quiet: ['今日无任务。通讯保持', '清单为空。可以待命'],
    done: ['清单完成。{{done}} 项，归档', '{{total}} 项全部完成。收工'],
  },
}

const EXTRA_INTERACTIONS = {
  tomato: {
    talk: ['我在。{{phase}}的{{activity}}，{{index}} {{title}} 在 {{session}}，{{detail}}', '{{total}} 件里还剩 {{left}} 件，{{title}} 在 {{index}}，{{time}}；我陪你'],
    pat: ['我在呢……{{index}} {{title}}，{{time}}，{{session}}，{{detail}}', '摸头收到。{{left}} 件小事，{{index}} {{title}}，我记着'],
    talkQuiet: ['想聊什么都没有也可以，我在这里'],
    patQuiet: ['摸头也可以，今天我归你管'],
    talkDone: ['{{total}} 件都收好了，我可以陪你到很晚'],
    patDone: ['全都做完了……再摸一下也没关系'],
  },
  mint: {
    talk: ['薄荷在听！{{index}} {{title}}，{{time}} 在 {{session}}，{{detail}}', '{{left}} 件还剩着，{{title}} 在 {{index}}，{{time}}，薄荷陪你'],
    pat: ['呼噜……{{title}} 在 {{index}}，{{time}}，薄荷记着', '摸头收到！{{left}} 件，{{index}} {{title}}，薄荷陪你'],
    talkQuiet: ['薄荷在，今天可以慢慢聊'],
    patQuiet: ['呼噜……今天可以多摸一下'],
    talkDone: ['全都做完了，薄荷要陪你玩一会儿'],
    patDone: ['清单空了，薄荷的尾巴归你摸'],
  },
  garnet: {
    talk: ['{{index}}：{{title}}。{{time}}，{{session}}。{{detail}}。说完了', '还剩 {{left}} 件。{{title}}，{{time}}。别让我提醒'],
    pat: ['手拿开。{{index}} {{title}}，{{time}}，{{session}}。记住', '摸一下就够了。{{left}} 件，{{title}} 在 {{index}}'],
    talkQuiet: ['没安排。你可以说，我听'],
    patQuiet: ['只准一下。今天没有下一件'],
    talkDone: ['都做完了。现在可以说话'],
    patDone: ['做完了。手可以拿开……再放一会儿也行'],
  },
  xun: {
    talk: ['客人，{{index}} {{title}}，{{time}} 在 {{session}}，{{detail}}，慢慢来', '茶还热着。还剩 {{left}} 件，{{title}} 排在 {{index}}'],
    pat: ['摸头可以，{{index}} {{title}}，{{time}}，{{session}}，茶要凉了', '客人，{{left}} 件还在，{{title}} 在 {{index}}，不急'],
    talkQuiet: ['客人，今天店里不忙，想聊什么'],
    patQuiet: ['摸头可以，今天茶管够'],
    talkDone: ['都做完了。客人，坐下喝杯茶'],
    patDone: ['收摊了。今天可以多摸一下'],
  },
  hathor: {
    talk: ['通讯稳定。{{index}} {{title}}，{{time}}，{{session}}，{{detail}}', '剩余 {{left}} 项。{{title}}，{{time}}，目标 {{session}}'],
    pat: ['接触确认。{{index}} {{title}}，{{time}}，{{session}}', '许可。{{left}} 项待处理，{{title}} 在 {{index}}'],
    talkQuiet: ['今日无任务。通讯保持，可以聊'],
    patQuiet: ['接触确认。今日无任务，可以摸'],
    talkDone: ['清单清空。可以聊别的'],
    patDone: ['任务结束。摸头许可'],
  },
}

for (const [variant, topics] of Object.entries(EXTRA_VOICES)) {
  for (const [topic, lines] of Object.entries(topics)) {
    if (VOICES[variant]?.[topic]) VOICES[variant][topic].push(...lines)
  }
}
for (const [variant, groups] of Object.entries(EXTRA_INTERACTIONS)) {
  for (const [group, lines] of Object.entries(groups)) {
    if (INTERACTIONS[variant]?.[group]) INTERACTIONS[variant][group].push(...lines)
  }
}

const PHASE_TEXT = { dawn: '清晨', morning: '上午', day: '白昼', dusk: '傍晚', night: '夜里' }

/**
 * User-triggered talk / pat lines. These are intentionally more specific than
 * ambient chatter: they must answer with the real next item, its time, content,
 * and session instead of a generic "嗯嗯".
 */
export function buildPetInteraction({
  kind = 'talk', variant = 'tomato', plan = null, nextItem = null, sessions = [],
  weather = 'off', phase = 'day', activity = '', rng = Math.random, lastKey = '', avoidKeys = [],
} = {}) {
  const interactionKind = kind === 'pat' ? 'pat' : 'talk'
  const voice = INTERACTIONS[variant] || INTERACTIONS.tomato
  const items = flattenItems(plan)
  const pending = items.filter(isPending).sort((a, b) => (Number(a.scheduled_at) || 0) - (Number(b.scheduled_at) || 0) || itemOrder(a) - itemOrder(b))
  const next = (nextItem && isPending(nextItem) ? nextItem : pending[0]) || null
  const chosen = next || pending[Math.floor(rng() * pending.length)] || items[items.length - 1] || null
  const index = chosen ? items.indexOf(chosen) + 1 : 0
  const done = items.filter(isDone).length
  const total = items.length
  const leftCount = pending.length
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
    weather: WEATHER_TEXT[weather] || '',
    activity: trim(activity || chosen?.title || '陪着你', 16),
    phase: PHASE_TEXT[phase] || '现在',
  }
  const group = !items.length
    ? `${interactionKind}Quiet`
    : (leftCount ? interactionKind : `${interactionKind}Done`)
  const templates = voice[group] || voice[interactionKind]
  const picked = pickTemplate({ [group]: templates }, group, rng, lastKey, avoidKeys)
  const parts = stripTrailingPeriod(render(picked.text, values))
  return {
    key: `${variant}:${interactionKind}:${picked.key}`,
    templateKey: picked.key,
    kind: interactionKind,
    topic: group,
    parts,
    text: parts.map((part) => part.text).join(''),
    index,
    title: values.title,
    session: values.session,
  }
}

export const PET_CHATTER_TOPICS = Object.keys(TOPIC_WEIGHTS)
