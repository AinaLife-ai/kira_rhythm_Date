const VOICE = {
  tomato: {
    idle: ['番茄，最好了。', '今天也不想动……'],
    look: ['那边红红的，是番茄吗？', '城市好吵，但还可以。'],
    stretch: ['伸个懒腰，番茄不会掉。', '骨头在响。'],
    dance: ['番茄也会跳舞吗？', '只跳一下。'],
    phone: ['红红的图标，像番茄。', '消息好多，不想回。'],
    sleep: ['番茄城堡……先睡一下。', '三分钟，再睡三分钟。'],
    read: ['这一页有番茄的味道。', '读完就睡。'],
    eat: ['番茄酱是我的。', '这个可以蘸番茄吗？'],
    work: ['好麻烦……但会做完。', '别催，我在想。'],
    music: ['耳机里的歌很轻。', '番茄也在听。'],
    umbrella: ['伞往我这边一点。', '雨会把番茄打湿。'],
    scarf: ['围巾像番茄酱的颜色。', '暖和。'],
    run: ['要出发了吗？', '番茄跟上。'],
    pat: ['摸头可以，番茄不能拿走。', '再摸一下也可以。'],
    held: ['放我下来，番茄要掉了。', '我抓着你的袖子。'],
    thrown: ['不要转圈。', '我会飞吗？'],
    land: ['番茄安全着陆。', '脚先落地。'],
    dizzy: ['番茄在晃。', '世界转得慢一点。'],
    default: ['番茄在这里。', '……嗯。'],
  },
  mint: {
    idle: ['今天也精神满满。', '尾巴自己动了。'],
    look: ['海风的方向在那边。', '那家店在卖什么？'],
    stretch: ['喵——伸展开。', '尾巴也要伸。'],
    dance: ['这个节拍不错。', '跟着跳两下。'],
    phone: ['有人发了新消息。', '这张图好可爱。'],
    sleep: ['尾巴借你当抱枕。', '睡一小会儿。'],
    read: ['这本讲海边的故事。', '看完就去散步。'],
    eat: ['苏打气泡在跳。', '这个甜甜的。'],
    work: ['先把这件事做好。', '做完就去玩。'],
    music: ['耳机分你一只。', '这个歌单很适合海边。'],
    umbrella: ['雨落在伞上，好好听。', '靠近一点。'],
    scarf: ['围巾毛茸茸的。', '尾巴也想围。'],
    run: ['要追上去吗？', '我跑得很快。'],
    pat: ['耳朵不能一直摸……', '再摸一下。'],
    held: ['我的尾巴！', '轻一点。'],
    thrown: ['好高。', '我会不会飞起来？'],
    land: ['稳稳落地。', '猫是这样落地的。'],
    dizzy: ['世界在打转。', '尾巴找不到方向了。'],
    default: ['薄荷在这里。', '喵。'],
  },
  garnet: {
    idle: ['风有点大。', '别站太近。'],
    look: ['云压得很低。', '那边有人。'],
    stretch: ['肩膀有点僵。', '活动一下。'],
    dance: ['不跳。', '……只一下。'],
    phone: ['等我回个消息。', '看到一点有用的。'],
    sleep: ['闭目养神。', '别吵。'],
    read: ['这页写得还行。', '再翻一页。'],
    eat: ['先吃饭。', '别浪费。'],
    work: ['先把事情做完。', '专注一会儿。'],
    music: ['这首歌可以。', '音量小一点。'],
    umbrella: ['雨比预想的大。', '伞够用。'],
    scarf: ['风很冷。', '围巾正好。'],
    run: ['我先过去。', '别掉队。'],
    pat: ['只准一下。', '手拿开。'],
    held: ['放我下来。', '别拎衣领。'],
    thrown: ['别扔。', '我鞋跟很高。'],
    land: ['落地了。', '下次别这样。'],
    dizzy: ['……有点晕。', '站稳。'],
    default: ['我在。', '有事说。'],
  },
  xun: {
    idle: ['店面今天照常营业。', '茶还热着。'],
    look: ['这条街，我熟。', '灯笼亮得早。'],
    stretch: ['年纪大了，要活动。', '肩颈。'],
    dance: ['年轻时倒是常跳。', '看心情。'],
    phone: ['客人来消息了。', '等我回一下。'],
    sleep: ['打烊前小睡。', '别把客人吵醒。'],
    read: ['旧账本，翻一翻。', '这页记着旧城。'],
    eat: ['坐下，先吃点热的。', '汤要趁热。'],
    work: ['今天账还没对。', '做完就收摊。'],
    music: ['留声机还能转。', '这首听过。'],
    umbrella: ['雨大，站进来。', '红伞够两个人。'],
    scarf: ['夜里凉。', '披上。'],
    run: ['要出门？', '伞带上。'],
    pat: ['老板娘可不是随便摸的。', '……下不为例。'],
    held: ['放我下来。', '衣服会皱。'],
    thrown: ['别闹。', '这把伞会掉。'],
    land: ['站稳了。', '毛手毛脚。'],
    dizzy: ['老了，经不起转。', '缓一缓。'],
    default: ['客人，慢慢看。', '我在店里。'],
  },
  hathor: {
    idle: ['今天也照常配送。', '路线确认。'],
    look: ['目标在那边。', '城市的路我熟。'],
    stretch: ['翅膀有点僵。', '活动一下。'],
    dance: ['不跳，影响配送。', '……节拍还行。'],
    phone: ['新单。', '等我确认地址。'],
    sleep: ['闭眼十分钟。', '别超时。'],
    read: ['配送条例。', '这页有必要看。'],
    eat: ['先补充能量。', '咖啡就好。'],
    work: ['按路线执行。', '目标出现。'],
    music: ['头盔里放点歌。', '这首适合夜路。'],
    umbrella: ['雨会影响能见度。', '伞给你。'],
    scarf: ['夜风很冷。', '围巾不影响行动。'],
    run: ['目标出现，开始行动。', '我先过去，你跟上。'],
    pat: ['翅膀不可以乱碰。', '只准一下。'],
    held: ['放我下来，还有单。', '别抓翅膀。'],
    thrown: ['这不安全。', '我在赶时间。'],
    land: ['落地稳定。', '下次别扔。'],
    dizzy: ['路线在转。', '重新校准。'],
    default: ['天使，随时出发。', '收到。'],
  },
}


const VOICE_TAILS = {
  tomato: ['番茄记住了', '番茄城堡今天也开着', '番茄酱要留一点', '再等一下下', '番茄在这里', '今天慢慢来'],
  mint: ['尾巴说好', '海风刚好', '猫耳朵听见了', '气泡还在跳', '今天也精神满满', '再来一次'],
  garnet: ['风有点大', '就这样', '我在听', '别靠太近', '这件事记下了', '稳住'],
  xun: ['茶还热着', '店里照常', '慢慢来', '我记下了', '雨还没停', '客人先请'],
  hathor: ['路线确认', '收到', '时间刚好', '目标不变', '注意安全', '我在赶路'],
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
    poses: { type: Object, default: () => ({}) },
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
      walkTimer: null,
      walking: false,
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
    currentSprite() {
      if (this.action === 'sleep') return this.poses.sleep || this.sprite
      if (['read'].includes(this.action)) return this.poses.sit || this.sprite
      if (['phone'].includes(this.action)) return this.poses.phone || this.sprite
      return this.poses.idle || this.sprite
    },
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
    if (window.innerWidth >= 1100) this.x = 90
    this.showLabel(true)
    this.showCare()
    this.chooseAction(true)
    this.idleTimer = setInterval(() => this.chooseAction(false), 12000)
  },
  beforeUnmount() {
    clearInterval(this.idleTimer)
    clearInterval(this.wanderTimer)
    clearTimeout(this.walkTimer)
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
      if (/音乐|听歌|耳机/.test(text)) return 'music'
      if (/散步|出门|走|逛/.test(text)) return 'look'
      return ''
    },
    chooseAction(force) {
      if (this.dragging || Date.now() < this.actionLockUntil) return
      if (this.walking && !['walk', 'run'].includes(this.action)) this.stopWalking()
      if (this.phase === 'night') this.sleepiness = Math.min(4, this.sleepiness + 1)
      else this.sleepiness = 0
      if (this.event === 'imminent') {
        this.setAction('look', this.speechFor('run'))
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
      const idle = this.pickIdle()
      if (force) this.setAction(idle, this.speechFor(idle))
      else this.action = idle
    },
    pickIdle() {
      const list = ['idle', 'look', 'stretch', 'dance', 'phone', 'sleep']
      return list[Math.floor(Math.random() * list.length)]
    },
    setAction(action, text) {
      const changed = this.action !== action
      this.action = action
      if (changed) { this.showLabel(true); if (text) this.setSpeech(text) }
    },
    speechFor(action) {
      const base = VOICE[this.variant]?.[action] || VOICE[this.variant]?.default || ['我在']
      const tails = VOICE_TAILS[this.variant] || []
      const variants = [...base]
      for (let i = 0; i < Math.min(6, tails.length); i += 1) {
        variants.push(`${base[i % base.length].replace(/[。！？]$/, '')}，${tails[i]}`)
      }
      const line = variants[Math.floor(Math.random() * variants.length)]
      return line.replace(/。$/, '')
    },
    stopWalking() {
      clearTimeout(this.walkTimer)
      this.walkTimer = null
      this.walking = false
    },
    nextWalkTarget() {
      let next = window.innerWidth >= 1100 ? 64 + Math.random() * 24 : 20 + Math.random() * 58
      if (Math.abs(next - this.x) < 12) next = next > this.x ? Math.min(94, this.x + 16) : Math.max(16, this.x - 16)
      return next
    },
    wander() {
      if (this.dragging || this.walking || this.lift > 0 || this.panel || this.event === 'imminent') return
      if (!['idle', 'look', 'phone', 'walk'].includes(this.action)) return
      this.startWalking(this.nextWalkTarget())
    },
    startWalking(target) {
      const shell = this.$el.closest('.app-shell') || this.$el.parentElement
      const width = Math.max(260, shell?.getBoundingClientRect().width || window.innerWidth)
      this.stopWalking()
      this.walking = true
      this.lift = 0
      this.facing = target > this.x ? 1 : -1
      this.action = 'walk'
      const step = () => {
        if (!this.walking || this.dragging) { this.walking = false; this.walkTimer = null; return }
        const diff = target - this.x
        if (Math.abs(diff) < 0.35) {
          this.x = target
          this.walking = false
          this.walkTimer = null
          this.action = 'idle'
          return
        }
        const stepPct = (1.7 / width) * 100
        this.x += Math.sign(diff) * Math.min(Math.abs(diff), stepPct)
        this.walkTimer = setTimeout(step, 40)
      }
      step()
    },
    pat() {
      if (this.dragging || this.suppressClick) return
      this.stopWalking()
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
      this.stopWalking()
      this.fullness = Math.min(100, this.fullness + 10)
      this.setAction('eat', this.speechFor('eat'))
      this.panel = false
    },
    talk() {
      this.stopWalking()
      this.setAction('phone', this.speechFor('phone'))
      this.panel = false
    },
    rest() {
      this.stopWalking()
      this.setAction('sleep', this.speechFor('sleep'))
      this.panel = false
    },
    startDrag(event) {
      this.stopWalking()
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
          this.setAction('held', this.speechFor('held'))
        }
      }, 220)
      const move = (e) => {
        const dx = e.clientX - this.dragStart
        const dy = e.clientY - this.dragStartY
        if (Math.abs(dx) > 4 || Math.abs(dy) > 4) this.moved = true
        if (!this.moved) return
        this.dragging = true
        const maxX = window.innerWidth < 700 ? 79 : 90
        this.x = Math.max(7, Math.min(maxX, this.dragOrigin + dx / rect.width * 100))
        this.lift = Math.max(0, Math.min(300, this.dragLift - dy))
        this.facing = dx > 0 ? 1 : -1
        if (this.lift > 8) this.setAction('held', this.speechFor('held'))
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
          this.setAction('thrown', this.speechFor('thrown'))
          setTimeout(() => { this.lift = 10 + Math.random() * 34; this.setAction('land', this.speechFor('land')); this.mood = Math.min(100, this.mood + 1) }, 420)
          setTimeout(() => { this.setAction('dizzy', this.speechFor('dizzy')) }, 820)
          setTimeout(() => { if (this.action === 'dizzy') this.action = 'idle' }, 2100)
        } else if (this.moved || heldLong) {
          this.suppressClick = true
          this.lift = this.lift > 6 ? 8 + Math.random() * 20 : 0
          this.setAction('land', this.speechFor('land'))
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
  <div class="pet-companion" :class="[petClass, 'pet-action-' + action, { 'pet-large': large, 'pet-panel-open': panel, 'pet-left': x < 45, 'pet-dragging': dragging, 'pet-facing-left': facing < 0 }]" :style="petStyle">
    <transition name="pet-bubble">
      <div v-if="speech" class="pet-bubble" @click="openPanel">{{ speech }}<i></i></div>
    </transition>
    <div class="pet-hearts" v-if="hearts"><span v-for="n in hearts" :key="n" :style="{left:(n*6-6)+'px', animationDelay:(n*.07)+'s'}"></span></div>
    <div class="pet-umbrella" v-if="isUmbrella"><i></i><b></b></div>
    <div class="pet-scarf" aria-hidden="true"></div>
    <button class="pet-hit" @click="pat" @pointerdown="startDrag" aria-label="摸摸像素伙伴">
      <span class="pet-shadow"></span>
      <span class="pet-figure">
        <img class="pet-sprite" :src="currentSprite" alt="">
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
