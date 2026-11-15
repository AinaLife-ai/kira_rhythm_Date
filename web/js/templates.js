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
  { id: 'lacrimosa_dusk', name: '夜巡', description: '黑白双马尾与番茄红霓虹的夜行', color: '#e0526e', mode: 'dark', art: 'lacrimosa', tone: 'lacrimosa' },
  { id: 'lacrimosa_dream', name: '玻璃花房', description: '紫蓝晨光与玻璃温室里的短暂休息', color: '#a980ff', mode: 'dark', art: 'lacrimosa_dream', tone: 'dream' },
  { id: 'mint_morning', name: '晨风', description: '青绿猫耳与清晨玻璃露台', color: '#45b99b', mode: 'light', art: 'mint', tone: 'mint' },
  { id: 'mint_soda', name: '海盐苏打', description: '正午海岸、条纹遮阳棚与气泡汽水', color: '#49a9b9', mode: 'light', art: 'mint_soda', tone: 'soda' },
  { id: 'crimson_sunset', name: '赤色晚照', description: '雨后晚霞与赤色城市锋芒', color: '#c7444c', mode: 'dark', art: 'crimson', tone: 'crimson' },
  { id: 'crimson_rain', name: '蓝调雨夜', description: '深蓝雨夜中的绯红倒影', color: '#9d3f66', mode: 'dark', art: 'crimson_rain', tone: 'rain' },
  { id: 'lacrimosa_noir', name: '黑曜档案', description: '冷银地下档案库与猩红应急灯', color: '#c8cbe0', mode: 'dark', art: 'lacrimosa_noir', tone: 'noir' },
  { id: 'lacrimosa_rose', name: '蔷薇雨夜', description: '午夜屋顶花园与深红蔷薇', color: '#ff7898', mode: 'dark', art: 'lacrimosa_rose', tone: 'rose' },
  { id: 'mint_rain', name: '雨幕街角', description: '蓝绿雨幕、玻璃拱廊与湿地反光', color: '#72c5d0', mode: 'dark', art: 'mint_rain', tone: 'rainmint' },
  { id: 'mint_peach', name: '蜜桃午后', description: '奶油色客厅与轻柔的午后阳光', color: '#eaa38e', mode: 'light', art: 'mint_peach', tone: 'peach' },
  { id: 'crimson_night', name: '午夜泳池', description: '深蓝水面与城市远灯', color: '#ca5b88', mode: 'dark', art: 'crimson_night', tone: 'night' },
  { id: 'crimson_ember', name: '余烬天桥', description: '琥珀烟尘与工业天桥的晚风', color: '#e89b59', mode: 'dark', art: 'crimson_ember', tone: 'ember' },
  { id: 'kira_mist', name: '雾紫', description: '柔雾纸张与安静微光', color: '#9b8cff', mode: 'dark', art: '', customArt: 'themes/mist.webp', pixel: 'mist', tone: 'mist' },
  { id: 'city_night', name: '雨夜通勤', description: '青色光轨穿过霓虹高架与雨巷', color: '#ff3d7f', mode: 'dark', art: '', customArt: 'scenes/night.webp', pixel: 'lacrimosa', tone: 'city' },
  { id: 'city_dusk', name: '黄昏轻轨', description: '雨后晚霞压在轻轨与旧楼上', color: '#ff7a59', mode: 'dark', art: '', customArt: 'scenes/dusk.webp', pixel: 'crimson', tone: 'ember' },
  { id: 'city_day', name: '白昼林荫', description: '玻璃塔楼与树影之间的清醒日常', color: '#48d8d1', mode: 'dark', art: '', customArt: 'scenes/day.webp', pixel: 'mint', tone: 'day' },
]
