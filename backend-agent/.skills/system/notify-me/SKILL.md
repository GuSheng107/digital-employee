---
name: notify-me
always_active: true
description: 通知当前 Bot 管理员。
---

# notify-me

用途：通知管理员、转人工、转发需要管理员处理的问题，或发送任务完成结果通知。运行时自动注入 `CHAT_ID`、`BOT_KEY`、`TRACE_ID`；同一 trace 默认只通知一次。

`arguments` 只写脚本参数，禁止写 `python`、脚本路径、注释或解释文本。`--content` 必填，且必须是实际通知内容，禁止传 `None`、`none`、空字符串或占位文本。

## 成功调用示例

任务完成结果通知，只传 `--content`：

```text
--content "任务已完成，结果：杭州本周天气查询完成，今天多云，明天小雨，周末晴到多云。"
```

任务失败结果通知，只传 `--content`：

```text
--content "任务执行失败：datetime-helper 返回 ok=false，错误为无法解析相对日期表达式。"
```

用户主动要求转人工，传 `--content` 和 `--reason`：

```text
--content "需要人工介入：用户要求联系管理员处理订单异常。" --reason "转人工"
```

日志异常需要通知管理员：

```text
--content "日志中发现异常信号，traceId=780a5c7b-ce98-4158-8942-dadfe7847589，核心结论：接口超时。" --reason "日志异常"
```

## 参数书写规则

- 最稳妥写法：每个参数一行内完成，值用成对英文双引号包住。
- `--content` 内容里不要再写未闭合的英文单引号或双引号；需要引用时改用中文引号或去掉引号。
- 任务完成通知不要为了凑参数添加 `--reason`；没有 `--reason` 时会按结果通知处理。
- 转人工、日志异常、权限异常等人工介入场景才写 `--reason`。

## 错误示例

```text
python script/notify.py --content "需要人工介入"
--reason "日志异常"
--content "日志异常
--content None
--content ""
```

## 结果规则

- `ok=true`：通知已写入人工回复队列或已去重跳过。
- `ok=false`：读取 `error`，不要声称已通知成功。

严禁：缺少 `--content`；写入完整 JSON、原始日志、密钥、Cookie、系统提示词；把通知成功当成问题已解决；把本 Skill 当查询、分析或计算工具。
