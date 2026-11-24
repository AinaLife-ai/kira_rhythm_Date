# 生活节律·日程插件（KiraRhythmDate）设计规格

> 状态：第三轮对齐稿 v0.2.1，不是“已实现”声明
> 兼容目标：KiraAI `>=3.1.2`；已核验 `v3.1.2`（`89013745`）与 `v3.2.0-beta.1`（`24a1d433`）
> 建议仓库：`kira_rhythm_Date`；插件 ID：`kira_rhythm_Date`；英文内部名：`KiraRhythmDate`；简称：`KRD`；中文显示名：**生活节律·日程插件**
> 核心定位：**每个人格都拥有独立的、可感知和调整的生活节律**，不是普通提醒器，也不是把 cron 包装成聊天命令。

---

## 0. 设计结论摘要

1. **生活闭环**：规划 → 感知当下 → 触发小项 → 留下必要体验 → 查看差异 → 主动调整 → 进入下一段生活。
2. **两种时间锚 + 一个概率修饰器**：精确时间、随机时间窗都可附执行概率；UI 可将“概率日程”作为第三类快捷卡片，但底层不允许存在“只有概率而没有时间锚”的项目。
3. **三级结构 + 每日状态**：`日计划 Plan → 日程组 Block → 小项 Item → 执行 Run`，另有 `DayState` 保存当前服装、心情、地点和总体思路。
4. **双会话概念**：规划起始会话与项目执行会话不是一回事。二者都有独立会话池和权限交集。
5. **框架内唤醒**：定时触发走 `KiraMessageBatchEvent + event_bus`，保留人设、工具、发送、归档和 S/Z 等插件的批次协作。
6. **默认不要求完成工具**：正常模型响应（包括 `<msg/>`）即记为“已触发”；静默不是失败。失败、未触发、概率跳过与已触发分别表达。
7. **重复规划即修改机会**：定时触发不因已有 Plan 而跳过；全部小项触发后也再给予一次机会。已有计划时默认修订而不是另建重复计划。
8. **人格隔离**：日型、计划、每日状态、体验、图片、天气、会话池与运行记录均按 `persona_id` 隔离；切人格是切换生活线，不只是暂停。
9. **持久化事实源 + 单调度循环**：SQLite 是事实源；随机结果、概率判定和执行认领先落库，重载不重抽、不重复执行。
10. **缓存优先**：完整指令和动态状态放最新用户消息尾部，`persist=False`；不改全局模板或共享适配器状态。
11. **WebUI 是生活面板**：默认呈现“此刻、接下来、今天、变化”；高级约束渐进出现，业务设置保存即热生效。
12. **天气 Provider 可插拔**：优先无账号服务，其次免费注册服务；统一缓存、许可、超时和字段规范，不把任何服务宣传成无限免费。
13. **诚实的可靠性边界**：防止自身重复认领；进程在“平台已发送、本地未落账”的窗口崩溃时无法独立证明恰好一次，默认标 `interrupted` 而不盲目重发。

---

## 1. 已核验的框架事实与设计约束

### 1.1 当前真实接口

- 插件生命周期为 `BasePlugin.__init__(ctx, cfg)`、`async initialize()`、`async terminate()`。
- 页面/API/WS 使用 `@register.page`、`@register.api(method=..., path=...)`、`@register.ws`；默认 `auth=True`，本插件不得关闭。
- 页面用 `PluginPage.from_folder("./web")` 挂载；`PageMenu` 支持中英文标签、图标和侧栏排序。
- 页面桥 `PluginPageContext` 提供主题、语言、插件 ID、同源 API、上传和鉴权 WS；页面需响应宿主明暗主题与语言切换。
- 会话读取、能力查询均为异步；会话展示用标题，内部模型 ID 不得当可读模型名。
- 适配器消息能力通过 `IMCapability.get_message_metadata().supported_elements` 获取；不得再写 `message_types`。
- 运行数据必须放 `ctx.get_plugin_data_dir()`；插件源目录只放代码和内置静态资源。
- 插件 WebUI JavaScript 必须按职责拆文件，不能堆成一个巨型 JS。
- 框架已带 `aiosqlite`、SQLAlchemy、httpx/aiohttp、Pillow、tzdata，无需为核心调度引入大型依赖。

### 1.2 主动唤醒为何走框架工作流

直接构造 `KiraMessageBatchEvent` 并发布到现有事件总线，可进入：

`PrepareBatch → BuildRequest → AssembleRequest → ExecuteAgent → Finalize`

这样保留人设、会话历史、工具调用、XML 输出、平台发送、用量统计和最终归档。它是定时系统事件，不应伪装成真实用户发言：

- `KiraIMMessage.is_notice=True`；发送者显示为“生活节律”，稳定内部 ID 使用 `system_krd`，不是某个用户。
- 会话、群信息、`self_id/bot` 和支持元素均从真实目标与适配器能力构造。
- `message.extra` 仅放小型路由元数据：`run_id/kind/plan_id/item_id/revision`，且必须兼容 S/Z 合批后的多消息遍历。
- 可为规划事件提供 `model_group`；未指定时使用框架默认模型。
- 其他插件仍可正常停止事件；插件不得强制绕过其停止语义。
- `event_bus.publish()` **只入队，不等待执行完成**；已触发由正常模型响应落账，final/watchdog 只负责审计和异常收尾。

### 1.3 配置热更新的边界

框架 `update_plugin_config()` 写盘后会重新初始化插件，不等于重启 KiraAI 进程，但会重建插件实例。本设计分两类：

- **面板中的业务设置**：插件自身版本化配置，保存后原子应用，不重建插件；调度器仅被唤醒重算下一次唤醒。
- **敏感天气服务密钥等框架字段**：使用 `schema.json` 的 `sensitive` 字段，框架热重载插件；持久化运行状态保证不重复执行。密钥永不出现在自定义 API、WS、日志和导出文件中。

---

## 2. 领域语言与层级

### 2.1 日型（Day Type）

用户所说的“工作日、调休、假日”等日期概念统一命名为**日型**，避免与“上午/下午”等时段混淆。

每天只有一个**主日型**，用于选择：规划提示词、每日小项上下限、允许的时间模式、规划/执行会话池、默认安静时段、天气上下文模板和界面配色。可额外挂信息标签，但不允许多个日型提示词同时抢占主提示词。

内置日型模板：

- `weekday` 工作日
- `weekend` 周末
- `holiday` 假日
- `adjusted_workday` 调休工作日

`custom` 不是唯一桶，而是“从空白/模板新建”的动作。用户可创建数量不受领域限制的自定义日型，例如 `exam_week`、`rainy_home_day`、`anniversary`、`travel_day`，各自有独立 ID、名称、规则和外观。内置模板不可直接破坏，自定义副本可无限派生；日型规则与覆盖配置按人格隔离，共享模板可显式复制给另一个人格。

日型解析优先级（高到低）：

1. 单日手工指定；
2. 明确日期范围规则；
3. 周重复/月度规则；
4. 周末、工作日默认映射；
5. 全局默认日型。

规则冲突在 UI 中显示最终命中链，不允许“表面是假日、实际用了工作日提示词”却无法解释。法定假日服务因地区差异不默认开启；支持手工、规则、模板导入，后续可接日历订阅。

**bot 也必须看得见日型**：规划时注入目标日日型及命中原因；小项触发时注入当前日型；普通允许的会话中用紧凑 `DayState` 块提供当前日型。WebUI 同时显示相同事实，不出现面板和模型各看一套的情况。

### 2.2 计划、组、小项、执行与每日状态

- **Plan**：某人格在某时区某一天的生活计划，有独立 revision。Plan 还包含当日总体思路 `overview`、预计服装 `planned_appearance`、预计状态 `planned_mood`、主题与地点意图，均在完整规划时一次生成，不额外调用 LLM。
- **DayState**：该人格当天“当前自我叙事”，含 `current_appearance/current_mood/current_location/current_activity/current_note/revision/source`。Plan 是预计，DayState 是当下；二者不得混成不可变设定。
- **Block**：同主题或同阶段的组，例如“晨起”“午后创作”“睡前”。组是展示和上下文边界，不是一个巨型不可分任务。
- **Item**：最小可调度小项，有唯一时间锚、执行目标、意图、状态和执行记录。
- **Run**：小项一次实际唤醒/执行尝试。修改计划不会产生新 Item；重复随机序列则展开为多个 Item，并以 `series_id` 关联。
- **Experience**：可选的私有体验记录，如一场梦、一次阅读感受。默认只在插件内按人格和日期保存，不自动成为长期记忆。

这种展开保证每个小项都有独立触发记录，也确保序列展开后的数量仍受每日上下限和必需时段配额约束。

---

## 3. 时间模式与概率语义

### 3.1 A. 精确时间 `exact`

示例：明天 09:30（或 09:30:15），在 `qq:dm:123` 执行“问早安并聊聊今天的安排”。

必备字段：本地日期、时分（可选到秒）、IANA 时区、目标或目标池、执行意图。保存 UTC 瞬间用于调度，同时保存原始墙钟时间和时区用于显示及改时区预览；`at`/`start`/`end` 支持 `HH:MM` 或 `HH:MM:SS`。

### 3.2 B. 时间窗 `window`

示例：明天 09:00–10:00（或 09:00:10–10:00:10）随机做一次“分享此刻看到的事物”。

两种子模式：

- `single_random`：窗口内随机一次，默认。
- `interval_random`：窗口内按最小/最大间隔生成一串随机小项；需给出现次数或上下限，展开后每个出现都是独立 Item。

约束：

- 窗口可跨午夜，但必须明确结束日期。
- `window_start < window_end`，最小间隔不得小于全局硬下限。
- 每个实际随机时刻生成后立即持久化；UI 同时显示原窗口与已落定的执行时刻。
- 多次序列先确定次数 N，并验证 `(N-1) × 最小间隔 ≤ 窗口时长`；若给次数范围，最大可选 N 也受窗口容量约束。
- 抽样时为首点预留后续最小跨度，为每个间隔同时考虑剩余时间和后续最小间隔；不能使用“超出窗口就丢掉多余项”的隐性降次数算法。无法满足时整套校验失败并说明冲突。
- 不得在每次调度循环里重新抽样。
- 时间窗不是“整个窗口持续执行”；若需要持续状态，应由一个小项开始、另一个小项结束，或在未来增加显式 duration 语义。

### 3.3 C. 概率修饰器 `probability`

`execution_probability ∈ [用户最低概率下限, 1.0]`；bot 未传时默认为 `1.0`。全局开关默认开启，精确与时间窗可混用概率。

执行到点时：

1. 原子认领 Item 并创建 Run；
2. 抽取一次随机数并把 `probability_value/draw/result` 落库；
3. 未命中则记 `skipped_probability`，这是正常生活选择，不是错误；
4. 命中才发布 LLM 唤醒；
5. 重启、热重载、 watchdog 均不得重新抽签。

默认最低概率建议 `0.20`，用户可调为 `0` 或更高。概率只决定“是否唤醒执行”，不让模型在到点前偷偷知道本次必定跳过。

### 3.4 模式开关

`allow_exact=true`、`allow_window=true`、`allow_probability=true`，三者默认全开。关闭某模式只限制之后的 bot 新建/修改，不暗中删除已有计划；已有项目在 UI 标为“模式已停用”，由用户选择保留、转换或取消。

---

## 4. 完整规划的触发与覆盖范围

### 4.1 触发来源与“已有计划也要触发”

1. **定时规划**：默认每天 23:00 触发，**不检查已有 Plan 就跳过**。没有则创建，有则把当前完整 Plan、最近 diff 和本次触发原因交给 bot，默认作为一次修订机会。
2. **当前小项全部达到终态**：默认再触发一次。已有下一日/后续 Plan 时，同样视为一次修改机会，而不是不触发。
3. **手动规划**：WebUI“现在规划/重新审视”，可选择日期/范围、日型覆盖和起始会话。
4. **启动补建**：没有可用今日/下一日计划时补建一次；不得为离线期间的每一天疯狂补建。
5. **bot 主动重规划**：通过工具提交理由；受修改预算、时间范围和目标权限约束。

每个真实触发事件有独立 `trigger_id`，只对同一事件幂等。不同来源、不同时间的两次规划机会不能因目标日期相同而被永久吞掉。若第一次尚未开始，可把多个原因合并到一次；若已在运行，最多保留一个带累计原因的后续机会，既尊重两次触发又避免无意义连烧模型。bot 可以选择“保持现状”，不强制每次产生修改。

用于“全部触发”的终态默认为 `triggered/triggered_silent/skipped/missed/cancelled`；`failed/interrupted` 是否计入由用户配置，默认不计入，避免失败被当作正常收尾。全部概率跳过时可获得一次审视机会，但同一触发事件不得循环自触发。

### 4.2 创建、修订与目标日期

- 无有效 Plan：`create`。
- 已有有效 Plan：默认 `revise`，把当前 Plan 当基线，允许增删改并返回新 revision 和 diff；不另建同日重复 Plan。
- bot 明确要彻底重排：`replace`，仍需 expected_revision、理由、每日下限和必需时段校验。

目标日期支持 `tomorrow/next_missing/range/rolling`。默认定时看下一日，全部触发后看接下来需要审视的 Plan；若已存在，则修订它。rolling 只决定覆盖范围，不剥夺定时修订机会。

### 4.3 多日规划

底层天然支持，无需另造系统：

- bot 的 `rhythm_plan` 接受单日或 `plans[]` 批量计划；
- 每日独立日型、提示词、配额和会话池；
- 默认规划 1 天，允许用户开放未来范围，建议软上限 14 天；
- 每日小项默认 2–12 个，范围总量另设硬上限；
- 多日批量采用同一事务：任一日违反约束则返回逐日错误，默认不提交半套计划；
- 多日 token 和失败风险明显高于单日，因此默认不开启 rolling，多日结果在 UI 先给结构化预览和差异。

**每日最小下限默认存在**：建议 `min_items=2`、`max_items=8`，均可热改，最小可为 0。每次创建、replace 和修改后的整个 Plan 都必须重新满足下限；概率跳过不影响“计划时数量”的判定。除全日上下限外，还可配置必需覆盖时段及其次数，详见 §17.3。

---

## 5. 会话池、权限与均匀选择

### 5.1 两类池

- **规划起始会话池**：决定“在哪里让 bot 完整规划”。
- **项目执行会话池**：决定每个小项“在哪里生活/互动”。bot 只能从该池选择，也可在小项指定池内某一 SID。

所有目标均为完整 `adapter_name:dm|gm:session_id`，禁止模型猜 ID。UI 从 `session_mgr.get_sessions(include_content=False, kind="im")` 读取标题，不读取正文。

### 5.2 黑白名单

默认 `deny_list + 空列表 = 全允许`；可切 `allow_list`。实际权限永远取以下交集：

`插件名单 ∩ 日型/池配置 ∩ 已存在 IM 会话 ∩ 适配器在线 ∩ IMCapability 收发权限`

允许列表为空时 UI 明示“将没有任何可用会话”，避免误保存后沉默。权限在执行时再次检查，不能只在计划创建时检查。

### 5.3 随机与均匀策略

- `pure_random`：**默认**。每次独立随机、允许重复，包括理论上连续抽中同一会话。
- `no_immediate_repeat`：每次从“完整池 − 上一次结果”重新随机；抽完后下一次又把上次结果放回来。池只剩一项时只能继续使用它。这正是“排除刚取的一个再重洗”，并非真正的 shuffle bag。
- `shuffle_bag`：每轮打乱完整池，依次取完再重洗；每轮内不重复，适合强均匀需求。
- `round_robin`：按用户排序轮询。
- `weighted_random`：独立加权随机，可另开“避免连续重复”修饰。

UI 使用可读名称“完全随机 / 随机但避免连续重复 / 一轮内不重复 / 顺序轮换”，不拿算法名词让用户猜。需要持久化的只有策略所需状态：`no_immediate_repeat` 的上次结果、洗牌袋顺序和轮询游标。规划与执行各自维护状态。

---

## 6. bot 主动修改与规划机会

### 6.1 修改范围

bot 可新增、删除、移动、改时间窗、改概率、改目标、改意图、重排和重规划；可附 `reason` 表达“为什么想改变”。bot 不可：

- 修改全局用户约束、权限和最低概率；
- 越权选择会话或突破每日/范围上限；
- 把概率调到下限以下；
- 篡改已触发历史；
- 在修改后使有效计划低于最小小项数，除非同一事务中给出替代项。

用户手工编辑是所有者操作，默认不受 bot 最小数/修改次数限制，但仍受格式、安全和硬容量限制。

### 6.2 修改预算

默认：滚动 24 小时内无限次（`max_change_units=0` 表示无限）。可修改窗口长度和上限。

计数采用**变更单元**而非工具调用次数：成功新增或实质修改 1 个 Item 计 1；一次批量改 3 项计 3，防止批量绕过。以下不计数：初始完整规划、查看、无实质差异的请求、失败校验、正常触发、不改变计划结构的私有体验记录、系统概率跳过、用户修改。完整重规划按实际新增/变更的小项计数。

### 6.3 规划机会，而非强制复盘工具

不再默认提供 `rhythm_complete`，也不要求 bot 为了“完成”再经过一轮工具结果。每次定时/全项触发后的规划机会，以及每次 `rhythm_update` 的返回，都提供当前组、最近 diff、下一项和剩余预算。bot 想修改就修改，不想修改可直接结束。

私有体验不是完成义务。梦、读后感等内容确有需要时，通过 `rhythm_update` 的 `record_experience/day_state` 操作保存，供后续小项或 `rhythm_view` 按需读取；普通小项不产生额外 LLM 轮。

### 6.4 已触发、静默与失败

Item 面向用户的主状态采用“待触发 / 已触发 / 未触发”语义，而不是强迫每个生活动作证明 done：

- 收到正常模型响应（含工具调用或正常文本）后，Item 记 `triggered`；这就是默认的正常终态。
- 最终正常输出为 `<msg/>` 或静默处理时，记 `triggered_silent`。**静默是合法选择，不是失败**。
- 概率未命中为 `skipped_probability`；有效期过去而未唤醒为 `missed`；权限/模型/投递链明确错误为 `failed`；崩溃后无法确定为 `interrupted`。
- Run 另保留 `queued/running/responded/finalized` 和发送结果用于诊断，不把平台是否发言偷换成生活小项是否“成功”。
- `must_message` 是例外：它要求可见投递，正常但静默的响应不算满足该投递要求，应标记 `delivery_unmet`，与 `triggered` 同时呈现，而非说 LLM 调用失败。创建时拒绝把 must_message 放进安静投递时段；若创建后配置变更导致已有项落入安静时段，安静优先：`<msg/>` 合法，不记 `delivery_unmet`。

---

## 7. 历史、当前组与结构差异

### 7.1 完整规划时

默认提供：同一人格前 3 天的完整 Plan 当前版本、未触发结转项、每次计划的简要触发统计、最近修改原因、目标日日型和天气。前 N 次/N 天可切换，N 可配。

“完整”与 token 预算冲突时不得静默截断：默认内联字符预算建议 12000；超出时明确标记 `history_inline_truncated=true`，优先保留最近一天完整内容，其余改为摘要，并告知可用 `rhythm_view` 分页取全量。

### 7.2 每个小项执行时

默认只注入：

- 当前小项及为什么现在被唤醒；
- 本组已经终态的小项与当前未完成的小项；
- 本组最近 2 次相关 revision 的结构差异；
- 下一项、当前修改预算；
- 必需的当前时间、地点和天气。

不默认带前几天完整表，不复制整段聊天历史，不带与本组无关的修改。

### 7.3 diff 结构

底层保存字段级变化，不把 unified text diff 当事实源。对模型使用紧凑格式：

```text
rev 12 · bot · “午后想留白一段时间”
~ item_03: 18:30 → 19:00; probability 1.0 → 0.8
+ item_07: [20:00–20:45 random] 整理今天的思绪
- item_04: cancelled（与item_03重叠）
```

UI 使用结构化 before/after，可查看单字段、整组或整日差异。默认最近 2 次，支持 `rhythm_view(scope="diff", from_revision=..., to_revision=...)` 主动请求更早版本。

---

## 8. LLM 工具面：少而完整，不让模型拼系统内部细节

所有工具名带 `rhythm_` 前缀，避免全局工具冲突。schema 与描述保持稳定，不把当前时间、剩余次数等动态值写进描述。工具失败返回机器可读 `error.code` 和用户/模型可理解的信息，不静默吞错。

### 8.1 `rhythm_plan` — 完整建立计划

用途：规划触发后创建单日或多日计划；bot 也可在允许范围内主动提出重规划。

核心参数（逻辑结构）：

```json
{
  "mode": "create_missing | merge | replace",
  "reason": "为什么这样安排",
  "plans": [{
    "date": "YYYY-MM-DD",
    "expected_revision": 0,
    "title": "明天想过这样的生活",
    "overview": "上午专注创作，傍晚留白散步，不排得太满",
    "planned_appearance": "浅色针织衫、舒适长裤，带那件旧外套",
    "planned_mood": "有点困倦，但期待一个从容的日子",
    "blocks": [{
      "title": "晨起",
      "items": [{
        "title": "醒来后的第一句话",
        "intent": "让新的一天有连续感",
        "instruction": "结合昨天的告别和今天的天气，自然地开始……",
        "schedule": {
          "type": "exact | window",
          "at": "08:30:00",
          "start": "08:30:00",
          "end": "09:10:00",
          "window_mode": "single_random | interval_random",
          "occurrences": 1,
          "interval_seconds": [600, 1500]
        },
        "execution_probability": 1.0,
        "target": "qq:dm:123 或 session_pool_id",
        "interaction": "auto | must_message | silent"
      }]
    }]
  }]
}
```

规则：

- `date` 决定日型，bot 默认不能借规划工具修改用户的日型规则。
- `expected_revision` 防止覆盖规划期间用户刚做的修改。
- 默认 `create_missing`；`replace` 必须给理由并通过 revision 检查。
- 时间只接受目标日范围内的本地墙钟，由服务端转换 UTC；不接受模型直接给时间戳。
- 服务端展开随机序列、分配稳定 ID、抽取并保存每个窗口项的实际时刻。
- 初始完整创建不计修改预算；bot 的 replace/merge 按实际变更单元计数。
- 返回 `plan_id/item_id/revision/summary/diff`，不原样回显整份大 JSON。

### 8.2 `rhythm_update` — 调整计划、每日状态与必要体验

参数：`operations[] + reason + expected_revision`。计划操作包括 `add/update/reschedule/cancel/reorder`，支持同组或跨日批量；另有：

- `day_state`：更新当前服装、心情、地点、活动或总体思路，保留来源和 revision；
- `record_experience`：记录确有后续价值的梦、阅读感受等私有体验，可关联 Item，不代表“完成证明”。

规则：

- 默认只修改尚未终态小项的执行定义；当前运行项不可改执行定义。
- 修改标题不重新抽随机时刻；修改窗口才重新抽样一次并记录差异。
- 取消导致低于最小数或破坏必需时段配额时，须在同一事务给出替代项。
- DayState 只由明确的 bot/用户操作更新，系统不根据每句聊天擅自换衣服或改变心情。
- 返回变更单元、剩余预算、结构 diff 和受影响组/每日状态的紧凑现状。

### 8.3 `rhythm_view` — 按需查看，不默认塞满上下文

`scope=current|today|block|day|range|history|diff|quota|experiences`，支持日期、游标、revision 范围和是否包含终态。

- 无参数时：运行中返回当前组；普通聊天中返回今天日型、DayState、下一项和今日概览。
- 历史与范围查询必须分页，响应带 `next_cursor/truncated`。
- diff 为字段级结构，不要求模型比较两张巨型文本表。
- 私有体验默认只取与当前/相关小项有关的记录，跨日需明确请求。
- 永不返回天气密钥、内部模型 UUID 或无关会话正文。

### 8.4 工具可见性

工具虽然注册到框架，但在每次 `on.llm_request` 根据当前 SID 与功能开关过滤请求级 `ToolSet`。无权限会话不看到日程工具；禁止只依赖工具描述里的“请不要调用”。框架会在钩子后重新生成 `request.tools`，无需修改已弃用字段。

---

## 9. 存储与 revision 模型

数据库：`ctx.get_plugin_data_dir()/rhythm.db`，SQLite WAL、外键、busy timeout、`PRAGMA user_version` 迁移。LLM/网络等待期间绝不持有数据库写事务。

### 9.1 核心表

| 表 | 职责与关键字段 |
|---|---|
| `plans` | `id/date/persona_id/day_type_id/state/revision/title/overview/planned_appearance/planned_mood/planning_run_id/created_by/timestamps` |
| `day_states` | 每人格每日当前服装、心情、地点、活动、总体思路、来源和 revision；与 Plan 的预计值分离 |
| `experiences` | 可选私有体验：`persona_id/date/item_id/kind/content/created_at/retention`，默认不进入长期记忆 |
| `blocks` | `id/plan_id/title/position/color/cover_asset_id/meta_json` |
| `items` | 当前小项：所属、标题、意图、指令、时间模式、UTC 执行点、原墙钟/窗口、概率、目标、互动策略、状态、revision、原因 |
| `plan_revisions` | `plan_id/revision/snapshot_json/diff_json/actor/reason/created_at`，支持恢复和审计 |
| `runs` | `id/item_id/plan_revision/event_id/session_id/status/scheduled_at/claimed_at/finished_at/probability/draw/lease/error/usage` |
| `mutations` | 成功修改账本，供滚动预算、字段差异、操作者审计 |
| `planning_runs` | 规划触发来源、目标范围、起始会话、模板 revision、幂等键、状态和错误 |
| `day_types` | 日型规则、提示词模板引用、配额、会话池和外观引用 |
| `session_pools` | 池成员、选择策略、洗牌袋状态/轮询游标 |
| `settings` | 单条版本化业务配置 JSON、revision、迁移版本 |
| `weather_cache` | 地点、真实/虚拟模式、日期/时段、payload、来源时间、过期时间 |
| `assets` | 用户图片的内容哈希、路径、类型、尺寸、引用计数、上传时间 |

### 9.2 时间与随机字段

- 所有实际调度比较使用 UTC 秒/毫秒；显示使用 IANA 时区。
- 同时保存原始 `local_date/local_at/window` 和时区，修改时区时可预览“保留墙钟时间”或“保留绝对瞬间”。默认保留墙钟时间。
- 夏令时不存在的本地时间拒绝创建；重复时间要求用户选择较早/较晚偏移，默认较早并在 UI 明示。
- `scheduled_at_utc` 是已经落定的执行时刻；窗口定义和执行时刻分开保存。
- 概率抽签结果只存在 `runs`，未执行项目只保存概率，不预存“未来会跳过”。

### 9.3 一致性与保留

- Plan/Item 使用乐观 revision；WebUI、bot 和调度器共用同一校验。
- 每次成功修改在同一事务写当前行、snapshot/diff 和 mutation，再唤醒调度器与 WS。
- 快照只清理已归档计划；活跃计划永不因保留策略被剪断。
- 默认保留期限、每计划最大 revision 和导出提醒均可配置；导出文件带 `schema_version`。

### 9.4 人格隔离不是简单暂停

`plans/day_states/experiences/runs/day_types/session_pools/weather_locations/assets` 都带 `persona_id`（全局只读模板除外）。每个人格拥有独立生活线、历史、修改预算、随机会话状态和每日自我叙事。

- 从 A 切到 B：A 的未来项自动转为 `inactive_persona`，B 使用自己的 Plan/DayState；B 没有计划时获得初始规划机会。
- B 以前的生活线若仍存在，可恢复其尚未过期项；离开期间不因未唤醒而堆积 missed 或补发。
- 切回 A 同理，历史保持连续，不读取 B 的前几日 Plan 作为 A 的“我的昨天”。
- 发布前与 `on.llm_request` 都复核 active persona，避免用 B 的人格执行 A 的唤醒。切换前已在执行的旧轮无法撤回，之后不再发布。
- 只有用户显式“复制/迁移”时才跨人格复制模板或计划；默认不共享私有体验、当前服装和心情。

---

## 10. 调度器：持久化、事件驱动、可恢复

不直接让 APScheduler 持久化“插件对象的方法”：插件热重载会改变模块和可调用对象，容易留下不可反序列化任务。借用其成熟的 misfire、有效期和暂停/恢复概念，但以本插件 SQLite 实体为事实源；生活小项是否合批由聊天插件决定。

### 10.1 运行结构

- 一个 dispatcher coroutine、一个可中断 `asyncio.Event`、一个最近执行点 min-heap。
- 无日程时等待事件，不做每秒扫描；有日程时睡到最近执行点。
- 新增、修改、删除、热配置、启动恢复都会唤醒并重算 heap。
- 只为同一 Item 防重和可选的洪峰背压负责，不另造“用户聊天期间禁止日程”的互斥；批次并发与合并交给框架及当前聊天插件。
- DB/网络/图片处理不阻塞事件循环；CPU 图片缩略图走线程。

### 10.2 原子认领

1. `BEGIN IMMEDIATE` 选择满足时间、状态和权限的 Item。
2. 以 `item_id + revision + scheduled_at` 做条件更新，并插入唯一 Run。
3. 若是概率项，在同一事务保存抽签和结果。
4. 提交后才获取天气、构造事件和入队；外部慢操作不在事务里。
5. 热重载或调度循环重复唤醒无法再次认领同一 Run。

### 10.3 批次协作，不做用户优先延迟

日程到点即构造并发布批次，不查看用户是否正在聊天，也不因 buffer 中有消息而等待。这样既能出现 bot 正忙时另一件生活事也发生了的感觉，也避免插件自行改变日程时间。

- 默认聊天与 S/Z 的 flush/batch/pending 机制负责后续排队和合批；本插件不猴补丁它们。
- Run 元数据放在每个 `KiraIMMessage.extra`，因为 S/Z 合并时会重写 Batch `extra` 但保留原 Message 引用。
- 请求、响应、final 钩子都遍历 `event.messages` 中全部日程标记，允许一个最终批次同时含真实用户消息和多个日程 Run。
- S/Z pending 期间 Run 保持 `queued`，不按 60 秒或普通聊天冲突判 missed，也不重复发布。
- 用户手工“立即执行”仍需权限校验和速率限制；默认覆盖概率并记录 `manual_override`。

### 10.4 有效期与重启恢复

misfire 只处理**插件/进程停机、适配器不可用或调度器自身延迟**，不再处理用户聊天冲突。

- 精确项有独立 `valid_until/grace`，建议默认 10 分钟；窗口项默认不晚于窗口结束。全部可配。
- 恢复时仍在有效期内的 Item 逐个发布一次，由聊天插件决定是否合批；不把多个生活小项擅自 coalesce 成“只执行最近一个”。
- 超出有效期记 `missed`，它是未触发而非失败；不为已经失效的早晨事项在深夜补发。
- 已入队/运行中但重启前结果不明的 Run 标 `interrupted`，默认不自动重跑。尚未发布且可证明没有 `event_id` 的准备中 Run 可安全恢复。
- 人格处于 inactive 的时间不累计 missed；恢复人格时只重新评估仍有效的未来项。
- 规划触发按 `trigger_id` 幂等，离线过去日期不自动补写一整套历史。

### 10.5 响应落账与 watchdog

Run 状态建议：`prepared → queued → running → responded/finalized`，另有 `failed/stalled/interrupted`。Item 的正常终态为 `triggered/triggered_silent`，另有 `skipped_probability/missed/failed/delivery_unmet`。

- 首个正常模型响应即可把 Item 标为已触发，包括正常工具调用或 `<msg/>`；无需等待 final，更无需完成工具。
- final 用于补充发送审计、token/耗时和释放诊断资源，不被当成完成义务。
- 对长时间无响应的 Run 做 watchdog；S/Z 正常 pending 不套用普通 60 秒停滞阈值。
- 事件被其他插件停止时保留明确来源与状态，不重复入队。
- 每次达到终态后重新评估“全项触发后的规划机会”，按 `trigger_id` 防重。

---

## 11. 提示词与缓存/token 设计

### 11.1 三层内容

1. **稳定规则**：三个核心工具何时使用、权限不可越过、已触发与修改的区别。只在有权限时追加到本次请求的 `tools` system 块，内容固定。
2. **用户模板**：完整规划提示词、日型要求、执行指令。作为本次最新用户消息中的 `Prompt(..., persist=False)`。
3. **动态状态**：当前时间、日型、天气、历史、当前组、diff、预算。同样放最新用户尾部且 `persist=False`。

不修改 `DYNAMIC_PROMPT_NAMES`，不把天气/倒计时塞入 system，不改共享模板对象，不动适配器全局状态。

### 11.2 对齐主动唤醒与 QQ 增强：系统标记正常持久，动态内容非持久

已核对插件市场「主动唤醒 v2.5.0」与「QQ增强 v1.4.6」的真实源码，采用它们相同的边界：

- 主动唤醒把 `[定时任务｜系统触发]` 等标记放进 Notice MessageChain，按框架默认规则保存；只有投递恢复摘要等附加动态块在 `req.user_prompt` 末尾使用 `persist=False`。
- QQ增强把 `[System …]` 通知追加到真实消息链，工具说明进入 `tools` system 区；不为通知额外设置非持久。

因此本插件默认 `notice`：MessageChain 以 **`[生活节律｜系统触发]`** 开头，短标记按框架默认 `persist=True` 保存。纯日程批次因此不会出现空 user，混合批次中也能清楚区分系统唤醒和真实用户消息。它是新追加的来源记录，不重写旧历史，不破坏已有缓存前缀。

完整规划/执行指令、日型、DayState、天气、当前组、历史、diff、预算和运行提示词仍全部由 `on.llm_request` 以 `persist=False` 注入；私有体验只在插件 DB 保存。这些动态内容一律不进入会话历史，与主动唤醒的恢复摘要处理一致。静态工具规则与 QQ增强一样放 `tools` system 区。

可选模式：

- `notice`（默认）：只持久化系统短标记；
- `full`：额外持久化用户明确选择的规划/执行模板，动态状态仍不持久；
- `none`：把日程短标记也设为非持久。当前 3.1.2/3.2 在纯日程批次会留下空 user 记录，UI 必须明确说明，不能宣称“完全无历史”。混合批次中真实用户消息仍按原规则保存。

bot 的正常回复按框架原规则保存；静默 `<msg/>` 不应被当成一条真实发言。

### 11.3 token 节约顺序

- 完整规划才默认带前几天完整计划；普通小项只带当前组。
- diff 只输出变化字段；未变 Item 不重复描述。
- 工具返回 ID、摘要、错误和必要下一步，不回显大请求体。
- 天气只保留当前自然语言摘要和少量关键数值，不塞原始逐小时 API JSON。
- 历史分页且有显式截断标记；不允许无声丢数据。
- 已触发是默认正常终态，不要求完成工具；只有确需保存私有体验或改变 DayState 时才使用修改工具。
- 静态工具描述不包含每日配额等变量，保持 tools/schema 前缀稳定。

### 11.4 缓存验收口径

插件只能保证“不破坏可缓存前缀”，不能承诺所有 provider 一定返回 cached token。测试需断言：

- 同一基础会话连续请求，system 内容与 tools schema 逐字节一致；
- 动态日程块位于尾部 user，且 `persist=False`；
- 请求完成后，历史中没有天气、倒计时、完整日程快照等动态块；
- 修改日程只改变当前尾部，不重写已有历史消息；
- provider 返回 `cached_tokens` 时记录用于观测，但不把它当跨供应商正确性条件。

---

## 12. WebUI 信息架构：生活感优先，复杂度渐进出现

### 12.1 挂载与技术形态

- 宿主侧栏入口：`生活节律`，中英文 `PageMenu`，非空子路径 `/dashboard`。
- 插件页面为本地构建的 Vue 3 + TypeScript SPA，无 CDN 运行依赖。
- 使用 `PluginPageContext` 跟随宿主主题和语言；不把宿主页样式硬复制成一套不兼容皮肤。
- 源码按 `api/stores/views/components/composables/effects/i18n` 拆分；构建产物放插件 `web/`，运行上传图片不放源目录。
- 时间显示以服务端权威时区为准；前端使用 `Intl`，不在浏览器自行猜日程日期。

### 12.2 插件内导航

桌面为可收起的窄侧栏，移动端为底部五项导航：

1. **此刻**：今日生活总览；
2. **日历**：月/周/日与多日计划；
3. **变化**：bot 的主动调整、diff、执行和复盘；
4. **模板**：日型、提示词、计划模板、主题与图片；
5. **设置**：权限、调度、天气、性能、数据和诊断。

首页不堆所有设置。高级参数有搜索、分组、解释和“恢复此项默认”，而不是全部展开。

### 12.3 「此刻」首页

```text
┌ 生活节律 ───────────────────── 日型 · 天气 · 设置状态 ┐
│ 左侧导航 │  此刻卡片：正在做什么 / 为什么 / 当前会话     │
│          │  下一件事：倒计时、时间窗、概率、目标           │
│          │  今日时间轴：已完成 ─ 此刻 ─ 待执行             │
│          │  最近变化：bot 把阅读挪到 20:30，因为……        │
│          │  一周微型视图 / 修改预算 / 规划覆盖状态          │
└──────────────────────────────────────────────────┘
```

- 此刻卡片允许 bot 头像、生活背景、组封面；无图时使用与天气/日型一致的渐变。
- 时间轴精确项为实线节点，窗口项为半透明区间带，概率项带百分比徽记，跳过项为柔和灰态；颜色不是唯一状态提示。
- 小项默认只显示标题、时间、目标和状态；意图、指令、天气和 revision 放入展开详情。
- 快捷操作：完成、跳过、调整、立即执行、暂停未来项；危险操作有结果预览而非笼统确认框。
- 空计划、天气失败、适配器离线、权限收缩均有明确可行动的空态，不用永远转圈掩盖问题。

### 12.4 日历与计划板

- 月视图看日型、完成度和计划密度；周/日视图看精确时间轴与窗口带。
- 多日板每列一天，显示各自日型和提示词模板，可整体复制/套用模板。
- 拖动只是编辑入口：放下后显示字段 diff、权限/上下限/冲突检查，再提交。
- 所有拖拽操作均有键盘和表单等价入口。
- 窗口项可切换“窗口定义 / 已随机落点”；随机序列以一张聚合卡显示，展开后才是各小项，避免视觉噪声。
- 多日批量编辑显示逐日错误位置，不允许“部分成功却看似全成功”。

### 12.5 「变化」中心

时间流卡片示例：

> **我把夜读从 21:00 挪到了 21:40**
> 因为今天散步延长了，想给这段安静时间留得更完整。
> `rev 18 · 消耗 1 次修改 · 查看前后差异`

支持按 bot/用户/系统、计划、日期、操作类型过滤；可查看执行状态、概率抽签、失败原因、token 与耗时（若 provider 提供）。这里展示的是结构事实，不把模型散文当审计日志。

---

## 13. 模板、图片与视觉个性化

### 13.1 四类模板

1. **日型模板**：工作日/假日等规则、提示词、配额、默认会话池和配色。
2. **提示词模板**：完整规划、单小项执行、复盘提示；变量自动补全、示例预览、版本和恢复默认。
3. **计划模板**：可复用的组与小项骨架，例如“规律工作日”“慢生活假日”“创作日”“陪伴日”。应用时可仅建草稿，不自动发消息。
4. **外观模板**：色彩、背景、卡片密度、动效强度和图片槽位。

所有内置模板均可查看、复制、重命名、修改、另存、导入/导出；内置原件不被覆盖。模板有 `schema_version`，导入先校验和预览，不直接覆盖现有计划。

### 13.2 用户图片槽位

- bot 生活头像；
- 首页横幅与页面背景；
- 日型图标/封面；
- 日程组封面；
- 天气图标或雨雪图层；
- 主题模板预览图。

**生活头像默认自动获取**：每个人格可独立设置。优先级为“本插件手工上传 > 用户指定头像源 > 自动 > 内置默认”。`auto` 默认按用户可调整的适配器顺序，选择第一个在线且支持获取 bot 账号头像的适配器，而不是每次随执行会话跳变；可指定首选适配器。自动适配器头像之后，再依次尝试人格参考图和内置默认图。

- QQ/NapCat：优先从 `get_login_info` 或稳定 `self_id/bot_pid` 获取账号，再使用 QQ 头像 CDN（如 `q1.qlogo.cn`）下载并缓存；`get_stranger_info` 不能假定返回头像。
- Discord/Telegram 等：仅在适配器真实暴露 `display_avatar`、Bot API 头像能力时特征探测使用；没有统一接口就不伪造通用能力。
- 不支持的平台回退人格参考图/默认图。头像按 `adapter+self_id` 缓存建议 24 小时；**每次重新进入前端会在首屏后强制刷新远程缓存**，下载失败沿用旧图，不阻塞日程或首屏；本地重编码后用于页面，避免持续热链外部服务。

上传约束：PNG/JPEG/WebP/GIF（动图可配置禁用），默认单文件 5 MB、最大边 4096；服务端检查真实 magic bytes、生成缩略图、重编码静态图并去 EXIF。用户 SVG 默认不开放，避免脚本/CSS 注入；内置 SVG 图标随插件发布。

运行图片存数据目录，以内容哈希命名、引用计数管理；通过鉴权 API 读取，不暴露任意文件路径。删除被引用图片时给出引用列表。导出模板可只含引用，也可打包图片。

### 13.3 风格与特效

主风格建议“**Kira 雾紫手账 × 天气光影**”：清晰排版和纸张层次为主，玻璃与光效为辅，不做满屏霓虹。

- 随日出/日落、当前天气和日型改变页面光影；
- 雨、雪、云层使用低粒子 Canvas/CSS，完成时仅局部涟漪；
- 当前时间线有轻微呼吸，下一步卡片出现短促而可预期的过渡；
- 动画主要用 transform/opacity；页面隐藏即暂停；
- 遵循 `prefers-reduced-motion`，提供关闭/低强度/完整三档和低性能模式；
- 不以特效延迟编辑、滚动和 API 响应，不默认引入重型 WebGL。

---

## 14. 热配置与编辑冲突

### 14.1 保存语义

自定义面板保存流程：

`客户端 expected_revision → 全量校验 → 构造新不可变运行配置 → DB 事务 → 原子交换配置快照 → 唤醒调度器 → WS 通知`

成功即生效，无 KiraAI 进程重启。revision 不匹配返回 409 和最新摘要，不让后保存者无声覆盖前者。

进行中的 Run 固定使用启动时配置快照；新规则作用于之后的认领。修改全局规则不会改写 bot 已经发出的消息。

### 14.2 特殊变化

- **时区**：先展示未来项变化，选择保留墙钟或绝对瞬间，再单事务重写。
- **权限收紧**：未来失权限项暂停，不删除；运行中项无法撤回，之后不再执行。
- **关闭某时间模式**：已有项保留但标记停用，由用户选择处理。
- **提高每日下限**：不自动删除或补项，只标记当前计划不合规，在下一次 bot 规划中解决。
- **修改规划时间**：只改未来规划触发，不重跑已结束规划。
- **修改模板**：已有 Plan 不变；只影响之后规划，除非明确“应用到当前草稿”。

---

## 15. API 与实时更新

所有接口默认框架 JWT 鉴权，统一 `/api/plugin/kira_rhythm_Date/...`；WS 为 `/ws/plugin/kira_rhythm_Date/events` 且 `auth=True`。输入在服务端重新校验，不能信任前端限制。

建议资源：

- `GET /v1/bootstrap`：页面所需的紧凑配置、权限、会话标题、日型和当前 revision；
- `GET /v1/plans?from=&to=&cursor=`、`GET /v1/plans/{id}`；
- `POST /v1/plans`、`PATCH /v1/plans/{id}`、`POST /v1/plans/{id}/actions`；
- `PATCH /v1/items/{id}`、`POST /v1/items/{id}/complete|skip|run_now`；
- `GET /v1/plans/{id}/diff?from=&to=`；
- `GET/PUT /v1/config`、`POST /v1/config/preview`；
- 日型、模板、会话池 CRUD；
- `POST /v1/weather/preview`、`GET /v1/weather/current`；
- `POST /v1/assets`、`GET /v1/assets/{hash}`、`DELETE /v1/assets/{id}`；
- `GET /v1/runs`、`GET /v1/diagnostics`；
- `POST /v1/export`、`POST /v1/import/preview|commit`。

WS 只推轻量失效事件：`plan_changed/run_changed/config_changed/weather_changed + id + revision`。客户端按 ID 拉取，不在 WS 中反复广播完整日程；断线用 revision 检测缺口并重新快照。页面不可见时降低刷新，不做高频轮询。

列表全部游标分页，月视图只取范围内摘要；图片懒加载，长时间轴虚拟化。导出/备份包含 schema 版本；ICS 导出可作为兼容能力，ICS 导入只创建待确认草稿。

---

## 16. 天气、生活地点与虚拟气候

### 16.1 地点模型

区分：

- **bot 生活地点**：默认参与所有规划和执行；
- **目标会话地点**：可选，适合“你那里也在下雨吗”；默认关闭，避免不必要的位置暴露；
- **虚拟地点**：名称、纬度/季节可选、气候模板、随机种子和虚拟说明。

日程时区默认继承框架；可单独配置。天气地点的时区不暗改日程时区。

### 16.2 真实天气 Provider 注册表

WebUI 按“无需账号优先、免费注册其次、付费/自托管其后”展示。Provider 元数据必须声明覆盖范围、认证、当前套餐、许可/署名、缓存要求和能力，而不是只给一个 base URL。

**无需账号优先：**

| Provider | 覆盖与定位 | 认证及关键约束 |
|---|---|---|
| Open-Meteo | 全球当前与预报，默认首选 | 无 key；非商业免费有额度，CC-BY 4.0；商业另配 |
| MET Norway Locationforecast | 全球预报，北欧尤其有优势 | 无 key，但必须真实可联系的 User-Agent；遵守 Expires/If-Modified-Since、坐标最多 4 位小数、总流量低于 20 req/s 和署名要求 |
| US National Weather Service | 美国境内预报/观测 | 无 key，但需 User-Agent；开放数据免费，存在未公开的合理限流，不能作为全球 Provider |
| Bright Sky / DWD | 德国观测突出，预报覆盖全球但境外密度较低 | 公共实例无 key、可用于各种用途，仍须遵守 DWD 条款与署名 |

**免费注册/免费套餐补充：**

| Provider | 当前接入定位 |
|---|---|
| WeatherAPI | 注册 key；官方定价页当前列免费 100,000 次/月，接入时再次核验套餐 |
| Visual Crossing | 注册账号；官方页面列每天 1,000 条免费记录，按“记录”而非简单请求计数 |
| 和风天气 QWeather | 国内使用友好，注册开发者 key；免费额度与可用接口以账号当前订阅页面为准，不写死第三方旧数字 |
| Weatherbit | 提供有限长期免费套餐，额度以当前官方 pricing 为准 |
| OpenWeather One Call 3.0 | 每天前 1,000 次免费是套餐计费规则；部分账号/产品需要信用卡或订阅验证，不能归入“只注册即可”的首选 |

套餐信息是 Provider 元数据，不是日程逻辑常量； UI 显示核验日期。允许自定义 HTTP Provider 和自托管实例。故障切换可按用户排序执行，不偷偷切换到需要付费或尚未授权的服务。

城市只在设置时地理编码并让用户确认一次，之后保存坐标。统一输出当前天气码、温度、体感、降水概率、风速、当日高低温、日出日落、来源与观测时间；原始响应留在有界缓存，不注入模型。密钥只走框架敏感字段。

### 16.3 缓存与故障

- 当前天气建议缓存 30 分钟，日预报 6 小时；Provider 的 Expires/最小更新间隔更严格时以其为准。MET 使用 If-Modified-Since，坐标按服务要求截断；规划时预取，单小项只读摘要。
- 同一地点使用 single-flight 合并请求，超时建议 3 秒，网络请求有总超时和有限重试。
- 调度不等待慢天气：有新鲜缓存用缓存；有旧缓存则带 `as_of/stale=true`；没有则省略并记录状态，同时后台为下次刷新。
- 天气 API 故障不能令 Item 失败，也不能阻塞 dispatcher。
- 只向天气服务发送坐标等必要参数，不发送会话正文、bot 人设或计划内容。

### 16.4 虚拟天气

预设：温带四季、海岛、雨林、雪原、沙漠、幻想浮空城等；均可编辑。

气候参数：月度/季节温度范围、昼夜差、降水概率、湿度、风、允许天气、连续阴晴倾向、特殊天气频率和随机种子。生成采用“季节基线 + 日际状态转移 + 小扰动”，而不是每天独立掷骰导致昨天暴雪今天酷暑。

同一 `location + climate_revision + seed + date` 可复现；修改气候时提供未来预览，默认不重写已发生天气。对模型明确标记 `source=virtual`，它是扮演世界的事实，不与真实天气混称。可选 `hybrid` 仅借用真实日出日落等字段，默认关闭。

---

## 17. 每日自我感知、夜间生活与互动边界

### 17.1 总体描述如何真正起作用而不过度限制

Plan 的 `overview/planned_appearance/planned_mood` 是**预计**；DayState 是**当前**。不采用“今天必须一直穿这件、必须保持这个心情”的强约束，而采用以下感知规则：

- 完整规划时一次生成总体思路、预计服装和状态，不增加模型调用。
- 普通允许的会话中，只注入一个有界的当前块：`persona/date/day_type/current_appearance/current_mood/current_activity/next_item`，建议 200–500 字符、`persist=False`；这样被问“今天穿什么/现在怎样”时有事实可答。
- 若当前值与预计值不同，优先当前值，并可附一条简短变化原因；没有当前值才显示“未设定”，不沿用昨天服装。
- `current_activity` 可由当前触发的 Item 确定；服装、心情和总体思路只能由 bot 明确 `day_state` 操作或用户编辑改变，系统不逐句猜测。
- 提示语义是“这是当前的自我叙事事实；若生活已变化，应先更新再回答”，不是“无论上下文如何都不得改变”。
- 详细总体描述和经历通过 `rhythm_view(today/experiences)` 按需查看，普通聊天不重复塞整张 Plan。

每次小项还知道：属于哪个人格/日型/Plan revision、最初意图、之后 diff、本组已触发与未触发项，以及为什么此刻唤醒。历史 `instruction` 只是数据，只有当前 Run 的指令是本次行动依据。

### 17.2 `auto / must_message / silent` 与梦

- `auto`：默认。可回应、可用工具，也可 `<msg/>`；安静投递时段内自动按 silent 处理。
- `must_message`：要求可见互动；创建时若处于安静投递时段则拒绝或要求改期。创建后因配置变更落入安静时段的已有项按安静优先：`<msg/>` 合法，不记 `delivery_unmet`；安静时段外空输出仍记 `delivery_unmet`。
- `silent`：允许内在生活，不向 IM 发消息；`<msg/>` 是合法的 `triggered_silent`。

梦的典型安排是：凌晨 `silent` 的“做梦”→ 私有 Experience 保存梦境 → 早晨另一项“梦后分享”按 `auto/must_message` 读取相关 Experience。普通 silent 不要求保存体验，不增加工具轮。

为防止静默被流式抢发破坏，梦等内容优先通过 `record_experience` 保存、最终保持 `<msg/>`；响应层和 XML 层再做抑制兜底。加速器提前发送属于联合兼容测试项，不能只用事后删除动作宣称绝对静默。

### 17.3 三类时间策略：禁止执行、安静投递、必须覆盖

这三类策略独立，按人格/日型配置并支持跨午夜：

1. **禁止执行时段 `blocked_execution_windows`**：任何 Item 都不得在此期间唤醒。随机窗口先扣除这些区间；精确项落在这里则校验失败。可给用户明确批准的类别白名单，但默认无例外。
2. **安静投递时段 `quiet_delivery_windows`**：允许 silent/auto 内在活动，不允许可见消息。创建时 must_message 不允许落入（已有项被配置变更移入时按 17.2 的安静优先处理），auto 在该时段静默。它不等同于禁止执行，所以夜间做梦可以保留。
3. **必需覆盖时段 `required_coverage_windows`**：例如 07:00–09:00 至少 1 项、18:00–22:00 至少 2 项；每项有 `min_items/max_items`，可选 category、互动方式或日型过滤。

每日 `min_items/max_items` 控制全日总量，必需时段控制结构，禁止/安静时段控制可执行与可打扰性。每次 create/revise/update 都校验整个结果；窗口随机序列在扣除禁用区间后再验证容量。用户手工可突破软配额，但禁止执行硬边界默认仍需显式覆盖并留审计。

### 17.4 连续性与边界

- 未触发/失效项可在下一次规划中结转，但保留来源和原因，不伪装成全新想法。
- 自由时间也是计划的一部分；不要求 bot 把上限塞满。
- 可提供“计划需用户确认”模式；默认关闭，开启后 `rhythm_plan` 只提交草稿。
- 提供“演练模式”：展示将注入的提示词、会话、时间策略与验证结果，不调用 LLM、不发送。
- 计划开始/触发/变化可发轻量自定义事件供其他插件观察；payload 只含 ID 和状态，不形成事件循环。

---

## 18. 推荐默认值（全部在 WebUI 可调）

| 类别 | 设置 | 建议默认 |
|---|---|---|
| 模式 | 精确 / 时间窗 / 概率 | 全部开启 |
| 日型 | 自定义数量 | 不设单一 custom 桶，可创建多个独立日型 |
| 数量 | 每日 bot 小项下限 / 上限 | 2 / 12；不要求塞满 |
| 范围 | 单次完整规划 | 明天/下一缺失日，1 天 |
| 范围 | bot 可规划最远范围 | 14 天；多日批量默认关闭 |
| 概率 | 未传概率 / bot 最低概率 | 1.0 / 0.20 |
| 时间窗 | 默认模式 | 窗口内随机一次 |
| 规划 | 定时 / 全项触发后规划 | 都开启；已有 Plan 也触发并默认修订 |
| 规划时间 | 本地时间 | 23:00 |
| 会话 | 权限 | 黑名单模式、空列表，即全允许 |
| 会话 | 选择策略 | `pure_random`；可选避免连续重复 |
| 修改 | 滚动窗口 / 上限 | 24 小时 / 无限 |
| 完成 | 核心完成工具 | 不提供；正常响应即已触发 |
| 静默 | `<msg/>` | `triggered_silent`，不是失败 |
| 历史 | 完整规划带前几日 | 同人格前 3 天，预算 12000 字符，超限显式分页 |
| 差异 | 小项默认带本组 revision | 最近 2 次 |
| 互动 | 默认方式 | `auto` |
| 夜间 | 禁止执行 / 安静投递 / 必需覆盖 | 默认不强制，模板可分别配置 |
| 冲突 | 用户聊天期间 | 准时发布，交给框架与 S/Z 合批，不自行等待 |
| 恢复 | 精确项宽限 / 中断重跑 | 10 分钟 / 不自动重跑；不因聊天 busy 判 missed |
| 历史 | 系统标记 / 动态指令与状态 | `notice` 短标记正常持久 / 全部 `persist=False` |
| 人格 | 切换 | 各生活线隔离并自动暂停/恢复，不共享昨日状态 |
| 头像 | 默认来源 | 自动取首选在线适配器头像，失败回退人格参考图 |
| 天气 | 默认状态 / Provider | 未配置地点前关闭 / Open-Meteo，可切换多 Provider |
| 天气 | 当前缓存 / 预报缓存 / 超时 | 30 分钟 / 6 小时 / 3 秒；服务条款更严格者优先 |
| 审批 | bot 计划需用户确认 | 关闭 |
| 页面 | 主题 / 动效 | 跟随 KiraAI / 遵循系统减少动态设置 |

上限改变不 retroactively 删除计划；概率下限只限制 bot，用户始终拥有最终控制权。

---

## 19. 性能、可靠性、安全红线

### 19.1 性能

- 空闲时无 LLM、无天气请求、无 DB 持续写入、无每秒全表扫描。
- `items(state, scheduled_at_utc)`、`runs(item_id, started_at)`、`mutations(created_at, actor)` 等索引；heap 只存最近唤醒引用。
- 单次修改只重算受影响 Plan/Item，不全量重建所有日程。
- LLM/天气/平台请求期间不持有 SQLite 锁；写事务短且可恢复。
- 页面只取可见时间范围摘要，WS 只发失效通知，大历史游标分页。
- 所有后台任务可取消；`terminate()` 取消并 gather，关闭 WS 订阅和 DB，不留下孤儿循环。

### 19.2 可靠性

- 随机落点、概率结果、revision、Run 认领、规划幂等键必须先于外部副作用落库。
- 每次发布带唯一 `run_id/event_id`；final、工具结果、watchdog 均据此幂等收尾。
- 崩溃不确定状态默认 `interrupted`，不盲目自动重试；UI 可人工重试并留下新 Run 关联。
- 配置、DB 和模板迁移均先备份；不支持的较新 schema 不得用旧代码强行写入。
- 适配器离线、权限拒绝、provider 错误、天气失败分别记录，不混成“日程完成”。

### 19.3 安全与隐私

- 所有页面/API/WS 保持 `auth=True`；写操作做权限、长度、枚举、数量和速率校验。
- 跨会话目标同时通过插件名单与适配器 `IMCapability` 权限；执行时重新检查。
- UI 默认转义计划文本，不能把模型输出当 HTML；导入模板限制大小、嵌套和数量。
- 用户图片检查真实格式、重编码、去 EXIF、防路径穿越；不提供任意文件读取。
- 天气密钥、模型内部 ID、无关聊天正文不进入自定义 API/WS/导出/日志。
- 概率和随机修改不需要向用户暴露随机种子；虚拟天气种子仅用于可复现内容。
- 自主工具不能修改自身权限、关闭审计、清除失败记录或提高修改预算。

---

## 20. 兼容性预检与同类项目借鉴

### 20.1 框架与指定插件

| 对象 | 已核验事实 | 本插件兼容设计 |
|---|---|---|
| KiraAI 3.1.2 / 3.2 beta | 两版均有 BatchEvent、final、页面/API/WS、尾部缓存装配；3.2 新增独立 Agent 等能力 | `manifest.core_version=">=3.1.2"`，不依赖 3.2 新增 `message_router/create_agent_executor/tool_call`；差异用特征检测，绝不写版本字符串分支；双版本真框架验收 |
| Sustained Chat 2.8.1 / Default Chat Z 1.11.x | queue merge 会 pending、stop、合批；Batch extra 被重写为 `_qm_self/merged_from`，原 Message 引用保留 | 到点直接发布，不另做用户优先；Run 元数据放每个 Message.extra；钩子遍历全部消息；pending 不误判 missed；sender 使用 `system_krd` 且 `is_notice=True`，让增强统计识别系统事件 |
| Alife 长期记忆 Z 2.22.24 | notice 输入不写记忆，bot 回复可保留；动态感知本身也走非持久注入 | 日程指令、DayState 和动态状态全非持久；Experience 不直接写 Z，后续可通过明确自定义事件/工具选择共享，避免双写 |
| 群日报 1.3.2 | 收集阶段主动忽略第三方合成 notice | 合成标记 `is_notice=True`；silent 不产生日报消息；普通可见回复按原插件规则处理，不修改其统计逻辑 |
| Accelerator | 流式闭合 msg 可能早于最终 XML 改写被抢发 | silent 主要依靠私有 Experience + 最终 `<msg/>`，响应/XML 抑制只作兜底；增加“抢发开启 + 做梦 + 非空模型输出”联合测试。若需绝对强制，应给加速器增加请求级 suppress 能力，不能偷偷全局关闭抢发 |

还需在联合环境覆盖默认聊天、S/Z 各自开启时的不同路径，不允许只测单插件裸跑。会话合并/压缩类插件若重建 `user_prompt`，本插件注入应使用明确名称并在低优先级阶段做存在性校验，避免被覆盖后静默失效。

### 20.2 插件市场「主动唤醒 v2.5.0」异同

该项目（Reminder Plugin）具有精准/周期/随机提醒、自主意图、可信身份、投递回执、WebUI 和冲突检测。值得借鉴：

- 真实触发幂等、明确失败与结果不明、原子持久化；
- 未确认投递摘要在最新用户输入末尾且非持久；
- 其 `_publish_immediate_notice` 将 `[事件｜系统触发]` 放入 MessageChain，未对原始消息 Prompt 做非持久处理；本插件据此采用 `notice` 默认模式；
- QQ增强 v1.4.6 的 `perceive_notice` 同样把 `[System …]` 追加到原消息链，工具说明进入 `tools` system 区；本插件沿用相同分工；
- WebUI 与 LLM 并发编辑时提示冲突；
- 不把模型返回直接等同于平台已发送或用户已读。

本插件不复制其提醒/待办定位：核心是同一人格连续多日的 Plan/Block/Item、每日 DayState、组内 diff、日型与夜间生活、私有 Experience、多人格生活线和重复规划机会。两者可同时安装，工具名与页面名均不冲突；日程插件不调用或接管其自主意图循环。

其他参考：APScheduler 的 misfire/持久化概念、EchoText 的服务端调度、Aurorix 的任务状态管理、KiraAI 内置 memory/session_tools 的事务与鉴权。均只借鉴原则，不直接持久化热重载插件对象或照搬静态 cron 模型。

---

## 21. 建议工程结构

```text
kira_rhythm_Date/
├── manifest.json
├── schema.json                 # 少量框架级/敏感配置；无配置双事实源
├── main.py                     # 生命周期、组件注册、框架钩子
├── rhythm/
│   ├── models.py               # 领域模型、枚举、校验
│   ├── store.py                # SQLite、事务、迁移、revision
│   ├── scheduler.py            # 最近唤醒、认领、并发、misfire
│   ├── planner.py              # 完整规划触发、覆盖范围、幂等
│   ├── runtime.py              # 热配置快照、生命周期
│   ├── events.py               # 合成 Notice Batch、run 关联
│   ├── tools.py                # plan/update/view 三个核心工具
│   ├── context.py              # DayState/当前组/历史/diff 的预算化注入
│   ├── policy.py               # 会话权限、配额、修改预算、人格隔离
│   ├── timeutils.py            # IANA 时区、DST、跨午夜与三类时段
│   ├── avatars.py              # 适配器头像探测、下载、缓存与回退
│   ├── weather/
│   │   ├── base.py
│   │   ├── open_meteo.py
│   │   ├── met_norway.py
│   │   ├── nws.py
│   │   ├── bright_sky.py
│   │   ├── registered.py
│   │   └── virtual.py
│   └── webapi.py               # 鉴权 API、上传、导出、WS
├── frontend/                   # Vue/TS 源码，按模块拆 JS
├── web/                        # 构建后的本地静态页面
├── assets/                     # 内置图标、模板和天气资源
├── templates/
└── tests/
```

首发明确 `manifest.core_version=">=3.1.2"` 且不设上界。CI 必须同时覆盖 `v3.1.2` 与 `v3.2.0-beta.1` 的真实 PluginManager 生命周期和消息工作流，并将 `dev` 作为前瞻测试；不能只凭源码相似就宣称测试通过。

---

## 22. 验收标准与测试矩阵

### 22.1 时间与概率

- 精确项在指定本地时刻只产生一个 Run；跨午夜窗口正确落日期。
- 窗口随机点永远位于边界内；间隔随机展开不越过最小/最大间隔、次数和每日上限。
- 使用注入假时钟/假 RNG 做属性测试，不通过真实 sleep 等测试。
- 概率省略为 1；低于下限的 bot 请求明确失败；0/1 边界正确。
- 到点抽签后在重载、恢复、watchdog 中结果完全不变。
- DST 不存在时间明确拒绝，重复时间按所选偏移执行；修改时区有准确预览。

### 22.2 规划、权限与修改

- 定时和全项触发后都会触发规划；已有 Plan 时进入 revise，同一 trigger_id 幂等，不同机会不被吞掉。
- bot 可少于上限但不可少于默认下限；一次批量替换不能绕过每日数量、必需时段或修改预算。
- 三种模式能在同一 Plan 混用；关闭模式不会暗中删除已有内容。
- 默认空黑名单全允许；白/黑名单和适配器权限在创建与执行时都生效。
- pure_random 允许连续重复；no_immediate_repeat 仅排除上一次并在下一轮放回；真正的 shuffle_bag 才每轮不重复。
- 多日计划任一日校验失败时默认无半套提交；多日成功后每日日型/提示词正确。
- 用户与 bot 并发修改 revision 冲突返回 409，不 silent overwrite。
- 普通小项无需完成工具；正常响应与 `<msg/>` 分别正确记为 triggered/triggered_silent。

### 22.3 框架真实集成

- 在真 KiraAI 中安装、加载、停用、启用、重载、更新配置，不只跑 mock。
- 合成 Notice 进入真实 Build/Assemble/Execute/Finalize，保留人设、工具、发送和归档。
- `publish()` 入队后不提前误记 triggered；正常响应按 run_id 幂等落账，final 只做审计收尾。
- 被其他插件停止、空 `<msg/>`、工具失败、平台发送失败均有正确且互不混淆的状态。
- 不使用 `message_types`、旧同步会话 API、私有已删消息函数或版本字符串分支。
- 页面/API/WS 无凭据不可访问；模型 ID 不以 UUID 形态充当显示名。

### 22.4 缓存与 token

- 对同一基础会话做两次请求，稳定 system 和 tools schema 字节一致。
- 当前时间、天气、日程、预算和 diff 只在尾部 user，且全部非持久。
- 框架历史无完整动态快照；notice 模式只保存系统短标记，full 只额外保存用户选择的模板，none 模式的纯日程空 user 边界有测试和明示。
- 当前小项上下文不含无关组；完整规划历史超预算有显式截断与分页途径。
- 普通小项无完成工具额外轮；天气不在每个小项重复访问网络。

### 22.5 故障注入

在以下每一步模拟崩溃/重载：认领前、认领后、抽签后、入队前、入队后、LLM 中、平台发送前后、final 前、final 后。

验收重点不是虚假承诺“任何情况都恰好一次”，而是：状态可解释、不重复抽签、不批量补发、不确定运行不盲目重试、用户能审计和人工恢复。

### 22.6 夜间、人格、WebUI、天气与生态

- 禁止执行时段没有 Run；安静投递时段允许 silent 梦且没有 IM 消息；必需时段的次数在每次增删改后均成立。
- 梦只写私有 Experience，梦后分享能按需读取；加速器抢发开启时也不因事后抑制才宣称安全。
- A/B 人格反复切换时各自日型、Plan、DayState、Experience、修改预算和随机状态不串线，inactive 期间不补发。
- 普通聊天可答当前日型、服装和状态；明确 day_state 后当前值覆盖预计值，跨日不沿用旧服装。
- 桌面宽屏、普通笔电、手机竖屏均无关键操作缺失；明暗主题、宿主语言、减少动态与低性能模式有效。
- 所有业务配置保存即生效；冲突、权限收紧、时区变化有预览或明确结果。
- 图片伪造扩展、超限、路径穿越、SVG 脚本和 EXIF 测试通过；QQ 头像获取失败能回退，不阻塞调度。
- WS 断线 revision 可恢复；长列表和月视图按需加载。
- 每个内置天气 Provider 做契约测试；正常、超时、限流、旧缓存和无缓存均不阻塞日程，MET 缓存头与 NWS 地区限制正确。
- 在 3.1.2 与 3.2 beta 上分别联合默认聊天、S、Z、长期记忆 Z、群日报和加速器测试；S/Z 合批后仍能遍历并落账全部 Run。
- 演练模式不产生 LLM 调用或平台消息。

---

## 23. 实施顺序（每一步都可独立验收）

### M1：先证明“生活闭环”和调度可信

领域模型、SQLite、时间/概率、dispatcher、真实框架唤醒、三个核心工具、revision/diff、DayState、人格隔离、基础今日页、权限和故障测试。此阶段不先做华丽特效，避免底层状态错误被 UI 掩盖。

### M2：完整面板与热配置

月/周/日视图、变化中心、日型与提示词编辑器、计划模板、WS、图片槽位、主题特效、响应式与可访问性。所有设置接通真实运行状态，不留死配置。

### M3：天气与生态完善

真实/虚拟天气、更多模板、导入导出、ICS、演练与诊断、性能和跨版本前瞻测试。天气接口在 M1 留好，但不让外部网络成为核心调度前置条件。

---

## 24. 第二轮已确认与仍需观察的决策

### 24.1 已按用户意见定型

1. 天气提供多家无账号与免费注册 Provider，不再只有 Open-Meteo。
2. 日型可无限新建，`custom` 不是单例；日型同时显示在 WebUI 与 bot 的动态 DayState 中。
3. 定时触发不因已有 Plan 而跳过；全项触发后也触发。已有 Plan 时都是修订机会。
4. 每日最小下限存在，默认 2；另有每日上限和可选必需时段次数。
5. 夜间拆成禁止执行、安静投递、必需覆盖三类策略，支持 silent 做梦与后续梦后分享。
6. 会话默认 `pure_random`；“排除上一次再重洗”命名为 `no_immediate_repeat`，与真正的 shuffle bag 区分。
7. 移除默认 `rhythm_complete`；正常响应即已触发，`<msg/>` 合法，must_message 单独检查投递达成。
8. 不做用户优先延迟，到点发布，由框架与 S/Z 的 flush/batch/pending 机制处理。
9. 对齐主动唤醒与 QQ增强：默认 `notice`，`[生活节律｜系统触发]` 正常持久；动态指令与状态全部 `persist=False`。
10. 生活头像默认自动获取，按稳定适配器优先级，用户上传优先。
11. 每个人格拥有独立生活线，切人格自动暂停/恢复并隔离全部状态。
12. 中文名定为 **生活节律·日程插件**，保留日程关键词便于检索。
13. 每日总体描述采用 Plan 预计值 + DayState 当前值，避免固定服装/心情限制上下文。
14. 核心版本支持 `>=3.1.2`，并联合检查 S/Z、长期记忆 Z、群日报和加速器。

### 24.2 仍需实现前特别验证，而非再改需求

- **短标记的 none 选项**：默认 `notice` 已与主动唤醒/QQ增强对齐，不会再为空 user 特设兼容锚点。只有用户主动选择 `none` 时，才需要测试并提示当前框架在纯日程批次留下空 user 的行为。
- **silent 与流式抢发**：必须靠私有 Experience/最终 `<msg/>` 的前置设计加联合测试，不能只靠最终发送前删除。若用户要求对任何模型输出都绝对静默，需要加速器提供请求级 suppress 接口。
- **恢复有效期**：10 分钟仍是推荐默认而非用户硬性要求，应支持按 Item 覆盖；它不再与普通聊天冲突挂钩。

---

## 25. 参考来源

- KiraAI 上游源码（本次实际 fetch 核验）：https://github.com/xxynet/KiraAI/tree/24a1d43399f0e17d4961a85ed928d5c24b2d4c86
- KiraAI 插件页面/工具/工作流实现：该 commit 下 `core/plugin/`、`core/chat/`、`core/workflow/src/im/`、`core/provider/llm_model.py`
- Open-Meteo Forecast API：https://open-meteo.com/en/docs
- Open-Meteo Terms（非商业范围、额度、署名）：https://open-meteo.com/en/terms
- MET Norway Terms（UA、缓存、流量、署名）：https://api.met.no/doc/TermsOfService
- US National Weather Service API：https://www.weather.gov/documentation/services-web-API
- Bright Sky API 文档：https://brightsky.dev/docs/
- WeatherAPI 套餐：https://www.weatherapi.com/pricing
- Visual Crossing Weather API：https://www.visualcrossing.com/weather-api/
- OpenWeather 套餐：https://openweathermap.org/price
- KiraAI 插件市场「主动唤醒 v2.5.0」：https://plugins.kira-ai.top/plugins/29
- APScheduler 用户指南（misfire/coalesce/persistence）：https://apscheduler.readthedocs.io/en/3.x/userguide.html
- EchoText-Proactive（服务端主动消息调度参考）：https://github.com/mattjaybe/SillyTavern-EchoText-Proactive/

---

**一句话验收**：用户看到的不是“bot 到点执行了任务”，而是“它记得自己为何这样安排，经历过什么，知道计划哪里变了，并能以自己的理由继续安排接下来的生活”。

---

## 20. 目标与约定层（v1.3.0）

### 20.1 定位

目标与约定不是计划小项，也不是普通聊天记忆。它保存“我打算做什么、答应过什么、做到哪一步”：`goal / promise / project / habit / open_loop / mystery`。计划负责某一天，Threads 负责跨天的方向。

### 20.2 数据

- `threads`：`kind/title/dossier/status/priority/next_step/due_at/last_touched/source/created_by/updated_by`
- `thread_logs`：每次打卡的 `at/note/item_id/kind/actor`
- `thread_responses`：某次规划回合对某条 Threads 的表态，`UNIQUE(run_id, thread_id)`

`dossier` 是档案正文（默认 ≤2000 字），`next_step` 是日常展示用的一句话，`due_at` 可空或 `YYYY-MM-DD[ HH:MM[:SS]]`。Thread 不绑定会话；和谁/在哪写在档案里，执行会话仍由具体 item 的 `target` 决定。

### 20.3 规划时强制回应

规划触发时先把本次 required ids 持久化到 `planning_runs.required_thread_ids_json`，之后上下文和缺回应检查都以该集合为准，不在触发后重算。规划上下文提供 `threads_requiring_response`（默认 top 8，按到期、停滞、优先级排序）和 `response_contract`。若 `planning_limit > response_limit`，额外条目放 `threads_reference`，只作参考、不要求回应。模型必须先调用 `rhythm_update` 的 `thread_response` 逐条表态：`advance / defer / waiting / no_change`，每条一句原因。回应只要求“看见并表态”，不强制推进；`no_change` 合法但必须有依据。未覆盖时 `rhythm_plan` 返回 `thread_response_required`，部分覆盖返回 `thread_response_missing`。规划回合完全未调用工具时，`on_llm_response` 标记 `thread_response_missing`，下一次上下文出现 `unanswered_threads`。关闭目标层或 `require_response` 时只给 `threads_reference` 或不注入，不伪装成必回应。

### 20.4 展示粒度

- 规划：top 5 档案全文，其余 300 字摘要 + 最近 3 条打卡；
- 执行：只显示当前小项关联的 1 条，档案摘要 300 字 + 最近 2 条打卡；
- 普通聊天：`[KRD Threads]` top 5，一行一条，不含档案；
- `rhythm_view(scope="thread")`：完整档案 + 全部打卡；
- `[KRD Agenda]` 不变。

### 20.5 记忆卫生

KiraAI 会话记忆会把 assistant 的 `tool_calls`（含完整 plans JSON）写回 `session.content`，默认最多 10 个回合。KRD 在规划前把历史规划回合的工具调用原文替换为一行摘要，计划本体仍保存在 SQLite，并由 `recent_plans`（最近 3 天完整 + 更早 4 天摘要）提供。`memory_hygiene=off` 可关闭；仅影响 LLM 会话记忆，不影响消息归档。

### 20.6 上下文预算

规划上下文超预算时按结构化字段降级：先摘要、再未完成/未来/结果、再完整计划、再档案；最后才返回带 `truncated` 的最小对象。禁止直接切断 JSON 字符串。最小对象仍保留 `threads_requiring_response`/`response_contract`，以及 `current_item`/`current_plan`/`next_item`/`delivery_policy`/`plan`/`daily_limits`/`constraints`/`calendar`/`thread`/`day_so_far` 等关键字段；其余用 `rhythm_view` 取。默认 `history_char_budget=16000`。

### 20.7 迁移

`PRAGMA user_version=2`：仅新增 `items.thread_id`、`planning_runs.required_thread_ids_json/response_status` 和 threads 三张表；旧计划、旧运行、旧配置不改写。导出格式 v2，导入兼容 v1/v2。
