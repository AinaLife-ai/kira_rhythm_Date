# KRD 验证记录

验证日期：2026-11-15（Asia/Shanghai）。

## 测试结论

| 范围 | 结果 |
|---|---|
| KiraAI 3.2.0-beta.1 领域/调度/缓存/资源测试 | **24 passed** |
| KiraAI 3.1.2 同一套测试 | **24 passed** |
| 3.2 真实 PluginManager 生命周期 | 通过：3 工具、31+ 鉴权 API、WS、页面、静态目录 |
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
```

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
