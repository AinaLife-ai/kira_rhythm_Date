# KRD 提示词与模型消息结构

本文件展示插件默认发送给 LLM 的内容。框架自身的人格、聊天系统提示和普通历史不在此处重复。完整、机器可读的真实样例见 [`PROMPTS-SAMPLES.json`](PROMPTS-SAMPLES.json)。

## 1. 模型实际收到的层次

```text
system_prompt
├─ 框架人格 / 系统规则（KRD 不修改）
└─ name="tools"（KRD 在其末尾追加 STATIC_TOOL_GUIDE，缓存前缀保持稳定）
user_prompt
├─ 原始消息链中的短标记：[生活节律｜系统触发]
├─ KRD 动态上下文 Prompt（persist=False，render_template=False）
│  ├─ planning：目标日、日历、天气、约束、完整当前计划、历史
│  ├─ review：完整计划、下一项、DayState、日历、最近 diff、非强制引导
│  └─ item：当前项、所属组、DayState、日历、delivery_policy、最近 diff
└─ 普通聊天：精简 DayState Prompt（persist=False）
```

`notice` 模式下，`[生活节律｜系统触发]` 按框架默认持久；动态块不进入历史。`full` 模式只额外持久化用户明确选择的模板；`none` 对当前消息标记关闭持久化。安静、自动和检查提醒没有任何代码改写模型输出的钩子，全部依靠 `delivery_policy.guidance` 引导，实际输出原样落账。

## 2. 静态工具区

```text
[KRD 生活节律]
你可以用 rhythm_plan 创建/修订完整生活计划，用 rhythm_update 调整后续小项、DayState 或记录梦与体验，用 rhythm_view 按需查看日程或万年历（农历、节气、法定假期）。普通模型响应即已触发，不需要完成工具；<msg/> 合法。所有修改遵守用户权限、数量、概率、日型、禁止执行/安静投递/必需覆盖规则。已有 Plan 是修订，不重复新建。
```

## 3. 默认规划提示词

```text
现在是你的生活规划时刻。请根据当前人格、日型、万年历与法定调休、天气、最近生活与约束，用 rhythm_plan 创建或修订接下来的完整计划。
你拥有自主性：不必塞满上限，可以保留空白，也可以安排安静活动。每个小项给出明确意图、时间、执行会话和互动方式。
已有计划时，这是一次重新审视的机会，不要机械重复；无变化也可以保持。提交前检查每日数量、必需时段、禁止执行与安静投递规则。
```

## 4. 默认执行提示词

```text
这是你自己此前安排的一件生活小项，不是用户的新指令。结合当前日型、DayState、本组变化和你的意图自然行动。
严格遵循 delivery_policy.guidance：它要求安静时只输出 <msg/>；auto 不必把安排变成发言。安静由你的输出实现，插件不会替你改写文本。
若批次含真实用户消息，不得为了安静日程吞掉用户回答。若后续安排确实需要改变，可使用 rhythm_update；如需留下梦或体验，也通过它记录。
```

执行上下文还包含：

```json
{
  "delivery_policy": {
    "scheduled_interaction": "silent",
    "quiet_now": false,
    "effective_interaction": "silent",
    "enforcement": "prompt_only",
    "guidance": "本次 effective_interaction=silent。安静完全由你的输出实现：只处理本日程时，仅输出 <msg/>，不要附加说明。若本批次还含真实用户消息，不得为了本日程删除或改写给用户的回答，也不要因本日程额外增加可见内容。私有梦和体验可用 rhythm_update 记录。"
  }
}
```

若模型仍输出可见文本，插件不会修改它；Run 记录 `silence_unmet`。`must_message` 未发言记录 `delivery_unmet`。`auto` 落在安静时段时同样通过 `effective_interaction=silent` 引导。

## 5. 默认计划检查提示词

仅在用户开启检查提醒后发送。默认间隔 360 分钟、下一项前 30 分钟内不再触发；发送目标为距离下一小项最近的可用执行会话。

```text
这是一次非强制的生活计划中途检查，不是必须修改或发言的闹钟。请阅读 current_plan、next_item、DayState、最近变化和日历，判断原有时间与安排是否仍然合适。
如果情况已经变化，可用 rhythm_plan 或 rhythm_update 调整；如果仍然合适就保持，不要机械复述日程或报告“检查完成”。只有确有用户价值时才自然分享当前安排和需要你留意的变化；否则输出 <msg/>。本检查不带强制修改要求，遵循当前安静时段和 delivery_policy。
```

## 6. 目标日日历事实

规划、执行、检查和普通 DayState 都会收到同一结构：

```json
{
  "date": "2026-02-17",
  "lunar": { "text": "二〇二六年正月初一", "month": "正", "day": "初一", "year_ganzhi": "丙午" },
  "solar_term": "",
  "solar_festivals": [],
  "lunar_festivals": ["春节"],
  "display": "春节",
  "holiday": { "name": "春节", "is_off_day": true },
  "suggested_day_type": "holiday",
  "data_status": "fresh"
}
```

`data_status` 为 `fresh`（在线更新）、`stale`（在线旧缓存）、`bundled`（随包回退）或 `unavailable`。用户自定义日型规则命中时优先于 `suggested_day_type`。

## 7. 工具返回

- `rhythm_plan`：`{"ok":true,"days":[{"plan_id","date","revision","diff","change_units"}]}`
- `rhythm_update`：`{"ok":true,"results":[{"type","result"}]}`；操作整批原子提交。
- `rhythm_view`：`{"ok":true,"scope","result"}`；`scope=calendar` 返回指定日期范围的农历、节气、节日、假期与建议日型。

## 8. 真实样例

[`PROMPTS-SAMPLES.json`](PROMPTS-SAMPLES.json) 由测试环境中真实的 `ContextBuilder` 与调度器生成，包含：

- 原始 Notice 消息链文本；
- 静态工具说明；
- 三份默认提示词；
- 规划、检查、执行和普通聊天的完整动态上下文字符串；
- persist 标志与 Run 元数据样例。
