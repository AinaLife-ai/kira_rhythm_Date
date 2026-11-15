# KRD 验证记录

验证日期：2026-11-15（Asia/Shanghai）。

## 测试结论

| 范围 | 结果 |
|---|---|
| KiraAI 3.2.0-beta.1 领域/并发/调度/缓存/资源测试 | **73 passed** |
| KiraAI 3.1.2 同一套测试 | **73 passed** |
| 3.2 真实 PluginManager 生命周期 | 通过：3 工具、34 条鉴权 API/页面/静态路由、WS |
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
