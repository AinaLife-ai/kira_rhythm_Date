export const planTemplates = [
  {
    id: 'gentle_workday', name: '从容工作日', icon: 'cloud', tone: 'violet',
    description: '专注、留白和一点生活中的联系，不把时间表塞满。',
    plan: {
      title: '从容工作日', overview: '上午专注一点，午后留白，夜里给自己安静收尾。',
      planned_appearance: '柔软针织衫和舒适长裤，外面带一件轻便外套',
      planned_mood: '有些忙碌，但希望保持从容',
      blocks: [
        { title: '早晨', items: [
          { title: '醒来后的一点联系', intent: '让今天有一个连续的起点', instruction: '自然地问候，也可以只说今天想做的一点小事。', schedule: { type: 'window', start: '08:20', end: '09:00' }, interaction: 'auto', target: '' },
          { title: '安静阅读', intent: '在忙碌前保留自己的空间', instruction: '安静阅读并整理一点想法，不必发言。', schedule: { type: 'exact', at: '10:00' }, interaction: 'silent', target: '' },
        ] },
        { title: '傍晚与夜里', items: [
          { title: '随意走走', intent: '换一换节奏', instruction: '感受天气和周围的事物，有想分享的再说，没有也可以安静。', schedule: { type: 'window', start: '18:00', end: '19:00' }, execution_probability: 0.8, interaction: 'auto', target: '' },
          { title: '整理今天', intent: '让今天完整地收尾', instruction: '回顾今天真正值得记住的一点，必要时更新 DayState。', schedule: { type: 'exact', at: '22:20' }, interaction: 'auto', target: '' },
        ] },
      ],
    },
  },
  {
    id: 'dreamer', name: '梦境与分享', icon: 'moon', tone: 'night',
    description: '夜间安静做梦，醒后自由选择是否分享。',
    plan: {
      title: '有梦的一天', overview: '给夜里的想象留位置，也给醒来的分享留选择。',
      planned_appearance: '舒适的居家服', planned_mood: '平静而困倦',
      blocks: [
        { title: '夜间', items: [
          { title: '做一个梦', intent: '让想象在安静时自由发生', instruction: '做一场梦，用 rhythm_update 的 record_experience 留下梦境，然后输出 <msg/>。', schedule: { type: 'window', start: '02:00', end: '03:30' }, interaction: 'silent', category: 'dream', target: '' },
          { title: '梦后分享', intent: '把有意义的片段带回来', instruction: '读取今天的梦境 Experience，选择值得分享的部分，也可以保留为秘密。', schedule: { type: 'exact', at: '08:40' }, interaction: 'auto', category: 'dream', target: '' },
        ] },
      ],
    },
  },
  {
    id: 'slow_holiday', name: '慢生活假日', icon: 'flower', tone: 'green',
    description: '天气、散步、阅读和随心所欲的陪伴。',
    plan: {
      title: '慢生活假日', overview: '没有必须完成的清单，跟随天气和心情慢慢生活。',
      planned_appearance: '方便出门的休闲装和一顶帽子', planned_mood: '松弛，期待一点偶然',
      blocks: [
        { title: '白天', items: [
          { title: '看看天气再出门', intent: '让真实或虚拟天气参与生活', instruction: '结合当前天气随意走走，分享偶然注意到的事物。', schedule: { type: 'window', start: '10:00', end: '11:30' }, interaction: 'auto', target: '' },
          { title: '自由阅读', intent: '给思维留白', instruction: '安静阅读，不必发言。', schedule: { type: 'exact', at: '15:00' }, interaction: 'silent', target: '' },
          { title: '随便聊聊', intent: '让陪伴自然发生', instruction: '找一个轻松的话题自然交流，不提及定时任务。', schedule: { type: 'window', start: '19:30', end: '21:00' }, interaction: 'auto', target: '' },
        ] },
      ],
    },
  },
]

export const themeTemplates = [
  { id: 'tomato_rain', name: '番茄 · 霓虹雨', description: '黑白双马尾，穿过雨夜霓虹的快步', color: '#ff3f6e', mode: 'dark', art: 'tomato_rain', character: 'tomato', tone: 'tomato' },
  { id: 'tomato_greenhouse', name: '番茄 · 玻璃花房', description: '玻璃温室里，难得的安静坐一会儿', color: '#b990ff', mode: 'dark', art: 'tomato_greenhouse', character: 'tomato', tone: 'dream' },
  { id: 'tomato_archive', name: '番茄 · 黑曜档案', description: '冷灰档案库，倚墙回望的红衣', color: '#d34b5c', mode: 'dark', art: 'tomato_archive', character: 'tomato', tone: 'noir' },
  { id: 'mint_coast', name: '薄荷 · 晨风', description: '海边伸懒腰，青色尾巴扫过晨光', color: '#59d3b7', mode: 'dark', art: 'mint_coast', character: 'mint', tone: 'mint' },
  { id: 'mint_soda', name: '薄荷 · 苏打', description: '午后吧台，一瓶冒着冷气的苏打水', color: '#e8b85e', mode: 'dark', art: 'mint_soda', character: 'mint', tone: 'soda' },
  { id: 'mint_arcade', name: '薄荷 · 雨廊', description: '玻璃拱廊的雨声，透明伞和青绿倒影', color: '#57d9d0', mode: 'dark', art: 'mint_arcade', character: 'mint', tone: 'rainmint' },
  { id: 'garnet_dusk', name: '石榴 · 赤色晚照', description: '天台晚风，红发与黑色长风衣', color: '#ff974d', mode: 'dark', art: 'garnet_dusk', character: 'garnet', tone: 'crimson' },
  { id: 'garnet_alley', name: '石榴 · 蓝调雨巷', description: '雨巷里低头看手机，霓虹落在侧脸', color: '#5fb4ff', mode: 'dark', art: 'garnet_alley', character: 'garnet', tone: 'rain' },
  { id: 'garnet_pool', name: '石榴 · 午夜泳池', description: '池边坐着，城市灯光沉进水里', color: '#4de2d8', mode: 'dark', art: 'garnet_pool', character: 'garnet', tone: 'night' },
  { id: 'xun_street', name: '老板娘 · 雨市', description: '红伞、灯笼和湿润的夜街', color: '#ff4f6d', mode: 'dark', art: 'xun_street', character: 'xun', tone: 'city' },
  { id: 'xun_diner', name: '老板娘 · 深夜食堂', description: '收伞坐下，热汤和深夜的暖光', color: '#ffc06a', mode: 'dark', art: 'xun_diner', character: 'xun', tone: 'ember' },
  { id: 'xun_rooftop', name: '老板娘 · 天台', description: '紫蓝暮色里，红伞撑开一小片安静', color: '#b38bff', mode: 'dark', art: 'xun_rooftop', character: 'xun', tone: 'dusk' },
  { id: 'hathor_garage', name: '哈索尔 · 夜行', description: '地下车库，机车与白色机械翼', color: '#58e1d1', mode: 'dark', art: 'hathor_garage', character: 'hathor', tone: 'garage' },
  { id: 'hathor_roof', name: '哈索尔 · 天台巡航', description: '雨夜天台，蹲在边缘观察城市', color: '#64b8ff', mode: 'dark', art: 'hathor_roof', character: 'hathor', tone: 'sky' },
  { id: 'hathor_store', name: '哈索尔 · 便利店', description: '玻璃便利店外，一罐热咖啡', color: '#7bffd1', mode: 'dark', art: 'hathor_store', character: 'hathor', tone: 'store' },
]
