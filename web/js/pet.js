const VOICE = {
  tomato: {
    read: ['这一页，番茄想再看一遍。', '书里也会写到番茄吗？'],
    idle: ['番茄，最好了。', '今天也慢慢来。'],
    sleep: ['番茄城堡……先睡一下。', '别把番茄酱拿走。'],
    pat: ['摸头可以，番茄要留着。', '再一下下。'],
    umbrella: ['伞够大，站进来一点。'],
  },
  mint: {
    eat: ['这个甜甜的，你要不要？', '气泡在舌尖跳。'],
    walk: ['海风把尾巴吹乱了。', '去前面看看。'],
    sleep: ['尾巴借你当抱枕。', '睡一小会儿。'],
    pat: ['耳朵、耳朵不能一直摸。', '喵……再摸一下。'],
    idle: ['今天也要精神一点。'],
  },
  garnet: {
    work: ['先把手头这件事做完。', '专注一会儿。'],
    phone: ['等一下，我回个消息。', '看到一个有意思的东西。'],
    sleep: ['别吵，我闭目养神。', '夜里安静。'],
    pat: ['……只准一下。', '手拿开，我要工作了。'],
    idle: ['风有点大。'],
  },
  xun: {
    eat: ['坐下来，先吃点热的。', '汤要趁热。'],
    umbrella: ['雨太大，站进来。', '伞往你那边一点。'],
    read: ['这一页，讲的是旧城。', '陪我坐一会儿。'],
    pat: ['老板娘可不是随便摸的。', '……下不为例。'],
    idle: ['店面今天也照常营业。'],
  },
  hathor: {
    run: ['目标出现，开始行动。', '我先过去，你跟上。'],
    work: ['配送路线确认。', '按计划执行。'],
    phone: ['接到一个新单。', '等我回个消息。'],
    pat: ['翅膀不可以乱碰。', '只准碰一下。'],
    idle: ['今晚的风很适合出发。'],
  },
}

const ACTIONS = {
  idle: '发呆', walk: '散步', read: '看书', eat: '吃点东西', phone: '看手机',
  work: '专注', music: '听歌', sleep: '打盹', umbrella: '撑伞', scarf: '围巾',
  run: '赶路', happy: '开心', stretch: '伸懒腰', dance: '跳舞', look: '看风景',
  held: '被拿起', thrown: '被丢起来', land: '落地', dizzy: '晕乎乎',
}

export const PetCompanion = {
  props: {
    variant: { type: String, default: 'mono' },
    nextItem: { type: Object, default: null },
    weather: { type: String, default: 'off' },
    phase: { type: String, default: 'day' },
    event: { type: String, default: 'quiet' },
    activity: { type: String, default: '' },
    sprite: { type: String, default: '' },
    large: { type: Boolean, default: false },
  },
  data() {
    return {
      x: 77,
      facing: -1,
      action: 'idle',
      speech: '',
      speechUntil: 0,
      panel: false,
      hearts: 0,
      fullness: 76,
      mood: 88,
      idleTimer: null,
      speechTimer: null,
      wanderTimer: null,
      dragging: false,
      dragStart: 0,
      dragStartY: 0,
      dragOrigin: 77,
      dragLift: 0,
      lift: 0,
      moved: false,
      holdTimer: null,
      suppressClick: false,
      actionLockUntil: 0,
      labelVisible: true,
      labelHint: true,
      careVisible: true,
      labelTimer: null,
      careTimer: null,
      sleepiness: 0,
    }
  },
  computed: {
    petStyle() { return { left: this.x + '%', '--pet-lift': this.lift + 'px' } },
    label() { return ACTIONS[this.action] || '发呆' },
    isUmbrella() { return this.action === 'umbrella' },
    isScarf() { return this.action === 'scarf' },
    isBook() { return this.action === 'read' },
    isPhone() { return this.action === 'phone' },
    isCup() { return this.action === 'eat' },
    isWork() { return this.action === 'work' },
    isMusic() { return this.action === 'music' },
    isSleep() { return this.action === 'sleep' },
    petClass() {
      return `pet-${this.variant}`
    },
    statusLine() {
      if (this.event === 'imminent') return '下一件事快到了'
      if (this.weather === 'rain') return '正在听雨'
      if (this.weather === 'snow') return '雪落在围巾上'
      if (this.phase === 'night') return '夜色刚好'
      return '今天也在陪你'
    },
  },
  watch: {
    nextItem() { this.chooseAction(true) },
    weather() { this.chooseAction(true) },
    phase() { this.chooseAction(true) },
    event() { this.chooseAction(true) },
    activity() { this.chooseAction(false) },
  },
  mounted() {
    if (window.innerWidth >= 1100) this.x = 94
    this.showLabel(true)
    this.showCare()
    this.chooseAction(true)
    this.idleTimer = setInterval(() => this.chooseAction(false), 12000)
    this.wanderTimer = setInterval(() => this.wander(), 7600)
  },
  beforeUnmount() {
    clearInterval(this.idleTimer)
    clearInterval(this.wanderTimer)
    clearTimeout(this.speechTimer)
    clearTimeout(this.labelTimer)
    clearTimeout(this.careTimer)
  },
  methods: {
    showLabel(hint = false, ms = 3000) {
      this.labelVisible = true
      this.labelHint = hint
      clearTimeout(this.labelTimer)
      this.labelTimer = setTimeout(() => { this.labelVisible = false }, ms)
    },
    showCare(ms = 3000) {
      this.careVisible = true
      clearTimeout(this.careTimer)
      this.careTimer = setTimeout(() => { this.careVisible = false }, ms)
    },
    setSpeech(text, ms = 4200) {
      if (!text) return
      this.speech = text
      this.speechUntil = Date.now() + ms
      clearTimeout(this.speechTimer)
      this.speechTimer = setTimeout(() => { this.speech = '' }, ms)
    },
    keywordAction() {
      const item = this.nextItem || {}
      const text = `${item.title || ''} ${item.intent || ''} ${this.activity || ''}`
      if (/睡|梦|午休|休息/.test(text)) return 'sleep'
      if (/书|阅读|读|学习|复习/.test(text)) return 'read'
      if (/咖啡|吃|餐|食|甜点|喝/.test(text)) return 'eat'
      if (/工作|专注|写|整理|开会|做事/.test(text)) return 'work'
      if (/音乐|听歌|耳机|散步|出门|走|逛/.test(text)) return 'walk'
      return ''
    },
    chooseAction(force) {
      if (this.dragging || this.lift > 0 || Date.now() < this.actionLockUntil) return
      if (this.phase === 'night') this.sleepiness = Math.min(4, this.sleepiness + 1)
      else this.sleepiness = 0
      if (this.event === 'imminent') {
        this.setAction('run', this.speechFor('run'))
        return
      }
      if (this.event === 'live') {
        this.setAction('work', this.speechFor('work'))
        return
      }
      if (this.weather === 'rain') {
        this.setAction('umbrella', this.speechFor('umbrella'))
        return
      }
      if (this.weather === 'snow') {
        this.setAction('scarf', this.speechFor('scarf'))
        return
      }
      const keyword = this.keywordAction()
      if (keyword) {
        this.setAction(keyword, this.speechFor(keyword))
        return
      }
      if (this.phase === 'night' && this.sleepiness > 1) {
        this.setAction('sleep', this.speechFor('sleep'))
        return
      }
      if (force) this.setAction(this.pickIdle(), this.speechFor(this.action))
      else this.action = this.pickIdle()
    },
    pickIdle() {
      const list = ['idle', 'look', 'stretch', 'dance', 'phone', 'walk']
      return list[Math.floor(Math.random() * list.length)]
    },
    setAction(action, text) {
      const changed = this.action !== action
      this.action = action
      if (changed) { this.showLabel(true); if (text) this.setSpeech(text) }
    },
    speechFor(action) {
      const lines = VOICE[this.variant]?.[action]
      if (lines?.length) return lines[Math.floor(Math.random() * lines.length)]
      return ({
        read: '这一页刚好看到喜欢的地方。', eat: '先认真吃一点东西。', work: '我先安静陪你一会儿。',
        walk: '去窗边走走，顺便看看天气。', phone: '刚好看到一张很想给你看的图。',
        music: '耳机分你一只。', sleep: '我眯一小会儿，有事叫我。', idle: '我在。',
        look: '今天的城市看起来有点不一样。', stretch: '伸个懒腰，再继续。', dance: '心情不错，跳两下。',
      })[action] || '我在。'
    },
    wander() {
      if (this.dragging || this.lift > 0 || this.panel || this.event === 'imminent') return
      if (!['idle', 'look', 'walk', 'phone'].includes(this.action)) return
      let next = window.innerWidth >= 1100 ? 64 + Math.random() * 24 : 20 + Math.random() * 58
      if (Math.abs(next - this.x) < 12) next = next > this.x ? Math.min(94, this.x + 16) : Math.max(16, this.x - 16)
      this.facing = next > this.x ? 1 : -1
      this.x = next
      if (Math.random() > 0.45) this.setAction('walk', '')
      setTimeout(() => { if (this.action === 'walk') this.action = 'idle' }, 2800)
    },
    pat() {
      if (this.dragging || this.suppressClick || this.lift > 0) return
      this.showLabel(false)
      this.showCare()
      this.hearts = 4
      this.mood = Math.min(100, this.mood + 2)
      this.action = 'happy'
      this.setSpeech(this.speechFor('pat'))
      setTimeout(() => { this.hearts = 0 }, 900)
      setTimeout(() => { if (this.action === 'happy') this.action = 'idle' }, 1400)
    },
    feed() {
      this.fullness = Math.min(100, this.fullness + 10)
      this.setAction('eat', '谢谢，我会好好吃完的。')
      this.panel = false
    },
    talk() {
      this.setAction('phone', '你说，我在听。')
      this.panel = false
    },
    rest() {
      this.setAction('sleep', '好，我靠着你休息一会儿。')
      this.panel = false
    },
    startDrag(event) {
      const shell = this.$el.closest('.app-shell') || this.$el.parentElement
      const rect = shell.getBoundingClientRect()
      const startedAt = performance.now()
      this.dragging = false
      this.moved = false
      this.dragStart = event.clientX
      this.dragStartY = event.clientY
      this.dragOrigin = this.x
      this.dragLift = this.lift
      clearTimeout(this.holdTimer)
      this.holdTimer = setTimeout(() => {
        if (!this.moved) {
          this.dragging = true
          this.setAction('held', '哇，放我下来。')
        }
      }, 220)
      const move = (e) => {
        const dx = e.clientX - this.dragStart
        const dy = e.clientY - this.dragStartY
        if (Math.abs(dx) > 4 || Math.abs(dy) > 4) this.moved = true
        if (!this.moved) return
        this.dragging = true
        this.x = Math.max(7, Math.min(94, this.dragOrigin + dx / rect.width * 100))
        this.lift = Math.max(0, Math.min(300, this.dragLift - dy))
        this.facing = dx > 0 ? 1 : -1
        if (this.lift > 8) this.setAction('held', '我会抓紧你的。')
      }
      const up = () => {
        clearTimeout(this.holdTimer)
        window.removeEventListener('pointermove', move)
        window.removeEventListener('pointerup', up)
        const heldLong = performance.now() - startedAt > 220
        const flew = this.lift > 36
        this.dragging = false
        if (flew) {
          this.suppressClick = true
          this.actionLockUntil = Date.now() + 2400
          this.setAction('thrown', '哇——我要飞起来了！')
          setTimeout(() => { this.lift = 0; this.setAction('land', '安全着陆。'); this.mood = Math.min(100, this.mood + 1) }, 420)
          setTimeout(() => { this.setAction('dizzy', '世界还在转……') }, 820)
          setTimeout(() => { if (this.action === 'dizzy') this.action = 'idle' }, 2100)
        } else if (this.moved || heldLong) {
          this.suppressClick = true
          this.lift = 0
          this.setAction('land', '放我下来啦。')
          setTimeout(() => { if (this.action === 'land') this.action = 'idle' }, 900)
        } else {
          this.lift = 0
        }
        setTimeout(() => { this.suppressClick = false }, 260)
      }
      window.addEventListener('pointermove', move)
      window.addEventListener('pointerup', up)
    },
    openPanel() {
      this.panel = !this.panel
      this.showCare()
      if (this.panel) { this.showLabel(false); this.setSpeech('', 0) }
    },
  },
  template: `
  <div class="pet-companion" :class="[petClass, 'pet-action-' + action, { 'pet-large': large, 'pet-panel-open': panel, 'pet-left': x < 45, 'pet-dragging': dragging }]" :style="petStyle">
    <transition name="pet-bubble">
      <div v-if="speech" class="pet-bubble" @click="openPanel">{{ speech }}<i></i></div>
    </transition>
    <div class="pet-hearts" v-if="hearts"><span v-for="n in hearts" :key="n" :style="{left:(n*6-6)+'px', animationDelay:(n*.07)+'s'}"></span></div>
    <div class="pet-umbrella" v-if="isUmbrella"><i></i><b></b></div>
    <div class="pet-scarf" aria-hidden="true"></div>
    <button class="pet-hit" @click="pat" @pointerdown="startDrag" aria-label="摸摸像素伙伴">
      <span class="pet-shadow"></span>
      <span class="pet-figure">
        <span class="pet-sprite" :style="{ backgroundImage: 'url(' + sprite + ')' }"></span>
        <span class="pet-prop-book" v-if="isBook"><i></i><i></i></span>
        <span class="pet-prop-phone" v-if="isPhone"><i></i></span>
        <span class="pet-prop-cup" v-if="isCup"></span>
        <span class="pet-prop-laptop" v-if="isWork"><i></i></span>
        <span class="pet-notes" v-if="isMusic"><b></b><b></b></span>
        <span class="pet-zzz" v-if="isSleep"><b>Z</b><b>z</b></span>
      </span>
    </button>
    <span v-if="labelVisible" class="pet-shadow-label">{{ label }}<template v-if="labelHint"> · 可拖动</template></span>
    <button v-if="careVisible || panel" class="pet-care-toggle" @click="openPanel" :aria-expanded="panel" aria-label="打开陪伴面板"><span></span><span></span></button>
    <transition name="pet-panel">
      <div v-if="panel" class="pet-panel">
        <div class="pet-panel-head"><span>陪伴模式 / PET</span><button @click="panel = false" aria-label="关闭">×</button></div>
        <strong>{{ statusLine }}</strong>
        <p>她会读懂下一项日程、关键词和天气。按住可以拖拽、提起或丢下，也会自己散步和打盹。</p>
        <div class="pet-meters"><label>饱腹 <i><b :style="{width:fullness+'%'}"></b></i></label><label>心情 <i><b :style="{width:mood+'%'}"></b></i></label></div>
        <div class="pet-buttons"><button @click="pat">摸摸</button><button @click="feed">投喂</button><button @click="talk">聊天</button><button @click="rest">休息</button></div>
      </div>
    </transition>
  </div>`,
}
