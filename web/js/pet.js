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
    this.chooseAction(true)
    this.idleTimer = setInterval(() => this.chooseAction(false), 12000)
    this.wanderTimer = setInterval(() => this.wander(), 7600)
  },
  beforeUnmount() {
    clearInterval(this.idleTimer)
    clearInterval(this.wanderTimer)
    clearTimeout(this.speechTimer)
  },
  methods: {
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
        this.setAction('run', '还有一点时间，要出发了。')
        return
      }
      if (this.event === 'live') {
        this.setAction('work', '正在陪你经历这一小段。')
        return
      }
      if (this.weather === 'rain') {
        this.setAction('umbrella', '下雨了，我带了伞。')
        return
      }
      if (this.weather === 'snow') {
        this.setAction('scarf', '下雪了，围巾分你一半。')
        return
      }
      const keyword = this.keywordAction()
      if (keyword) {
        this.setAction(keyword, this.speechFor(keyword))
        return
      }
      if (this.phase === 'night' && this.sleepiness > 1) {
        this.setAction('sleep', '夜深了，我在这里睡一会儿。')
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
      if (changed && text) this.setSpeech(text)
    },
    speechFor(action) {
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
      const next = window.innerWidth >= 1100 ? 86 + Math.random() * 8 : 20 + Math.random() * 58
      this.facing = next > this.x ? 1 : -1
      this.x = next
      if (Math.random() > 0.45) this.setAction('walk', '')
      setTimeout(() => { if (this.action === 'walk') this.action = 'idle' }, 2800)
    },
    pat() {
      if (this.dragging || this.suppressClick || this.lift > 0) return
      this.hearts = 4
      this.mood = Math.min(100, this.mood + 2)
      this.setAction('happy', ['再摸一下。', '今天也很喜欢你。', '嘿嘿，痒。', '我在听。'][Math.floor(Math.random() * 4)])
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
      if (this.panel) this.setSpeech('', 0)
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
      <svg class="pet-figure" viewBox="0 0 72 128" shape-rendering="crispEdges" aria-hidden="true">
        <g v-if="variant === 'mono'" class="pet-hair-back">
          <path d="M18 14h8V8h8V4h8v4h8v6h6v10h4v30h-6V36h-4v20h-5V30h-8v-5h-8v5h-8v26h-5V34h-4v24h-6V28h4z" fill="#1b1b23"/>
          <path d="M48 10h8v6h6v10h4v34h-7V32h-4v26h-5V30h-2z" fill="#f2ebe1"/>
        </g>
        <g v-else-if="variant === 'mint'" class="pet-hair-back">
          <path d="M18 22V8h8V4h20v4h8v14h4v20h-6V26h-4v12h-5V25H25v13h-5V26h-2z" fill="#45b99b"/>
          <path d="M20 9 24 0l5 10M45 10 50 0l5 10" fill="#45b99b"/>
          <path d="M56 66c9-5 12 4 8 10-2 4-7 6-9 2z" fill="#45b99b"/>
        </g>
        <g v-else class="pet-hair-back">
          <path d="M17 18V7h9V4h20v3h9v14h4v52h-7V31h-4v33h-5V28H29v29h-5V31h-3v39h-7V23z" fill="#a9243d"/>
          <path d="M17 25h4v34h-4zM51 27h4v36h-4z" fill="#7d172c"/>
        </g>

        <g class="pet-head">
          <rect x="23" y="17" width="26" height="21" rx="2" fill="#f6d6c8"/>
          <path d="M21 14h30v4H21zM21 18h6v8h-6zM45 18h6v8h-6z" fill="var(--pet-hair)"/>
          <rect x="27" y="26" width="3" height="5" fill="#2b2229"/><rect x="42" y="26" width="3" height="5" fill="#2b2229"/>
          <rect x="27" y="26" width="1" height="1" fill="#fff"/><rect x="42" y="26" width="1" height="1" fill="#fff"/>
          <rect x="24" y="30" width="4" height="2" fill="#e78b8e" opacity=".7"/><rect x="44" y="30" width="4" height="2" fill="#e78b8e" opacity=".7"/>
          <rect x="34" y="32" width="4" height="1" fill="#b66a72"/>
          <rect x="31" y="38" width="10" height="3" fill="#f6d6c8"/>
          <path v-if="variant === 'mint'" d="M21 19h10v3H21zM41 19h10v3H41z" fill="#fff" opacity=".5"/>
        </g>

        <g class="pet-arm pet-arm-left"><rect x="18" y="43" width="6" height="25" fill="var(--pet-jacket)"/><rect x="18" y="66" width="6" height="4" fill="#f6d6c8"/></g>
        <g class="pet-arm pet-arm-right"><rect x="48" y="43" width="6" height="25" fill="var(--pet-jacket)"/><rect x="48" y="66" width="6" height="4" fill="#f6d6c8"/></g>

        <g class="pet-body">
          <path d="M24 40h24v28H24z" fill="var(--pet-jacket)"/>
          <path d="M31 40h10v24H31z" fill="#f7f1e6"/>
          <path d="M35 41h2v21h-2z" fill="#c8bfd0" opacity=".55"/>
          <path d="M24 45h8v3h-8zM40 45h8v3h-8z" fill="var(--pet-jacket-dark)"/>
          <path v-if="variant === 'crimson'" d="M22 65h28v6H22zM18 69h8v24h-6V76h-2zM46 69h8v24h-6V76h-2z" fill="#181820"/>
          <path v-if="variant === 'mint'" d="M22 40h28v5H22zM22 63h28v4H22z" fill="#bce8d8" opacity=".55"/>
          <path d="M22 68h28l3 13H19z" fill="var(--pet-skirt)"/>
          <path d="M27 69h3v11h-3zM36 69h3v11h-3zM45 69h3v11h-3z" fill="var(--pet-skirt-dark)" opacity=".55"/>
          <path v-if="variant === 'mono'" d="M30 38h5v4h-5zM38 38h5v4h-5z" fill="#d94960"/>
          <path v-if="variant === 'mint'" d="M32 38h8v4h-8z" fill="#fff" opacity=".6"/>
        </g>

        <g class="pet-leg pet-leg-left"><rect x="26" y="81" width="7" height="24" fill="#f6d6c8"/><rect x="26" y="90" width="7" height="14" fill="var(--pet-sock)"/><rect x="23" y="112" width="11" height="4" fill="#1b1b21"/></g>
        <g class="pet-leg pet-leg-right"><rect x="39" y="81" width="7" height="24" fill="#f6d6c8"/><rect x="39" y="90" width="7" height="14" fill="var(--pet-sock)"/><rect x="38" y="112" width="11" height="4" fill="#1b1b21"/></g>

        <g v-if="isBook" class="pet-prop prop-book"><rect x="19" y="60" width="34" height="18" fill="#f3ead9"/><rect x="35" y="61" width="2" height="16" fill="#d9b6a6"/><rect x="23" y="64" width="10" height="2" fill="#8a6a83"/><rect x="23" y="68" width="8" height="2" fill="#8a6a83"/><rect x="40" y="64" width="9" height="2" fill="#8a6a83"/></g>
        <g v-if="isPhone" class="pet-prop prop-phone"><rect x="53" y="48" width="9" height="16" fill="#1c2430"/><rect x="54" y="50" width="7" height="12" fill="#72e8e1"/></g>
        <g v-if="isCup" class="pet-prop prop-cup"><rect x="50" y="57" width="9" height="12" fill="#f1d7b6"/><rect x="52" y="55" width="5" height="3" fill="#b57b57"/><rect x="58" y="60" width="4" height="2" fill="#f1d7b6"/></g>
        <g v-if="isWork" class="pet-prop prop-laptop"><rect x="17" y="63" width="38" height="5" fill="#7a838e"/><rect x="21" y="52" width="30" height="12" fill="#1c2530"/><rect x="23" y="54" width="26" height="8" fill="#82d8e0" opacity=".45"/></g>
        <g v-if="isMusic" class="pet-notes"><rect x="57" y="34" width="2" height="10" fill="#ffd25e"/><rect x="59" y="34" width="5" height="2" fill="#ffd25e"/><rect x="14" y="28" width="2" height="7" fill="#ffd25e"/><rect x="10" y="28" width="6" height="2" fill="#ffd25e"/></g>
        <g v-if="isSleep" class="pet-zzz"><text x="54" y="28">Z</text><text x="60" y="20">z</text></g>
      </svg>
    </button>
    <span class="pet-shadow-label">{{ label }} · 可拖动</span>
    <button class="pet-care-toggle" @click="openPanel" :aria-expanded="panel" aria-label="打开陪伴面板"><span></span><span></span></button>
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
