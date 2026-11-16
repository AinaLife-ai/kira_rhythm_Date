# KRD 验证记录

验证日期：2026-11-16（Asia/Shanghai）。

## 测试结论

| 范围 | 结果 |
|---|---|
| KiraAI 3.2.0-beta.1 领域/并发/调度/缓存/资源测试 | **100 passed** |
| KiraAI 3.1.2 同一套测试 | **100 passed** |
| 3.2 真实 PluginManager 生命周期 | 通过：3 工具、38 条鉴权 API/页面/静态路由、WS |
| 3.1.2 真实 PluginManager 生命周期 | 同上，通过 |
| 3.2 真实 IM 工作流 E2E | 通过：triggered、finalized、发送与历史边界 |
| 3.1.2 真实 IM 工作流 E2E | 同上，通过；含 `resolve_session` 特征回退 |
| Sustained Chat 最新 main 合批契约 | 通过：原 Message 引用与 extra 保留 |
| Default Chat Z 最新 main 合批契约 | 同上，通过 |
| 长期记忆 Z / 群日报 / 加速器边界 | 契约检查通过 |
| Python compileall + pyflakes | 0 错误 |
| 前端全部 JS `node --check` | 通过 |
| 发布契约审计 | 通过 |
| 浏览器桌面今日/日历/设置与手机布局 | 实际渲染通过 |

## 覆盖的回归点

- 精确时间、跨午夜窗口、DST 不存在时间、随机间隔容量。
- 概率跳过重载不重抽；认领幂等；正常响应与 `<msg/>` 分别落账。
- 用户 busy 不制造 missed；过期与结果不明状态分离。
- 人格切换不关闭旧人格 Run；每日状态与私有体验隔离。
- 日型提示词/配额覆盖；禁止执行、安静投递与必需覆盖分别生效。
- 多日原子回滚；同标题组不重复；已触发历史不可改写。
- 配置 revision 冲突返回 409；自定义模板、头像缓存和图片重编码。
- 动态日程上下文 `persist=False`；notice 短标记按框架默认持久。
- 无 CDN、无天气密钥进入前端、无 `auth=False`、无旧同步会话 API。

## 第二轮完整审计（v1.0.1）

本轮未使用子代理。除上述双版本测试外，执行了以下额外验收：

## 第三轮完整审计（v1.2.3 收尾，2026-11-16）

本轮同样未使用子代理，基于真实 PluginManager、真实 FastAPI HTTP/WS、真实 SQLite 和真实 Chromium 页面完成。

| 验收 | 真实结果 |
|---|---|
| 双版本全量 | KiraAI 3.1.2 / 3.2.0-beta.1 各 **100 passed**；真实 PluginManager、IM E2E、真实 HTTP API、100 项压力全部通过 |
| 行走移除 | `assets/pets/*_walk*.webp` 为 0；源码无 `pet-action-walk`/`pixel-walk`；散步、出门、运动等关键词只触发连续跳跃 |
| 运动中跳跃 | 真实页面连续 3–6 次跳跃，标签保持「运动中」，高度随机、横向仅小偏移、无走路位移 |
| 真实页面闭环 | uvicorn + 真实插件 API + SQLite 页面加载通过；真实浏览器 bootstrap、计划、DayState、主题读写、刷新按钮、WebSocket 均通过 |
| API 全路由探测 | 真实 HTTP 路由通过计划/日历/DayState/配置 revision/模板/资产上传与保护/导出导入/头像/诊断；缺失资产返回结构化错误 |
| WebSocket | 真实 WS ready、ping/pong、config_changed 均到达页面 |
| 刷新按钮 | 真实 API 响应过快时仍保证 ≥420ms 的刷新旋转可见窗口 |
| 响应式 | 1440px 桌面和 390px 手机五视图、五设置页签实际渲染；`scrollWidth == innerWidth`，零 JS 异常 |
| 单文件预览 | `KRD-1.2.3-preview.html` 零外部资源请求、零 JS 错误、启动和页面渲染正常 |
| 长稳 | 31 秒空闲 `data_version 2→2`、零新事件、调度器存活 |
| 头像占位 | 未设置或图片加载失败显示问号头像；上传成功后显示真实头像（`naturalWidth=40`） |
| 陪伴面板 | 使用真实日程：今日完成/总数、进度条、下一项标题/时间/倒计时；不再使用假饱腹/心情 |
| 时间精度 | 当前时间显示到秒；计划时间/日期在秒数非零时自动显示秒 |
| 秒级调度 | exact at、window start/end、规划时刻、禁止/安静/必需覆盖时段、随机间隔和检查间隔 `interval_seconds` 均实测；LLM 可读时间含秒，前端 `type=time step=1` |
| 图标与作者 | `manifest.json` author=`znq19`，icon=`assets/icon.svg`，文件存在且 SVG 可解析 |
| 3.1.2 会话兼容 | `SessionManager.get_sessions()` 无 `kind` 参数时无参读取并按 `dm/gm` 过滤；真实错误已复现并回归 |
| 模板/日型编辑 | 内置与自定义模板可编辑/覆盖/恢复默认；内置日型可保存规则、日期范围、规划/执行提示词，按钮不再触发 Vue 异常 |
| 深色下拉 | 天气/模式等 select option 使用深色背景与浅色文字，浏览器 computed style 验证 |
| 天气凭据 | Provider 切换显示对应字段；A/B 凭据分别保存并切换保留；保存后缓存失效，配置 API 不回传明文 |
| 城市搜索 | Open-Meteo “桂林”自动补“桂林市”，首条为广西桂林；重名显示国家/省/市/区；阳朔县无结果显示，QWeather GeoAPI 作为中国区县补充 |
| 规划目标 | 立即规划传当前选中日期；planning focus.date/reason 明确首要日期；LLM 顶层 items/entries 与扁平 at/start/end 自动归一化 |
| 日历/日型分离 | 日历事实与日型独立；普通农历不发给 bot；发送/显示开关分开；基础日型默认关闭 |
| 多日型 | 同日多个日型按优先级显示与拼接提示词；内置基础日型分区、默认关闭；空值不进入模型上下文 |
| 自定义日型开关 | 自定义日型可停用但保留记录；停用后不解析、不发送名称/提示词，可随时重新开启 |
| 紧凑上下文 | `scheduled_at` 改为短 `at`/必要时 `on`；day_types 合并字符串；移除动态 rules；短 item 引用 12 位；daily_limits 三处一致 |
| 工具 schema | `rhythm_plan` 仅暴露 plans[] + 扁平 items；无具体示例；框架工具注册通过 |
| 模板 | 结构化分组/小项编辑、图标预设/上传、预设模板分区折叠、按模板规划 |
| 头像/图标分离 | `icon.svg` 仅作插件图标并透明化；`avatar.svg` 为问号默认生活头像；WebUI 未设置/失败仍显示问号 |
| 缓存键 | 页面 HTML no-store；前端 API GET 请求使用 no-store；CSS/JS/内置资源带 `?v=1.2.3`；上传资产内容哈希 + immutable |
| 性能/token | 动态 Prompt 仍为尾部 persist=False；静态工具区稳定；首屏不等待 Remote 头像/天气；日历远程刷新后台化 |

真实页面验收使用 `TemporaryDirectory` 与测试人格/会话适配器，但业务数据、插件 API、SQLite 事务、WebSocket 与前端资源均为真实链路；不是业务 mock。

### 本轮外部服务边界


| 验收 | 真实结果 |
|---|---|
| 真实 HTTP API | 双版本通过 bootstrap、非法配置、DayState、计划、人格 diff 隔离、离线投递失败 |
| 生产前端 → 真实 API → SQLite | Chromium 无业务数据 mock：创建/修订/跳过、DayState、设置、日型、模板、上传均通过 |
| 重新进入持久化 | 计划 r3、DayState、配置 r4、头像与横幅均保持；图片实际 `naturalWidth=24` |
| 头像缓存 | 每次进入产生新 `entry`；`/avatar` 为 `no-store`，普通适配器读取使用缓存，进入时强制后台刷新 |
| 图片缓存 | 内容哈希 URL、`ETag`、WebP、`Cache-Control: private, max-age=31536000, immutable` |
| WebSocket | 真实服务诊断 `websocket_clients=1`，变更可到达页面 |
| 并发与原子性 | 同日创建/同版本修订单赢家；12 路规划去重；事务外读不到未提交数据；导入失败全回滚 |
| 100 项压力 | 两版 100/100 入队；保存约 52–99ms，整树读取约 2–3ms，100 项派发约 183–382ms |
| 31 秒空闲长稳 | 跨越人格检测周期；`data_version 2→2`、零新事件、调度器存活，无持续写入 |
| 桌面/手机全视图 | 五视图和五设置页签实际渲染，零 JS 异常；手机日历 6px 溢出已修复并复测 390px 全通过 |

真实浏览器验收还实际发现并修复了原有 mock 未暴露的问题：完整设置携带只读字段导致必败、月份锚生成 `YYYY-MM-DD-01`、模板应用后展示错误日期，以及保存后差异仍指向旧计划。对应静态发布契约已加入 `tests/audit_contract.py`。

### 本轮外部服务边界

尝试真实 Open-Meteo 时，沙箱直连超时、代理 TLS 失败，因此**不声称外部天气服务实测成功**。九 Provider 的解析代码、HTTP 状态检查、超时、缓存、陈旧回退与首屏/调度不等待网络均有本地测试；线上服务仍需按实际网络与账号验收。

## 重复执行

### 领域测试

```sh
cd /path/to/KiraAI
PYTHONPATH=/path/to/KiraAI:/path/to/kira_rhythm_Date \
  python3 -m pytest -q /path/to/kira_rhythm_Date/tests/test_*.py
```

### 真实框架加载

```sh
python3 tests/framework_smoke.py /path/to/KiraAI /path/to/kira_rhythm_Date
```

### 真实 IM 工作流 E2E

```sh
python3 tests/framework_e2e.py /path/to/KiraAI /path/to/kira_rhythm_Date
python3 tests/api_integration.py /path/to/KiraAI /path/to/kira_rhythm_Date
```

百项压力与 31 秒空闲长稳分别使用 `tests/stress_audit.py`、`tests/soak_audit.py`；`tests/run_all.sh` 默认包含双版本单元、真实框架、真实 HTTP API 与百项压力，长稳脚本单独运行以免拖慢每次提交。

### S/Z 与生态契约

`tests/ecosystem_contract.py` 接受 S、Z、长期记忆 Z、群日报、加速器的本地源码根目录。S/Z 测试使用其最新 `origin/main` 的真实 `queue_merge.py`，不是重新实现的假合并器。

### 发布审计

```sh
python3 tests/audit_contract.py .
python3 -m pyflakes main.py krd/*.py
for f in web/js/*.js; do node --check "$f" || exit 1; done
```

## 浏览器验收

`tests/web_fixture.js` 提供可重复的数据装置，用于桌面和移动端实际 Vue 渲染测试。预览页不随生产包保留；生产仅在带 `debug` 查询参数时暴露根实例用于诊断。

## 诚实边界

未使用真实用户 QQ 账号发送消息，未声称外部平台在进程崩溃时绝对恰好一次。发送由真实框架链路与测试传输共同验证；线上适配器、模型和天气服务仍应做用户环境验收。
